"""Task model definitions."""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum as SQLEnum, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class TaskType(str, Enum):
    HTTP = "http"
    BASH = "bash"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    task_type = Column(SQLEnum(TaskType), nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.ACTIVE)
    
    # Task configuration (JSON field for flexibility)
    # For HTTP: {"url": str, "method": str, "headers": dict, "body": any, "timeout": int}
    # For BASH: {"command": str, "args": list, "env": dict, "timeout": int, "working_dir": str}
    config = Column(JSON, nullable=False)
    
    # Retry configuration
    max_retries = Column(Integer, default=3)
    retry_delay = Column(Integer, default=5)  # seconds
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run = Column(DateTime)
    next_run = Column(DateTime)
    
    # Statistics
    run_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type.value if self.task_type else None,
            "status": self.status.value if self.status else None,
            "config": self.config,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count
        }