import pytest
from unittest.mock import patch, MagicMock

from database import init_supabase

@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    # Clear the Streamlit cache before each test to ensure fresh execution
    init_supabase.clear()

@patch('database.create_client')
@patch('database.st.secrets')
def test_init_supabase_success(mock_secrets, mock_create_client):
    # Setup
    def mock_get(key, default=""):
        if key == "SUPABASE_URL":
            return "dummy_url"
        if key == "SUPABASE_KEY":
            return "dummy_key"
        return default

    mock_secrets.get.side_effect = mock_get

    mock_client_instance = MagicMock()
    mock_create_client.return_value = mock_client_instance

    # Execute
    result = init_supabase()

    # Verify
    assert result == mock_client_instance
    mock_create_client.assert_called_once_with("dummy_url", "dummy_key")

@patch('database.create_client')
@patch('database.st.secrets')
def test_init_supabase_missing_key(mock_secrets, mock_create_client):
    # Setup
    def mock_get(key, default=""):
        if key == "SUPABASE_URL":
            return "dummy_url"
        return default

    mock_secrets.get.side_effect = mock_get

    # Execute
    result = init_supabase()

    # Verify
    assert result is None
    mock_create_client.assert_not_called()

@patch('database.create_client')
@patch('database.st.secrets')
def test_init_supabase_missing_url(mock_secrets, mock_create_client):
    # Setup
    def mock_get(key, default=""):
        if key == "SUPABASE_KEY":
            return "dummy_key"
        return default

    mock_secrets.get.side_effect = mock_get

    # Execute
    result = init_supabase()

    # Verify
    assert result is None
    mock_create_client.assert_not_called()

@patch('database.create_client')
@patch('database.st.secrets')
def test_init_supabase_missing_both(mock_secrets, mock_create_client):
    # Setup
    mock_secrets.get.side_effect = lambda key, default="": default

    # Execute
    result = init_supabase()

    # Verify
    assert result is None
    mock_create_client.assert_not_called()
