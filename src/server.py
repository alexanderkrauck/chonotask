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
from models import Task
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
    description: Optional[str] = None
    status_category: Optional[str] = "open"
    status_text: Optional[str] = None
    completion_criteria: Optional[str] = None  # JSON string
    execution_config: Optional[str] = None     # JSON string
    schedule_config: Optional[str] = None      # JSON string
    schedule_enabled: bool = False
    custom_fields: Optional[str] = None        # JSON string


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status_category: Optional[str] = None
    status_text: Optional[str] = None
    completion_criteria: Optional[str] = None  # JSON string
    execution_config: Optional[str] = None     # JSON string
    schedule_config: Optional[str] = None      # JSON string
    schedule_enabled: Optional[bool] = None
    custom_fields: Optional[str] = None        # JSON string


class TaskScheduleUpdate(BaseModel):
    schedule_config: str  # JSON string
    schedule_enabled: bool = True


# 1. Create normal FastAPI app (for mounting)
app = FastAPI(
    title="ChronoTask API",
    description="Task scheduling and automation service",
    version="1.0.0"
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
    """
    Create a new task.

    **Parameters:**
    - name (str, required): The name of the task
    - task_type (str, required): The type of task (e.g., 'todo', 'http', 'bash')
    - description (str, optional): Description of the task
    - status_category (str, optional): Status category ('open', 'in_progress', 'waiting', 'completed', 'cancelled')
    - status_text (str, optional): Custom status text
    - completion_criteria (str, optional): JSON string for completion criteria
    - execution_config (str, optional): JSON string for execution configuration
    - schedule_config (str, optional): JSON string for scheduling configuration
    - schedule_enabled (bool, optional): Whether scheduling is enabled
    - custom_fields (str, optional): JSON string for arbitrary custom fields

    **Responses:**
    - 200: Successful response with task details
    - 400: Invalid JSON in configurations
    - 500: Internal server error
    """
    try:
        import json

        # Parse JSON fields
        def parse_json_field(field_value, field_name):
            if field_value:
                try:
                    return json.loads(field_value)
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON in {field_name}")
            return None

        completion_criteria = parse_json_field(task.completion_criteria, "completion_criteria")
        execution_config = parse_json_field(task.execution_config, "execution_config")
        schedule_config = parse_json_field(task.schedule_config, "schedule_config")
        custom_fields = parse_json_field(task.custom_fields, "custom_fields")

        with db_manager.get_session() as session:
            db_task = Task(
                name=task.name,
                description=task.description,
                task_type=task.task_type,
                status_category=task.status_category,
                status_text=task.status_text,
                completion_criteria=completion_criteria,
                execution_config=execution_config,
                schedule_config=schedule_config,
                schedule_enabled=task.schedule_enabled,
                custom_fields=custom_fields
            )
            session.add(db_task)
            session.commit()
            session.refresh(db_task)

            # Add to scheduler if scheduling is enabled
            if task.schedule_enabled and schedule_config and scheduler_manager:
                scheduler_manager.enable_task_schedule(db_task.id, schedule_config)

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
    status: Optional[str] = Query(None, description="Filter by status category"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    scheduled_only: bool = Query(False, description="Only show scheduled tasks")
):
    """
    List all tasks.

    **Query Parameters:**
    - status (str, optional): Filter by status category ('open', 'in_progress', 'waiting', 'completed', 'cancelled')
    - task_type (str, optional): Filter by task type ('todo', 'http', 'bash')
    - scheduled_only (bool, optional): Only show tasks with scheduling enabled

    **Responses:**
    - 200: Successful response with list of tasks and count
    - 500: Internal server error
    """
    try:
        with db_manager.get_session() as session:
            query = session.query(Task)

            if status:
                query = query.filter(Task.status_category == status)
            if task_type:
                query = query.filter(Task.task_type == task_type)
            if scheduled_only:
                query = query.filter(Task.schedule_enabled == True)

            tasks = query.all()
            task_list = [task.to_dict() for task in tasks]

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
    """
    Get a specific task.

    **Path Parameters:**
    - task_id (int, required): The ID of the task to retrieve

    **Responses:**
    - 200: Successful response with task details
    - 404: Task not found
    - 500: Internal server error
    """
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            return {
                "success": True,
                "task": task.to_dict()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/tasks/{task_id}", response_model=Dict[str, Any])
async def update_task(task_id: int, update: TaskUpdate):
    """
    Update a task.

    **Path Parameters:**
    - task_id (int, required): The ID of the task to update

    **Body Parameters (TaskUpdate):**
    - name (str, optional): New name for the task
    - description (str, optional): New description
    - status_category (str, optional): New status category ('open', 'in_progress', 'waiting', 'completed', 'cancelled')
    - status_text (str, optional): Custom status text
    - completion_criteria (str, optional): JSON string for completion criteria
    - execution_config (str, optional): JSON string for execution configuration
    - schedule_config (str, optional): JSON string for scheduling configuration
    - schedule_enabled (bool, optional): Whether scheduling is enabled
    - custom_fields (str, optional): JSON string for arbitrary custom fields

    **Responses:**
    - 200: Successful response with updated task details
    - 400: Invalid JSON in configurations
    - 404: Task not found
    - 500: Internal server error
    """
    try:
        import json

        # Parse JSON fields
        def parse_json_field(field_value, field_name):
            if field_value is not None:
                try:
                    return json.loads(field_value)
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON in {field_name}")
            return None

        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            # Track if schedule settings changed
            schedule_changed = False
            old_schedule_enabled = task.schedule_enabled

            # Update fields
            if update.name is not None:
                task.name = update.name
            if update.description is not None:
                task.description = update.description
            if update.status_category is not None:
                task.status_category = update.status_category
            if update.status_text is not None:
                task.status_text = update.status_text
            if update.completion_criteria is not None:
                task.completion_criteria = parse_json_field(update.completion_criteria, "completion_criteria")
            if update.execution_config is not None:
                task.execution_config = parse_json_field(update.execution_config, "execution_config")
            if update.schedule_config is not None:
                task.schedule_config = parse_json_field(update.schedule_config, "schedule_config")
                schedule_changed = True
            if update.schedule_enabled is not None:
                task.schedule_enabled = update.schedule_enabled
                schedule_changed = True
            if update.custom_fields is not None:
                task.custom_fields = parse_json_field(update.custom_fields, "custom_fields")

            task.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(task)

            # Update scheduler if schedule settings changed
            if schedule_changed and scheduler_manager:
                if task.schedule_enabled and task.schedule_config:
                    scheduler_manager.enable_task_schedule(task_id, task.schedule_config)
                elif old_schedule_enabled and not task.schedule_enabled:
                    scheduler_manager.disable_task_schedule(task_id)

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
            if scheduler_manager:
                scheduler_manager.disable_task_schedule(task_id)
            
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


# Task scheduling endpoints
@app.post("/tasks/{task_id}/schedule", response_model=Dict[str, Any])
async def enable_task_schedule(task_id: int, schedule_update: TaskScheduleUpdate):
    """
    Enable scheduling for a task.

    **Parameters:**
    - task_id (int, required): The ID of the task to schedule
    - schedule_config (str, required): JSON string with schedule configuration
      - For 'once': '{"type": "once", "datetime": "2025-01-15T14:30:00"}'
      - For 'cron': '{"type": "cron", "expression": "0 14 * * *"}'
      - For 'interval': '{"type": "interval", "seconds": 3600}'
    - schedule_enabled (bool, optional): Whether schedule is active (default: true)

    **Examples:**
    - One-time execution: '{"type": "once", "datetime": "2025-01-15T09:00:00"}'
    - Daily at 9am: '{"type": "cron", "expression": "0 9 * * *"}'
    - Every hour: '{"type": "interval", "seconds": 3600}'

    **Responses:**
    - 200: Successful response with task details
    - 400: Invalid JSON in schedule_config
    - 404: Task not found
    - 500: Internal server error
    """
    try:
        import json
        try:
            config_dict = json.loads(schedule_update.schedule_config)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in schedule_config")

        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            # Update task with schedule configuration
            task.schedule_config = config_dict
            task.schedule_enabled = schedule_update.schedule_enabled

            session.commit()

            # Add to scheduler if enabled
            if schedule_update.schedule_enabled and scheduler_manager:
                scheduler_manager.enable_task_schedule(task_id, config_dict)

            return {
                "success": True,
                "task": task.to_dict(),
                "message": f"Scheduling {'enabled' if schedule_update.schedule_enabled else 'disabled'} for task '{task.name}'"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/tasks/{task_id}/schedule", response_model=Dict[str, Any])
async def disable_task_schedule(task_id: int):
    """Disable scheduling for a task."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            # Disable scheduling
            task.schedule_enabled = False
            session.commit()

            # Remove from scheduler
            if scheduler_manager:
                scheduler_manager.disable_task_schedule(task_id)

            return {
                "success": True,
                "task": task.to_dict(),
                "message": f"Scheduling disabled for task '{task.name}'"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling task schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/{task_id}/complete", response_model=Dict[str, Any])
async def complete_task(task_id: int):
    """Mark a task as completed."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            task.status_category = 'completed'
            task.status_text = 'manually completed'
            session.commit()

            return {
                "success": True,
                "task": task.to_dict(),
                "message": f"Task '{task.name}' marked as completed"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/completion-criteria/evaluate", response_model=Dict[str, Any])
async def evaluate_completion_criteria():
    """Evaluate completion criteria for all tasks and update their status."""
    try:
        if scheduler_manager:
            scheduler_manager.evaluate_all_completion_criteria()

        return {
            "success": True,
            "message": "Completion criteria evaluation completed"
        }
    except Exception as e:
        logger.error(f"Error evaluating completion criteria: {e}")
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


# Task status endpoint
@app.get("/tasks/{task_id}/status", response_model=Dict[str, Any])
async def get_task_status(task_id: int):
    """Get task status and scheduling information."""
    try:
        with db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            # Get next run time from scheduler if scheduled
            next_run = None
            if task.schedule_enabled and scheduler_manager:
                job_id = f"task_{task_id}"
                job = scheduler_manager.scheduler.get_job(job_id) if scheduler_manager.scheduler else None
                if job and job.next_run_time:
                    next_run = job.next_run_time.isoformat()

            return {
                "success": True,
                "task_id": task_id,
                "task_name": task.name,
                "status": {
                    "status_category": task.status_category,
                    "status_text": task.status_text,
                    "is_scheduled": task.schedule_enabled,
                    "schedule_config": task.schedule_config,
                    "next_run": next_run,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "updated_at": task.updated_at.isoformat() if task.updated_at else None
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 2. Convert to MCP
logger.info("Converting FastAPI app to MCP...")
mcp = FastMCP.from_fastapi(app, name="ChronoTask MCP")

# 3. Create MCP's ASGI app
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