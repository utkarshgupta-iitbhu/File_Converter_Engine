from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.paths import resource_path, writable_app_dir
from core.py_converters import _document_timeout, _word_timeout


class PortabilityTests(unittest.TestCase):
    def test_resource_path_uses_frozen_bundle_root(self):
        with TemporaryDirectory() as directory:
            with patch.object(sys, "_MEIPASS", directory, create=True):
                self.assertEqual(resource_path("assets", "icon.ico"), Path(directory) / "assets" / "icon.ico")

    def test_resource_path_uses_project_root_when_not_frozen(self):
        expected = Path(__file__).resolve().parents[1] / "README.md"
        self.assertEqual(resource_path("README.md"), expected)

    def test_writable_directory_is_not_based_on_bundle_root(self):
        with TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"LOCALAPPDATA": directory}, clear=False):
                writable = writable_app_dir()
            self.assertTrue(writable.is_dir())
            self.assertNotEqual(writable, Path(getattr(sys, "_MEIPASS", "")))

    def test_timeout_policy_is_configurable(self):
        with patch.dict("os.environ", {"FCE_PDF_DOCX_TIMEOUT_SECONDS": "22", "FCE_WORD_TIMEOUT_SECONDS": "31"}):
            self.assertEqual(_document_timeout("source.pdf", "DOCX"), 22)
            self.assertEqual(_word_timeout(), 31)


if __name__ == "__main__":
    unittest.main()
