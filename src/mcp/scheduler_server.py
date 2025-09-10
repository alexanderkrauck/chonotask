"""MCP server implementation for ChronoTask scheduler."""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.mcp_protocol import MCPServer
from database import db_manager
from scheduler import SchedulerManager

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Initializing ChronoTask MCP server...")
    
    # Initialize database
    db_manager.initialize()
    
    # Initialize scheduler
    scheduler = SchedulerManager(db_manager)
    scheduler.initialize()
    
    # Create and run MCP server
    server = MCPServer("chronotask-scheduler")
    
    logger.info("MCP server ready, listening on stdio")
    await server.run_stdio()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP server shutting down")