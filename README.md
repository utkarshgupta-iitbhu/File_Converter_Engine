# File Converter Engine

A Windows-first desktop file converter built with Python, CustomTkinter and a small optional C++ extension. The application uses local conversion engines; format support depends on installed libraries and external tools.

## Requirements

- Python 3.10+ (the included prebuilt extension, if retained, must match your exact Python version and Windows architecture)
- Python packages from `requirements.txt`
- FFmpeg available on `PATH` for audio/video conversion
- LibreOffice for document conversion when installed; Microsoft Word plus `pywin32` is a Windows fallback
- CMake and a compatible C++ compiler only if rebuilding the optional C++ extension

Install Python dependencies from the project folder:

```powershell
python -m pip install -r requirements.txt
```

## Build a single Windows executable

On the Windows build machine, install the build dependencies and run:

```powershell
python -m pip install -r build-requirements.txt
build_exe.bat
```

The reproducible build uses [FileConverterEngine.spec](FileConverterEngine.spec) and creates
`dist\FileConverterEngine.exe` with PyInstaller `--onefile --windowed` behavior. The spec includes
CustomTkinter, tkinterdnd2 resources, PythonCOM support, multiprocessing hooks, and the optional
CPython-version-specific `cpp_engine.cp312-win_amd64.pyd` when that file is present. The C++ extension
must match the Python ABI used to build the executable; rebuild it with `build_cpp.bat` when necessary.

The executable bundles Python and Python packages, so recipients do not need Python, pip, a compiler,
or the source repository. LibreOffice, Microsoft Office/Word, and FFmpeg are external applications and
are not bundled. The application detects them at runtime and reports actionable errors when unavailable.
Builds should be performed from a clean environment containing only this project's runtime and build
requirements; a broad development environment can make PyInstaller scan unrelated packages.

## Run

```powershell
python main.py
```

Run the focused regression tests with:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

You can also pass one or more file paths when launching the app, for example:

```powershell
python main.py "C:\Users\You\Pictures\image.png"
```

## C++ extension (optional)

The C++ extension is not used by the normal conversion workflow. Its byte-inversion function is an experimental reversible byte transformation, **not encryption and not file-format conversion**. It streams data in chunks to avoid loading an entire file into RAM.

To build the extension from source on Windows, install CMake, a compatible C++ compiler, and `pybind11`, then run `build_cpp.bat` from the project folder. Alternatively, run from the project folder:

```powershell
cmake -S cpp_engine -B cpp_engine/build -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
cmake --build cpp_engine/build --config Release
```

The exact command may vary by compiler and CMake generator. Do not copy a compiled `.pyd` from a different Python version or architecture.

## Supported conversion families

The UI offers target formats by the input file's extension/category. Actual success still depends on the input content and the capabilities of installed engines. Media conversion uses FFmpeg; tables use Pandas and the relevant Excel/Parquet dependencies.

### Document backends

Document backends are discovered at runtime for every conversion. LibreOffice is searched in this order:

1. `soffice`/`soffice.com` on `PATH`.
2. Standard `Program Files`, `Program Files (x86)`, `ProgramW6432`, and per-user LibreOffice locations.
3. LibreOffice installation information in the Windows uninstall registry keys.

Microsoft Word is detected through Windows Office installation registry information and a COM availability probe when needed. The application never assumes that Windows Search visibility makes a command-line executable available.

LibreOffice always has priority when it supports the requested pair. Word is used only when LibreOffice is unavailable, does not support that pair, or fails and Word supports the same pair. No software is downloaded or installed automatically.

Conversion attempts are logged in the Activity tab, including backend selection, timeout, cleanup, fallback, and output validation. LibreOffice uses a 45-second default timeout for PDF-to-DOCX because PDF import can hang, and 180 seconds for other document conversions. Override these with `FCE_PDF_DOCX_TIMEOUT_SECONDS` and `FCE_DOCUMENT_TIMEOUT_SECONDS`. Microsoft Word automation runs in an isolated worker process with a 120-second default timeout, configurable with `FCE_WORD_TIMEOUT_SECONDS`; only the Word process created for that conversion is targeted during timeout cleanup.

The supported document pairs are:

- LibreOffice: DOC/DOCX/ODT/RTF/TXT to PDF, DOCX, ODT, or TXT; PDF to PDF, DOCX, ODT, or TXT where the installed LibreOffice build can import the PDF.
- Microsoft Word fallback: DOC/DOCX/ODT/RTF/TXT/PDF to PDF, DOCX, ODT, or TXT where Word and `pywin32` support the pair.

PDF-to-DOCX is an editable reconstruction, not a promise of faithful visual or structural recovery. The selected backend and this limitation are reported in Activity output or the command-line output.

If no compatible backend is detected, the document target is not offered in the GUI and direct conversion reports the missing software and next step. Packaged EXEs must ship their Python dependencies or use a bundled runtime, but LibreOffice and Microsoft Office remain recipient-machine prerequisites and are detected at runtime.

## Notes

- Output files are checked for existence and non-zero size. This is a practical sanity check, not a full semantic guarantee for every file format.
- Batch jobs currently require one compatible conversion family at a time.
- Metadata privacy controls are persisted per Windows user under `%APPDATA%\FileConverterEngine\settings.json`.
	EXIF, GPS/location, comments/descriptive fields, and colour profiles have separate controls. These operations
	apply only where Pillow and the target format support them; no metadata tool can guarantee removal of every
	possible chunk, and metadata removal cannot remove information visible in image pixels.
- Dropping a ZIP validates every entry before extraction, rejects absolute and traversal paths, limits entry count
	and uncompressed size, skips unsupported files, and extracts into a temporary workspace. The original archive is
	never modified and extracted files are never executed.
- Windows context-menu registration is per-user and can be added, removed, or repaired from Settings. It provides
	an Open in File Converter command plus target formats derived from the router for each source extension. Explorer
	conversions write beside each source file and choose a unique name instead of silently overwriting an output.
	Windows 11 may place these commands under Show more options depending on Explorer policy.
- Hardware acceleration is persisted in `%APPDATA%\FileConverterEngine\settings.json` and is also honored by
	media conversions launched from the Explorer context menu. Windowless Explorer failures are surfaced through
	a native Windows error dialog as well as diagnostic output.
- The C++ extension remains optional and is not part of normal conversion.

### Troubleshooting document conversion

- If no document targets appear, install LibreOffice or Microsoft Office with Word and `pywin32`, then restart the app.
- If LibreOffice is installed outside standard locations, add its `program` directory to `PATH` or ensure its uninstall entry is present.
- If Word is installed but unavailable, repair Office or install the matching `pywin32` package for the application runtime.
- Conversion failures preserve the existing destination and include the backend error in Activity output.
- Packaged Windows builds must include the Python multiprocessing/freeze-support configuration and `pywin32` if Word fallback is required. LibreOffice and Office are still recipient-machine prerequisites.
- The one-file executable was built and launched from a different working directory on the development machine. A clean Windows machine without Python or development tools was not available for verification.
