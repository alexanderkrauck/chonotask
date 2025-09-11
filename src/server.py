#!/usr/bin/env python3
"""ChronoTask FastAPI + MCP Server using FastMCP."""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Query
from fastmcp import FastMCP
from pydantic import BaseModel
from models import Task, TaskType, TaskStatus, Schedule, ScheduleType
from database import db_manager
from scheduler.core import SchedulerManager
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global scheduler manager
scheduler_manager = None


# Pydantic models for request/response
class TaskCreate(BaseModel):
    name: str
    task_type: str
    config: Dict[str, Any]
    description: Optional[str] = None
    max_retries: int = 3
    retry_delay: int = 5


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    max_retries: Optional[int] = None
    retry_delay: Optional[int] = None


class ScheduleCreate(BaseModel):
    task_id: int
    schedule_type: str
    schedule_config: Dict[str, Any]
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    schedule_config: Optional[Dict[str, Any]] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global scheduler_manager
    
    # Startup
    logger.info("Starting ChronoTask server...")
    db_manager.initialize()
    scheduler_manager = SchedulerManager(db_manager)
    scheduler_manager.initialize()
    logger.info("ChronoTask server started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down ChronoTask server...")
    if scheduler_manager:
        scheduler_manager.shutdown()
    logger.info("ChronoTask server shut down")


# 1. Create normal FastAPI app
app = FastAPI(
    title="ChronoTask API",
    description="Task scheduling and automation service",
    version="1.0.0",
    lifespan=lifespan
)


# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "chronotask",
        "version": "1.0.0",
        "scheduler": scheduler_manager.get_scheduler_status() if scheduler_manager else None
    }


