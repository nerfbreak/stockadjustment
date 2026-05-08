import pytest
import pandas as pd
import zipfile
import io
from unittest.mock import MagicMock, patch
from data_processor import load_data

def test_load_data_none():
    assert load_data(None) is None

def test_load_data_csv_tab_separated():
    content = "col1\tcol2\nval1\tval2"
    file_obj = io.BytesIO(content.encode('utf-8'))
    file_obj.name = "test.csv"

    df = load_data(file_obj)

    assert df is not None
    assert df.shape == (1, 2)
    assert list(df.columns) == ["col1", "col2"]
    assert df.iloc[0]["col1"] == "val1"

def test_load_data_csv_comma_separated():
    # If the tab separation results in 1 column, it falls back to comma
    content = "col1,col2\nval1,val2"
    file_obj = io.BytesIO(content.encode('utf-8'))
    file_obj.name = "test.csv"

    df = load_data(file_obj)

    assert df is not None
    assert df.shape == (1, 2)
    assert list(df.columns) == ["col1", "col2"]
    assert df.iloc[0]["col1"] == "val1"

@patch('data_processor.pd.read_excel')
def test_load_data_excel(mock_read_excel):
    mock_df = pd.DataFrame({"col": ["val"]})
    mock_read_excel.return_value = mock_df

    file_obj = MagicMock()
    file_obj.name = "test.xlsx"

    df = load_data(file_obj)

    assert df is not None
    assert df.equals(mock_df)
    mock_read_excel.assert_called_once_with(file_obj, dtype=str)

@patch('data_processor.pd.read_excel')
def test_load_data_xls(mock_read_excel):
    mock_df = pd.DataFrame({"col": ["val"]})
    mock_read_excel.return_value = mock_df

    file_obj = MagicMock()
    file_obj.name = "test.xls"

    df = load_data(file_obj)

    assert df is not None
    assert df.equals(mock_df)
    mock_read_excel.assert_called_once_with(file_obj, dtype=str)

def test_load_data_zip_invt_master():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("INVT_MASTER_2023.csv", "col1\tcol2\nval1\tval2")
        zf.writestr("other.csv", "other1\tother2\nval1\tval2")

    zip_buffer.seek(0)
    zip_buffer.name = "test.zip"

    df = load_data(zip_buffer)

    assert df is not None
    assert df.shape == (1, 2)
    assert list(df.columns) == ["col1", "col2"]

def test_load_data_zip_fallback_csv():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("some_data.csv", "colA\tcolB\nvalA\tvalB")
        zf.writestr("readme.txt", "hello")

    zip_buffer.seek(0)
    zip_buffer.name = "test.zip"

    df = load_data(zip_buffer)

    assert df is not None
    assert df.shape == (1, 2)
    assert list(df.columns) == ["colA", "colB"]

@patch('data_processor.pd.read_csv')
@patch('data_processor.st.error')
def test_load_data_exception(mock_st_error, mock_read_csv):
    mock_read_csv.side_effect = Exception("Test Error")

    file_obj = io.BytesIO(b"data")
    file_obj.name = "test.csv"

    df = load_data(file_obj)

    assert df is None
    mock_st_error.assert_called_once()
    assert "Test Error" in mock_st_error.call_args[0][0]
