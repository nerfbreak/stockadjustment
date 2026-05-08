import pytest
from unittest.mock import MagicMock
from database import authenticate_user

def test_authenticate_user_success():
    mock_supabase = MagicMock()
    mock_execute_result = MagicMock()
    mock_execute_result.data = [{"id": 1, "username": "testuser"}]

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute_result

    result = authenticate_user(mock_supabase, "testuser", "correctpass")

    assert result is True
    mock_supabase.table.assert_called_with("users_auth")
    mock_supabase.table.return_value.select.assert_called_with("*")
    mock_supabase.table.return_value.select.return_value.eq.assert_called_with("username", "testuser")
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.assert_called_with("password", "correctpass")

def test_authenticate_user_invalid_credentials():
    mock_supabase = MagicMock()
    mock_execute_result = MagicMock()
    mock_execute_result.data = []

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute_result

    result = authenticate_user(mock_supabase, "testuser", "wrongpass")
    assert result is False

def test_authenticate_user_exception():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("DB Connection Error")

    result = authenticate_user(mock_supabase, "testuser", "testpass")
    assert result is False

def test_authenticate_user_none_supabase():
    result = authenticate_user(None, "testuser", "testpass")
    assert result is False
