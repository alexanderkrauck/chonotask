"""Bash command executor."""

import asyncio
import os
import shlex
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
from .base import BaseExecutor, ExecutionResult
from config import settings

logger = logging.getLogger(__name__)


class BashExecutor(BaseExecutor):
    """Executor for bash commands on the host system."""
    
    def _validate_command(self, command: str) -> bool:
        """Validate if command is allowed to run."""
        if not settings.allow_host_commands:
            logger.error("Host commands are disabled in configuration")
            return False
        
        if settings.allowed_bash_commands:
            # Check if command is in allowed list
            cmd_parts = shlex.split(command)
            if cmd_parts and cmd_parts[0] not in settings.allowed_bash_commands:
                logger.error(f"Command '{cmd_parts[0]}' not in allowed commands list")
                return False
        
        return True
    
    async def execute(self, config: Dict[str, Any]) -> ExecutionResult:
        """Execute a bash command based on configuration.
        
        Config structure:
        {
            "command": "echo 'Hello World'",
            "args": ["arg1", "arg2"],  # Optional arguments
            "env": {"VAR1": "value1"},  # Environment variables
            "working_dir": "/path/to/dir",  # Working directory
            "timeout": 300,  # seconds
            "shell": true,  # Whether to use shell
            "capture_output": true  # Whether to capture output
        }
        """
        started_at = datetime.utcnow()
        
        try:
            # Extract configuration
            command = config.get("command")
            if not command:
                raise ValueError("Command is required for bash task")
            
            # Validate command
            if not self._validate_command(command):
                raise ValueError(f"Command not allowed: {command}")
            
            args = config.get("args", [])
            env_vars = config.get("env", {})
            working_dir = config.get("working_dir")
            timeout = config.get("timeout", settings.bash_timeout)
            use_shell = config.get("shell", True)
            capture_output = config.get("capture_output", True)
            
            # Build full command
            if args and not use_shell:
                # If not using shell, command should be a list
                full_command = [command] + args
            elif args and use_shell:
                # If using shell, append args to command string
                full_command = f"{command} {' '.join(shlex.quote(arg) for arg in args)}"
            else:
                full_command = command
            
            # Prepare environment
            env = os.environ.copy()
            env.update(env_vars)
            
            # Log execution
            logger.info(f"Executing bash command: {command}")
            if args:
                logger.debug(f"Arguments: {args}")
            if env_vars:
                logger.debug(f"Environment variables: {list(env_vars.keys())}")
            if working_dir:
                logger.debug(f"Working directory: {working_dir}")
            
            # Execute command
            if use_shell:
                process = await asyncio.create_subprocess_shell(
                    full_command,
                    stdout=asyncio.subprocess.PIPE if capture_output else None,
                    stderr=asyncio.subprocess.PIPE if capture_output else None,
                    cwd=working_dir,
                    env=env
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *full_command,
                    stdout=asyncio.subprocess.PIPE if capture_output else None,
                    stderr=asyncio.subprocess.PIPE if capture_output else None,
                    cwd=working_dir,
                    env=env
                )
            
            try:
                # Wait for completion with timeout
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                finished_at = datetime.utcnow()
                duration = (finished_at - started_at).total_seconds()
                
                # Prepare output
                output = {
                    "exit_code": process.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                    "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
                    "command": command,
                    "args": args
                }
                
                success = process.returncode == 0
                
                if success:
                    logger.info(f"Command completed successfully (exit code: {process.returncode})")
                else:
                    logger.warning(f"Command failed with exit code: {process.returncode}")
                
                return ExecutionResult(
                    success=success,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration=duration,
                    output=output,
                    error=None if success else f"Exit code: {process.returncode}"
                )
                
            except asyncio.TimeoutError:
                # Kill the process on timeout
                process.kill()
                await process.wait()
                
                finished_at = datetime.utcnow()
                duration = (finished_at - started_at).total_seconds()
                error_msg = f"Command timeout after {timeout} seconds"
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
            error_msg = f"Bash command failed: {str(e)}"
            logger.error(error_msg)
            
            return ExecutionResult(
                success=False,
                started_at=started_at,
                finished_at=finished_at,
                duration=duration,
                error=error_msg
            )