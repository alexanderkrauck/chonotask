"""Tests for scheduler core functionality."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models import Task, TaskType, TaskStatus, Schedule, ScheduleType
from scheduler import SchedulerManager, validate_cron, parse_cron_expression
from database import DatabaseManager


@pytest.fixture
def db_manager():
    """Create test database manager."""
    manager = DatabaseManager()
    # Use in-memory database for tests
    with patch.object(manager, '__init__', lambda x: None):
        manager.engine = None
        manager.SessionLocal = None
    return manager


@pytest.fixture
def scheduler(db_manager):
    """Create test scheduler."""
    return SchedulerManager(db_manager)


class TestCronParser:
    """Test cron expression parsing."""
    
    def test_validate_cron_valid(self):
        """Test valid cron expressions."""
        assert validate_cron("* * * * *") is True
        assert validate_cron("0 */2 * * *") is True
        assert validate_cron("0 0 * * 0") is True
        assert validate_cron("15 14 1 * *") is True
    
    def test_validate_cron_invalid(self):
        """Test invalid cron expressions."""
        assert validate_cron("invalid") is False
        assert validate_cron("* * * *") is False  # Too few fields
        assert validate_cron("* * * * * *") is False  # Too many fields
        assert validate_cron("60 * * * *") is False  # Invalid minute
    
    def test_parse_cron_expression(self):
        """Test parsing cron expression for next run time."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Every minute
        next_time = parse_cron_expression("* * * * *", base_time)
        assert next_time == datetime(2024, 1, 1, 12, 1, 0)
        
        # Every hour at minute 0
        next_time = parse_cron_expression("0 * * * *", base_time)
        assert next_time == datetime(2024, 1, 1, 13, 0, 0)
        
        # Daily at midnight
        next_time = parse_cron_expression("0 0 * * *", base_time)
        assert next_time == datetime(2024, 1, 2, 0, 0, 0)


class TestSchedulerManager:
    """Test scheduler manager."""
    
    @pytest.mark.asyncio
    async def test_execute_task_http(self, scheduler):
        """Test executing an HTTP task."""
        # Mock HTTP executor
        with patch('scheduler.core.HTTPExecutor') as MockExecutor:
            mock_executor = AsyncMock()
            mock_result = Mock(
                success=True,
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                duration=1.0,
                output={"status_code": 200},
                error=None,
                retry_count=0
            )
            mock_executor.execute_with_retry.return_value = mock_result
            MockExecutor.return_value = mock_executor
            
            # Mock database session
            with patch.object(scheduler.db_manager, 'get_session') as mock_session:
                mock_task = Mock(
                    id=1,
                    name="Test Task",
                    task_type=TaskType.HTTP,
                    status=TaskStatus.ACTIVE,
                    config={"url": "http://example.com"},
                    max_retries=3,
                    retry_delay=5,
                    run_count=0,
                    success_count=0,
                    failure_count=0
                )
                
                session_mock = Mock()
                session_mock.query.return_value.filter_by.return_value.first.return_value = mock_task
                session_mock.__enter__ = Mock(return_value=session_mock)
                session_mock.__exit__ = Mock(return_value=None)
                mock_session.return_value = session_mock
                
                # Execute task
                await scheduler._execute_task(1)
                
                # Verify execution
                assert mock_task.run_count == 1
                assert mock_task.success_count == 1
                assert mock_task.failure_count == 0
    
    def test_create_trigger_once(self, scheduler):
        """Test creating a one-time trigger."""
        schedule = Mock(
            schedule_type=ScheduleType.ONCE,
            schedule_config={"datetime": "2024-12-25T10:00:00"}
        )
        
        trigger = scheduler._create_trigger(schedule)
        assert trigger is not None
    
    def test_create_trigger_cron(self, scheduler):
        """Test creating a cron trigger."""
        schedule = Mock(
            schedule_type=ScheduleType.CRON,
            schedule_config={"expression": "0 */2 * * *"}
        )
        
        trigger = scheduler._create_trigger(schedule)
        assert trigger is not None
    
    def test_create_trigger_interval(self, scheduler):
        """Test creating an interval trigger."""
        schedule = Mock(
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600}
        )
        
        trigger = scheduler._create_trigger(schedule)
        assert trigger is not None
    
    def test_create_trigger_invalid(self, scheduler):
        """Test creating trigger with invalid config."""
        schedule = Mock(
            schedule_type=ScheduleType.CRON,
            schedule_config={"expression": "invalid"}
        )
        
        trigger = scheduler._create_trigger(schedule)
        assert trigger is None