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
from models import Task
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
            'http': HTTPExecutor(),
            'bash': BashExecutor()
        }
        self._running_tasks = set()
        self._all_tasks_cache = []  # In-memory cache for completion criteria evaluation
        
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

        # Load existing scheduled tasks from database
        self._load_scheduled_tasks()

    def _load_scheduled_tasks(self):
        """Load all scheduled tasks from database."""
        with self.db_manager.get_session() as session:
            # Get all tasks with scheduling enabled
            scheduled_tasks = session.query(Task).filter_by(schedule_enabled=True).all()

            for task in scheduled_tasks:
                if task.schedule_config and task.status_category in ['open', 'in_progress']:
                    self._add_job(task)
                    logger.info(f"Loaded scheduled task '{task.name}' (ID: {task.id})")

            # Load all tasks into memory cache for completion criteria evaluation
            self._all_tasks_cache = session.query(Task).all()

            logger.info(f"Loaded {len(scheduled_tasks)} scheduled tasks")
    
    def _add_job(self, task: Task):
        """Add a job to the scheduler."""
        job_id = f"task_{task.id}"

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        # Create trigger based on schedule configuration
        trigger = self._create_trigger(task.schedule_config)
        if not trigger:
            logger.error(f"Failed to create trigger for task {task.id}")
            return

        # Add job to scheduler
        self.scheduler.add_job(
            func=self._execute_task,
            trigger=trigger,
            args=[task.id],
            id=job_id,
            name=f"{task.name} (Task {task.id})",
            replace_existing=True
        )

        logger.info(f"Added scheduled job for task '{task.name}' (ID: {task.id})")
    
    def _create_trigger(self, schedule_config: Dict[str, Any]):
        """Create APScheduler trigger from schedule configuration."""
        try:
            if not schedule_config:
                return None

            schedule_type = schedule_config.get("type")

            if schedule_type == "once":
                # One-time execution
                run_date = schedule_config.get("datetime")
                if run_date:
                    if isinstance(run_date, str):
                        run_date = datetime.fromisoformat(run_date.replace('Z', '+00:00').replace('+00:00', ''))
                    return DateTrigger(run_date=run_date)

            elif schedule_type == "cron":
                # Cron-based schedule
                expression = schedule_config.get("expression")
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

            elif schedule_type == "interval":
                # Fixed interval schedule
                seconds = schedule_config.get("seconds", 0)
                start_date = schedule_config.get("start_date")

                if seconds > 0:
                    kwargs = {"seconds": seconds}
                    if start_date:
                        if isinstance(start_date, str):
                            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00').replace('+00:00', ''))
                        kwargs["start_date"] = start_date
                    return IntervalTrigger(**kwargs)

        except Exception as e:
            logger.error(f"Failed to create trigger from config {schedule_config}: {e}")

        return None
    
    async def _execute_task(self, task_id: int):
        """Execute a scheduled or manual task."""
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

                if task.status_category in ['completed', 'cancelled']:
                    logger.info(f"Task {task_id} is {task.status_category}, skipping execution")
                    return

                logger.info(f"Executing task '{task.name}' (ID: {task_id})")

                # Refresh tasks cache for completion criteria evaluation
                self._all_tasks_cache = session.query(Task).all()

                # Check if task is executable
                if not task.is_executable():
                    logger.info(f"Task '{task.name}' is not executable (todo type)")
                    # For todos, just check completion criteria
                    if task.evaluate_completion_criteria(self._all_tasks_cache):
                        task.status_category = 'completed'
                        logger.info(f"Todo task '{task.name}' completed based on criteria")
                    session.commit()
                    return

                # Get executor for executable tasks
                executor = self.executors.get(task.task_type)
                if not executor:
                    logger.error(f"No executor found for task type {task.task_type}")
                    return

                # Update task status
                task.status_category = 'in_progress'
                if not task.status_text:
                    task.status_text = 'executing'

                # Execute task
                try:
                    result = await executor.execute_with_retry(task.execution_config)

                    if result.success:
                        # Check if completion criteria are met
                        if task.completion_criteria:
                            if task.evaluate_completion_criteria(self._all_tasks_cache):
                                task.status_category = 'completed'
                                task.status_text = 'completed successfully'
                            else:
                                task.status_category = 'waiting'
                                task.status_text = 'execution completed, waiting for criteria'
                        else:
                            # No completion criteria, mark as completed
                            task.status_category = 'completed'
                            task.status_text = 'completed successfully'

                        logger.info(f"Task '{task.name}' executed successfully")
                    else:
                        task.status_category = 'open'
                        task.status_text = f'execution failed: {result.error}'
                        logger.warning(f"Task '{task.name}' failed: {result.error}")

                except Exception as e:
                    task.status_category = 'open'
                    task.status_text = f'execution error: {str(e)}'
                    logger.error(f"Task '{task.name}' execution error: {e}")

                # Handle one-time scheduled tasks
                if (task.schedule_enabled and task.schedule_config and
                    task.schedule_config.get("type") == "once"):
                    task.schedule_enabled = False
                    job_id = f"task_{task_id}"
                    if self.scheduler.get_job(job_id):
                        self.scheduler.remove_job(job_id)
                    logger.info(f"One-time scheduled task {task_id} completed and disabled")

                session.commit()

        except Exception as e:
            logger.error(f"Error executing task {task_id}: {e}", exc_info=True)
        finally:
            self._running_tasks.discard(task_key)
    
    def enable_task_schedule(self, task_id: int, schedule_config: Dict[str, Any]) -> bool:
        """Enable scheduling for a task."""
        with self.db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found")
                return False

            # Update task with schedule configuration
            task.schedule_config = schedule_config
            task.schedule_enabled = True

            # Add to scheduler if task is active
            if task.status_category in ['open', 'in_progress']:
                self._add_job(task)

            session.commit()
            logger.info(f"Enabled scheduling for task '{task.name}' (ID: {task_id})")
            return True

    def disable_task_schedule(self, task_id: int) -> bool:
        """Disable scheduling for a task."""
        with self.db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found")
                return False

            # Remove from scheduler
            job_id = f"task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # Update task
            task.schedule_enabled = False

            session.commit()
            logger.info(f"Disabled scheduling for task '{task.name}' (ID: {task_id})")
            return True

    def update_task_schedule(self, task_id: int, schedule_config: Dict[str, Any]) -> bool:
        """Update schedule configuration for a task."""
        with self.db_manager.get_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found")
                return False

            # Update schedule configuration
            task.schedule_config = schedule_config

            # Update scheduler job if enabled
            if task.schedule_enabled and task.status_category in ['open', 'in_progress']:
                self._add_job(task)
            else:
                # Remove job if not enabled or not active
                job_id = f"task_{task_id}"
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)

            session.commit()
            logger.info(f"Updated schedule for task '{task.name}' (ID: {task_id})")
            return True

    def refresh_task_cache(self):
        """Refresh the in-memory task cache."""
        with self.db_manager.get_session() as session:
            self._all_tasks_cache = session.query(Task).all()

    def evaluate_all_completion_criteria(self):
        """Evaluate completion criteria for all tasks and update their status."""
        with self.db_manager.get_session() as session:
            # Refresh cache
            self._all_tasks_cache = session.query(Task).all()

            updated_count = 0
            for task in self._all_tasks_cache:
                if task.completion_criteria and task.status_category not in ['completed', 'cancelled']:
                    if task.evaluate_completion_criteria(self._all_tasks_cache):
                        task.status_category = 'completed'
                        task.status_text = 'completed based on criteria'
                        updated_count += 1

            if updated_count > 0:
                session.commit()
                logger.info(f"Updated {updated_count} tasks based on completion criteria")
    
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