"""Task executor manager for the scheduler."""

from typing import Dict, Any, Optional
from executors import HTTPExecutor, BashExecutor, BaseExecutor, ExecutionResult
import logging

logger = logging.getLogger(__name__)


class TaskExecutorManager:
    """Manages task execution for different task types."""

    def __init__(self):
        self.executors: Dict[str, BaseExecutor] = {
            'http': HTTPExecutor(),
            'bash': BashExecutor()
        }

    async def execute(self, task_type: str, config: Dict[str, Any],
                     max_retries: int = 3, retry_delay: int = 5) -> ExecutionResult:
        """Execute a task based on its type and configuration.

        Args:
            task_type: Type of task to execute ('http', 'bash', etc.)
            config: Task configuration
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds

        Returns:
            ExecutionResult object
        """
        executor = self.executors.get(task_type)

        if not executor:
            raise ValueError(f"No executor available for task type: {task_type}")

        # Configure retry settings
        executor.max_retries = max_retries
        executor.retry_delay = retry_delay

        # Execute with retry
        result = await executor.execute_with_retry(config)

        return result

    def register_executor(self, task_type: str, executor: BaseExecutor):
        """Register a custom executor for a task type.

        Args:
            task_type: Task type to register executor for
            executor: Executor instance
        """
        self.executors[task_type] = executor
        logger.info(f"Registered executor for task type: {task_type}")

    def get_executor(self, task_type: str) -> Optional[BaseExecutor]:
        """Get executor for a task type.

        Args:
            task_type: Task type

        Returns:
            Executor instance or None if not found
        """
        return self.executors.get(task_type)