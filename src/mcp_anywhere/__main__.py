"""Main command-line entry point for MCP Anywhere.

This module acts as the main command-line entry point as specified in Phase 3
of the engineering documentation.
"""

import argparse
import asyncio
import shutil
import sys

from mcp_anywhere.config import Config
from mcp_anywhere.transport.http_server import run_http_server
from mcp_anywhere.transport.stdio_gateway import run_connect_gateway
from mcp_anywhere.transport.stdio_server import run_stdio_server


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for MCP Anywhere CLI.

    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="MCP Anywhere - Unified gateway for Model Context Protocol servers",
        prog="mcp-anywhere",
    )

    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # Serve command - starts management server with MCP transport options
    serve_parser = subparsers.add_parser(
        "serve", help="Start the MCP Anywhere server (management UI + MCP transport)"
    )

    serve_subparsers = serve_parser.add_subparsers(
        dest="transport", help="MCP transport mode for client connections", required=True
    )

    # HTTP transport - Management UI + MCP over HTTP
    http_parser = serve_subparsers.add_parser(
        "http", help="Run with HTTP transport (Web UI at /, MCP endpoint at /mcp with OAuth)"
    )
    http_parser.add_argument("--host", type=str, default="0.0.0.0")
    http_parser.add_argument("--port", type=int, default=8000)

    # STDIO transport - Management UI + MCP over STDIO
    stdio_parser = serve_subparsers.add_parser(
        "stdio", help="Run with STDIO transport (Web UI at /, MCP over stdio without OAuth)"
    )
    stdio_parser.add_argument("--host", type=str, default="0.0.0.0")
    stdio_parser.add_argument("--port", type=int, default=8000)

    # Connect command - for MCP clients
    connect_parser = subparsers.add_parser(
        "connect", help="Connect as MCP client via STDIO (lightweight mode)"
    )
    # No arguments needed - runs in stdio mode only

    # Reset subcommand
    reset_parser = subparsers.add_parser(
        "reset", help="Reset MCP Anywhere data (clears database and keys)"
    )
    reset_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")

    return parser


def reset_data(confirm: bool = False) -> None:
    """Reset MCP Anywhere data by clearing the data directory.

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

    except (OSError, PermissionError, FileNotFoundError) as e:
        print(f"Error during reset: {e}")
        sys.exit(1)


async def main() -> None:
    """Main entry point for MCP Anywhere application.

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
            if args.transport == "http":
                await run_http_server(host=args.host, port=args.port)

            elif args.transport == "stdio":
                await run_stdio_server(host=args.host, port=args.port)

        elif args.command == "connect":
            await run_connect_gateway()

        else:
            # This should not be reachable due to argparse configuration
            raise ValueError(f"Invalid command: {args.command}")

    except KeyboardInterrupt:
        # Silent exit for all modes
        pass

    except (ValueError, RuntimeError, ConnectionError) as e:
        # Only show errors for non-connect modes
        if args.command != "connect":
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
