import io
import logging

import pytest
from mcp_router.server_manager import MCPServerManager


def _run_read_output(manager: MCPServerManager, text: str, stream_name: str = "STDERR"):
    """Utility to run _read_output_stream synchronously using StringIO"""
    stream = io.StringIO(text)
    manager._read_output_stream(stream, stream_name)


@pytest.mark.parametrize(
    "line,expected_level",
    [
        ("INFO: Starting STDIO transport\n", logging.INFO),
        ("WARNING: Using default config\n", logging.WARNING),
        ("ERROR: Something went wrong\n", logging.ERROR),
        ("DEBUG: internal detail\n", logging.DEBUG),
    ],
)
def test_log_level_detection(line, expected_level, caplog):
    """_read_output_stream should classify log levels based on message content, not stream."""
    manager = MCPServerManager()
    with caplog.at_level(logging.DEBUG):
        _run_read_output(manager, line, stream_name="STDERR")

    # Extract captured records for MCP Server logger
    records = [r for r in caplog.records if r.name == "mcp_router.server_manager" and "MCP Server:" in r.message]
    assert records, "No log records captured"

    # Use the first captured record to verify level
    record = records[0]
    assert record.levelno == expected_level, f"Expected level {expected_level} but got {record.levelno}"

    # Ensure the original line (trimmed) is present in the log message
    assert line.strip() in record.message 