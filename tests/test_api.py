"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api.http_server import app
from models import Task, TaskType, TaskStatus, Schedule, ScheduleType


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock database session."""
    with patch('api.endpoints.get_db') as mock:
        session = MagicMock()
        mock.return_value = session
        yield session


@pytest.fixture
def mock_scheduler():
    """Mock scheduler manager."""
    with patch('api.endpoints.get_scheduler') as mock:
        scheduler = Mock()
        mock.return_value = scheduler
        yield scheduler


class TestTaskEndpoints:
    """Test task-related endpoints."""
    
    def test_create_task(self, client, mock_db):
        """Test creating a new task."""
        task_data = {
            "name": "Test Task",
            "description": "Test description",
            "task_type": "http",
            "config": {"url": "http://example.com"},
            "max_retries": 3,
            "retry_delay": 5
        }
        
        # Mock the database add and commit
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        response = client.post("/api/v1/tasks", json=task_data)
        
        assert response.status_code == 201
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
    
    def test_list_tasks(self, client, mock_db):
        """Test listing tasks."""
        mock_tasks = [
            Mock(spec=Task, to_dict=lambda: {"id": 1, "name": "Task 1"}),
            Mock(spec=Task, to_dict=lambda: {"id": 2, "name": "Task 2"})
        ]
        
        mock_query = Mock()
        mock_query.count.return_value = 2
        mock_query.offset.return_value.limit.return_value.all.return_value = mock_tasks
        mock_db.query.return_value = mock_query
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        response = client.get("/api/v1/tasks")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["tasks"]) == 2
    
    def test_get_task(self, client, mock_db):
        """Test getting a specific task."""
        mock_task = Mock(spec=Task)
        mock_task.to_dict.return_value = {"id": 1, "name": "Test Task"}
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        response = client.get("/api/v1/tasks/1")
        
        assert response.status_code == 200
        assert response.json()["id"] == 1
    
    def test_get_task_not_found(self, client, mock_db):
        """Test getting non-existent task."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        response = client.get("/api/v1/tasks/999")
        
        assert response.status_code == 404
    
    def test_update_task(self, client, mock_db):
        """Test updating a task."""
        mock_task = Mock(spec=Task)
        mock_task.to_dict.return_value = {"id": 1, "name": "Updated Task"}
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        update_data = {"name": "Updated Task"}
        response = client.put("/api/v1/tasks/1", json=update_data)
        
        assert response.status_code == 200
        assert mock_task.name == "Updated Task"
        mock_db.commit.assert_called_once()
    
    def test_delete_task(self, client, mock_db, mock_scheduler):
        """Test deleting a task."""
        mock_task = Mock(spec=Task)
        mock_schedules = [Mock(id=1), Mock(id=2)]
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        mock_db.query.return_value.filter.return_value.all.return_value = mock_schedules
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        response = client.delete("/api/v1/tasks/1")
        
        assert response.status_code == 200
        mock_db.delete.assert_called_once_with(mock_task)
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_task_now(self, client, mock_db, mock_scheduler):
        """Test immediate task execution."""
        mock_task = Mock(spec=Task)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        mock_scheduler.execute_task_now.return_value = True
        
        response = client.post("/api/v1/tasks/1/execute")
        
        assert response.status_code == 200
        mock_scheduler.execute_task_now.assert_called_once_with(1)


class TestScheduleEndpoints:
    """Test schedule-related endpoints."""
    
    def test_create_schedule(self, client, mock_db, mock_scheduler):
        """Test creating a schedule."""
        mock_task = Mock(spec=Task)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        mock_schedule = Mock(spec=Schedule)
        mock_schedule.to_dict.return_value = {"id": 1, "task_id": 1}
        mock_scheduler.create_schedule.return_value = mock_schedule
        
        schedule_data = {
            "task_id": 1,
            "schedule_type": "cron",
            "schedule_config": {"expression": "0 * * * *"}
        }
        
        response = client.post("/api/v1/schedules", json=schedule_data)
        
        assert response.status_code == 201
        mock_scheduler.create_schedule.assert_called_once()
    
    def test_list_schedules(self, client, mock_db):
        """Test listing schedules."""
        mock_schedules = [
            Mock(spec=Schedule, to_dict=lambda: {"id": 1}),
            Mock(spec=Schedule, to_dict=lambda: {"id": 2})
        ]
        
        mock_query = Mock()
        mock_query.count.return_value = 2
        mock_query.offset.return_value.limit.return_value.all.return_value = mock_schedules
        mock_db.query.return_value = mock_query
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        response = client.get("/api/v1/schedules")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["schedules"]) == 2
    
    def test_update_schedule(self, client, mock_db, mock_scheduler):
        """Test updating a schedule."""
        mock_schedule = Mock(spec=Schedule)
        mock_schedule.to_dict.return_value = {"id": 1, "is_active": False}
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule
        mock_db.__enter__.return_value = mock_db
        mock_db.__exit__.return_value = None
        
        mock_scheduler.update_schedule.return_value = True
        
        update_data = {"is_active": False}
        response = client.put("/api/v1/schedules/1", json=update_data)
        
        assert response.status_code == 200
        mock_scheduler.update_schedule.assert_called_once_with(
            schedule_id=1,
            is_active=False,
            schedule_config=None
        )
    
    def test_delete_schedule(self, client, mock_scheduler):
        """Test deleting a schedule."""
        mock_scheduler.delete_schedule.return_value = True
        
        response = client.delete("/api/v1/schedules/1")
        
        assert response.status_code == 200
        mock_scheduler.delete_schedule.assert_called_once_with(1)


class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "ChronoTask"
        assert data["version"] == "1.0.0"
    
    def test_health_endpoint(self, client, mock_scheduler):
        """Test health check endpoint."""
        mock_scheduler.get_scheduler_status.return_value = {
            "running": True,
            "jobs_count": 5
        }
        
        with patch('api.http_server.scheduler_manager', mock_scheduler):
            response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["scheduler"]["running"] is True