"""Schedule and execution history models."""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Float, Text, JSON
from sqlalchemy.orm import relationship
from .task import Base


class ScheduleType(str, Enum):
    ONCE = "once"  # One-time execution
    CRON = "cron"  # Cron expression
    INTERVAL = "interval"  # Fixed interval


class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    schedule_type = Column(String(20), nullable=False)
    
    # Schedule configuration
    # For ONCE: {"datetime": "2024-01-01T10:00:00"}
    # For CRON: {"expression": "0 */2 * * *"}
    # For INTERVAL: {"seconds": 3600, "start_date": "2024-01-01T00:00:00"}
    schedule_config = Column(JSON, nullable=False)
    
    # State
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime)
    next_run = Column(DateTime)
    
    # APScheduler job ID
    job_id = Column(String(255), unique=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "schedule_type": self.schedule_type,
            "schedule_config": self.schedule_config,
            "is_active": self.is_active,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "job_id": self.job_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ExecutionHistory(Base):
    __tablename__ = "execution_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.id", ondelete="SET NULL"))
    
    # Execution details
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    duration = Column(Float)  # seconds
    
    # Status
    success = Column(Boolean, nullable=False)
    error_message = Column(Text)
    
    # Execution data
    input_data = Column(JSON)  # What was sent
    output_data = Column(JSON)  # What was received
    
    # Retry information
    retry_count = Column(Integer, default=0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "schedule_id": self.schedule_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration": self.duration,
            "success": self.success,
            "error_message": self.error_message,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "retry_count": self.retry_count
        }