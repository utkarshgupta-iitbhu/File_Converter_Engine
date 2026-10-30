"""Runtime discovery and routing for document conversion backends."""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
import multiprocessing
import queue as stdlib_queue


DOCUMENT_TARGETS = {"pdf", "docx", "odt", "txt"}
DOCUMENT_SOURCES = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt"}


@dataclass(frozen=True)
class Backend:
    name: str
    kind: str
    executable: str | None
    supports: frozenset[tuple[str, str]]
    warning: str = ""

    def supports_pair(self, source_extension, target_format):
        return (source_extension.lower(), target_format.lower().lstrip(".")) in self.supports


def _document_pairs(include_pdf=True):
    pairs = {
        (source, target)
        for source in DOCUMENT_SOURCES - {".pdf"}
        for target in DOCUMENT_TARGETS
        if source != "." + target
    }
    if include_pdf:
        pairs.update({(".pdf", "pdf"), (".pdf", "docx"), (".pdf", "odt"), (".pdf", "txt")})
    return frozenset(pairs)


def _office_pairs():
    return frozenset(
        (source, target)
        for source in DOCUMENT_SOURCES
        for target in DOCUMENT_TARGETS
        if source != "." + target
    )


def _candidate_executables(env):
    values = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramW6432", "LOCALAPPDATA"):
        value = env.get(key)
        if value:
            values.extend(
                [
                    Path(value) / "LibreOffice" / "program" / "soffice.exe",
                    Path(value) / "LibreOffice" / "program" / "soffice.com",
                ]
            )
    return values


def _registry_libreoffice_paths():
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    paths = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    uninstall_roots = (
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    for root in roots:
        for uninstall_root in uninstall_roots:
            try:
                with winreg.OpenKey(root, uninstall_root) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, index)
                            with winreg.OpenKey(key, subkey_name) as app_key:
                                name = str(winreg.QueryValueEx(app_key, "DisplayName")[0]).lower()
                                if "libreoffice" not in name:
                                    continue
                                for value_name in ("InstallLocation", "DisplayIcon"):
                                    try:
                                        value = str(winreg.QueryValueEx(app_key, value_name)[0]).split(",", 1)[0].strip('"')
                                    except OSError:
                                        continue
                                    path = Path(value)
                                    paths.append(path if path.is_dir() else path.parent)
                        except OSError:
                            continue
            except OSError:
                continue
    return paths


def find_libreoffice(which=shutil.which, env=None, registry_paths=None):
    env = os.environ if env is None else env
    for command in ("soffice", "soffice.com"):
        found = which(command)
        if found:
            return str(Path(found))
    candidates = list(_candidate_executables(env))
    registry_candidates = _registry_libreoffice_paths() if registry_paths is None else registry_paths
    candidates.extend(Path(path) / "program" / "soffice.exe" for path in registry_candidates)
    candidates.extend(Path(path) / "soffice.exe" for path in registry_candidates)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _registry_word_installed():
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    for root in roots:
        for base in (r"Software\Microsoft\Office", r"Software\WOW6432Node\Microsoft\Office"):
            try:
                with winreg.OpenKey(root, base) as office_key:
                    for index in range(winreg.QueryInfoKey(office_key)[0]):
                        try:
                            version = winreg.EnumKey(office_key, index)
                            with winreg.OpenKey(office_key, version + r"\Word\InstallRoot") as word_key:
                                path, _ = winreg.QueryValueEx(word_key, "Path")
                                if path and Path(path).exists():
                                    return True
                        except OSError:
                            continue
            except OSError:
                continue
    return False


def _word_probe_worker(result_queue):
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Quit()
        result_queue.put(True)
    except Exception:
        result_queue.put(False)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _com_word_probe(timeout=10):
    if sys.platform != "win32":
        return False
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    worker = context.Process(target=_word_probe_worker, args=(result_queue,), name="FCE-Word-Probe")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        worker.terminate()
        worker.join(5)
        return False
    try:
        return bool(result_queue.get_nowait())
    except stdlib_queue.Empty:
        return False


def find_word(word_probe=None, registry_probe=None):
    registry_probe = _registry_word_installed if registry_probe is None else registry_probe
    word_probe = _com_word_probe if word_probe is None else word_probe
    return bool(registry_probe() or word_probe())


def discover_document_backends(which=shutil.which, env=None, registry_paths=None, word_probe=None, registry_probe=None):
    """Return installed document backends in enforced priority order."""
    backends = []
    libreoffice = find_libreoffice(which=which, env=env, registry_paths=registry_paths)
    if libreoffice:
        backends.append(Backend("LibreOffice", "libreoffice", libreoffice, _document_pairs()))
    if find_word(word_probe=word_probe, registry_probe=registry_probe):
        backends.append(
            Backend(
                "Microsoft Word",
                "word",
                None,
                _office_pairs(),
                "PDF reconstruction through Word may not preserve the original layout exactly.",
            )
        )
    return tuple(backends)


def choose_document_backend(source_path, target_format, backends=None):
    """Choose the first installed backend that explicitly supports the pair."""
    source_extension = Path(source_path).suffix.lower()
    target = target_format.lower().lstrip(".")
    if source_extension not in DOCUMENT_SOURCES or target not in DOCUMENT_TARGETS:
        return None, f"Unsupported document conversion pair: {source_extension or '(no extension)'} to {target}."
    backends = discover_document_backends() if backends is None else backends
    for backend in backends:
        if backend.supports_pair(source_extension, target):
            warning = backend.warning
            if source_extension == ".pdf" and target == "docx":
                warning = "PDF-to-DOCX conversion is an editable reconstruction; visual and structural fidelity is not guaranteed."
            return backend, warning
    installed = ", ".join(backend.name for backend in backends) or "none"
    return None, f"No installed document backend supports {source_extension} to {target}. Detected backends: {installed}. Install LibreOffice or Microsoft Word with pywin32, then retry."


def supported_document_targets(source_path, backends=None):
    source_extension = Path(source_path).suffix.lower()
    backends = discover_document_backends() if backends is None else backends
    return [
        target.upper()
        for target in sorted(DOCUMENT_TARGETS)
        if any(backend.supports_pair(source_extension, target) for backend in backends)
    ]
