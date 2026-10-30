
# PyInstaller one-file Windows build for File Converter Engine.

from pathlib import Path

from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


# Project root
PROJECT = Path(SPECPATH).resolve()

# Native C++ extension
native_extension = PROJECT / "cpp_engine.cp312-win_amd64.pyd"

# FFmpeg must be bundled into the final executable.
ffmpeg_exe = PROJECT / "vendor" / "ffmpeg" / "ffmpeg.exe"

if not ffmpeg_exe.is_file():
    raise FileNotFoundError(
        f"Required FFmpeg executable not found: {ffmpeg_exe}\n"
        "Place ffmpeg.exe inside vendor/ffmpeg/ before building."
    )


# --------------------------------------------------
# Data files
# --------------------------------------------------

datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("tkinterdnd2")


# --------------------------------------------------
# Hidden imports
# --------------------------------------------------

hiddenimports = []
hiddenimports += collect_submodules("customtkinter")
hiddenimports += ["tkinterdnd2"]


# --------------------------------------------------
# Binary files
# --------------------------------------------------

# Bundle FFmpeg at the root of the extracted runtime.
binaries = [
    (str(ffmpeg_exe), "."),
]

# Include the prebuilt C++ extension when available.
if native_extension.is_file():
    binaries.append((str(native_extension), "."))


# --------------------------------------------------
# Analyze the application
# --------------------------------------------------

a = Analysis(
    [str(PROJECT / "main.py")],
    pathex=[str(PROJECT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tests",
        "test_cpp",
        "pybind11",
        "torch",
        "torchvision",
        "tensorflow",
        "transformers",
        "cv2",
        "sklearn",
        "scipy",
        "matplotlib",
        "IPython",
        "pytest",
        "yt_dlp",
        "zmq",
        "jedi",
        "sympy",
        "numba",
        "xgboost",
        "dask",
        "spacy",
        "plotly",
        "seaborn",
        "tensorboard",
    ],
    noarchive=False,
)


# --------------------------------------------------
# Python bytecode archive
# --------------------------------------------------

pyz = PYZ(a.pure)


# --------------------------------------------------
# Single-file executable
# --------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FileConverterEngine",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
