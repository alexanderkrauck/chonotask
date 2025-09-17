# ChronoTask

Task scheduling and automation service with HTTP API and MCP support.

## Quick Start

### Docker Commands

```bash
# Build the image
docker build -t chronotask .

# Run the container
docker run -d \
  --name chronotask \
  -p 8000:8000 \
  -v chronotask-data:/app/data \
  chronotask

# View logs
docker logs -f chronotask

# Stop and remove
docker stop chronotask
docker rm chronotask

# Clean up volume
docker volume rm chronotask-data
```

### Docker Compose

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Rebuild after code changes
docker-compose up -d --build
```

## Development

### Local Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python src/server.py

# Run with custom settings
export API_HOST=0.0.0.0
export API_PORT=8000
python src/server.py
```

### Database

```bash
# Database is auto-created at data/chronotask.db
# To reset the database
rm data/chronotask.db
```

### Testing the API

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Create a task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Task",
    "task_type": "http",
    "execution_config": "{\"url\": \"https://httpbin.org/get\", \"method\": \"GET\", \"timeout\": 30}"
  }'

# List tasks
curl http://localhost:8000/api/v1/tasks

# Execute task immediately
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/execute

# Create a schedule
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_config": "{\"type\": \"interval\", \"seconds\": 300}"
  }'
```

## Environment Variables

```bash
# API Configuration
API_HOST=0.0.0.0         # Default: 0.0.0.0
API_PORT=8000            # Default: 8000
LOG_LEVEL=INFO           # Default: INFO

# Database
DATABASE_URL=sqlite:///data/chronotask.db  # Default location

# Scheduler
SCHEDULER_TIMEZONE=UTC   # Default: UTC
```

## Modeling Criteria

ChronoTask can model **criteria** - ongoing conditions that should always be maintained. Unlike tasks that complete once, criteria are continuously monitored.

**Pattern**: Use `'todo'` task type + periodic scheduling + completion criteria

```json
{
  "name": "API Health Check",
  "task_type": "todo",
  "completion_criteria": "{\"type\": \"manual\"}",
  "schedule_config": "{\"type\": \"interval\", \"seconds\": 300}",
  "schedule_enabled": true
}
```

Criteria transition between `'open'` (unmet) and `'completed'` (met) states. Other tasks can depend on criteria being met.

## API Endpoints

- **API Docs**: http://localhost:8000/api/v1/docs
- **Health**: http://localhost:8000/api/v1/health
- **MCP**: http://localhost:8000/llm/mcp

## Directory Structure

```
chronotask/
├── src/
│   ├── server.py         # Main FastAPI + MCP server
│   ├── models/           # Database models
│   ├── scheduler/        # Task scheduling logic
│   ├── executors/        # Task executors (HTTP, Bash)
│   └── database/         # Database management
├── data/                 # SQLite database (auto-created)
├── requirements.txt      # Python dependencies
├── Dockerfile
└── docker-compose.yml
```

## Debugging

```bash
# Check running containers
docker ps

# Check scheduler status
curl http://localhost:8585/api/v1/status

# View task history
curl http://localhost:8585/api/v1/tasks/{task_id}/history

# Interactive shell in container
docker exec -it chronotask /bin/bash

# Python shell with app context
docker exec -it chronotask python
>>> from src.database import db_manager
>>> from src.models import Task
>>> with db_manager.get_session() as session:
...     tasks = session.query(Task).all()
```

## Common Issues

### Port already in use
```bash
# Find process using port
lsof -i :8000
# Or change port
docker run -p 8001:8000 chronotask
```

### Database locked
```bash
# Restart the container
docker restart chronotask
```

### Schedule not running
```bash
# Check scheduler status
curl http://localhost:8000/api/v1/status

# Check task status
curl http://localhost:8000/api/v1/tasks/{task_id}
```