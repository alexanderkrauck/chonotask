"""Unified Task model for todos and scheduled tasks."""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, JSON, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Task(Base):
    __tablename__ = "tasks"

    # Core identity
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    task_type = Column(String(50), nullable=False)  # 'todo', 'http', 'bash', custom types

    # Status system
    status_category = Column(String(20), default='open')  # 'open', 'in_progress', 'waiting', 'completed', 'cancelled'
    status_text = Column(String(200))  # "waiting for client feedback", "blocked by deployment"

    # Completion criteria (flexible structure)
    # Examples:
    # {"type": "manual"} - mark as done manually
    # {"type": "checklist", "items": ["item1", "item2"], "completed": ["item1"]}
    # {"type": "depends_on_tasks", "required_tasks": [123, 456], "condition": "all_completed"}
    # {"type": "http_success", "expected_status": 200}
    # {"type": "composite", "conditions": [...], "logic": "all"}
    completion_criteria = Column(JSON)

    # Execution config (null for simple todos)
    # For HTTP: {"url": str, "method": str, "headers": dict, "body": any, "timeout": int}
    # For BASH: {"command": str, "args": list, "env": dict, "timeout": int, "working_dir": str}
    execution_config = Column(JSON)

    # Scheduling (null for non-scheduled items)
    # {"type": "cron", "expression": "0 */2 * * *"}
    # {"type": "interval", "seconds": 3600}
    # {"type": "once", "datetime": "2024-01-01T10:00:00"}
    schedule_config = Column(JSON)
    schedule_enabled = Column(Boolean, default=False)

    # Arbitrary custom fields
    # {"priority": "high", "assignee": "@john", "epic": "user-auth", "estimate": "3h", "tags": ["urgent", "client"]}
    custom_fields = Column(JSON)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "status_category": self.status_category,
            "status_text": self.status_text,
            "completion_criteria": self.completion_criteria,
            "execution_config": self.execution_config,
            "schedule_config": self.schedule_config,
            "schedule_enabled": self.schedule_enabled,
            "custom_fields": self.custom_fields,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def is_schedulable(self) -> bool:
        """Check if this task can be scheduled."""
        return self.schedule_enabled and self.schedule_config is not None

    def is_executable(self) -> bool:
        """Check if this task can be executed."""
        return self.execution_config is not None and self.task_type in ['http', 'bash']

    def is_todo(self) -> bool:
        """Check if this is a simple todo (non-executable)."""
        return self.task_type == 'todo' or not self.is_executable()

    def evaluate_completion_criteria(self, all_tasks: list = None) -> bool:
        """Evaluate if completion criteria are met."""
        if not self.completion_criteria:
            return False

        criteria_type = self.completion_criteria.get('type')

        if criteria_type == 'manual':
            return self.status_category == 'completed'
        elif criteria_type == 'depends_on_tasks' and all_tasks:
            required_tasks = self.completion_criteria.get('required_tasks', [])
            condition = self.completion_criteria.get('condition', 'all_completed')

            completed_tasks = [t for t in all_tasks if t.id in required_tasks and t.status_category == 'completed']

            if condition == 'all_completed':
                return len(completed_tasks) == len(required_tasks)
            elif condition == 'any_completed':
                return len(completed_tasks) > 0
        elif criteria_type == 'composite' and all_tasks:
            conditions = self.completion_criteria.get('conditions', [])
            logic = self.completion_criteria.get('logic', 'all')

            results = []
            for condition in conditions:
                # Create temporary task object to evaluate individual conditions
                temp_task = Task()
                temp_task.completion_criteria = condition
                temp_task.status_category = self.status_category
                results.append(temp_task.evaluate_completion_criteria(all_tasks))

            if logic == 'all':
                return all(results)
            elif logic == 'any':
                return any(results)

        return False