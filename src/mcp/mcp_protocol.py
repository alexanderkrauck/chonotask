"""Simple MCP protocol implementation without external dependencies."""

import json
import asyncio
import sys
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MCPServer:
    """Simple MCP-compatible JSON-RPC server."""
    
    def __init__(self, name: str = "chronotask-scheduler"):
        self.name = name
        self.methods = {}
        self._setup_default_methods()
    
    def _setup_default_methods(self):
        """Set up default MCP methods."""
        self.methods["initialize"] = self._handle_initialize
        self.methods["list_tools"] = self._handle_list_tools
        self.methods["call_tool"] = self._handle_call_tool
    
    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "server_info": {
                "name": self.name,
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": True
            }
        }
    
    async def _handle_list_tools(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List available tools."""
        return [
            {
                "name": "create_task",
                "description": "Create a new scheduled task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "task_type": {"type": "string", "enum": ["http", "bash"]},
                        "config": {"type": "object"}
                    },
                    "required": ["name", "task_type", "config"]
                }
            },
            {
                "name": "list_tasks",
                "description": "List all tasks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["active", "paused", "disabled"]}
                    }
                }
            },
            {
                "name": "execute_task",
                "description": "Execute a task immediately",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"}
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "create_schedule",
                "description": "Create a schedule for a task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "schedule_type": {"type": "string", "enum": ["once", "cron", "interval"]},
                        "schedule_config": {"type": "object"}
                    },
                    "required": ["task_id", "schedule_type", "schedule_config"]
                }
            },
            {
                "name": "delete_task",
                "description": "Delete a task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"}
                    },
                    "required": ["task_id"]
                }
            }
        ]
    
    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool calls."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        # Import here to avoid circular imports
        from database import db_manager
        from scheduler import SchedulerManager
        from models import Task, TaskType, TaskStatus, Schedule, ScheduleType
        
        scheduler = SchedulerManager(db_manager)
        
        try:
            if tool_name == "create_task":
                with db_manager.get_session() as session:
                    task = Task(
                        name=arguments["name"],
                        description=arguments.get("description"),
                        task_type=TaskType(arguments["task_type"]),
                        config=arguments["config"],
                        status=TaskStatus.ACTIVE
                    )
                    session.add(task)
                    session.commit()
                    session.refresh(task)
                    return {"success": True, "task": task.to_dict()}
            
            elif tool_name == "list_tasks":
                with db_manager.get_session() as session:
                    query = session.query(Task)
                    if "status" in arguments:
                        query = query.filter(Task.status == TaskStatus(arguments["status"]))
                    tasks = query.all()
                    return {"success": True, "tasks": [t.to_dict() for t in tasks]}
            
            elif tool_name == "execute_task":
                success = await scheduler.execute_task_now(arguments["task_id"])
                return {"success": success}
            
            elif tool_name == "create_schedule":
                schedule = scheduler.create_schedule(
                    task_id=arguments["task_id"],
                    schedule_type=ScheduleType(arguments["schedule_type"]),
                    schedule_config=arguments["schedule_config"]
                )
                return {"success": schedule is not None, "schedule_id": schedule.id if schedule else None}
            
            elif tool_name == "delete_task":
                with db_manager.get_session() as session:
                    task = session.query(Task).filter_by(id=arguments["task_id"]).first()
                    if task:
                        session.delete(task)
                        session.commit()
                        return {"success": True}
                    return {"success": False, "error": "Task not found"}
            
            else:
                return {"error": f"Unknown tool: {tool_name}"}
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method in self.methods:
                result = await self.methods[method](params)
                return {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": request_id
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    },
                    "id": request_id
                }
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e)
                },
                "id": request_id
            }
    
    async def run_stdio(self):
        """Run MCP server on stdio."""
        logger.info("Starting MCP server on stdio")
        
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        writer = sys.stdout
        
        while True:
            try:
                # Read line from stdin
                line = await reader.readline()
                if not line:
                    break
                
                # Parse JSON-RPC request
                request = json.loads(line.decode())
                logger.debug(f"Received request: {request}")
                
                # Handle request
                response = await self.handle_request(request)
                
                # Write response
                writer.write(json.dumps(response).encode() + b'\n')
                writer.flush()
                
            except Exception as e:
                logger.error(f"Error in stdio loop: {e}")
                break