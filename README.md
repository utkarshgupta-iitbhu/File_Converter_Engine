<div align="center">

# ⚡ File Converter Engine

**A fast, local-first, privacy-focused desktop file conversion workspace for Windows.**

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](#)
[![UI](https://img.shields.io/badge/GUI-CustomTkinter-blue)](#)
[![Build](https://img.shields.io/badge/Packaging-PyInstaller%20One--File-orange)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

*Convert images, videos, audio, office documents, and tabular data completely offline on your own machine. Features native Windows Explorer right-click cascading menus, GPU hardware acceleration, intelligent document backends, and fine-grained metadata privacy controls.*

</div>

---

## 🌟 Highlights & Features

- **🖱️ Native Windows 11 & 10 Explorer Cascading Menu**
  - Right-click any supported file in File Explorer and hover over **Convert to >** for immediate, headless conversions in the same directory.
  - Multi-file selection support (up to 100 items at once) with collision-free naming (e.g. `file_1.png`).
  - Per-user registry integration — requires zero administrator privileges and leaves system files untouched.

- **🔒 100% Offline & Privacy-Focused**
  - Your files never leave your machine — no cloud servers, no bandwidth limits, no telemetry.
  - One-click metadata scrubbing: strip EXIF data, GPS location coordinates, author comments, and color profiles before sharing.

- **🚀 GPU Hardware Acceleration & Live Progress**
  - Media transcoding powered by bundled FFmpeg with optional NVENC (NVIDIA), QSV (Intel), and AMF (AMD) GPU acceleration.
  - Real-time progress percentage, conversion speed (e.g. `1.85x`), live ETA, and smooth background execution.
  - Interactive video quality controls: Video CRF slider, custom audio bitrates, and video-to-audio extraction (`MP4 -> MP3/WAV/FLAC`).

- **📄 Dual-Engine Document Conversion**
  - Converts between `PDF`, `DOCX`, `ODT`, `RTF`, and `TXT`.
  - Automatic dual-engine detection: prioritizes **LibreOffice CLI** for headless conversions and automatically falls back to **Microsoft Word COM automation** (`pywin32`) if LibreOffice is unavailable.
  - Automated hang-detection watchdog timeouts and background Word COM prompt suppression.

- **📦 Safe Drag-and-Drop & Archive Processing**
  - Drag and drop individual files, folders (recursive discovery), or ZIP archives directly onto the interface.
  - Strict ZIP slip protection (validates against directory traversal attacks) and automated workspace sandbox cleanup.

- **🛑 Non-Blocking Multithreaded UI**
  - Modern, dark-themed CustomTkinter interface with parallel batch processing for images and data.
  - Instant cancellation: stop conversions cleanly at any time with automated temporary file cleanup.

---

## 🔄 Supported Format Matrix

| Category | Input Formats | Available Target Formats | Engine Backend |
| :--- | :--- | :--- | :--- |
| **🖼️ Images** | `PNG`, `JPG`, `JPEG`, `WEBP`, `BMP`, `TIFF`, `ICO` | `PNG`, `JPEG`, `WEBP`, `BMP`, `TIFF`, `ICO` | Pillow / ImageOps |
| **🎬 Video** | `MP4`, `MKV`, `AVI`, `MOV`, `WEBM`, `FLV`, `TS`, `M4V` | `MP4`, `MKV`, `AVI`, `MOV`, `WEBM` *(+ Audio Extraction)* | FFmpeg + NVENC/QSV/AMF |
| **🎵 Audio** | `MP3`, `WAV`, `AAC`, `FLAC`, `OGG`, `M4A`, `WMA` | `MP3`, `WAV`, `AAC`, `FLAC`, `OGG`, `M4A` | FFmpeg |
| **📄 Documents** | `DOCX`, `DOC`, `PDF`, `ODT`, `RTF`, `TXT` | `PDF`, `DOCX`, `ODT`, `TXT` | LibreOffice / MS Word COM |
| **📊 Data Tables** | `CSV`, `XLSX`, `XLS`, `JSON`, `PARQUET`, `TSV` | `CSV`, `XLSX`, `JSON`, `PARQUET`, `TSV` | Pandas / OpenPyXL / PyArrow |

---

## 📥 Installation & Usage

### Option 1: Standalone Executable (Recommended for End Users)

1. Download the latest `FileConverterEngine.exe` from the [Releases](https://github.com/utkarshgupta-iitbhu/File_Converter_Engine/releases) section.
2. Run `FileConverterEngine.exe` (no installation or Python required).
3. *(Optional)* Go to the **Settings** tab in the app and click **Add to context menu** to activate right-click conversion in Windows Explorer.

---

### Option 2: Run from Source (For Developers)

#### Prerequisites
- Windows 10 or 11
- Python 3.10, 3.11, or 3.12
- *(Optional)* [FFmpeg](https://ffmpeg.org/) on system `PATH` (if not using the bundled binary in `vendor/ffmpeg/`)
- *(Optional)* [LibreOffice](https://www.libreoffice.org/) or Microsoft Office for document conversion

#### Setup
1. **Clone the repository:**
   ```powershell
   git clone https://github.com/utkarshgupta-iitbhu/File_Converter_Engine.git
   cd File_Converter_Engine
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. **Launch the application:**
   ```powershell
   python main.py
   ```

---

## 🛠️ Building the Standalone `.exe`

The repository includes a production-ready PyInstaller build script ([FileConverterEngine.spec](FileConverterEngine.spec)) and batch runner:

1. **Install build dependencies:**
   ```powershell
   python -m pip install -r build-requirements.txt
   ```

2. **Ensure FFmpeg binary is placed:**
   Verify `vendor\ffmpeg\ffmpeg.exe` exists in the project tree.

3. **Run the build script:**
   ```powershell
   .\build_exe.bat
   ```

4. The optimized, single-file binary will be generated in `dist\FileConverterEngine.exe`.

---

## 🖱️ Windows Explorer Right-Click Integration

The engine features a native static cascading menu built according to the Windows Shell specification:

```text
Right Click on file (e.g. photo.jpg)
 ├── Open in File Converter       (Launches the full GUI with file pre-loaded)
 └── Convert to >
      ├── PNG                     (Converts headlessly in-place)
      ├── JPEG
      ├── WEBP
      └── ...
```

* **No Administrator Rights Needed**: Registers strictly within `HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations`.
* **Safe Management**: Activate, remove, or repair the context menu anytime directly from the **Settings** tab in the application.
* **Seamless Updates**: Uses Windows `SHChangeNotify` to notify the shell immediately without terminating or flickering `explorer.exe`.

---

## 🧪 Testing

The project maintains a comprehensive regression test suite covering backend detection, fallback prioritization, error boundaries, zip safety, and portable path resolution:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 📂 Project Architecture

```text
File_Converter_Engine/
├── core/
│   ├── archive_utils.py    # Safe archive validation and sandbox extraction
│   ├── backends.py         # Dynamic runtime discovery for LibreOffice & Word COM
│   ├── context_menu.py     # Windows Shell registry static cascading integration
│   ├── headless.py         # Silent, windowless in-place conversion runner
│   ├── paths.py            # Frozen bundle vs. source portable path resolution
│   ├── py_converters.py    # FFmpeg, Pillow, and Pandas conversion pipelines
│   ├── router.py           # Extension mapping and supported format routing
│   └── settings.py         # Persistent JSON settings (%APPDATA%)
├── cpp_engine/             # Optional C++ extension (CMake + pybind11)
├── tests/                  # Unit and integration test suite
├── vendor/ffmpeg/          # Bundled FFmpeg runtime executable
├── build_exe.bat           # Automated PyInstaller build script
├── FileConverterEngine.spec# PyInstaller packaging configuration
├── main.py                 # CustomTkinter GUI & CLI dispatcher
└── requirements.txt        # Runtime Python dependencies
```

---

## 🛡️ Privacy & Security Philosophy

1. **Zero External Requests**: No outbound network sockets or external telemetry calls exist anywhere in the core engine.
2. **Safe Decompression**: ZIP archives are verified prior to extraction to prevent directory traversal (`../../`) vulnerabilities.
3. **No File Overwrites**: Automatic collision resolution ensures converted files append numeric indices (e.g., `document_1.pdf`) rather than destructively overwriting originals.
4. **Isolated Document Automation**: Word COM automation executes in a sandboxed background thread with prompt suppression and strict process timeout termination.

---

## 🤝 Contributing

Contributions, feature suggestions, and bug reports are very welcome!
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

<div align="center">
  <sub>Crafted with precision by <a href="https://github.com/utkarshgupta-iitbhu">Utkarsh Gupta</a></sub>
</div>
