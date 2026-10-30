"""Optional Windows Explorer context-menu integration."""
import os
import sys
import ctypes
from pathlib import Path
from .backends import discover_document_backends, supported_document_targets
from .router import FileRouter

if sys.platform == "win32":
    import winreg
else:
    winreg = None

MENU_NAME = "Open in File Converter"
REG_PATH = r"*\shell\File_Converter_Engine"
ASSOCIATION_ROOT = r"Software\Classes\SystemFileAssociations"
COMMAND_PREFIX = "FileConverterEngine_"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform == "win32" else False
    except Exception:
        return False


def _registry_path():
    """Use per-user registration so admin rights are not normally required."""
    return "Software\\Classes\\" + REG_PATH


def _get_launcher():
    """Get the correct executable or python launcher command line and icon path."""
    if getattr(sys, "frozen", False):
        exe_path = os.path.abspath(sys.executable)
        launcher = f'"{exe_path}"'
    else:
        project_root = Path(__file__).resolve().parents[1]
        main_py = project_root / "main.py"
        if main_py.is_file():
            exe_path = str(main_py)
        else:
            exe_path = os.path.abspath(sys.argv[0])
        launcher = f'"{sys.executable}" "{exe_path}"' if exe_path.lower().endswith(".py") else f'"{exe_path}"'
    return launcher, exe_path


def add_to_registry():
    if sys.platform != "win32":
        return False, "Windows Explorer integration is available only on Windows."
    try:
        launcher, exe_path = _get_launcher()
        key_path = _registry_path()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, MENU_NAME)
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, MENU_NAME)
            winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
            if os.path.isfile(exe_path):
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, exe_path)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'{launcher} --open "%1"')

        router = FileRouter()
        for extension, targets in _targets_by_extension(router).items():
            if not targets:
                continue
            base = f"{ASSOCIATION_ROOT}\\{extension}\\shell\\FileConverterConvert"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
                winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "Convert to")
                winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "")
                winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
                if os.path.isfile(exe_path):
                    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, exe_path)

            for idx, target in enumerate(targets, start=1):
                command_name = f"{idx:02d}_{target.lower()}"
                target_key = base + "\\shell\\" + command_name
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, target_key) as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, target)
                    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, target)
                    winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, target_key + r"\command") as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'{launcher} --convert-to "{target}" --same-folder "%1"')
        _remove_command_store_entries()
        _notify_shell()
        return True, "Registered per-user context-menu commands for supported formats."
    except Exception as exc:
        return False, f"Could not add context-menu entry: {exc}"


def remove_from_registry():
    if sys.platform != "win32":
        return False, "Windows Explorer integration is available only on Windows."
    try:
        base = _registry_path()
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + r"\command")
        except FileNotFoundError:
            pass
        base_missing = False
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
        except FileNotFoundError:
            base_missing = True
        for category in ("image", "video", "audio", "data", "document"):
            for extension in sorted(_extensions_for_category(category, FileRouter())):
                _delete_tree(winreg.HKEY_CURRENT_USER, f"{ASSOCIATION_ROOT}\\{extension}\\shell\\FileConverterConvert")
        _remove_command_store_entries()
        _notify_shell()
        if base_missing:
            return True, "No per-user context-menu entry was present."
        return True, "Removed the per-user right-click commands."
    except Exception as exc:
        return False, f"Could not remove context-menu entry: {exc}"


def registry_status():
    if sys.platform != "win32":
        return "Not available", "Windows Explorer integration is available only on Windows."
    try:
        generic_command = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _registry_path() + r"\command") as key:
                generic_command, _ = winreg.QueryValueEx(key, "")
        except FileNotFoundError:
            pass
        conversion_entry_count = 0
        for category in ("image", "video", "audio", "data", "document"):
            for extension in sorted(_extensions_for_category(category, FileRouter())):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{ASSOCIATION_ROOT}\\{extension}\\shell\\FileConverterConvert\\shell") as key:
                        conversion_entry_count += winreg.QueryInfoKey(key)[0]
                except FileNotFoundError:
                    pass
        if generic_command and conversion_entry_count == 0:
            return "Partially configured", "The Open command is registered, but no format-specific conversion entries were found."
        if not generic_command and conversion_entry_count:
            return "Partially configured", "Format-specific conversion entries exist, but the Open command is missing."
        if not generic_command:
            return "Not registered", "No per-user File Explorer integration is registered."
        return "Registered", "Per-user File Explorer integration is registered."
    except Exception as exc:
        return "Error", f"Could not inspect registration: {exc}"


def refresh_registry():
    removed, remove_message = remove_from_registry()
    if not removed:
        return False, remove_message
    return add_to_registry()


def _targets_by_extension(router):
    targets = {}
    document_backends = discover_document_backends()
    for category in ("image", "video", "audio", "data", "document"):
        for extension in sorted(_extensions_for_category(category, router)):
            if category == "document":
                targets[extension] = supported_document_targets(f"file{extension}", document_backends)
            else:
                targets[extension] = router.get_supported_conversions("", f"file{extension}")
    return targets


def _remove_command_store_entries():
    legacy_root = r"Software\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, legacy_root) as key:
            names = []
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(key, index)
                    index += 1
                    if name.startswith(COMMAND_PREFIX):
                        names.append(name)
                except OSError:
                    break
        for name in names:
            _delete_tree(winreg.HKEY_CURRENT_USER, legacy_root + "\\" + name)
    except FileNotFoundError:
        pass


def _notify_shell():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x1000, None, None)
        except Exception:
            pass


def _extensions_for_category(category, router):
    from . import router as router_module
    mapping = {
        "image": router_module.IMAGE_EXTENSIONS,
        "video": router_module.VIDEO_EXTENSIONS,
        "audio": router_module.AUDIO_EXTENSIONS,
        "data": router_module.DATA_EXTENSIONS,
        "document": router_module.DOCUMENT_EXTENSIONS,
    }
    return mapping[category]


def _delete_tree(root, path):
    try:
        with winreg.OpenKey(root, path) as key:
            children = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            _delete_tree(root, path + "\\" + child)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    success, msg = refresh_registry()
    print(f"Registry refresh result: {success} ({msg})")