# Task endpoints
@app.post("/tasks", response_model=Dict[str, Any])
async def create_task(task: TaskCreate):
    """Create a new task."""
    try:
        with db_manager.get_session() as session:
            db_task = Task(
                name=task.name,
                description=task.description,
                task_type=TaskType(task.task_type),
                config=task.config,
                status=TaskStatus.ACTIVE,
                max_retries=task.max_retries,
                retry_delay=task.retry_delay
            )
            session.add(db_task)
            session.commit()
            session.refresh(db_task)
            return {
                "success": True,
                "task": db_task.to_dict(),
                "message": f"Task '{task.name}' created successfully"
            }
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks", response_model=Dict[str, Any])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    include_schedules: bool = Query(False, description="Include schedules")
):
    """List all tasks."""
    try:
        with db_manager.get_session() as session:
            query = session.query(Task)
            if status:
                query = query.filter(Task.status == TaskStatus(status))
            tasks = query.all()
            
            task_list = []
            for task in tasks:
                task_dict = task.to_dict()
                if include_schedules:
                    schedules = session.query(Schedule).filter_by(task_id=task.id).all()
                    task_dict["schedules"] = [s.to_dict() for s in schedules]
                task_list.append(task_dict)
            
            return {
                "success": True,
                "tasks": task_list,
                "count": len(task_list)
            }
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}", response_model=Dict[str, Any])
async def get_task(task_id: int):
    """Get a specific task."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            schedules = session.query(Schedule).filter_by(task_id=task.id).all()
            task_dict = task.to_dict()
            task_dict["schedules"] = [s.to_dict() for s in schedules]
            
            return {
                "success": True,
                "task": task_dict
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/tasks/{task_id}", response_model=Dict[str, Any])
async def update_task(task_id: int, update: TaskUpdate):
    """Update a task."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            if update.name is not None:
                task.name = update.name
            if update.description is not None:
                task.description = update.description
            if update.status is not None:
                task.status = TaskStatus(update.status)
            if update.config is not None:
                task.config = update.config
            if update.max_retries is not None:
                task.max_retries = update.max_retries
            if update.retry_delay is not None:
                task.retry_delay = update.retry_delay
            
            task.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(task)
            
            # Update scheduler if status changed
            if update.status is not None:
                scheduler_manager.update_task_status(task_id, TaskStatus(update.status))
            
            return {
                "success": True,
                "task": task.to_dict(),
                "message": f"Task '{task.name}' updated successfully"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/tasks/{task_id}", response_model=Dict[str, Any])
async def delete_task(task_id: int):
    """Delete a task."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            task_name = task.name
            
            # Remove from scheduler first
            scheduler_manager.remove_task_schedules(task_id)
            
            # Delete schedules
            session.query(Schedule).filter_by(task_id=task_id).delete()
            
            # Delete task
            session.delete(task)
            session.commit()
            
            return {
                "success": True,
                "message": f"Task '{task_name}' deleted successfully"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/{task_id}/execute", response_model=Dict[str, Any])
async def execute_task(task_id: int):
    """Execute a task immediately."""
    try:
        success = await scheduler_manager.execute_task_now(task_id)
        if success:
            return {
                "success": True,
                "message": f"Task {task_id} execution started"
            }
        else:
            raise HTTPException(status_code=500, detail=f"Failed to execute task {task_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Schedule endpoints
@app.post("/schedules", response_model=Dict[str, Any])
async def create_schedule(schedule: ScheduleCreate):
    """Create a schedule for a task."""
    try:
        db_schedule = scheduler_manager.create_schedule(
            task_id=schedule.task_id,
            schedule_type=ScheduleType(schedule.schedule_type),
            schedule_config=schedule.schedule_config
        )
        
        if db_schedule:
            # Set the enabled status if provided
            if hasattr(schedule, 'enabled'):
                with db_manager.get_session() as session:
                    db_schedule = session.query(Schedule).filter_by(id=db_schedule.id).first()
                    db_schedule.is_active = schedule.enabled
                    session.commit()
            with db_manager.get_session() as session:
                fresh_schedule = session.query(Schedule).filter_by(id=db_schedule.id).first()
                return {
                    "success": True,
                    "schedule": fresh_schedule.to_dict() if fresh_schedule else None,
                    "message": f"Schedule created for task {schedule.task_id}"
                }
        else:
            raise HTTPException(status_code=500, detail="Failed to create schedule")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schedules", response_model=Dict[str, Any])
async def list_schedules(
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status")
):
    """List all schedules."""
    try:
        with db_manager.get_session() as session:
            query = session.query(Schedule)
            if task_id is not None:
                query = query.filter_by(task_id=task_id)
            if enabled is not None:
                query = query.filter_by(enabled=enabled)
            
            schedules = query.all()
            schedule_list = []
            
            for schedule in schedules:
                schedule_dict = schedule.to_dict()
                # Include task info
                task = session.query(Task).filter_by(id=schedule.task_id).first()
                if task:
                    schedule_dict["task_name"] = task.name
                schedule_list.append(schedule_dict)
            
            return {
                "success": True,
                "schedules": schedule_list,
                "count": len(schedule_list)
            }
    except Exception as e:
        logger.error(f"Error listing schedules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schedules/{schedule_id}", response_model=Dict[str, Any])
async def get_schedule(schedule_id: int):
    """Get a specific schedule."""
    try:
        with db_manager.get_session() as session:
            schedule = session.query(Schedule).filter_by(id=schedule_id).first()
            if not schedule:
                raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
            
            schedule_dict = schedule.to_dict()
            task = session.query(Task).filter_by(id=schedule.task_id).first()
            if task:
                schedule_dict["task_name"] = task.name
            
            return {
                "success": True,
                "schedule": schedule_dict
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/schedules/{schedule_id}", response_model=Dict[str, Any])
async def update_schedule(schedule_id: int, update: ScheduleUpdate):
    """Update a schedule."""
    try:
        with db_manager.get_session() as session:
            schedule = session.query(Schedule).filter_by(id=schedule_id).first()
            if not schedule:
                raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
            
            if update.enabled is not None:
                schedule.enabled = update.enabled
            if update.schedule_config is not None:
                schedule.schedule_config = update.schedule_config
            
            schedule.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(schedule)
            
            # Update scheduler
            if update.enabled is not None:
                if update.enabled:
                    scheduler_manager.enable_schedule(schedule_id)
                else:
                    scheduler_manager.disable_schedule(schedule_id)
            
            return {
                "success": True,
                "schedule": schedule.to_dict(),
                "message": f"Schedule {schedule_id} updated successfully"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/schedules/{schedule_id}", response_model=Dict[str, Any])
async def delete_schedule(schedule_id: int):
    """Delete a schedule."""
    try:
        with db_manager.get_session() as session:
            schedule = session.query(Schedule).filter_by(id=schedule_id).first()
            if not schedule:
                raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
            
            # Remove from scheduler
            scheduler_manager.remove_schedule(schedule_id)
            
            # Delete from database
            session.delete(schedule)
            session.commit()
            
            return {
                "success": True,
                "message": f"Schedule {schedule_id} deleted successfully"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Status endpoint
@app.get("/status", response_model=Dict[str, Any])
async def get_status():
    """Get scheduler status."""
    try:
        status = scheduler_manager.get_scheduler_status()
        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Task history endpoint
@app.get("/tasks/{task_id}/history", response_model=Dict[str, Any])
async def get_task_history(task_id: int, limit: int = Query(10, description="Max entries")):
    """Get task execution history."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            return {
                "success": True,
                "task_id": task_id,
                "task_name": task.name,
                "history": {
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                    "run_count": task.run_count,
                    "success_count": task.success_count,
                    "failure_count": task.failure_count
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 2. Convert to MCP
logger.info("Converting FastAPI app to MCP...")
mcp = FastMCP.from_fastapi(app, name="ChronoTask MCP")

# 3. Create MCP's ASGI app - try with SSE transport for Claude MCP compatibility
mcp_app = mcp.http_app(path='/mcp')


@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    """Combined lifespan for both ChronoTask and MCP."""
    # Start our database and scheduler services
    global scheduler_manager
    logger.info("Starting ChronoTask server...")
    db_manager.initialize()
    scheduler_manager = SchedulerManager(db_manager)
    scheduler_manager.initialize()
    logger.info("ChronoTask server started successfully")
    
    # Start MCP services
    async with mcp_app.lifespan(app):
        yield
    
    # Shutdown
    logger.info("Shutting down ChronoTask server...")
    if scheduler_manager:
        scheduler_manager.shutdown()
    logger.info("ChronoTask server shut down")


# 4. Create the final app with combined lifespan
final_app = FastAPI(
    title="ChronoTask Service",
    description="Task scheduling with both HTTP API and MCP support",
    version="1.0.0",
    lifespan=combined_lifespan
)

# Mount the original API
final_app.mount("/api/v1", app)

# Mount the MCP app
final_app.mount("/llm", mcp_app)

# Add a root endpoint
@final_app.get("/")
async def root():
    """Root endpoint showing available APIs."""
    return {
        "service": "ChronoTask",
        "version": "1.0.0",
        "apis": {
            "http": "/api/v1",
            "mcp": "/llm/mcp",
            "health": "/api/v1/health",
            "docs": "/api/v1/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        final_app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower()
    )