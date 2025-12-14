import unittest
from unittest.mock import MagicMock, patch
import sys
import thumbnail  # noqa: E402


class TestThumbnail(unittest.TestCase):

    def setUp(self):
        # Ensure we start with clean modules for each test if possible,
        # but since we are patching sys.modules, context managers handle cleanup.
        pass

    def test_dry_run(self):
        """Test that dry_run returns True without doing work."""
        result = thumbnail.generate_thumbnail("input.pdf", "output.jpg", dry_run=True)
        self.assertTrue(result)

    def test_unsupported_format(self):
        """Test that non-PDF formats are rejected."""
        result = thumbnail.generate_thumbnail(
            "input.txt", "output.jpg", file_format="txt"
        )
        self.assertFalse(result)

    @patch("os.path.exists")
    def test_input_not_found(self, mock_exists):
        """Test failure when input file doesn't exist."""
        mock_exists.return_value = False
        result = thumbnail.generate_thumbnail("missing.pdf", "output.jpg")
        self.assertFalse(result)

    def test_generate_success(self):
        """Test successful thumbnail generation."""
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_count = 1
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.width = 100
        mock_pix.height = 100
        mock_pix.samples = b"fake_data"

        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pix
        mock_fitz.open.return_value = mock_doc

        mock_pil = MagicMock()
        mock_image = MagicMock()
        mock_pil.Image = mock_image
        mock_img_obj = MagicMock()
        mock_image.frombytes.return_value = mock_img_obj

        with patch.dict(
            sys.modules, {"fitz": mock_fitz, "PIL": mock_pil, "PIL.Image": mock_image}
        ):
            with patch("os.path.exists", return_value=True):
                with patch("os.makedirs"):
                    # We need to reload or ensure the import inside function hits our mock.
                    # Since it's 'import fitz', it checks sys.modules.
                    result = thumbnail.generate_thumbnail("input.pdf", "output.jpg")

        self.assertTrue(result)
        mock_fitz.open.assert_called_with("input.pdf")
        mock_doc.load_page.assert_called_with(0)
        mock_image.frombytes.assert_called()
        mock_img_obj.thumbnail.assert_called()
        mock_img_obj.save.assert_called()

    def test_missing_fitz(self):
        """Test failure when fitz is missing."""
        # Remove fitz from sys.modules to simulate ImportError
        with patch.dict(sys.modules):
            if "fitz" in sys.modules:
                del sys.modules["fitz"]
            # We also need to make sure it can't be found by import mechanism
            # Setting it to None or using a side_effect on builtins.__import__ is tricky.
            # Easiest is to patch builtins.__import__ but that's dangerous.
            # Better: use a Mock that raises ImportError when accessed?
            # Actually, if we just delete it from sys.modules, python tries to find it.
            # If it's installed, it will find it.
            # So we must prevent it from being found.

            # This is too aggressive, it blocks ALL imports if we patch builtins.__import__ indiscriminately
            pass

        # Alternative: Use patch.dict with a key that maps to None? No, that just makes import return None.
        # Let's try mocking the function logic where it does `import fitz`.
        # Since we can't easily uninstall packages, let's use a wrapper that raises ImportError for specific names.

        original_import = __import__

        def import_mock(name, *args, **kwargs):
            if name == "fitz":
                raise ImportError("No fitz")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_mock):
            with patch("os.path.exists", return_value=True):
                result = thumbnail.generate_thumbnail("input.pdf", "output.jpg")
                self.assertFalse(result)

    def test_missing_pillow(self):
        """Test failure when Pillow is missing."""
        mock_fitz = MagicMock()

        original_import = __import__

        def import_mock(name, *args, **kwargs):
            if name == "PIL":
                raise ImportError("No PIL")
            # We must allow fitz
            if name == "fitz":
                return mock_fitz
            return original_import(name, *args, **kwargs)

        # Ensure PIL is not in sys.modules so import is forced to run
        with patch.dict(sys.modules):
            if "PIL" in sys.modules:
                del sys.modules["PIL"]

            with patch("builtins.__import__", side_effect=import_mock):
                with patch("os.path.exists", return_value=True):
                    # We need fitz to import successfully for this test to reach PIL import
                    result = thumbnail.generate_thumbnail("input.pdf", "output.jpg")
                    self.assertFalse(result)

    def test_empty_pdf(self):
        """Test handling of PDF with no pages."""
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_count = 0
        mock_fitz.open.return_value = mock_doc

        mock_pil = MagicMock()
        mock_image = MagicMock()
        mock_pil.Image = mock_image

        with patch.dict(
            sys.modules, {"fitz": mock_fitz, "PIL": mock_pil, "PIL.Image": mock_image}
        ):
            with patch("os.path.exists", return_value=True):
                result = thumbnail.generate_thumbnail("input.pdf", "output.jpg")

        self.assertFalse(result)

    def test_exception_handling(self):
        """Test general exception handling during processing."""
        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = Exception("General failure")

        mock_pil = MagicMock()

        with patch.dict(sys.modules, {"fitz": mock_fitz, "PIL": mock_pil}):
            with patch("os.path.exists", return_value=True):
                result = thumbnail.generate_thumbnail("input.pdf", "output.jpg")

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
