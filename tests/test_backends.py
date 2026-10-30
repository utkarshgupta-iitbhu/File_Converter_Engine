from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.backends import Backend, choose_document_backend, discover_document_backends, find_libreoffice
from core.py_converters import convert_document


class BackendTests(unittest.TestCase):
    def test_libreoffice_path_detection_does_not_require_path(self):
        with TemporaryDirectory() as directory:
            install = Path(directory) / "LibreOffice"
            executable = install / "program" / "soffice.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"stub")
            detected = find_libreoffice(which=lambda _name: None, env={}, registry_paths=[install])
            self.assertEqual(detected, str(executable))

    def test_libreoffice_is_prioritized_over_word(self):
        libreoffice = Backend("LibreOffice", "libreoffice", "C:/Program Files/LibreOffice/program/soffice.exe", frozenset({(".docx", "pdf")}))
        word = Backend("Microsoft Word", "word", None, frozenset({(".docx", "pdf")}))
        selected, warning = choose_document_backend("report with spaces.docx", "PDF", (libreoffice, word))
        self.assertIs(selected, libreoffice)
        self.assertEqual(warning, "")

    def test_word_is_used_when_libreoffice_does_not_support_pair(self):
        libreoffice = Backend("LibreOffice", "libreoffice", "soffice.exe", frozenset())
        word = Backend("Microsoft Word", "word", None, frozenset({(".docx", "pdf")}))
        selected, _ = choose_document_backend("report.docx", "PDF", (libreoffice, word))
        self.assertIs(selected, word)

    def test_unsupported_pair_reports_missing_backend(self):
        selected, message = choose_document_backend("report.docx", "PDF", ())
        self.assertIsNone(selected)
        self.assertIn("Detected backends: none", message)

    def test_document_conversion_uses_detected_path_and_spaces(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report with spaces.docx"
            source.write_bytes(b"source")
            output = root / "converted.pdf"
            libreoffice = Backend("LibreOffice", "libreoffice", str(root / "program" / "soffice.exe"), frozenset({(".docx", "pdf")}))

            with patch("core.py_converters.discover_document_backends", return_value=(libreoffice,)), patch("core.py_converters._convert_with_libreoffice", return_value=(True, "")):
                success, result = convert_document(str(source), "PDF", out_path=str(output))
            self.assertTrue(success)
            self.assertEqual(result, str(output))

    def test_runtime_discovery_can_return_no_backends(self):
        backends = discover_document_backends(which=lambda _name: None, env={}, registry_paths=[], word_probe=lambda: False, registry_probe=lambda: False)
        self.assertEqual(backends, ())

    def test_document_failure_preserves_existing_destination(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.docx"
            output = root / "report.pdf"
            source.write_bytes(b"source")
            output.write_bytes(b"previous output")
            libreoffice = Backend("LibreOffice", "libreoffice", "soffice.exe", frozenset({(".docx", "pdf")}))
            failure = __import__("subprocess").CalledProcessError(1, ["soffice"], stderr="conversion failed")
            with patch("core.py_converters.discover_document_backends", return_value=(libreoffice,)), patch("core.py_converters.subprocess.run", side_effect=failure):
                success, message = convert_document(str(source), "PDF", out_path=str(output))
            self.assertFalse(success)
            self.assertIn("conversion failed", message)
            self.assertEqual(output.read_bytes(), b"previous output")

    def test_libreoffice_success_does_not_invoke_word(self):
        libreoffice = Backend("LibreOffice", "libreoffice", "soffice.exe", frozenset({(".pdf", "docx")}))
        word = Backend("Microsoft Word", "word", None, frozenset({(".pdf", "docx")}))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            output = Path(directory) / "source.docx"
            source.write_bytes(b"pdf")
            with patch("core.py_converters.discover_document_backends", return_value=(libreoffice, word)), patch("core.py_converters._convert_with_libreoffice", return_value=(True, "")) as libreoffice_run, patch("core.py_converters._convert_with_word") as word_run:
                success, _ = convert_document(str(source), "DOCX", out_path=str(output))
            self.assertTrue(success)
            libreoffice_run.assert_called_once()
            word_run.assert_not_called()

    def test_libreoffice_failure_invokes_word_fallback(self):
        libreoffice = Backend("LibreOffice", "libreoffice", "soffice.exe", frozenset({(".pdf", "docx")}))
        word = Backend("Microsoft Word", "word", None, frozenset({(".pdf", "docx")}))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            output = Path(directory) / "source.docx"
            source.write_bytes(b"pdf")
            with patch("core.py_converters.discover_document_backends", return_value=(libreoffice, word)), patch("core.py_converters._convert_with_libreoffice", return_value=(False, "timed out after 45 seconds; process cleanup completed.")), patch("core.py_converters._convert_with_word", return_value=(True, "")) as word_run:
                success, result = convert_document(str(source), "DOCX", out_path=str(output))
            self.assertTrue(success)
            self.assertEqual(result, str(output))
            word_run.assert_called_once()

    def test_timeout_fallback_is_logged(self):
        libreoffice = Backend("LibreOffice", "libreoffice", "soffice.exe", frozenset({(".pdf", "docx")}))
        word = Backend("Microsoft Word", "word", None, frozenset({(".pdf", "docx")}))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            output = Path(directory) / "source.docx"
            source.write_bytes(b"pdf")
            notices = []
            with patch("core.py_converters.discover_document_backends", return_value=(libreoffice, word)), patch("core.py_converters._convert_with_libreoffice", return_value=(False, "timed out after 45 seconds; process cleanup completed.")), patch("core.py_converters._convert_with_word", return_value=(True, "")):
                success, _ = convert_document(str(source), "DOCX", out_path=str(output), notice_callback=notices.append)
            self.assertTrue(success)
            self.assertTrue(any("Switching to Microsoft Word fallback" in notice for notice in notices))

    def test_word_only_path_is_used_when_libreoffice_unavailable(self):
        word = Backend("Microsoft Word", "word", None, frozenset({(".docx", "pdf")}))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.docx"
            output = Path(directory) / "source.pdf"
            source.write_bytes(b"docx")
            with patch("core.py_converters.discover_document_backends", return_value=(word,)), patch("core.py_converters._convert_with_word", return_value=(True, "")) as word_run:
                success, _ = convert_document(str(source), "PDF", out_path=str(output))
            self.assertTrue(success)
            word_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
