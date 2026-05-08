import pytest
from unittest.mock import patch
import requests
import app
import streamlit as st

@patch("app.st")
@patch("app.requests.post")
def test_send_telegram_alert_happy_path(mock_post, mock_st):
    # Setup mocks
    def mock_get_secret(key, default=""):
        if key == "TELEGRAM_BOT_TOKEN":
            return "test_bot_token"
        if key == "TELEGRAM_CHAT_ID":
            return "test_chat_id"
        return default

    mock_st.secrets.get.side_effect = mock_get_secret

    # Call the function
    app.send_telegram_alert("Hello World")

    # Assert requests.post was called with expected arguments
    expected_url = "https://api.telegram.org/bottest_bot_token/sendMessage"
    expected_payload = {
        "chat_id": "test_chat_id",
        "text": "Hello World",
        "parse_mode": "HTML"
    }

    mock_post.assert_called_once_with(expected_url, json=expected_payload, timeout=5)

@patch("app.st")
@patch("app.requests.post")
def test_send_telegram_alert_missing_secrets(mock_post, mock_st):
    # Setup mocks to return empty strings
    mock_st.secrets.get.return_value = ""

    # Call the function
    app.send_telegram_alert("Hello World")

    # Assert requests.post was NOT called because secrets are missing
    mock_post.assert_not_called()

@patch("app.st")
@patch("app.requests.post")
def test_send_telegram_alert_exception_handling(mock_post, mock_st):
    # Setup mocks
    def mock_get_secret(key, default=""):
        if key == "TELEGRAM_BOT_TOKEN":
            return "test_bot_token"
        if key == "TELEGRAM_CHAT_ID":
            return "test_chat_id"
        return default

    mock_st.secrets.get.side_effect = mock_get_secret

    # Setup requests.post to raise an exception
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

    # Call the function - it should swallow the exception and not crash
    try:
        app.send_telegram_alert("Hello World")
    except Exception as e:
        pytest.fail(f"Exception was not swallowed: {e}")

    # Verify post was called before the exception was raised and swallowed
    mock_post.assert_called_once()
