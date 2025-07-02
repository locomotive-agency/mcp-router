"""Test log deduplication functionality"""
import pytest
from unittest.mock import Mock, patch
from mcp_router.server_manager import MCPServerManager


def test_get_logs_with_from_index():
    """Test that get_logs correctly returns only new logs when from_index is provided"""
    # Create a mock Flask app
    app = Mock()
    
    # Create server manager
    manager = MCPServerManager(app)
    
    # Mock process
    manager.process = Mock()
    manager.process.pid = 12345
    
    # Add some test logs to the buffer
    test_logs = [
        "[2025-01-01 12:00:00] [STDERR] Log line 1",
        "[2025-01-01 12:00:01] [STDERR] Log line 2",
        "[2025-01-01 12:00:02] [STDERR] Log line 3",
        "[2025-01-01 12:00:03] [STDERR] Log line 4",
        "[2025-01-01 12:00:04] [STDERR] Log line 5"
    ]
    
    manager.log_buffer.extend(test_logs)
    
    # Test 1: Get all logs (no from_index)
    all_logs = manager.get_logs(12345, lines=50)
    assert len(all_logs) == 5
    assert all_logs == test_logs
    
    # Test 2: Get logs from index 2 (should return logs 3, 4, 5)
    new_logs = manager.get_logs(12345, lines=50, from_index=2)
    assert len(new_logs) == 2
    assert new_logs == test_logs[3:]
    
    # Test 3: Get logs from index 4 (no new logs)
    empty_logs = manager.get_logs(12345, lines=50, from_index=4)
    assert len(empty_logs) == 0
    
    # Test 4: Get logs from index beyond buffer size
    beyond_logs = manager.get_logs(12345, lines=50, from_index=10)
    assert len(beyond_logs) == 0
    
    # Test 5: Wrong PID should return empty
    wrong_pid_logs = manager.get_logs(99999, lines=50)
    assert len(wrong_pid_logs) == 0


def test_log_buffer_circular_behavior():
    """Test that log buffer maintains maxlen behavior"""
    app = Mock()
    manager = MCPServerManager(app)
    
    # Mock process
    manager.process = Mock()
    manager.process.pid = 12345
    
    # Add more logs than the buffer can hold
    for i in range(1100):  # Buffer maxlen is 1000
        manager.log_buffer.append(f"[2025-01-01 12:00:00] [STDERR] Log line {i}")
    
    # Should only have last 1000 logs
    assert len(manager.log_buffer) == 1000
    assert manager.log_buffer[0] == "[2025-01-01 12:00:00] [STDERR] Log line 100"
    assert manager.log_buffer[-1] == "[2025-01-01 12:00:00] [STDERR] Log line 1099" 