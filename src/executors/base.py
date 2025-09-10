"""Base executor class and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a task execution."""
    success: bool
    started_at: datetime
    finished_at: datetime
    duration: float  # seconds
    output: Any = None
    error: str = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration": self.duration,
            "output": self.output,
            "error": self.error,
            "retry_count": self.retry_count
        }


class BaseExecutor(ABC):
    """Base class for task executors."""
    
    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    @abstractmethod
    async def execute(self, config: Dict[str, Any]) -> ExecutionResult:
        """Execute the task with given configuration."""
        pass
    
    async def execute_with_retry(self, config: Dict[str, Any]) -> ExecutionResult:
        """Execute task with automatic retry on failure."""
        import asyncio
        
        last_error = None
        retry_count = 0
        
        for attempt in range(self.max_retries + 1):
            try:
                result = await self.execute(config)
                
                if result.success:
                    result.retry_count = retry_count
                    return result
                
                last_error = result.error
                
                if attempt < self.max_retries:
                    logger.warning(f"Execution failed (attempt {attempt + 1}/{self.max_retries + 1}): {last_error}")
                    await asyncio.sleep(self.retry_delay)
                    retry_count += 1
                else:
                    result.retry_count = retry_count
                    return result
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"Execution error (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                    retry_count += 1
                else:
                    # Return failure result on last attempt
                    started_at = datetime.utcnow()
                    return ExecutionResult(
                        success=False,
                        started_at=started_at,
                        finished_at=datetime.utcnow(),
                        duration=(datetime.utcnow() - started_at).total_seconds(),
                        error=last_error,
                        retry_count=retry_count
                    )
        
        # Should not reach here
        started_at = datetime.utcnow()
        return ExecutionResult(
            success=False,
            started_at=started_at,
            finished_at=datetime.utcnow(),
            duration=0,
            error=last_error or "Unknown error",
            retry_count=retry_count
        )