"""Python conversion engines. All outputs are written to explicit paths."""
import multiprocessing
import os
from pathlib import Path
import queue as stdlib_queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile

import pandas as pd
from PIL import Image, ImageOps

from .backends import choose_document_backend, discover_document_backends
from .paths import resource_path

WINDOWS_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def get_output_path(input_path, target_format, output_dir=None, prefix="", suffix="", template=None):
    out_dir = Path(output_dir) if output_dir else Path(input_path).parent
    base_name = Path(input_path).stem
    if template and "{name}" in template:
        out_name = template.replace("{name}", base_name)
    else:
        out_name = f"{prefix}{base_name}{suffix}"
    # Avoid path traversal or accidental nested output paths from a rename template.
    out_name = Path(out_name).name.strip()
    if not out_name:
        out_name = f"{base_name}_converted"
    return str(out_dir / f"{out_name}.{target_format.lower().lstrip('.')}")


def unique_path(path):
    """Return an unused filename without overwriting an existing file."""
    path = Path(path)
    if not path.exists():
        return str(path)
    for number in range(1, 100000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return str(candidate)
    raise RuntimeError(f"Could not find an unused output filename for {path.name}")


def package_to_zip(file_paths, zip_out_path):
    """Create a ZIP and verify that all requested files are present before success."""
    try:
        paths = [Path(p) for p in file_paths if Path(p).is_file()]
        if not paths:
            return False, "No valid output files were available to package."
        out = Path(zip_out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_name(out.stem + ".tmp.zip")
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            used_names = set()
            for path in paths:
                arcname = path.name
                if arcname in used_names:
                    arcname = f"{path.parent.name}_{arcname}"
                used_names.add(arcname)
                archive.write(path, arcname)
        with zipfile.ZipFile(temp, "r") as archive:
            bad = archive.testzip()
            expected = len(paths)
            if bad is not None or len(archive.namelist()) != expected:
                temp.unlink(missing_ok=True)
                return False, "ZIP verification failed; source outputs were preserved."
        os.replace(temp, out)
        return True, str(out)
    except Exception as exc:
        try:
            if "temp" in locals() and temp.exists():
                temp.unlink()
        except OSError:
            pass
        return False, str(exc)


def _ensure_parent(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _document_timeout(source_path, target_format):
    default = 45 if Path(source_path).suffix.lower() == ".pdf" and target_format.lower().lstrip(".") == "docx" else 180
    setting = "FCE_PDF_DOCX_TIMEOUT_SECONDS" if default == 45 else "FCE_DOCUMENT_TIMEOUT_SECONDS"
    try:
        return max(10, int(os.environ.get(setting, default)))
    except (TypeError, ValueError):
        return default


def _validate_document_output(path, target):
    output = Path(path)
    if not output.is_file() or output.stat().st_size == 0:
        return False
    target = target.lower().lstrip(".")
    if target in {"docx", "odt"}:
        try:
            with zipfile.ZipFile(output) as archive:
                return archive.testzip() is None and "[Content_Types].xml" in archive.namelist() if target == "docx" else archive.testzip() is None
        except (OSError, zipfile.BadZipFile):
            return False
    if target == "pdf":
        try:
            return output.open("rb").read(5) == b"%PDF-"
        except OSError:
            return False
    return True


def _cleanup_process(process):
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.communicate(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if os.name == "nt" and getattr(process, "pid", None):
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=10,
                    creationflags=WINDOWS_NO_WINDOW,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass


def _convert_with_libreoffice(backend, file_path, target, final_out, timeout):
    with tempfile.TemporaryDirectory(prefix="fce_doc_") as temp_dir:
        profile = Path(temp_dir) / "profile"
        profile.mkdir()
        source_ext = Path(file_path).suffix.lower()
        target_clean = target.lower().lstrip(".")
        command = [
            backend.executable,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={profile.as_uri()}",
        ]
        # Direct PDFs into Writer (writer_pdf_import) so Draw's missing DOCX filter is avoided
        if source_ext == ".pdf" and target_clean in {"docx", "odt", "txt", "rtf"}:
            command.append("--infilter=writer_pdf_import")
        command.extend([
            "--convert-to",
            target,
            "--outdir",
            temp_dir,
            os.path.abspath(file_path),
        ])
        process = None
        try:
            flags = (subprocess.CREATE_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flags,
            )
            stdout, stderr = process.communicate(timeout=timeout)
            if process.returncode != 0:
                return False, (stderr or stdout or "LibreOffice exited unsuccessfully.").strip()
            generated = Path(temp_dir) / f"{Path(file_path).stem}.{target}"
            if not _validate_document_output(generated, target):
                return False, "LibreOffice completed without producing a valid output file."
            os.replace(generated, final_out)
            return True, ""
        except FileNotFoundError:
            return False, "LibreOffice executable was not available at conversion time."
        except subprocess.TimeoutExpired:
            if process is not None:
                _cleanup_process(process)
            return False, f"LibreOffice timed out after {timeout} seconds; process cleanup completed."
        except (OSError, subprocess.SubprocessError) as exc:
            if process is not None and process.poll() is None:
                _cleanup_process(process)
            return False, f"LibreOffice execution failed: {exc}"


def _word_timeout():
    try:
        return max(15, int(os.environ.get("FCE_WORD_TIMEOUT_SECONDS", "120")))
    except (TypeError, ValueError):
        return 120


def _word_worker(file_path, target, final_out, result_queue):
    word = doc = None
    pythoncom = None
    temporary_word = None
    try:
        try:
            import pythoncom as _pythoncom
            import win32com.client
        except ImportError:
            result_queue.put(("result", False, "Microsoft Word automation requires the pywin32 package in the application runtime."))
            return
        pythoncom = _pythoncom
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            word.Options.ConfirmConversions = False
            if hasattr(word.Options, "DoNotPromptForConvert"):
                word.Options.DoNotPromptForConvert = True
        except Exception:
            pass
        try:
            import win32process
            _, word_pid = win32process.GetWindowThreadProcessId(word.Hwnd)
            result_queue.put(("word_pid", word_pid))
        except Exception:
            pass
        doc = word.Documents.Open(
            os.path.abspath(file_path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            NoEncodingDialog=True,
        )
        format_map = {"pdf": 17, "docx": 16, "odt": 23, "txt": 2}
        temporary_word = tempfile.NamedTemporaryFile(prefix="fce_word_", suffix=f".{target}", delete=False, dir=Path(final_out).parent).name
        save_method = getattr(doc, "SaveAs2", None) or doc.SaveAs
        save_method(os.path.abspath(temporary_word), FileFormat=format_map[target])
        doc.Close(False)
        doc = None
        word.Quit()
        word = None
        if not _validate_document_output(temporary_word, target):
            result_queue.put(("result", False, "Microsoft Word completed without producing a valid output file."))
            return
        os.replace(temporary_word, final_out)
        temporary_word = None
        result_queue.put(("result", True, ""))
    except Exception as exc:
        if isinstance(exc, ImportError):
            result_queue.put(("result", False, "Microsoft Word automation requires the pywin32 package in the application runtime."))
        else:
            result_queue.put(("result", False, f"Microsoft Word conversion failed: {exc}"))
    finally:
        try:
            if temporary_word:
                Path(temporary_word).unlink(missing_ok=True)
        except OSError:
            pass
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        try:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
        except Exception:
            pass


def _kill_owned_word(word_pid):
    if os.name != "nt" or not word_pid:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(word_pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=10,
            creationflags=WINDOWS_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _convert_with_word(file_path, target, final_out):
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    worker = context.Process(target=_word_worker, args=(file_path, target, final_out, result_queue), name="FCE-Word-Worker")
    worker.start()
    word_pid = None
    result = None
    deadline = _word_timeout()
    worker.join(deadline)
    while True:
        try:
            message = result_queue.get_nowait()
        except stdlib_queue.Empty:
            break
        if message[0] == "word_pid":
            word_pid = message[1]
        elif message[0] == "result":
            result = message[1:]
    if worker.is_alive():
        worker.terminate()
        worker.join(10)
        _kill_owned_word(word_pid)
        return False, f"Microsoft Word timed out after {deadline} seconds; owned Word process cleanup completed."
    worker.close()
    if result:
        return result
    return False, "Microsoft Word worker exited without returning a conversion result."


def convert_document(file_path, target_format, output_dir=None, out_path=None, notice_callback=None):
    out_dir = output_dir or str(Path(file_path).parent)
    target = target_format.lower().lstrip(".")
    final_out = out_path or get_output_path(file_path, target, out_dir)
    _ensure_parent(final_out)
    backends = discover_document_backends()
    selected, selection_message = choose_document_backend(file_path, target, backends)
    if selected is None:
        return False, selection_message
    candidates = [backend for backend in backends if backend.supports_pair(Path(file_path).suffix, target)]
    failures = []
    if notice_callback:
        notice_callback("Detected backends: " + (", ".join(backend.name for backend in backends) or "none") + ".")
    for index, backend in enumerate(candidates):
        if notice_callback:
            notice_callback(f"Attempting {Path(file_path).suffix.lower()} to {target} using {backend.name}.")
            if backend.warning:
                notice_callback(backend.warning)
            if selection_message and backend is selected and selection_message != backend.warning:
                notice_callback(selection_message)
        if backend.kind == "libreoffice":
            success, error = _convert_with_libreoffice(backend, file_path, target, final_out, _document_timeout(file_path, target))
        elif backend.kind == "word":
            success, error = _convert_with_word(file_path, target, final_out)
        else:
            success, error = False, f"Unknown document backend: {backend.name}"
        if success:
            if notice_callback:
                notice_callback(f"{backend.name} conversion completed; output validation passed.")
            return True, str(final_out)
        failures.append(f"{backend.name}: {error}")
        if index + 1 < len(candidates) and notice_callback:
            notice_callback(f"{backend.name} failed: {error}")
            notice_callback(f"Switching to {candidates[index + 1].name} fallback.")
    return False, "Document conversion failed. " + " | ".join(failures)


def convert_image(file_path, target_format, strip_exif=True, quality=90, output_dir=None, out_path=None, privacy=None):
    final_out = out_path or get_output_path(file_path, target_format, output_dir)
    privacy = privacy or {
        "remove_exif": strip_exif,
        "remove_location": strip_exif,
        "remove_comments": strip_exif,
        "remove_color_profile": False,
    }
    try:
        _ensure_parent(final_out)
        with Image.open(file_path) as source:
            preserved_exif = None
            if not privacy.get("remove_exif") or not privacy.get("remove_location") or not privacy.get("remove_comments"):
                exif = source.getexif()
                if exif:
                    if privacy.get("remove_location"):
                        exif.pop(34853, None)
                    if privacy.get("remove_comments"):
                        for tag in (270, 37510, 40092, 40093, 40094, 40095):
                            exif.pop(tag, None)
                    preserved_exif = exif.tobytes()
            image = ImageOps.exif_transpose(source) if privacy.get("remove_exif") else source.copy()
            image.load()
            image = image.copy()
            fmt = target_format.upper()
            save_options = {}
            if preserved_exif and fmt in {"JPEG", "JPG", "WEBP"}:
                save_options["exif"] = preserved_exif
            if not privacy.get("remove_color_profile") and source.info.get("icc_profile"):
                save_options["icc_profile"] = source.info["icc_profile"]
            if not privacy.get("remove_comments") and source.info.get("comment"):
                save_options["comment"] = source.info["comment"]
            if fmt in {"JPEG", "JPG"} and image.mode not in {"RGB", "L"}:
                if image.mode in {"RGBA", "LA"}:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGB", rgba.size, "white")
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
            with tempfile.NamedTemporaryFile(prefix="fce_image_", suffix=Path(final_out).suffix, delete=False, dir=Path(final_out).parent) as temporary:
                temporary_path = temporary.name
            try:
                if fmt == "ICO":
                    image.save(temporary_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
                elif fmt in {"JPEG", "JPG", "WEBP"}:
                    image.save(temporary_path, format="JPEG" if fmt == "JPG" else fmt, quality=max(10, min(100, int(quality))), optimize=True, **save_options)
                else:
                    image.save(temporary_path, format=fmt, **save_options)
                with Image.open(temporary_path) as check:
                    check.verify()
                os.replace(temporary_path, final_out)
            finally:
                Path(temporary_path).unlink(missing_ok=True)
            with Image.open(final_out) as check:
                check.verify()
        return True, str(final_out)
    except Exception as exc:
        return False, f"Image conversion failed: {exc}"


def _get_ffmpeg_executable():
    """Find FFmpeg bundled with the app, in the source tree, or on PATH."""
    if os.name == "nt":
        bundled_ffmpeg = resource_path("ffmpeg.exe")
        if bundled_ffmpeg.is_file():
            return str(bundled_ffmpeg)
        source_ffmpeg = resource_path("vendor", "ffmpeg", "ffmpeg.exe")
        if source_ffmpeg.is_file():
            return str(source_ffmpeg)
    return shutil.which("ffmpeg") or "ffmpeg"


def _get_media_duration(ffmpeg, file_path):
    """Estimate media duration in seconds for progress calculation."""
    try:
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-i", str(file_path)]
        probe = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            creationflags=WINDOWS_NO_WINDOW,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", probe.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return None


_DETECTED_HW_ENCODER = None
_HW_ENCODER_PROBED = False


def _detect_hardware_encoder(ffmpeg):
    global _DETECTED_HW_ENCODER, _HW_ENCODER_PROBED
    if _HW_ENCODER_PROBED:
        return _DETECTED_HW_ENCODER
    _HW_ENCODER_PROBED = True
    for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
        try:
            res = subprocess.run(
                [ffmpeg, "-nostdin", "-y", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.04", "-c:v", enc, "-f", "null", "-"],
                capture_output=True,
                timeout=2,
                creationflags=WINDOWS_NO_WINDOW,
            )
            if res.returncode == 0:
                _DETECTED_HW_ENCODER = enc
                return enc
        except Exception:
            pass
    return None


def convert_media(file_path, target_format, output_dir=None, out_path=None, quality=None, hardware_accel=False, progress_callback=None, cancel_event=None):
    if cancel_event and cancel_event.is_set():
        return False, "Conversion cancelled before starting."

    final_out = out_path or get_output_path(file_path, target_format, output_dir)
    _ensure_parent(final_out)
    final_path = Path(final_out)
    target_clean = target_format.upper().lstrip(".")

    temporary = str(final_path.with_name(f"{final_path.stem}.fce_tmp{final_path.suffix}"))
    ffmpeg = _get_ffmpeg_executable()

    def _report(frac, pct_str="100%", eta_str="00:00", speed_str="1.0x"):
        if not progress_callback:
            return
        try:
            progress_callback(frac, pct_str, eta_str, speed_str)
        except TypeError:
            try:
                progress_callback(frac, pct_str)
            except TypeError:
                try:
                    progress_callback(frac)
                except Exception:
                    pass
        except Exception:
            pass

    audio_targets = {"MP3", "WAV", "FLAC", "M4A", "OGG", "AAC"}
    is_audio_target = target_clean in audio_targets
    can_try_copy = not is_audio_target and quality is None

    if can_try_copy:
        cmd = [
            ffmpeg, "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
            "-i", file_path, "-map", "0", "-c", "copy", temporary
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, text=True,
                check=True, timeout=600,
                creationflags=WINDOWS_NO_WINDOW,
            )
            if Path(temporary).is_file() and Path(temporary).stat().st_size > 0:
                os.replace(temporary, final_out)
                _report(1.0, "100%", "00:00", "copy")
                return True, str(final_out)
        except (subprocess.CalledProcessError, Exception):
            pass

    try:
        Path(temporary).unlink(missing_ok=True)
        duration = _get_media_duration(ffmpeg, file_path)

        def _build_transcode_command(use_gpu=False):
            base_cmd = [
                ffmpeg, "-nostdin", "-y", "-hide_banner",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error",
                "-i", file_path
            ]
            if is_audio_target:
                q = int(quality) if quality is not None else 75
                bitrate_kbps = int(64 + ((max(10, min(100, q)) - 10) / 90.0) * 256)
                if target_clean == "MP3":
                    codec_args = ["-vn", "-c:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k"]
                elif target_clean in {"M4A", "AAC"}:
                    codec_args = ["-vn", "-c:a", "aac", "-b:a", f"{bitrate_kbps}k"]
                elif target_clean == "OGG":
                    codec_args = ["-vn", "-c:a", "libvorbis", "-b:a", f"{bitrate_kbps}k"]
                elif target_clean == "WAV":
                    codec_args = ["-vn", "-c:a", "pcm_s16le"]
                elif target_clean == "FLAC":
                    codec_args = ["-vn", "-c:a", "flac"]
                else:
                    codec_args = ["-vn"]
                return base_cmd + codec_args + [temporary]
            elif target_clean == "GIF":
                gif_filter = "fps=12,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
                return base_cmd + ["-vf", gif_filter, temporary]
            else:
                q = int(quality) if quality is not None else 90
                crf = int(38 - ((max(10, min(100, q)) - 10) / 90.0) * 20)
                if use_gpu:
                    gpu_enc = _detect_hardware_encoder(ffmpeg)
                    if gpu_enc:
                        if "nvenc" in gpu_enc:
                            v_args = ["-c:v", gpu_enc, "-preset", "p4", "-cq", str(crf)]
                        elif "qsv" in gpu_enc:
                            v_args = ["-c:v", gpu_enc, "-global_quality", str(crf)]
                        else:
                            v_args = ["-c:v", gpu_enc, "-quality", "speed"]
                        return base_cmd + v_args + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", temporary]
                v_args = ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium"]
                return base_cmd + v_args + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", temporary]

        try_gpu = bool(hardware_accel and not is_audio_target and target_clean != "GIF" and _detect_hardware_encoder(ffmpeg))
        retry_cmd = _build_transcode_command(use_gpu=try_gpu)

        def _run_ffmpeg(cmd):
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=WINDOWS_NO_WINDOW,
            )
            stderr_lines = []
            def _drain():
                for line in process.stderr:
                    stderr_lines.append(line)
            err_thread = threading.Thread(target=_drain, daemon=True)
            err_thread.start()

            start_time = time.time()
            timeout = 1800
            last_speed = 1.0

            for line in process.stdout:
                if cancel_event and cancel_event.is_set():
                    process.kill()
                    Path(temporary).unlink(missing_ok=True)
                    return False, "Conversion stopped by user."
                if time.time() - start_time > timeout:
                    process.kill()
                    raise subprocess.TimeoutExpired(cmd, timeout)

                line = line.strip()
                if line.startswith("speed="):
                    raw_sp = line.split("=")[1].strip().rstrip("x")
                    try:
                        parsed_sp = float(raw_sp)
                        if parsed_sp > 0:
                            last_speed = parsed_sp
                    except ValueError:
                        pass
                elif line.startswith("out_time_us=") and duration and duration > 0:
                    try:
                        us = int(line.split("=")[1])
                        current_sec = us / 1_000_000.0
                        frac = min(0.99, max(0.0, current_sec / duration))
                        pct = f"{int(frac * 100)}%"
                        elapsed = max(0.1, time.time() - start_time)
                        calc_speed = last_speed if last_speed > 0 else max(0.1, current_sec / elapsed)
                        rem_sec = max(0, (duration - current_sec) / calc_speed)
                        eta = f"{int(rem_sec // 60):02d}:{int(rem_sec % 60):02d}"
                        sp_str = f"{calc_speed:.1f}x"
                        _report(frac, pct, eta, sp_str)
                    except (ValueError, IndexError):
                        pass

            process.wait()
            err_thread.join(timeout=5)
            if process.returncode != 0:
                return False, "".join(stderr_lines).strip() or f"Process exited with code {process.returncode}"
            return True, ""

        success, err_msg = _run_ffmpeg(retry_cmd)

        if not success and try_gpu and not (cancel_event and cancel_event.is_set()):
            Path(temporary).unlink(missing_ok=True)
            cpu_cmd = _build_transcode_command(use_gpu=False)
            success, err_msg = _run_ffmpeg(cpu_cmd)

        if not success:
            return False, f"FFmpeg could not convert this file: {err_msg}"

        if Path(temporary).is_file() and Path(temporary).stat().st_size > 0:
            os.replace(temporary, final_out)
            _report(1.0, "100%", "00:00", "done")
            return True, str(final_out)

        return False, "FFmpeg did not create a non-empty output file."

    except FileNotFoundError:
        return False, "FFmpeg executable was not found. Please verify the bundled ffmpeg.exe."
    except subprocess.TimeoutExpired:
        return False, "FFmpeg conversion timed out after 30 minutes."
    except Exception as exc:
        return False, f"FFmpeg conversion failed: {exc}"
    finally:
        Path(temporary).unlink(missing_ok=True)


def convert_data(file_path, target_format, output_dir=None, out_path=None):
    ext = Path(file_path).suffix.lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext == ".json":
            df = pd.read_json(file_path)
        elif ext in {".xls", ".xlsx"}:
            df = pd.read_excel(file_path)
        elif ext == ".parquet":
            df = pd.read_parquet(file_path)
        else:
            return False, f"Unsupported data input format: {ext or '(no extension)'}"
        target = target_format.upper()
        if target not in {"CSV", "JSON", "XLSX", "PARQUET"}:
            return False, f"Unsupported data output format: {target}"
        final_out = out_path or get_output_path(file_path, target, output_dir)
        _ensure_parent(final_out)
        temporary_data = tempfile.NamedTemporaryFile(prefix="fce_data_", suffix=f".{target.lower()}", delete=False, dir=Path(final_out).parent).name
        if target == "CSV":
            df.to_csv(temporary_data, index=False)
        elif target == "JSON":
            df.to_json(temporary_data, orient="records", indent=4)
        elif target == "XLSX":
            df.to_excel(temporary_data, index=False, engine="openpyxl")
        elif target == "PARQUET":
            df.to_parquet(temporary_data, index=False)
        os.replace(temporary_data, final_out)
        if Path(final_out).is_file() and Path(final_out).stat().st_size > 0:
            return True, str(final_out)
        return False, "Data engine did not create a non-empty output file."
    except Exception as exc:
        try:
            if "temporary_data" in locals():
                Path(temporary_data).unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"Data conversion failed: {exc}"