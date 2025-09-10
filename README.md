# ChronoTask

A lightweight, reliable task scheduler with Docker support, HTTP/MCP APIs, and persistent storage.

## Features

- **Task Types**
  - HTTP/HTTPS requests with custom headers, authentication, and retry logic
  - Bash commands with environment variables and timeout control
  
- **Scheduling Options**
  - One-time execution at specified datetime
  - Cron-based recurring schedules
  - Fixed interval scheduling
  
- **APIs**
  - RESTful HTTP API (FastAPI)
  - MCP (Model Context Protocol) server for AI integration
  
- **Persistence**
  - SQLite database with automatic migrations
  - Full task execution history
  - Survives container restarts
  
- **Docker-First Design**
  - Alpine-based image (~50MB base)
  - Volume-based data persistence
  - Health checks included

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone <repository>
cd chronotask
```

2. Start the service:
```bash
docker-compose up -d
```

3. Check health:
```bash
curl http://localhost:8000/health
```

### Using Docker

```bash
# Build image
docker build -t chronotask .

# Run container
docker run -d \
  --name chronotask \
  -p 8000:8000 \
  -v chronotask-data:/app/data \
  chronotask
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run HTTP server
python src/main.py --mode http

# Run MCP server
python src/main.py --mode mcp

# Run both servers
python src/main.py --mode both
```

## API Usage

### Create a Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Check API Status",
    "task_type": "http",
    "config": {
      "url": "https://api.example.com/status",
      "method": "GET"
    }
  }'
```

### Create a Schedule

```bash
# Cron schedule (every hour)
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 1,
    "schedule_type": "cron",
    "schedule_config": {
      "expression": "0 * * * *"
    }
  }'

# One-time execution
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 1,
    "schedule_type": "once",
    "schedule_config": {
      "datetime": "2024-12-25T10:00:00"
    }
  }'

# Fixed interval (every 30 minutes)
curl -X POST http://localhost:8000/api/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 1,
    "schedule_type": "interval",
    "schedule_config": {
      "seconds": 1800
    }
  }'
```

### Execute Task Immediately

```bash
curl -X POST http://localhost:8000/api/v1/tasks/1/execute
```

### View Task History

```bash
curl http://localhost:8000/api/v1/tasks/1/history
```

## Task Configuration

### HTTP Task

```json
{
  "name": "API Call",
  "task_type": "http",
  "config": {
    "url": "https://api.example.com/endpoint",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer token"
    },
    "body": {
      "key": "value"
    },
    "timeout": 30,
    "params": {
      "query": "param"
    },
    "auth": {
      "username": "user",
      "password": "pass"
    }
  }
}
```

### Bash Task

```json
{
  "name": "Backup Script",
  "task_type": "bash",
  "config": {
    "command": "backup.sh",
    "args": ["--full", "--compress"],
    "env": {
      "BACKUP_DIR": "/backups"
    },
    "working_dir": "/scripts",
    "timeout": 300
  }
}
```

## Cron Expression Format

ChronoTask uses standard cron expression format:

```
* * * * *
│ │ │ │ │
│ │ │ │ └─── Day of week (0-6, Sunday=0)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

Examples:
- `* * * * *` - Every minute
- `0 * * * *` - Every hour
- `0 0 * * *` - Daily at midnight
- `0 9 * * 1-5` - Weekdays at 9 AM
- `*/15 * * * *` - Every 15 minutes
- `0 0 1 * *` - First day of each month

## Environment Variables

```bash
# Database
CHRONOTASK_DATABASE_URL=sqlite:///app/data/chronotask.db

# API Server
CHRONOTASK_API_HOST=0.0.0.0
CHRONOTASK_API_PORT=8000

# Scheduler
CHRONOTASK_SCHEDULER_TIMEZONE=UTC

# Task Execution
CHRONOTASK_HTTP_TIMEOUT=30
CHRONOTASK_BASH_TIMEOUT=300
CHRONOTASK_MAX_RETRIES=3
CHRONOTASK_RETRY_DELAY=5

# Security
CHRONOTASK_ALLOW_HOST_COMMANDS=true
CHRONOTASK_ALLOWED_BASH_COMMANDS=echo,ls,cat  # Optional whitelist

# Logging
CHRONOTASK_LOG_LEVEL=INFO
CHRONOTASK_LOG_FILE=/app/data/chronotask.log

# MCP
CHRONOTASK_MCP_ENABLED=true
CHRONOTASK_MCP_PORT=8001
```

## API Endpoints

### Tasks
- `POST /api/v1/tasks` - Create task
- `GET /api/v1/tasks` - List tasks
- `GET /api/v1/tasks/{id}` - Get task
- `PUT /api/v1/tasks/{id}` - Update task
- `DELETE /api/v1/tasks/{id}` - Delete task
- `POST /api/v1/tasks/{id}/execute` - Execute now
- `GET /api/v1/tasks/{id}/history` - Execution history

### Schedules
- `POST /api/v1/schedules` - Create schedule
- `GET /api/v1/schedules` - List schedules
- `GET /api/v1/schedules/{id}` - Get schedule
- `PUT /api/v1/schedules/{id}` - Update schedule
- `DELETE /api/v1/schedules/{id}` - Delete schedule

### System
- `GET /` - Service info
- `GET /health` - Health check
- `GET /api/v1/scheduler/status` - Scheduler status

## MCP Integration

ChronoTask includes an MCP server for AI-powered task management:

```python
# MCP Tools Available:
- create_task
- list_tasks
- get_task
- update_task
- delete_task
- execute_task
- create_schedule
- list_schedules
- update_schedule
- delete_schedule
- get_task_history
- get_scheduler_status
```

To use with an MCP client, connect to the stdio interface or configure your MCP client to use the ChronoTask MCP server.

## Security Considerations

1. **Host Commands**: By default, bash commands can be executed on the host. Disable with:
   ```
   CHRONOTASK_ALLOW_HOST_COMMANDS=false
   ```

2. **Command Whitelist**: Restrict allowed commands:
   ```
   CHRONOTASK_ALLOWED_BASH_COMMANDS=echo,ls,date
   ```

3. **Docker Socket**: The docker-compose.yml includes a commented section for mounting the Docker socket. Only enable if you need to run Docker commands from tasks.

4. **Network Isolation**: Consider using Docker networks to isolate ChronoTask from other services.

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## Architecture

```
ChronoTask
├── Database Layer (SQLite)
│   ├── Tasks
│   ├── Schedules
│   └── Execution History
├── Scheduler Core (APScheduler)
│   ├── Cron Parser
│   ├── Trigger Manager
│   └── Job Queue
├── Task Executors
│   ├── HTTP Executor
│   └── Bash Executor
├── API Layer
│   ├── FastAPI HTTP Server
│   └── MCP Server
└── Docker Container
    ├── Alpine Linux
    ├── Python 3.11
    └── Persistent Volume
```

## Troubleshooting

### Container won't start
Check logs: `docker logs chronotask`

### Tasks not executing
1. Check scheduler status: `curl http://localhost:8000/api/v1/scheduler/status`
2. Verify task is active: `curl http://localhost:8000/api/v1/tasks/{id}`
3. Check execution history: `curl http://localhost:8000/api/v1/tasks/{id}/history`

### Database issues
The database is stored in `/app/data/chronotask.db`. Back up regularly:
```bash
docker exec chronotask cat /app/data/chronotask.db > backup.db
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please ensure:
1. Tests pass (`pytest tests/`)
2. Code follows Python conventions
3. Documentation is updated

## Support

For issues, questions, or feature requests, please open an issue on GitHub.