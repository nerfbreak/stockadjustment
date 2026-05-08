import pytest
from unittest.mock import Mock, patch
import database

class MockSupabaseTable:
    def __init__(self, data):
        self.data = data

    def select(self, *args, **kwargs):
        return self

    def execute(self):
        class Result:
            def __init__(self, data):
                self.data = data
        return Result(self.data)

class MockSupabase:
    def __init__(self, table_name, data):
        self.table_name = table_name
        self.data = data

    def table(self, name):
        if name == self.table_name:
            return MockSupabaseTable(self.data)
        return MockSupabaseTable([])

@pytest.fixture(autouse=True)
def clear_caches():
    database.get_distributor_list.clear()

def test_get_distributor_list():
    mock_db = MockSupabase("distributor_vault", [{"nama_distributor": "Distributor A"}, {"nama_distributor": "Distributor B"}])

    # Test valid
    result = database.get_distributor_list(mock_db)
    assert result == ["Distributor A", "Distributor B"]

    # Test empty
    mock_empty = MockSupabase("distributor_vault", [])
    database.get_distributor_list.clear() # clear cache
    result2 = database.get_distributor_list(mock_empty)
    assert result2 == ["Belum ada data di Database"]

    # Test None
    database.get_distributor_list.clear() # clear cache
    result3 = database.get_distributor_list(None)
    assert result3 == ["Belum ada data di Database"]
