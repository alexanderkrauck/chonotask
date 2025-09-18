"""Query executor for safe Python code execution on ChronoTask database."""

import logging
import signal
import json
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta
from contextlib import contextmanager
from collections import Counter
from itertools import groupby

from RestrictedPython import compile_restricted, safe_globals, safe_builtins
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from models.task import Task

logger = logging.getLogger(__name__)


class TimeoutError(Exception):
    """Raised when code execution exceeds timeout."""
    pass


class ReadOnlySession:
    """Wrapper for SQLAlchemy session that prevents write operations."""

    def __init__(self, session: Session):
        self._session = session
        self._original_commit = session.commit
        self._original_flush = session.flush
        self._original_add = session.add
        self._original_delete = session.delete
        self._original_merge = session.merge

        # Block write operations
        session.commit = self._blocked_operation
        session.flush = self._blocked_operation
        session.add = self._blocked_operation
        session.delete = self._blocked_operation
        session.merge = self._blocked_operation
        session.bulk_save_objects = self._blocked_operation
        session.bulk_insert_mappings = self._blocked_operation
        session.bulk_update_mappings = self._blocked_operation

    def _blocked_operation(self, *args, **kwargs):
        raise PermissionError("Write operations are not allowed in query execution")

    def query(self, *args, **kwargs):
        """Allow read-only queries."""
        return self._session.query(*args, **kwargs)

    def close(self):
        """Restore original methods and close."""
        self._session.commit = self._original_commit
        self._session.flush = self._original_flush
        self._session.add = self._original_add
        self._session.delete = self._original_delete
        self._session.merge = self._original_merge
        self._session.close()


@contextmanager
def timeout_context(seconds: int):
    """Context manager for timeout."""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Code execution exceeded {seconds} seconds")

    # Set the signal handler and alarm
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        # Restore the original handler and cancel the alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


