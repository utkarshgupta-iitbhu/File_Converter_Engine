"""Persistent per-user settings for File Converter Engine."""
import json
import os
from pathlib import Path

DEFAULT_SETTINGS = {
    "privacy": {
        "remove_exif": True,
        "remove_location": True,
        "remove_comments": True,
        "remove_color_profile": False,
    },
    "conflict_policy": "unique",
    "context_menu_enabled": False,
    "default_output_dir": "",
    "hardware_acceleration": True,
}


def settings_path():
    root = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    base = Path(root) if root else Path.home() / ".config"
    return base / "FileConverterEngine" / "settings.json"


def _merge(default, value):
    if isinstance(default, dict):
        value = value if isinstance(value, dict) else {}
        return {key: _merge(item, value.get(key)) for key, item in default.items()}
    return value if value is not None else default


def load_settings():
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        data = {}
    return _merge(DEFAULT_SETTINGS, data)


def save_settings(settings):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_merge(DEFAULT_SETTINGS, settings), indent=2), encoding="utf-8")
    os.replace(temporary, path)
