"""Tests for task executors."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import httpx
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from executors import HTTPExecutor, BashExecutor, ExecutionResult


class TestHTTPExecutor:
    """Test HTTP task executor."""
    
    @pytest.mark.asyncio
    async def test_execute_get_success(self):
        """Test successful GET request."""
        executor = HTTPExecutor()
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_response = Mock(
                status_code=200,
                headers={"content-type": "application/json"},
                text="Success",
                json=lambda: {"result": "ok"}
            )
            
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client
            
            config = {
                "url": "http://example.com/api",
                "method": "GET"
            }
            
            result = await executor.execute(config)
            
            assert result.success is True
            assert result.output["status_code"] == 200
            assert result.output["body"]["result"] == "ok"
            assert result.error is None
    
    @pytest.mark.asyncio
    async def test_execute_post_with_json(self):
        """Test POST request with JSON body."""
        executor = HTTPExecutor()
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_response = Mock(
                status_code=201,
                headers={"content-type": "application/json"},
                text='{"id": 123}',
                json=lambda: {"id": 123}
            )
            
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client
            
            config = {
                "url": "http://example.com/api/items",
                "method": "POST",
                "body": {"name": "Test Item"},
                "headers": {"Authorization": "Bearer token"}
            }
            
            result = await executor.execute(config)
            
            assert result.success is True
            assert result.output["status_code"] == 201
            assert result.output["body"]["id"] == 123
            
            # Verify request was made correctly
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args[1]
            assert call_args["method"] == "POST"
            assert call_args["json"] == {"name": "Test Item"}
    
    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test request timeout."""
        executor = HTTPExecutor()
        
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            MockClient.return_value.__aenter__.return_value = mock_client
            
            config = {
                "url": "http://example.com/slow",
                "timeout": 1
            }
            
            result = await executor.execute(config)
            
            assert result.success is False
            assert "timeout" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_execute_with_retry(self):
        """Test execution with retry on failure."""
        executor = HTTPExecutor(max_retries=2, retry_delay=0.1)
        
        with patch('httpx.AsyncClient') as MockClient:
            # First two attempts fail, third succeeds
            mock_responses = [
                httpx.ConnectError("Connection failed"),
                httpx.ConnectError("Connection failed"),
                Mock(
                    status_code=200,
                    headers={},
                    text="Success",
                    json=lambda: {"result": "ok"}
                )
            ]
            
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=mock_responses)
            MockClient.return_value.__aenter__.return_value = mock_client
            
            config = {"url": "http://example.com/api"}
            
            result = await executor.execute_with_retry(config)
            
            assert result.success is True
            assert result.retry_count == 2


class TestBashExecutor:
    """Test Bash command executor."""
    
    @pytest.mark.asyncio
    async def test_execute_simple_command(self):
        """Test executing a simple command."""
        executor = BashExecutor()
        
        config = {
            "command": "echo",
            "args": ["Hello World"]
        }
        
        result = await executor.execute(config)
        
        assert result.success is True
        assert "Hello World" in result.output["stdout"]
        assert result.output["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_execute_with_env_vars(self):
        """Test command with environment variables."""
        executor = BashExecutor()
        
        config = {
            "command": "sh -c 'echo $TEST_VAR'",
            "env": {"TEST_VAR": "test_value"},
            "shell": True
        }
        
        result = await executor.execute(config)
        
        assert result.success is True
        assert "test_value" in result.output["stdout"]
    
    @pytest.mark.asyncio
    async def test_execute_command_failure(self):
        """Test command that returns non-zero exit code."""
        executor = BashExecutor()
        
        config = {
            "command": "sh -c 'exit 1'",
            "shell": True
        }
        
        result = await executor.execute(config)
        
        assert result.success is False
        assert result.output["exit_code"] == 1
        assert "Exit code: 1" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test command timeout."""
        executor = BashExecutor()
        
        config = {
            "command": "sleep 10",
            "timeout": 0.1,
            "shell": True
        }
        
        result = await executor.execute(config)
        
        assert result.success is False
        assert "timeout" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_validate_command(self):
        """Test command validation."""
        executor = BashExecutor()
        
        # Test with host commands enabled (default)
        assert executor._validate_command("echo test") is True
        
        # Test with host commands disabled
        with patch('executors.bash_executor.settings') as mock_settings:
            mock_settings.allow_host_commands = False
            assert executor._validate_command("echo test") is False
        
        # Test with allowed commands list
        with patch('executors.bash_executor.settings') as mock_settings:
            mock_settings.allow_host_commands = True
            mock_settings.allowed_bash_commands = ["echo", "ls"]
            assert executor._validate_command("echo test") is True
            assert executor._validate_command("rm -rf /") is False