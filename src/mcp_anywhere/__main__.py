"""
Main command-line entry point for MCP Anywhere.

This module acts as the main command-line entry point as specified in Phase 3
of the engineering documentation.
"""

import argparse
import asyncio
import sys
import shutil
from typing import Optional
from pathlib import Path

from mcp_anywhere.transport.http_server import run_http_server
from mcp_anywhere.transport.stdio_server import run_stdio_server
from mcp_anywhere.logging_config import configure_logging, get_logger
from mcp_anywhere.config import Config

# Configure logging before anything else
configure_logging(
    log_level=Config.LOG_LEVEL,
    log_format=Config.LOG_FORMAT,
    log_file=Config.LOG_FILE,
    json_logs=Config.LOG_JSON,
)

logger = get_logger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """
    Create and configure the argument parser for MCP Anywhere CLI.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="MCP Anywhere - Unified gateway for Model Context Protocol servers",
        prog="mcp-anywhere"
    )
    
    # Add subcommands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        required=True
    )
    
    # Serve subcommand
    serve_parser = subparsers.add_parser(
        "serve",
                    help="Start the MCP Anywhere server"
    )
    
    # Transport mode subcommands
    transport_subparsers = serve_parser.add_subparsers(
        dest="transport",
        help="Transport mode",
        required=True
    )
    
    # HTTP transport
    http_parser = transport_subparsers.add_parser(
        "http",
        help="Run as HTTP web server"
    )
    http_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address to bind to (default: 0.0.0.0)"
    )
    http_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to bind to (default: 8000)"
    )
    
    # STDIO transport
    stdio_parser = transport_subparsers.add_parser(
        "stdio",
        help="Run in STDIO mode with background web UI"
    )
    stdio_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address for background web UI (default: 0.0.0.0)"
    )
    stdio_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number for background web UI (default: 8000)"
    )
    
    # Reset subcommand
    reset_parser = subparsers.add_parser(
        "reset",
                    help="Reset MCP Anywhere data (clears database and keys)"
    )
    reset_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt"
    )
    
    return parser


def reset_data(confirm: bool = False) -> None:
    """
    Reset MCP Anywhere data by clearing the data directory.
    
    Args:
        confirm: Skip confirmation prompt if True
    """
    data_dir = Config.DATA_DIR
    
    if not data_dir.exists():
        print(f"Data directory {data_dir} does not exist. Nothing to reset.")
        return
    
    if not confirm:
        print(f"This will permanently delete all MCP Anywhere data in: {data_dir}")
        print("This includes:")
        print("  - Database (all servers, users, configurations)")
        print("  - OAuth keys and tokens")
        print("  - Any cached data")
        print()
        
        response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
        if response not in ("yes", "y"):
            print("Reset cancelled.")
            return
    
    try:
        # Remove the entire data directory
        if data_dir.exists():
            shutil.rmtree(data_dir)
            print(f"Successfully removed data directory: {data_dir}")
        
        # Recreate empty data directory
        data_dir.mkdir(exist_ok=True)
        print(f"Created fresh data directory: {data_dir}")
        
        print("\nMCP Anywhere data has been reset successfully!")
        print("Next startup will initialize with fresh database and new login credentials.")
        
    except Exception as e:
        print(f"Error during reset: {e}")
        sys.exit(1)


async def main() -> None:
    """
    Main entry point for MCP Anywhere application.
    
    Parses command-line arguments and calls the appropriate transport server
    function based on the chosen sub-command.
    """
    try:
        # Parse command-line arguments
        parser = create_parser()
        args = parser.parse_args()
        
        # Handle reset command (synchronous)
        if args.command == "reset":
            reset_data(confirm=args.confirm)
            return
        
        # Handle serve command (asynchronous)
        if args.command == "serve":
            # Extract common parameters
            host = args.host
            port = args.port
            
            # Route to appropriate transport server
            if args.transport == "http":
                logger.info(f"Starting MCP Anywhere in HTTP mode on {host}:{port}")
                await run_http_server(host=host, port=port)
                
            elif args.transport == "stdio":
                logger.info(f"Starting MCP Anywhere in STDIO mode with web UI on {host}:{port}")
                await run_stdio_server(host=host, port=port)
                
            else:
                # This should not be reachable due to argparse configuration
                raise ValueError(f"Invalid transport mode: {args.transport}")
        else:
            # This should not be reachable due to argparse configuration
            raise ValueError(f"Invalid command: {args.command}")
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        
    except Exception as e:
        logger.error(f"Failed to start MCP Anywhere: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())