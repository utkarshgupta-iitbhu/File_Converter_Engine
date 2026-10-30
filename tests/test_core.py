import os
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from core.archive_utils import extract_supported_zip
from core.headless import convert_from_explorer
from core.py_converters import convert_image
from core.router import FileRouter
from core.settings import load_settings, save_settings


class CoreRegressionTests(unittest.TestCase):
    def test_failed_image_conversion_preserves_destination(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            destination = root / "existing.jpg"
            Image.new("RGB", (8, 8), "red").save(source)
            destination.write_bytes(b"previous output")
            success, _ = convert_image(str(source), "invalid-format", out_path=str(destination))
            self.assertFalse(success)
            self.assertEqual(destination.read_bytes(), b"previous output")

    def test_zip_rejects_path_traversal(self):
        with TemporaryDirectory() as directory:
            archive_path = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.png", "not an image")
            with self.assertRaises(ValueError):
                extract_supported_zip(str(archive_path), FileRouter())

    def test_headless_conversion_uses_source_folder_and_unique_name(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.png"
            Image.new("RGB", (8, 8), "blue").save(source)
            self.assertEqual(convert_from_explorer([str(source)], "JPEG"), 0)
            self.assertTrue((root / "photo.jpeg").is_file())
            self.assertEqual(convert_from_explorer([str(source)], "JPEG"), 0)
            self.assertTrue((root / "photo_1.jpeg").is_file())

    def test_settings_round_trip(self):
        with TemporaryDirectory() as directory:
            previous = os.environ.get("APPDATA")
            os.environ["APPDATA"] = directory
            try:
                settings = load_settings()
                settings["privacy"]["remove_color_profile"] = True
                settings["hardware_acceleration"] = False
                save_settings(settings)
                self.assertTrue(load_settings()["privacy"]["remove_color_profile"])
                self.assertFalse(load_settings()["hardware_acceleration"])
            finally:
                if previous is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = previous

    def test_headless_media_conversion_uses_saved_hardware_setting(self):
        with TemporaryDirectory() as directory:
            previous = os.environ.get("APPDATA")
            os.environ["APPDATA"] = directory
            try:
                settings = load_settings()
                settings["hardware_acceleration"] = False
                save_settings(settings)
                source = Path(directory) / "sample.mp4"
                source.write_bytes(b"media")
                with patch("core.headless.FileRouter.category_for", return_value="video"), patch("core.headless.FileRouter.detect_true_format", return_value="video/mp4"), patch("core.headless.FileRouter.get_supported_conversions", return_value=["MP3"]), patch("core.headless.convert_media", return_value=(True, str(Path(directory) / "sample.mp3"))) as convert:
                    from core.headless import convert_from_explorer
                    self.assertEqual(convert_from_explorer([str(source)], "MP3"), 0)
                self.assertFalse(convert.call_args.kwargs["hardware_accel"])
            finally:
                if previous is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = previous


if __name__ == "__main__":
    unittest.main()
