#!/usr/bin/env python3
"""Main entry point for ChronoTask."""

import asyncio
import logging
import sys
import os
from pathlib import Path
import uvicorn
from concurrent.futures import ThreadPoolExecutor

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file) if settings.log_file else logging.NullHandler()
    ]
)

logger = logging.getLogger(__name__)


def run_http_server():
    """Run the HTTP API server."""
    logger.info(f"Starting HTTP server on {settings.api_host}:{settings.api_port}")
    
    uvicorn.run(
        "api.http_server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower()
    )


async def run_mcp_server():
    """Run the MCP server."""
    logger.info(f"Starting MCP server")
    
    from mcp.scheduler_server import main as mcp_main
    await mcp_main()


async def run_both_servers():
    """Run both HTTP and MCP servers concurrently."""
    # Run HTTP server in a thread
    with ThreadPoolExecutor() as executor:
        http_future = executor.submit(run_http_server)
        
        # Run MCP server in asyncio
        try:
            await run_mcp_server()
        except KeyboardInterrupt:
            logger.info("Shutting down servers...")
        finally:
            # HTTP server will shut down when the process exits
            pass


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ChronoTask Scheduler")
    parser.add_argument(
        "--mode",
        choices=["http", "mcp", "both"],
        default="http",
        help="Server mode to run (default: http)"
    )
    parser.add_argument(
        "--host",
        default=settings.api_host,
        help=f"HTTP server host (default: {settings.api_host})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.api_port,
        help=f"HTTP server port (default: {settings.api_port})"
    )
    
    args = parser.parse_args()
    
    # Update settings if provided
    if args.host:
        settings.api_host = args.host
    if args.port:
        settings.api_port = args.port
    
    # Database will be created in current directory
    
    try:
        if args.mode == "http":
            run_http_server()
        elif args.mode == "mcp":
            asyncio.run(run_mcp_server())
        else:  # both
            if settings.mcp_enabled:
                asyncio.run(run_both_servers())
            else:
                logger.warning("MCP is disabled in settings, running HTTP server only")
                run_http_server()
                
    except KeyboardInterrupt:
        logger.info("Shutting down ChronoTask...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()