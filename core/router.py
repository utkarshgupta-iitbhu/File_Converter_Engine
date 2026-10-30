"""File detection and supported conversion routing."""
from pathlib import Path
import mimetypes
from .backends import supported_document_targets

try:
    import magic
except ImportError:  # Optional fallback for systems without python-magic-bin
    magic = None

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".ico", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpeg", ".mpg", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"}
DATA_EXTENSIONS = {".csv", ".json", ".xls", ".xlsx", ".parquet"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf"}

class FileRouter:
    """Detect files and expose only conversion families supported by this app."""

    def __init__(self):
        self.mime_detector = magic.Magic(mime=True) if magic else None

    def detect_true_format(self, file_path):
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        if self.mime_detector:
            try:
                detected = self.mime_detector.from_file(str(path))
                if detected and not detected.startswith("application/octet-stream"):
                    return detected
            except Exception:
                pass
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or self._mime_from_extension(path.suffix.lower()) or "application/octet-stream"

    @staticmethod
    def _mime_from_extension(ext):
        if ext in IMAGE_EXTENSIONS: return "image/" + ("jpeg" if ext in {".jpg", ".jpeg"} else ext[1:])
        if ext in VIDEO_EXTENSIONS: return "video/" + ext[1:]
        if ext in AUDIO_EXTENSIONS: return "audio/" + ext[1:]
        if ext == ".csv": return "text/csv"
        if ext == ".json": return "application/json"
        if ext in {".xls", ".xlsx", ".parquet"}: return "application/data"
        if ext == ".pdf": return "application/pdf"
        if ext == ".doc": return "application/msword"
        if ext == ".docx": return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if ext == ".odt": return "application/vnd.oasis.opendocument.text"
        if ext == ".txt": return "text/plain"
        if ext == ".rtf": return "application/rtf"
        return None

    def category_for(self, file_path):
        ext = Path(file_path).suffix.lower()
        if ext in IMAGE_EXTENSIONS: return "image"
        if ext in VIDEO_EXTENSIONS: return "video"
        if ext in AUDIO_EXTENSIONS: return "audio"
        if ext in DATA_EXTENSIONS: return "data"
        if ext in DOCUMENT_EXTENSIONS: return "document"
        return "unsupported"

    def get_supported_conversions(self, mime_type, file_path=None):
        """Return formats for a file. file_path is preferred for extension-aware routing."""
        category = self.category_for(file_path) if file_path else self._category_from_mime(mime_type)
        if category == "image": return ["PNG", "JPEG", "WEBP", "BMP", "TIFF", "ICO"]
        if category == "video": return ["MP4", "MKV", "AVI", "MOV", "WEBM", "GIF", "MP3", "WAV", "FLAC", "M4A", "OGG"]
        if category == "audio": return ["MP3", "WAV", "FLAC", "M4A", "OGG"]
        if category == "data": return ["CSV", "JSON", "XLSX", "PARQUET"]
        if category == "document": return supported_document_targets(file_path)
        return []

    @staticmethod
    def _category_from_mime(mime_type):
        if mime_type.startswith("image/"): return "image"
        if mime_type.startswith("video/"): return "video"
        if mime_type.startswith("audio/"): return "audio"
        if mime_type in {"text/csv", "application/json", "application/data", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"}: return "data"
        if mime_type in {"application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.oasis.opendocument.text", "text/plain", "application/rtf"}: return "document"
        return "unsupported"
