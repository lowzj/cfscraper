import csv
from io import StringIO
from typing import AsyncGenerator, Dict, Any

import pytest

from app.utils.data_export import CSVExporter, ExportConfig


@pytest.fixture
def csv_exporter() -> CSVExporter:
    """Fixture for CSVExporter"""
    config = ExportConfig(csv_delimiter=",", csv_quote_char='"', csv_include_headers=True)
    return CSVExporter(config)

async def data_generator_dynamic_headers() -> AsyncGenerator[Dict[str, Any], None]:
    """Async generator for testing dynamic headers"""
    yield {"a": 1, "b": 2}
    yield {"a": 3, "b": 4, "c": 5}
    yield {"b": 6, "d": 7}

@pytest.mark.asyncio
async def test_csv_export_streaming_dynamic_headers(csv_exporter: CSVExporter):
    """Test CSV streaming export with dynamic headers"""
    output = StringIO()

    await csv_exporter.export_streaming(data_generator_dynamic_headers(), output)

    output.seek(0)
    result = output.read()

    # Verify headers
    expected_headers = "a,b,c,d\r\n"
    assert result.startswith(expected_headers)

    # Verify data
    reader = csv.DictReader(StringIO(result))
    rows = list(reader)

    assert len(rows) == 3
    assert rows[0] == {"a": "1", "b": "2", "c": "", "d": ""}
    assert rows[1] == {"a": "3", "b": "4", "c": "5", "d": ""}
    assert rows[2] == {"a": "", "b": "6", "c": "", "d": "7"}

async def data_generator_no_headers() -> AsyncGenerator[Dict[str, Any], None]:
    """Async generator that yields no data"""
    if False:
        yield {}

@pytest.mark.asyncio
async def test_csv_export_streaming_no_headers(csv_exporter: CSVExporter):
    """Test CSV streaming export with no headers"""
    output = StringIO()

    await csv_exporter.export_streaming(data_generator_no_headers(), output)

    output.seek(0)
    result = output.read()

    assert result == ""
