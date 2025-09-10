"""Core scheduler implementation using APScheduler."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from sqlalchemy.orm import Session
import logging

from config import settings
from models import Task, TaskType, TaskStatus, Schedule, ScheduleType, ExecutionHistory
from executors import HTTPExecutor, BashExecutor
from database import DatabaseManager
from .cron_parser import validate_cron

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages scheduled tasks using APScheduler."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.scheduler = None
        self.executors = {
            TaskType.HTTP: HTTPExecutor(),
            TaskType.BASH: BashExecutor()
        }
        self._running_tasks = set()
        
    def initialize(self):
        """Initialize the scheduler."""
        # Configure APScheduler
        jobstores = {
            'default': MemoryJobStore()
        }
        
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = settings.scheduler_job_defaults
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=settings.scheduler_timezone
        )
        
        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler initialized and started")
        
        # Load existing schedules from database
        self._load_schedules()
    
    def _load_schedules(self):
        """Load all active schedules from database."""
        with self.db_manager.get_session() as session:
            schedules = session.query(Schedule).filter_by(is_active=True).all()
            
            for schedule in schedules:
                task = session.query(Task).filter_by(id=schedule.task_id).first()
                if task and task.status == TaskStatus.ACTIVE:
                    self._add_job(schedule, task)
                    logger.info(f"Loaded schedule {schedule.id} for task '{task.name}'")
            
            logger.info(f"Loaded {len(schedules)} active schedules")
    
    def _add_job(self, schedule: Schedule, task: Task):
        """Add a job to the scheduler."""
        job_id = f"schedule_{schedule.id}"
        
        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Create trigger based on schedule type
        trigger = self._create_trigger(schedule)
        if not trigger:
            logger.error(f"Failed to create trigger for schedule {schedule.id}")
            return
        
        # Add job to scheduler
        self.scheduler.add_job(
            func=self._execute_task,
            trigger=trigger,
            args=[task.id, schedule.id],
            id=job_id,
            name=f"{task.name} (Schedule {schedule.id})",
            replace_existing=True
        )
        
        # Update job_id in database
        with self.db_manager.get_session() as session:
            db_schedule = session.query(Schedule).filter_by(id=schedule.id).first()
            if db_schedule:
                db_schedule.job_id = job_id
                
                # Calculate next run time
                job = self.scheduler.get_job(job_id)
                if job and job.next_run_time:
                    db_schedule.next_run = job.next_run_time.replace(tzinfo=None)
                
                session.commit()
    
    def _create_trigger(self, schedule: Schedule):
        """Create APScheduler trigger from schedule configuration."""
        try:
            config = schedule.schedule_config
            
            if schedule.schedule_type == ScheduleType.ONCE:
                # One-time execution
                run_date = config.get("datetime")
                if run_date:
                    if isinstance(run_date, str):
                        run_date = datetime.fromisoformat(run_date.replace('Z', '+00:00').replace('+00:00', ''))
                    return DateTrigger(run_date=run_date)
                    
            elif schedule.schedule_type == ScheduleType.CRON:
                # Cron-based schedule
                expression = config.get("expression")
                if expression and validate_cron(expression):
                    # Parse cron expression (minute hour day month day_of_week)
                    parts = expression.split()
                    if len(parts) == 5:
                        return CronTrigger(
                            minute=parts[0],
                            hour=parts[1],
                            day=parts[2],
                            month=parts[3],
                            day_of_week=parts[4]
                        )
                        
            elif schedule.schedule_type == ScheduleType.INTERVAL:
                # Fixed interval schedule
                seconds = config.get("seconds", 0)
                start_date = config.get("start_date")
                
                if seconds > 0:
                    kwargs = {"seconds": seconds}
                    if start_date:
                        if isinstance(start_date, str):
                            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00').replace('+00:00', ''))
                        kwargs["start_date"] = start_date
                    return IntervalTrigger(**kwargs)
                    
        except Exception as e:
            logger.error(f"Failed to create trigger for schedule {schedule.id}: {e}")
        
        return None
    
    async def _execute_task(self, task_id: int, schedule_id: Optional[int] = None):
        """Execute a scheduled task."""
        # Prevent concurrent execution of the same task
        task_key = f"task_{task_id}"
        if task_key in self._running_tasks:
            logger.warning(f"Task {task_id} is already running, skipping execution")
            return
        
        self._running_tasks.add(task_key)
        
        try:
            with self.db_manager.get_session() as session:
                # Get task from database
                task = session.query(Task).filter_by(id=task_id).first()
                if not task:
                    logger.error(f"Task {task_id} not found")
                    return
                
                if task.status != TaskStatus.ACTIVE:
                    logger.info(f"Task {task_id} is not active, skipping execution")
                    return
                
                logger.info(f"Executing task '{task.name}' (ID: {task_id})")
                
                # Get executor
                executor = self.executors.get(task.task_type)
                if not executor:
                    logger.error(f"No executor found for task type {task.task_type}")
                    return
                
                # Set retry configuration
                executor.max_retries = task.max_retries
                executor.retry_delay = task.retry_delay
                
                # Execute task with retry
                result = await executor.execute_with_retry(task.config)
                
                # Update task statistics
                task.run_count += 1
                task.last_run = datetime.utcnow()
                
                if result.success:
                    task.success_count += 1
                else:
                    task.failure_count += 1
                
                # Save execution history
                history = ExecutionHistory(
                    task_id=task_id,
                    schedule_id=schedule_id,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    duration=result.duration,
                    success=result.success,
                    error_message=result.error,
                    input_data=task.config,
                    output_data=result.output if isinstance(result.output, (dict, list)) else {"output": str(result.output)},
                    retry_count=result.retry_count
                )
                session.add(history)
                
                # Update schedule last_run
                if schedule_id:
                    schedule = session.query(Schedule).filter_by(id=schedule_id).first()
                    if schedule:
                        schedule.last_run = datetime.utcnow()
                        
                        # Update next_run
                        job_id = f"schedule_{schedule_id}"
                        job = self.scheduler.get_job(job_id)
                        if job and job.next_run_time:
                            schedule.next_run = job.next_run_time.replace(tzinfo=None)
                        
                        # Remove one-time schedules after execution
                        if schedule.schedule_type == ScheduleType.ONCE:
                            schedule.is_active = False
                            self.scheduler.remove_job(job_id)
                            logger.info(f"One-time schedule {schedule_id} completed and deactivated")
                
                # Calculate next run for the task
                self._update_task_next_run(session, task)
                
                session.commit()
                
                if result.success:
                    logger.info(f"Task '{task.name}' executed successfully")
                else:
                    logger.warning(f"Task '{task.name}' failed: {result.error}")
                    
        except Exception as e:
            logger.error(f"Error executing task {task_id}: {e}", exc_info=True)
        finally:
            self._running_tasks.discard(task_key)
    
    def _update_task_next_run(self, session: Session, task: Task):
        """Update task's next run time based on active schedules."""
        schedules = session.query(Schedule).filter_by(
            task_id=task.id,
            is_active=True
        ).all()
        
        next_runs = []
        for schedule in schedules:
            if schedule.next_run:
                next_runs.append(schedule.next_run)
        
        if next_runs:
            task.next_run = min(next_runs)
        else:
            task.next_run = None
    
    def create_schedule(self, task_id: int, schedule_type: ScheduleType, 
                       schedule_config: Dict[str, Any]) -> Optional[Schedule]:
        """Create a new schedule for a task."""
        with self.db_manager.get_session() as session:
            # Verify task exists
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found")
                return None
            
            # Create schedule
            schedule = Schedule(
                task_id=task_id,
                schedule_type=schedule_type,
                schedule_config=schedule_config,
                is_active=True
            )
            
            session.add(schedule)
            session.commit()
            
            # Get the ID before adding job
            schedule_id = schedule.id
            
            # Add to scheduler
            self._add_job(schedule, task)
            
            logger.info(f"Created schedule {schedule_id} for task '{task.name}'")
            
            # Return just the ID - the API will fetch fresh copy
            return schedule
    
    def update_schedule(self, schedule_id: int, is_active: Optional[bool] = None,
                       schedule_config: Optional[Dict[str, Any]] = None) -> bool:
        """Update an existing schedule."""
        with self.db_manager.get_session() as session:
            schedule = session.query(Schedule).filter_by(id=schedule_id).first()
            if not schedule:
                logger.error(f"Schedule {schedule_id} not found")
                return False
            
            task = session.query(Task).filter_by(id=schedule.task_id).first()
            if not task:
                logger.error(f"Task {schedule.task_id} not found")
                return False
            
            # Update fields
            if is_active is not None:
                schedule.is_active = is_active
            
            if schedule_config is not None:
                schedule.schedule_config = schedule_config
            
            schedule.updated_at = datetime.utcnow()
            
            # Update scheduler job
            job_id = f"schedule_{schedule_id}"
            
            if schedule.is_active and task.status == TaskStatus.ACTIVE:
                self._add_job(schedule, task)
            else:
                # Remove job if inactive
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
            
            session.commit()
            logger.info(f"Updated schedule {schedule_id}")
            return True
    
    def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule."""
        with self.db_manager.get_session() as session:
            schedule = session.query(Schedule).filter_by(id=schedule_id).first()
            if not schedule:
                logger.error(f"Schedule {schedule_id} not found")
                return False
            
            # Remove from scheduler
            job_id = f"schedule_{schedule_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Delete from database
            session.delete(schedule)
            session.commit()
            
            logger.info(f"Deleted schedule {schedule_id}")
            return True
    
    async def execute_task_now(self, task_id: int) -> bool:
        """Execute a task immediately (manual trigger)."""
        try:
            await self._execute_task(task_id)
            return True
        except Exception as e:
            logger.error(f"Failed to execute task {task_id}: {e}")
            return False
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        if not self.scheduler:
            return {"running": False}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "running": self.scheduler.running,
            "jobs_count": len(jobs),
            "jobs": jobs,
            "timezone": str(self.scheduler.timezone)
        }
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down")