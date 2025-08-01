"""End-to-end test for server mounting and prefixed tool calls using production code paths."""

import asyncio
import unittest
import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List

from fastmcp import Client, FastMCP

from mcp_router.server import create_mcp_manager, MCPManager
from mcp_router.models import MCPServer
from mcp_router.middleware import ToolFilterMiddleware


class TestE2EServerMounting(unittest.TestCase):
    """End-to-end tests for server mounting using production code paths."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_servers = [
            MCPServer(
                id="server01",
                name="TestServer1",
                github_url="https://github.com/test/server1",
                runtime_type="docker",
                start_command="echo 'test1'",
                description="Test server 1",
                is_active=True,
            ),
            MCPServer(
                id="server02", 
                name="TestServer2",
                github_url="https://github.com/test/server2",
                runtime_type="docker",
                start_command="echo 'test2'",
                description="Test server 2",
                is_active=True,
            ),
        ]

    def _mock_flask_context(self, mock_app: MagicMock) -> None:
        """Helper to set up Flask app context mocking."""
        mock_app.app_context.return_value.__enter__ = MagicMock()
        mock_app.app_context.return_value.__exit__ = MagicMock()

    def _mock_empty_servers(self, mock_get_servers: MagicMock) -> None:
        """Helper to mock empty server list."""
        mock_get_servers.return_value = []

    def test_dynamic_server_manager_workflow(self) -> None:
        """Test the MCPManager workflow with working in-memory servers."""
        router = FastMCP("TestRouter")
        router.add_middleware(ToolFilterMiddleware())
        manager = MCPManager(router)
        test_server1 = FastMCP("WorkingServer1")
        
        @test_server1.tool()
        def test_tool1() -> str:
            """A test tool from server 1."""
            return "result from server 1"
        
        test_server2 = FastMCP("WorkingServer2")
        
        @test_server2.tool()
        def test_tool2() -> str:
            """A test tool from server 2."""
            return "result from server 2"
        
        router.mount(test_server1, prefix="server01", as_proxy=True)
        router.mount(test_server2, prefix="server02", as_proxy=True)
        client = Client(router)

        async def _run() -> Dict[str, str]:
            async with client:
                result1 = await client.call_tool("server01_test_tool1", {})
                result2 = await client.call_tool("server02_test_tool2", {})
                return {
                    "server1_result": result1.structured_content["result"],
                    "server2_result": result2.structured_content["result"],
                }

        results = asyncio.run(_run())
        self.assertEqual(results["server1_result"], "result from server 1")
        self.assertEqual(results["server2_result"], "result from server 2")



    @patch('mcp_router.models.get_active_servers')
    @patch('mcp_router.server.app')
    def test_prefixed_tool_calls_with_production_router(self, mock_app: MagicMock, mock_get_servers: MagicMock) -> None:
        """Test that prefixed tool calls work with production router code."""
        self._mock_empty_servers(mock_get_servers)
        self._mock_flask_context(mock_app)

        manager = asyncio.run(create_mcp_manager())
        router = manager.router
        calculator_server = FastMCP("CalculatorServer")
        
        @calculator_server.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b
        
        @calculator_server.tool()
        def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            return x * y
        
        weather_server = FastMCP("WeatherServer")
        
        @weather_server.tool()
        def get_weather(city: str) -> str:
            """Get weather for a city."""
            return f"Weather in {city}: Sunny, 72°F"
        
        @weather_server.tool()
        def get_forecast(city: str, days: int) -> str:
            """Get weather forecast."""
            return f"{days}-day forecast for {city}: Mostly sunny"
        
        calc_prefix = "calc1234"
        weather_prefix = "wthr5678"
        
        router.mount(calculator_server, prefix=calc_prefix, as_proxy=True)
        router.mount(weather_server, prefix=weather_prefix, as_proxy=True)
        client = Client(router)

        async def _run() -> Dict[str, Any]:
            async with client:
                calc_result1 = await client.call_tool(f"{calc_prefix}_add", {"a": 15, "b": 27})
                calc_result2 = await client.call_tool(f"{calc_prefix}_multiply", {"x": 6, "y": 9})
                weather_result1 = await client.call_tool(f"{weather_prefix}_get_weather", {"city": "New York"})
                weather_result2 = await client.call_tool(f"{weather_prefix}_get_forecast", {"city": "London", "days": 5})
                return {
                    "add_result": calc_result1.structured_content["result"],
                    "multiply_result": calc_result2.structured_content["result"], 
                    "weather_result": weather_result1.structured_content["result"],
                    "forecast_result": weather_result2.structured_content["result"],
                }

        results = asyncio.run(_run())
        
        self.assertEqual(results["add_result"], 42)
        self.assertEqual(results["multiply_result"], 54)
        self.assertEqual(results["weather_result"], "Weather in New York: Sunny, 72°F")
        self.assertEqual(results["forecast_result"], "5-day forecast for London: Mostly sunny")
        


        

if __name__ == "__main__":
    unittest.main() 