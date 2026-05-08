import pytest
import pandas as pd
import io
import zipfile
from unittest.mock import patch, MagicMock
from data_processor import load_data

class MockUploadedFile(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name

def test_load_data_none():
    assert load_data(None) is None

def test_load_data_csv_tab_separated():
    csv_data = b"col1\tcol2\nval1\tval2\n"
    file = MockUploadedFile(csv_data, "test.csv")
    df = load_data(file)
    assert df is not None
    assert list(df.columns) == ["col1", "col2"]
    assert df.iloc[0]["col1"] == "val1"

def test_load_data_csv_comma_separated():
    csv_data = b"col1,col2\nval1,val2\n"
    file = MockUploadedFile(csv_data, "test.csv")
    df = load_data(file)
    assert df is not None
    assert list(df.columns) == ["col1", "col2"]
    assert df.iloc[0]["col1"] == "val1"

def test_load_data_xlsx():
    # Create an empty excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame({"col1": ["val1"], "col2": ["val2"]}).to_excel(writer, index=False)

    file = MockUploadedFile(output.getvalue(), "test.xlsx")
    df = load_data(file)
    assert df is not None
    assert list(df.columns) == ["col1", "col2"]
    assert df.iloc[0]["col1"] == "val1"

def test_load_data_zip_with_invt_master():
    csv_data = b"col1\tcol2\nval1\tval2\n"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr("some_folder/INVT_MASTER_2023.csv", csv_data)
        zip_file.writestr("other.csv", b"other1\tother2\n")

    file = MockUploadedFile(zip_buffer.getvalue(), "data.zip")
    df = load_data(file)
    assert df is not None
    assert list(df.columns) == ["col1", "col2"]

def test_load_data_zip_without_invt_master():
    csv_data = b"col1\tcol2\nval1\tval2\n"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr("random.csv", csv_data)
        zip_file.writestr("ignore.txt", b"text")

    file = MockUploadedFile(zip_buffer.getvalue(), "data.zip")
    df = load_data(file)
    assert df is not None
    assert list(df.columns) == ["col1", "col2"]

@patch('data_processor.st')
def test_load_data_exception(mock_st):
    file = MockUploadedFile(b"bad data", "test.csv")
    # Make pandas raise an exception when reading
    with patch('data_processor.pd.read_csv', side_effect=Exception("Read Error")):
        df = load_data(file)

    assert df is None
    mock_st.error.assert_called_once_with("Error reading file: Read Error")
