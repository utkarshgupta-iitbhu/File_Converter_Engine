"""Portable resource and writable-directory helpers for source and frozen runs."""
import os
import sys
from pathlib import Path


def resource_path(*parts):
    """Resolve bundled read-only resources in source and PyInstaller one-file runs."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base.joinpath(*parts)


def writable_app_dir():
    """Return a user-writable application directory outside the extracted bundle."""
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    path = Path(root) / "FileConverterEngine"
    path.mkdir(parents=True, exist_ok=True)
    return path
