import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock modules before importing database
sys.modules['streamlit'] = MagicMock()
sys.modules['supabase'] = MagicMock()
mock_bcrypt = MagicMock()
sys.modules['bcrypt'] = mock_bcrypt

import database

class TestDatabaseVulnerable(unittest.TestCase):
    def setUp(self):
        mock_bcrypt.reset_mock()

    def test_authenticate_user_plaintext_now_fails(self):
        # In the new implementation, it should NOT work with plaintext if bcrypt says no
        mock_supabase = MagicMock()
        mock_table = mock_supabase.table.return_value
        mock_select = mock_table.select.return_value
        mock_eq = mock_select.eq.return_value
        mock_execute = mock_eq.execute

        # Simulate user found with "plaintext" password (stored in DB)
        mock_execute.return_value.data = [{"username": "testuser", "password": "password123"}]

        # bcrypt.checkpw will fail because "password123" is not a valid hash
        mock_bcrypt.checkpw.side_effect = Exception("Invalid hash")

        result = database.authenticate_user(mock_supabase, "testuser", "password123")
        self.assertFalse(result)

    def test_authenticate_user_no_password_in_query(self):
        mock_supabase = MagicMock()
        mock_table = mock_supabase.table.return_value
        mock_select = mock_table.select.return_value
        mock_eq = mock_select.eq.return_value

        database.authenticate_user(mock_supabase, "testuser", "password123")

        # Verify that eq was NOT called with "password"
        for call in mock_select.mock_calls:
            if call[0] == 'eq' and call[1][0] == 'password':
                self.fail("Query still contains plaintext password comparison")

if __name__ == "__main__":
    unittest.main()
