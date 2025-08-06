"""
Test the stdio transport server functionality.

This module tests the stdio transport server as specified in Phase 3
of the engineering documentation.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.applications import Starlette

from mcp_anywhere.transport.stdio_server import run_stdio_server


@pytest.mark.asyncio
async def test_run_stdio_server_creates_app_and_tasks():
    """
    Test that run_stdio_server creates the Starlette app and sets up both 
    web UI and stdio tasks correctly.
    """
    # Mock dependencies
    mock_app = Mock(spec=Starlette)
    mock_app.state = Mock()
    mock_app.router = Mock()
    mock_app.router.lifespan_context = AsyncMock()
    mock_mcp_manager = Mock()
    mock_mcp_manager.router = Mock()
    mock_mcp_manager.router.run = AsyncMock()
    mock_app.state.mcp_manager = mock_mcp_manager
    
    mock_server = Mock()
    mock_server.serve = AsyncMock()
    
    with patch('mcp_anywhere.transport.stdio_server.create_app', return_value=mock_app) as mock_create_app, \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Config') as mock_config, \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Server', return_value=mock_server) as mock_server_class, \
         patch('asyncio.create_task') as mock_create_task, \
         patch('asyncio.gather', new_callable=AsyncMock) as mock_gather:
        
        # Setup mock tasks
        mock_web_task = AsyncMock()
        mock_stdio_task = AsyncMock()
        mock_create_task.side_effect = [mock_web_task, mock_stdio_task]
        
        # Call the function
        await run_stdio_server("127.0.0.1", 8001)
        
        # Verify app creation
        mock_create_app.assert_called_once()
        
        # Verify uvicorn configuration
        mock_config.assert_called_once_with(
            mock_app, 
            host="127.0.0.1", 
            port=8001, 
            log_level="info"
        )
        
        # Verify server creation
        mock_server_class.assert_called_once_with(mock_config.return_value)
        
        # Verify task creation
        assert mock_create_task.call_count == 2
        
        # Check that create_task was called with coroutines from the right methods
        calls = mock_create_task.call_args_list
        
        # First call should be for server.serve()
        assert len(calls[0][0]) == 1  # One positional argument
        assert hasattr(calls[0][0][0], '__await__')  # Should be a coroutine
        
        # Second call should be for router.run()
        assert len(calls[1][0]) == 1  # One positional argument  
        assert hasattr(calls[1][0][0], '__await__')  # Should be a coroutine
        
        # Verify tasks are gathered
        mock_gather.assert_called_once_with(mock_web_task, mock_stdio_task)


@pytest.mark.asyncio  
async def test_run_stdio_server_uses_correct_defaults():
    """
    Test that run_stdio_server uses correct default parameters.
    """
    mock_app = Mock(spec=Starlette)
    mock_app.state = Mock()
    mock_app.router = Mock()
    mock_app.router.lifespan_context = AsyncMock()
    mock_mcp_manager = Mock()
    mock_mcp_manager.router = Mock()
    mock_mcp_manager.router.run = AsyncMock()
    mock_app.state.mcp_manager = mock_mcp_manager
    
    mock_server = Mock()
    mock_server.serve = AsyncMock()
    
    with patch('mcp_anywhere.transport.stdio_server.create_app', return_value=mock_app), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Config') as mock_config, \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Server', return_value=mock_server), \
         patch('asyncio.create_task'), \
         patch('asyncio.gather', new_callable=AsyncMock):
        
        # Call with defaults
        await run_stdio_server()
        
        # Verify default parameters used
        mock_config.assert_called_once_with(
            mock_app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )


@pytest.mark.asyncio
async def test_run_stdio_server_handles_mcp_manager_missing():
    """
    Test that run_stdio_server handles cases where mcp_manager is not available.
    """
    # Mock app without mcp_manager
    mock_app = Mock(spec=Starlette)
    mock_app.state = Mock()
    mock_app.state.mcp_manager = None
    
    mock_server = Mock()
    mock_server.serve = AsyncMock()
    
    with patch('mcp_anywhere.transport.stdio_server.create_app', return_value=mock_app), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Config'), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Server', return_value=mock_server), \
         patch('asyncio.create_task') as mock_create_task, \
         patch('asyncio.gather') as mock_gather:
        
        with pytest.raises(AttributeError):
            await run_stdio_server()


@pytest.mark.asyncio
async def test_run_stdio_server_task_cancellation():
    """
    Test that run_stdio_server properly handles task cancellation.
    """
    mock_app = Mock(spec=Starlette)
    mock_app.state = Mock()
    mock_mcp_manager = Mock()
    mock_mcp_manager.router = Mock()
    mock_mcp_manager.router.run = AsyncMock(side_effect=asyncio.CancelledError)
    mock_app.state.mcp_manager = mock_mcp_manager
    
    mock_server = Mock()
    mock_server.serve = AsyncMock()
    
    with patch('mcp_anywhere.transport.stdio_server.create_app', return_value=mock_app), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Config'), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Server', return_value=mock_server), \
         patch('asyncio.create_task') as mock_create_task, \
         patch('asyncio.gather', new_callable=AsyncMock, side_effect=asyncio.CancelledError) as mock_gather:
        
        # Should propagate CancelledError
        with pytest.raises(asyncio.CancelledError):
            await run_stdio_server()


@pytest.mark.asyncio
async def test_run_stdio_server_concurrent_execution():
    """
    Test that both web UI and stdio tasks run concurrently.
    """
    mock_app = Mock(spec=Starlette)
    mock_app.state = Mock()
    mock_mcp_manager = Mock()
    mock_mcp_manager.router = Mock()
    
    # Track execution order
    execution_order = []
    
    async def mock_web_serve():
        execution_order.append("web_start")
        await asyncio.sleep(0.1)  # Simulate work
        execution_order.append("web_end")
    
    async def mock_stdio_run(transport):
        execution_order.append("stdio_start")
        await asyncio.sleep(0.05)  # Simulate work
        execution_order.append("stdio_end")
        
    mock_mcp_manager.router.run = mock_stdio_run
    mock_app.state.mcp_manager = mock_mcp_manager
    
    mock_server = Mock()
    mock_server.serve = mock_web_serve
    
    with patch('mcp_anywhere.transport.stdio_server.create_app', return_value=mock_app), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Config'), \
         patch('mcp_anywhere.transport.stdio_server.uvicorn.Server', return_value=mock_server):
        
        # Run the function
        await run_stdio_server()
        
        # Verify both tasks started and completed
        assert "web_start" in execution_order
        assert "stdio_start" in execution_order
        assert "web_end" in execution_order
        assert "stdio_end" in execution_order
        
        # Verify they ran concurrently (stdio should finish first due to shorter sleep)
        assert execution_order.index("stdio_end") < execution_order.index("web_end")