import sys
import unittest
from unittest.mock import patch
import playwright_engine

class TestPlaywrightEngine(unittest.TestCase):
    @patch('playwright_engine.subprocess.run')
    def test_ensure_playwright_success(self, mock_run):
        """Test that ensure_playwright successfully calls subprocess.run with correct args."""
        # Act
        playwright_engine.ensure_playwright()

        # Assert
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )

    @patch('playwright_engine.st.error')
    @patch('playwright_engine.subprocess.run')
    def test_ensure_playwright_failure(self, mock_run, mock_st_error):
        """Test that ensure_playwright handles exceptions and logs an error to streamlit."""
        # Arrange
        mock_run.side_effect = Exception("Test installation failure")

        # Act
        playwright_engine.ensure_playwright()

        # Assert
        mock_run.assert_called_once_with(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )
        mock_st_error.assert_called_once_with("Failed to install browser engine: Test installation failure")

if __name__ == '__main__':
    unittest.main()
