import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock streamlit and supabase before importing database
sys.modules['streamlit'] = MagicMock()
sys.modules['supabase'] = MagicMock()

from database import get_distributor_list

class TestGetDistributorList(unittest.TestCase):
    def test_get_distributor_list_success(self):
        # Mock supabase client
        mock_supabase = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{'nama_distributor': 'Distributor A'}, {'nama_distributor': 'Distributor B'}]
        mock_supabase.table.return_value.select.return_value.execute.return_value = mock_res

        result = get_distributor_list(mock_supabase)

        self.assertEqual(result, ['Distributor A', 'Distributor B'])
        mock_supabase.table.assert_called_once_with("distributor_vault")
        mock_supabase.table().select.assert_called_once_with("nama_distributor")

    def test_get_distributor_list_empty(self):
        # Mock supabase client returning empty data
        mock_supabase = MagicMock()
        mock_res = MagicMock()
        mock_res.data = []
        mock_supabase.table.return_value.select.return_value.execute.return_value = mock_res

        result = get_distributor_list(mock_supabase)

        self.assertEqual(result, ["Belum ada data di Database"])

    def test_get_distributor_list_exception(self):
        # Mock supabase client raising an exception
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("Connection error")

        result = get_distributor_list(mock_supabase)

        self.assertEqual(result, ["Belum ada data di Database"])

    def test_get_distributor_list_none_client(self):
        # Test with None client
        result = get_distributor_list(None)

        self.assertEqual(result, ["Belum ada data di Database"])

if __name__ == '__main__':
    unittest.main()
