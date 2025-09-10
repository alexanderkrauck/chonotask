"""API endpoints for task and schedule management."""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from database import get_db
from models import Task, TaskType, TaskStatus, Schedule, ScheduleType, ExecutionHistory
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_scheduler():
    """Get scheduler manager instance."""
    # Import here to avoid circular import
    from api.http_server import scheduler_manager
    if not scheduler_manager:
        raise RuntimeError("Scheduler not initialized")
    return scheduler_manager


# Pydantic models for request/response
class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    task_type: TaskType
    config: Dict[str, Any]
    max_retries: int = Field(3, ge=0, le=10)
    retry_delay: int = Field(5, ge=1, le=300)
    status: TaskStatus = TaskStatus.ACTIVE


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    config: Optional[Dict[str, Any]] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    retry_delay: Optional[int] = Field(None, ge=1, le=300)
    status: Optional[TaskStatus] = None


class ScheduleCreate(BaseModel):
    task_id: int
    schedule_type: ScheduleType
    schedule_config: Dict[str, Any]
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    schedule_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


# Task endpoints
@router.post("/tasks", status_code=201)
async def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task."""
    db_task = Task(
        name=task.name,
        description=task.description,
        task_type=task.task_type,
        config=task.config,
        max_retries=task.max_retries,
        retry_delay=task.retry_delay,
        status=task.status
    )
    
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    logger.info(f"Created task '{db_task.name}' (ID: {db_task.id})")
    return db_task.to_dict()


@router.get("/tasks")
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[TaskStatus] = None,
    task_type: Optional[TaskType] = None,
    db: Session = Depends(get_db)
):
    """List all tasks with optional filtering."""
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
    if task_type:
        query = query.filter(Task.task_type == task_type)
    
    total = query.count()
    tasks = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "tasks": [task.to_dict() for task in tasks]
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get a specific task by ID."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task.to_dict()


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: Session = Depends(get_db)
):
    """Update a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update fields
    if task_update.name is not None:
        task.name = task_update.name
    if task_update.description is not None:
        task.description = task_update.description
    if task_update.config is not None:
        task.config = task_update.config
    if task_update.max_retries is not None:
        task.max_retries = task_update.max_retries
    if task_update.retry_delay is not None:
        task.retry_delay = task_update.retry_delay
    if task_update.status is not None:
        task.status = task_update.status
    
    task.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(task)
    
    logger.info(f"Updated task {task_id}")
    return task.to_dict()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a task and all its schedules."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Delete associated schedules (cascade should handle this)
    scheduler = get_scheduler()
    schedules = db.query(Schedule).filter(Schedule.task_id == task_id).all()
    for schedule in schedules:
        scheduler.delete_schedule(schedule.id)
    
    db.delete(task)
    db.commit()
    
    logger.info(f"Deleted task {task_id}")
    return {"message": "Task deleted successfully"}


@router.post("/tasks/{task_id}/execute")
async def execute_task_now(task_id: int, db: Session = Depends(get_db)):
    """Execute a task immediately."""
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    scheduler = get_scheduler()
    success = await scheduler.execute_task_now(task_id)
    
    if success:
        return {"message": f"Task {task_id} execution started"}
    else:
        raise HTTPException(status_code=500, detail="Failed to execute task")


@router.get("/tasks/{task_id}/history")
async def get_task_history(
    task_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    success: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get execution history for a task."""
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    query = db.query(ExecutionHistory).filter(ExecutionHistory.task_id == task_id)
    
    if success is not None:
        query = query.filter(ExecutionHistory.success == success)
    
    # Order by most recent first
    query = query.order_by(ExecutionHistory.started_at.desc())
    
    total = query.count()
    history = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "history": [h.to_dict() for h in history]
    }


# Schedule endpoints
@router.post("/schedules", status_code=201)
async def create_schedule(
    schedule: ScheduleCreate,
    db: Session = Depends(get_db)
):
    """Create a new schedule for a task."""
    # Verify task exists
    task = db.query(Task).filter(Task.id == schedule.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    scheduler = get_scheduler()
    db_schedule = scheduler.create_schedule(
        task_id=schedule.task_id,
        schedule_type=schedule.schedule_type,
        schedule_config=schedule.schedule_config
    )
    
    if db_schedule:
        # Get fresh copy from database to avoid detached instance error
        fresh_schedule = db.query(Schedule).filter_by(id=db_schedule.id).first()
        if fresh_schedule:
            return fresh_schedule.to_dict()
        else:
            return db_schedule.to_dict() if hasattr(db_schedule, 'to_dict') else {"id": db_schedule.id}
    else:
        raise HTTPException(status_code=500, detail="Failed to create schedule")


@router.get("/schedules")
async def list_schedules(
    task_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """List all schedules with optional filtering."""
    query = db.query(Schedule)
    
    if task_id is not None:
        query = query.filter(Schedule.task_id == task_id)
    if is_active is not None:
        query = query.filter(Schedule.is_active == is_active)
    
    total = query.count()
    schedules = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "schedules": [schedule.to_dict() for schedule in schedules]
    }


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Get a specific schedule by ID."""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    return schedule.to_dict()


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    schedule_update: ScheduleUpdate,
    db: Session = Depends(get_db)
):
    """Update a schedule."""
    scheduler = get_scheduler()
    success = scheduler.update_schedule(
        schedule_id=schedule_id,
        is_active=schedule_update.is_active,
        schedule_config=schedule_update.schedule_config
    )
    
    if success:
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
        return schedule.to_dict()
    else:
        raise HTTPException(status_code=404, detail="Schedule not found")


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int):
    """Delete a schedule."""
    scheduler = get_scheduler()
    success = scheduler.delete_schedule(schedule_id)
    
    if success:
        return {"message": "Schedule deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Schedule not found")


# Scheduler status endpoint
@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get current scheduler status and job information."""
    scheduler = get_scheduler()
    return scheduler.get_scheduler_status()