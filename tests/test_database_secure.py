import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock modules before importing database
sys.modules['streamlit'] = MagicMock()
sys.modules['supabase'] = MagicMock()
mock_bcrypt = MagicMock()
sys.modules['bcrypt'] = mock_bcrypt

import database

class TestDatabaseSecure(unittest.TestCase):
    def setUp(self):
        mock_bcrypt.reset_mock()

    def test_authenticate_user_secure_success(self):
        # Mock Supabase client
        mock_supabase = MagicMock()
        mock_table = mock_supabase.table.return_value
        mock_select = mock_table.select.return_value
        mock_eq = mock_select.eq.return_value
        mock_execute = mock_eq.execute

        # Simulate user found with hashed password
        hashed_password_str = "$2b$12$KIX6r6K4.Y7X8.u9Z6Z6.ue9Z6Z6.ue9Z6Z6.ue9Z6Z6.ue9Z6Z6."
        mock_execute.return_value.data = [{"username": "testuser", "password": hashed_password_str}]

        # Mock bcrypt.checkpw to return True for correct password
        mock_bcrypt.checkpw.return_value = True

        result = database.authenticate_user(mock_supabase, "testuser", "password123")
        self.assertTrue(result)

        # Verify bcrypt.checkpw was called with correct arguments
        mock_bcrypt.checkpw.assert_called_once_with(
            "password123".encode('utf-8'),
            hashed_password_str.encode('utf-8')
        )

    def test_authenticate_user_secure_fail(self):
        mock_supabase = MagicMock()
        mock_table = mock_supabase.table.return_value
        mock_select = mock_table.select.return_value
        mock_eq = mock_select.eq.return_value
        mock_execute = mock_eq.execute

        hashed_password_str = "$2b$12$KIX6r6K4.Y7X8.u9Z6Z6.ue9Z6Z6.ue9Z6Z6.ue9Z6Z6.ue9Z6Z6."
        mock_execute.return_value.data = [{"username": "testuser", "password": hashed_password_str}]

        # Mock bcrypt.checkpw to return False for wrong password
        mock_bcrypt.checkpw.return_value = False

        result = database.authenticate_user(mock_supabase, "testuser", "wrongpass")
        self.assertFalse(result)

    def test_authenticate_user_no_plaintext_query(self):
        # Verify that the password is no longer part of the SQL query
        mock_supabase = MagicMock()
        mock_table = mock_supabase.table.return_value
        mock_select = mock_table.select.return_value
        mock_eq = mock_select.eq.return_value

        database.authenticate_user(mock_supabase, "testuser", "password123")

        # It should only call eq once for username
        mock_select.eq.assert_called_once_with("username", "testuser")

        # Verify that eq was NOT called with "password"
        # Since eq returns another mock (mock_eq), we check calls on mock_select and mock_eq
        for call in mock_select.mock_calls:
            if call[0] == 'eq' and call[1][0] == 'password':
                self.fail("Query still contains plaintext password comparison in select.eq")

        for call in mock_eq.mock_calls:
            if call[0] == 'eq' and call[1][0] == 'password':
                self.fail("Query still contains plaintext password comparison in eq.eq")

if __name__ == "__main__":
    unittest.main()
