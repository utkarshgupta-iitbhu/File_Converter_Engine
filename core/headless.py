"""Command-line conversion entry point used by Windows Explorer."""
import os
from pathlib import Path

from .py_converters import convert_data, convert_document, convert_image, convert_media, get_output_path, unique_path
from .router import FileRouter
from .settings import load_settings


def convert_from_explorer(paths, target):
    router = FileRouter()
    target = target.upper().lstrip(".")
    settings = load_settings()
    privacy = settings.get("privacy", {})
    hardware_accel = settings.get("hardware_acceleration", True)
    errors = []
    converted = []
    for raw_path in paths:
        source = Path(raw_path).resolve()
        if not source.is_file():
            errors.append(f"Not a file: {source}")
            continue
        category = router.category_for(source)
        supported = router.get_supported_conversions(router.detect_true_format(source), str(source))
        if category == "unsupported" or target not in supported:
            errors.append(f"Unsupported conversion for {source.name}: {target}")
            continue
        output = unique_path(get_output_path(str(source), target, str(source.parent)))
        if category == "image":
            result = convert_image(str(source), target, privacy=privacy, out_path=output)
        elif category in {"video", "audio"}:
            result = convert_media(str(source), target, out_path=output, hardware_accel=hardware_accel)
        elif category == "data":
            result = convert_data(str(source), target, out_path=output)
        else:
            result = convert_document(str(source), target, out_path=output, notice_callback=print)
        if result[0]:
            converted.append(result[1])
        else:
            errors.append(f"{source.name}: {result[1]}")
    if errors:
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, "\n".join(errors[:5]), "File Converter Engine", 0x10)
            except Exception:
                pass
        for error in errors:
            print(error)
    for output in converted:
        print(f"Converted: {output}")
    return 0 if converted and not errors else (1 if errors else 2)
