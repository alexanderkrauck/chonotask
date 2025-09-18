"""Configuration settings for ChronoTask."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database  
    database_url: str = "sqlite:////app/data/chronotask.db"
    database_echo: bool = False
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    
    # Scheduler
    scheduler_timezone: str = "UTC"
    scheduler_job_defaults: dict = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 30
    }
    
    # Executor settings
    http_timeout: int = 30
    bash_timeout: int = 300
    max_retries: int = 3
    retry_delay: int = 5
    
    # Security
    allow_host_commands: bool = True
    allowed_bash_commands: list = []  # Empty means all commands allowed

    # Query execution
    query_timeout: int = 5  # Maximum execution time in seconds
    query_max_result_size: int = 100000  # Maximum result size in bytes
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "data/chronotask.log"
    
    # MCP
    mcp_enabled: bool = True
    mcp_port: int = 8001
    
    class Config:
        env_prefix = "CHRONOTASK_"
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()