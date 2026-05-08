import sys
from unittest.mock import MagicMock, patch

# Mocking external dependencies before importing playwright_engine
sys.modules["streamlit"] = MagicMock()
sys.modules["supabase"] = MagicMock()
sys.modules["pandas"] = MagicMock()
sys.modules["database"] = MagicMock()

mock_playwright_mod = MagicMock()
sys.modules["playwright"] = mock_playwright_mod
sys.modules["playwright.sync_api"] = MagicMock()

# Define TimeoutError in the mock to avoid ImportError
class MockTimeoutError(Exception):
    pass

sys.modules["playwright.sync_api"].TimeoutError = MockTimeoutError
sys.modules["playwright.sync_api"].sync_playwright = MagicMock()

import playwright_engine

def test_import():
    assert playwright_engine is not None

def test_run_execution_timeout_interceptor():
    # Mocking the sync_playwright context manager
    with patch("playwright_engine.sync_playwright") as mock_sync_playwright:
        mock_p = mock_sync_playwright.return_value.__enter__.return_value
        mock_browser = mock_p.chromium.launch.return_value
        mock_context = mock_browser.new_context.return_value
        mock_page = mock_context.new_page.return_value

        # Mock wait_for to raise TimeoutError for the interceptor
        # We need to identify which wait_for is for the interceptor.
        # In run_execution, it's the one at line 173.

        def side_effect(state=None, timeout=None):
            if timeout == 5_000:
                raise MockTimeoutError("Timeout")
            return MagicMock()

        mock_page.locator.return_value.wait_for.side_effect = side_effect

        # We need to mock other things to make run_execution progress or stop early
        # Actually, if we just want to test that it catches PlaywrightTimeoutError and logs:

        ui_log = MagicMock()

        # We can try to run it but it will fail later due to other mocks.
        # But we just want to see if it reaches the except block and uses ui_log.

        try:
            playwright_engine.run_execution(
                df_view=MagicMock(),
                bot_user="user",
                bot_pass="pass",
                selected_distributor="dist",
                URL_LOGIN="url",
                TIMEOUT_MS=1000,
                WAREHOUSE="wh",
                REASON_CODE="rc",
                TABLE_UPDATE_INTERVAL=1,
                ui_log=ui_log,
                alert_callback=MagicMock(),
                table_placeholder=MagicMock(),
                log_label_placeholder=MagicMock(),
                supabase=MagicMock()
            )
        except Exception:
            pass # Expect failures later in the function

        # Check if ui_log was called with the expected message
        ui_log.assert_any_call("SYS", "No interceptor detected. Clean session acquired.")
