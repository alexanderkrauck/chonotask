"""HTTP task executor."""

import httpx
from datetime import datetime
from typing import Any, Dict
import json
import logging
from .base import BaseExecutor, ExecutionResult

logger = logging.getLogger(__name__)


class HTTPExecutor(BaseExecutor):
    """Executor for HTTP/HTTPS requests."""
    
    async def execute(self, config: Dict[str, Any]) -> ExecutionResult:
        """Execute an HTTP request based on configuration.
        
        Config structure:
        {
            "url": "https://api.example.com/endpoint",
            "method": "POST",  # GET, POST, PUT, DELETE, PATCH, etc.
            "headers": {"Content-Type": "application/json"},
            "body": {"key": "value"},  # Can be dict (JSON) or string
            "timeout": 30,  # seconds
            "params": {"query": "param"},  # URL query parameters
            "auth": {"username": "user", "password": "pass"}  # Basic auth
        }
        """
        started_at = datetime.utcnow()
        
        try:
            # Extract configuration
            url = config.get("url")
            if not url:
                raise ValueError("URL is required for HTTP task")
            
            method = config.get("method", "GET").upper()
            headers = config.get("headers", {})
            body = config.get("body")
            timeout = config.get("timeout", 30)
            params = config.get("params")
            auth_config = config.get("auth")
            
            # Prepare request arguments
            request_args = {
                "method": method,
                "url": url,
                "headers": headers,
                "timeout": timeout
            }
            
            if params:
                request_args["params"] = params
            
            # Handle authentication
            if auth_config:
                username = auth_config.get("username")
                password = auth_config.get("password")
                if username and password:
                    request_args["auth"] = (username, password)
            
            # Handle request body
            if body is not None:
                if isinstance(body, dict):
                    # Automatically serialize dict to JSON
                    request_args["json"] = body
                    if "Content-Type" not in headers:
                        headers["Content-Type"] = "application/json"
                elif isinstance(body, str):
                    request_args["content"] = body
                else:
                    request_args["content"] = str(body)
            
            # Execute request
            async with httpx.AsyncClient() as client:
                logger.info(f"Executing HTTP {method} request to {url}")
                response = await client.request(**request_args)
                
                finished_at = datetime.utcnow()
                duration = (finished_at - started_at).total_seconds()
                
                # Parse response
                output = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": None
                }
                
                # Try to parse response body
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    try:
                        output["body"] = response.json()
                    except json.JSONDecodeError:
                        output["body"] = response.text
                else:
                    output["body"] = response.text
                
                # Determine success based on status code
                success = 200 <= response.status_code < 300
                
                logger.info(f"HTTP request completed with status {response.status_code}")
                
                return ExecutionResult(
                    success=success,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration=duration,
                    output=output,
                    error=None if success else f"HTTP {response.status_code}"
                )
                
        except httpx.TimeoutException as e:
            finished_at = datetime.utcnow()
            duration = (finished_at - started_at).total_seconds()
            error_msg = f"Request timeout after {timeout} seconds"
            logger.error(error_msg)
            
            return ExecutionResult(
                success=False,
                started_at=started_at,
                finished_at=finished_at,
                duration=duration,
                error=error_msg
            )
            
        except Exception as e:
            finished_at = datetime.utcnow()
            duration = (finished_at - started_at).total_seconds()
            error_msg = f"HTTP request failed: {str(e)}"
            logger.error(error_msg)
            
            return ExecutionResult(
                success=False,
                started_at=started_at,
                finished_at=finished_at,
                duration=duration,
                error=error_msg
            )