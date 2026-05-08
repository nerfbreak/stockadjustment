import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock modules
sys.modules['streamlit'] = MagicMock()
sys.modules['supabase'] = MagicMock()
mock_bcrypt = MagicMock()
sys.modules['bcrypt'] = mock_bcrypt

import migrate_passwords

class TestMigration(unittest.TestCase):
    def setUp(self):
        mock_bcrypt.reset_mock()
        mock_bcrypt.gensalt.return_value = b"salt"
        mock_bcrypt.hashpw.side_effect = lambda p, s: p + s # dummy hash logic

    @patch('database.init_supabase')
    def test_migrate_passwords(self, mock_init):
        mock_supabase = MagicMock()
        mock_init.return_value = mock_supabase

        # Simulate users in DB
        mock_supabase.table.return_value.select.return_value.execute.return_value.data = [
            {"username": "user1", "password": "plaintext123"}, # Needs migration
            {"username": "user2", "password": "$2b$alreadyhashed"} # Should be skipped
        ]

        migrate_passwords.migrate_passwords()

        # Verify update was called for user1 but not user2
        mock_supabase.table.return_value.update.assert_called_once_with({"password": "plaintext123salt"})
        mock_supabase.table.return_value.update.return_value.eq.assert_called_once_with("username", "user1")

if __name__ == "__main__":
    unittest.main()
