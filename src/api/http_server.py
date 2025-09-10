"""FastAPI HTTP server setup."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from config import settings
from database import db_manager
from scheduler import SchedulerManager

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global scheduler_manager
    
    # Startup
    logger.info("Starting ChronoTask server...")
    
    # Initialize database
    db_manager.initialize()
    
    # Initialize scheduler
    scheduler_manager = SchedulerManager(db_manager)
    scheduler_manager.initialize()
    
    logger.info("ChronoTask server started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down ChronoTask server...")
    
    if scheduler_manager:
        scheduler_manager.shutdown()
    
    db_manager.close()
    
    logger.info("ChronoTask server shut down")


# Create FastAPI app
app = FastAPI(
    title="ChronoTask",
    description="A lightweight, reliable task scheduler with Docker support",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from .endpoints import router
from .mcp_endpoints import router as mcp_router

app.include_router(router, prefix="/api/v1")
app.include_router(mcp_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "ChronoTask",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    global scheduler_manager
    
    scheduler_status = scheduler_manager.get_scheduler_status() if scheduler_manager else {"running": False}
    
    return {
        "status": "healthy",
        "scheduler": scheduler_status
    }


# get_scheduler function moved to endpoints.py to avoid circular import