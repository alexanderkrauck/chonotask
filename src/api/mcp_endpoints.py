"""MCP endpoint for FastAPI - unified server approach."""

from fastapi import APIRouter, Request, Response, Header, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime
import secrets
import uuid

from models import Task, TaskType, TaskStatus, Schedule, ScheduleType
from database import get_db
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()


class MCPHandler:
    """Handle MCP protocol requests within FastAPI."""
    
    def __init__(self):
        self.methods = {
            "initialize": self._handle_initialize,
            "list_tools": self._handle_list_tools,
            "tools/list": self._handle_list_tools,  # Alternative method name
            "call_tool": self._handle_call_tool,
            "tools/call": self._handle_call_tool,  # Alternative method name
        }
        # Store active sessions
        self.sessions = {}
    
    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request."""
        # Generate a secure session ID
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "created_at": datetime.utcnow(),
            "protocol_version": params.get("protocolVersion", "2024-11-05"),
            "capabilities": params.get("capabilities", {})
        }
        
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "chronotask-scheduler",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            },
            "sessionId": session_id
        }
    
    async def _handle_list_tools(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List available MCP tools."""
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
                "name": "get_scheduler_status",
                "description": "Get scheduler status",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP tool calls using the same scheduler as HTTP."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        # Get the shared scheduler instance from HTTP server
        from api.http_server import scheduler_manager as scheduler
        
        # Use dependency injection to get database session
        from database import db_manager
        
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
                return {"success": success, "message": f"Task {arguments['task_id']} {'started' if success else 'failed'}"}
            
            elif tool_name == "create_schedule":
                schedule = scheduler.create_schedule(
                    task_id=arguments["task_id"],
                    schedule_type=ScheduleType(arguments["schedule_type"]),
                    schedule_config=arguments["schedule_config"]
                )
                if schedule:
                    with db_manager.get_session() as session:
                        fresh_schedule = session.query(Schedule).filter_by(id=schedule.id).first()
                        return {"success": True, "schedule": fresh_schedule.to_dict() if fresh_schedule else None}
                return {"success": False, "error": "Failed to create schedule"}
            
            elif tool_name == "get_scheduler_status":
                status = scheduler.get_scheduler_status()
                return {"success": True, "status": status}
            
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
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
            logger.error(f"Error handling MCP request: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e)
                },
                "id": request_id
            }


# Global MCP handler instance
mcp_handler = MCPHandler()


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    response: Response,
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id")
):
    """Handle MCP JSON-RPC requests over HTTP POST."""
    try:
        json_request = await request.json()
        
        # Handle initialize specially - it creates a session
        if json_request.get("method") == "initialize":
            result = await mcp_handler.handle_request(json_request)
            # Add session ID to response header if created
            if "result" in result and "sessionId" in result["result"]:
                response.headers["Mcp-Session-Id"] = result["result"]["sessionId"]
            return result
        
        # For other methods, validate session if provided
        if mcp_session_id and mcp_session_id not in mcp_handler.sessions:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": "Invalid session ID"
                },
                "id": json_request.get("id")
            }
        
        result = await mcp_handler.handle_request(json_request)
        return result
    except json.JSONDecodeError:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32700,
                "message": "Parse error"
            },
            "id": None
        }


@router.get("/mcp")
async def mcp_get_endpoint(
    accept: Optional[str] = Header(None),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id")
):
    """Handle MCP GET requests for SSE streaming."""
    # Check if client wants SSE
    if accept and "text/event-stream" in accept:
        async def event_generator():
            """Generate SSE events."""
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
            
            # Keep connection alive with ping events
            while True:
                await asyncio.sleep(30)
                yield f"data: {json.dumps({'type': 'ping', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    else:
        # Return server info for regular GET
        return {
            "name": "chronotask-scheduler",
            "version": "1.0.0",
            "protocol": "mcp",
            "transport": ["http", "sse"]
        }


@router.options("/mcp")
async def mcp_options_endpoint():
    """Handle OPTIONS requests for CORS preflight."""
    return Response(
        headers={
            "Allow": "GET, POST, OPTIONS",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Mcp-Session-Id, Authorization, Accept",
            "Access-Control-Max-Age": "86400"
        }
    )


@router.get("/mcp/sse")
async def mcp_sse_endpoint():
    """Legacy SSE endpoint for backward compatibility."""
    async def event_generator():
        """Generate SSE events."""
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
        
        # Keep connection alive
        while True:
            await asyncio.sleep(30)
            yield f"data: {json.dumps({'type': 'ping', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.get("/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools via HTTP GET."""
    tools = await mcp_handler._handle_list_tools({})
    return {"tools": tools}


@router.post("/mcp/tools/{tool_name}")
async def call_mcp_tool(tool_name: str, request: Request):
    """Call an MCP tool directly via HTTP POST."""
    try:
        arguments = await request.json()
        result = await mcp_handler._handle_call_tool({
            "name": tool_name,
            "arguments": arguments
        })
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}