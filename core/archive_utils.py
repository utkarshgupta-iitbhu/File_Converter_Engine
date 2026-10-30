"""Bounded, non-executable ZIP ingestion for dropped batch files."""
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_ENTRIES = 5000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


def extract_supported_zip(archive_path, router):
    """Extract supported files into a temporary directory after validating entries."""
    temp_dir = tempfile.TemporaryDirectory(prefix="fce_zip_")
    accepted = []
    skipped = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError(f"ZIP contains too many entries (maximum {MAX_ENTRIES}).")
            total_size = sum(max(0, item.file_size) for item in entries)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("ZIP uncompressed size exceeds the safety limit.")
            root = Path(temp_dir.name).resolve()
            used_destinations = set()
            for item in entries:
                name = item.filename.replace("\\", "/")
                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Unsafe ZIP path rejected: {item.filename}")
                if item.is_dir() or not name:
                    continue
                destination = (root / Path(*relative.parts)).resolve()
                if os.path.commonpath((str(root), str(destination))) != str(root):
                    raise ValueError(f"Unsafe ZIP path rejected: {item.filename}")
                category = router.category_for(name)
                if category == "unsupported":
                    skipped.append(f"{item.filename}: unsupported format")
                    continue
                destination_key = str(destination).casefold()
                if destination_key in used_destinations or destination.exists():
                    number = 1
                    original = destination
                    while destination_key in used_destinations or destination.exists():
                        destination = original.with_name(f"{original.stem}_{number}{original.suffix}")
                        destination_key = str(destination).casefold()
                        number += 1
                used_destinations.add(destination_key)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, destination.open("wb") as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                accepted.append(str(destination))
        if not accepted:
            temp_dir.cleanup()
            raise ValueError("ZIP contained no supported files.")
        return temp_dir, accepted, skipped
    except Exception:
        temp_dir.cleanup()
        raise