class QueryExecutor:
    """Executes Python queries against the ChronoTask database safely."""

    def __init__(self, session: Session, max_result_size: int = 10000):
        """
        Initialize the query executor.

        Args:
            session: SQLAlchemy database session
            max_result_size: Maximum size of result in bytes
        """
        self.session = ReadOnlySession(session)
        self.max_result_size = max_result_size
        self.namespace = self._create_namespace()

    def _create_namespace(self) -> Dict[str, Any]:
        """
        Create the restricted namespace for code execution.

        Returns a namespace with:
        - tasks: All Task objects (read-only)
        - Task: The Task model class
        - Safe built-ins and utilities
        """
        # Fetch all tasks
        tasks = self.session.query(Task).all()

        # Create namespace with safe built-ins
        namespace = {
            # Data
            'tasks': tasks,
            'Task': Task,

            # Safe built-ins with guards
            '__builtins__': {
                **safe_builtins,
                '_getattr_': getattr,
                '_getitem_': lambda obj, index: obj[index],
                '_getiter_': lambda obj: iter(obj),
                '_iter_unpack_sequence_': lambda it, spec: list(it),
                '_write_': lambda x: x,  # Allow writes to local variables
            },
            'len': len,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'filter': filter,
            'map': map,
            'sorted': sorted,
            'sum': sum,
            'min': min,
            'max': max,
            'all': all,
            'any': any,
            'enumerate': enumerate,
            'zip': zip,
            'reversed': reversed,
            'range': range,

            # Date/time utilities
            'datetime': datetime,
            'timedelta': timedelta,
            'now': datetime.utcnow,

            # JSON for data manipulation
            'json': json,

            # Query utilities
            'find': lambda pred: [t for t in tasks if pred(t)],
            'find_one': lambda pred: next((t for t in tasks if pred(t)), None),
            'count': lambda pred=None: len(tasks) if pred is None else sum(1 for t in tasks if pred(t)),
            'group_by': lambda key_func: {
                key: [t for t in tasks if key_func(t) == key]
                for key in set(key_func(t) for t in tasks)
            },
            'get_by_id': lambda task_id: next((t for t in tasks if t.id == task_id), None),

            # Status helpers
            'is_open': lambda t: t.status_category == 'open',
            'is_completed': lambda t: t.status_category == 'completed',
            'is_in_progress': lambda t: t.status_category == 'in_progress',
            'is_waiting': lambda t: t.status_category == 'waiting',
            'is_cancelled': lambda t: t.status_category == 'cancelled',

            # Result variable (user sets this)
            'result': None,
        }

        return namespace

    def execute(self, code: str, timeout: int = 5) -> Dict[str, Any]:
        """
        Execute Python code in a restricted environment.

        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds

        Returns:
            Dictionary with:
            - success: Whether execution succeeded
            - result: The value of the 'result' variable
            - execution_time: Time taken to execute
            - error: Error message if failed
        """
        import time
        start_time = time.time()

        # Step 1: Compile with RestrictedPython
        try:
            compiled = compile_restricted(
                code,
                filename='<query>',
                mode='exec'
            )

            # Handle different RestrictedPython return formats
            if hasattr(compiled, 'errors') and compiled.errors:
                return {
                    'success': False,
                    'error': f"Compilation errors: {'; '.join(compiled.errors)}"
                }

            if hasattr(compiled, 'warnings') and compiled.warnings:
                logger.warning(f"Compilation warnings: {compiled.warnings}")

            # If compile_restricted returns None, there was a compilation error
            if compiled is None:
                return {
                    'success': False,
                    'error': "Compilation failed - code contains restricted operations"
                }

        except SyntaxError as e:
            return {
                'success': False,
                'error': f"Syntax error: {e}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Compilation failed: {str(e)}"
            }

        # Step 2: Execute in restricted namespace with timeout
        namespace = self.namespace.copy()

        try:
            with timeout_context(timeout):
                # Handle different RestrictedPython return formats
                if hasattr(compiled, 'code'):
                    exec(compiled.code, namespace)
                else:
                    # compiled might be the bytecode directly
                    exec(compiled, namespace)

            execution_time = time.time() - start_time

            # Get the result
            result = namespace.get('result')

            # Check result size
            if result is not None:
                try:
                    result_str = json.dumps(self._serialize_result(result))
                    if len(result_str) > self.max_result_size:
                        return {
                            'success': False,
                            'error': f"Result too large (>{self.max_result_size} bytes)"
                        }
                except (TypeError, ValueError) as e:
                    # If result can't be serialized, try converting to dict
                    try:
                        result = self._serialize_result(result)
                    except:
                        result = str(result)

            return {
                'success': True,
                'result': result,
                'execution_time': round(execution_time, 3)
            }

        except TimeoutError as e:
            return {
                'success': False,
                'error': str(e)
            }
        except PermissionError as e:
            return {
                'success': False,
                'error': f"Permission denied: {e}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Execution failed: {str(e)}"
            }

    def _serialize_result(self, obj: Any) -> Any:
        """
        Convert result to JSON-serializable format.

        Handles Task objects and other common types.
        """
        if obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, (datetime,)):
            return obj.isoformat()
        elif isinstance(obj, Task):
            return obj.to_dict()
        elif isinstance(obj, list):
            return [self._serialize_result(item) for item in obj]
        elif isinstance(obj, tuple):
            return [self._serialize_result(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._serialize_result(v) for k, v in obj.items()}
        elif isinstance(obj, set):
            return [self._serialize_result(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return self._serialize_result(obj.__dict__)
        else:
            return str(obj)

    def close(self):
        """Close the read-only session."""
        self.session.close()


# Example query templates
QUERY_TEMPLATES = [
    {
        "name": "Find tasks by text",
        "description": "Find all tasks containing specific text in name or description",
        "code": """# Find tasks containing 'deploy' (case-insensitive)
search_term = 'deploy'
result = find(lambda t:
    search_term.lower() in (t.name or '').lower() or
    search_term.lower() in (t.description or '').lower()
)"""
    },
    {
        "name": "Filter by status",
        "description": "Get all tasks with a specific status",
        "code": """# Get all open tasks
open_tasks = find(is_open)
result = {
    'count': len(open_tasks),
    'tasks': [t.to_dict() for t in open_tasks[:10]]
}"""
    },
    {
        "name": "Recent tasks",
        "description": "Find tasks created in the last N days",
        "code": """# Tasks created in the last 7 days
days_ago = 7
cutoff = now() - timedelta(days=days_ago)

recent = find(lambda t: t.created_at and t.created_at > cutoff)
result = {
    'count': len(recent),
    'tasks': sorted(
        [{'id': t.id, 'name': t.name, 'created': t.created_at.isoformat()}
         for t in recent],
        key=lambda x: x['created'],
        reverse=True
    )
}"""
    },
    {
        "name": "Group by status",
        "description": "Count tasks grouped by status category",
        "code": """# Group and count by status
groups = group_by(lambda t: t.status_category)
result = {
    status: len(tasks_list)
    for status, tasks_list in groups.items()
}"""
    },
    {
        "name": "Complex filter with custom fields",
        "description": "Find urgent tasks with specific tags",
        "code": """# Find urgent open tasks with specific tags
urgent_open = [
    t for t in tasks
    if t.status_category == 'open'
    and t.custom_fields
    and 'urgent' in t.custom_fields.get('tags', [])
]

result = {
    'count': len(urgent_open),
    'tasks': [
        {
            'id': t.id,
            'name': t.name,
            'tags': t.custom_fields.get('tags', [])
        }
        for t in urgent_open
    ]
}"""
    },
    {
        "name": "Scheduled tasks analysis",
        "description": "Analyze scheduled vs non-scheduled tasks",
        "code": """# Analyze scheduling patterns
scheduled = find(lambda t: t.schedule_enabled)
not_scheduled = find(lambda t: not t.schedule_enabled)

# Group scheduled by type
schedule_types = {}
for t in scheduled:
    if t.schedule_config:
        stype = t.schedule_config.get('type', 'unknown')
        schedule_types[stype] = schedule_types.get(stype, 0) + 1

result = {
    'total_tasks': len(tasks),
    'scheduled': len(scheduled),
    'not_scheduled': len(not_scheduled),
    'schedule_types': schedule_types,
    'percentage_scheduled': round(len(scheduled) / len(tasks) * 100, 2) if tasks else 0
}"""
    },
    {
        "name": "Task dependencies",
        "description": "Find tasks with dependencies",
        "code": """# Find tasks that depend on other tasks
dependent_tasks = find(
    lambda t: t.completion_criteria
    and t.completion_criteria.get('type') == 'depends_on_tasks'
)

result = [
    {
        'id': t.id,
        'name': t.name,
        'depends_on': t.completion_criteria.get('required_tasks', []),
        'condition': t.completion_criteria.get('condition', 'all_completed')
    }
    for t in dependent_tasks
]"""
    }
]