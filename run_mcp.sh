#!/bin/bash
# Run ChronoTask MCP server in interactive mode

echo "Starting ChronoTask MCP Server..."
echo "Send JSON-RPC requests to stdin, receive responses on stdout"
echo ""
echo "Example requests:"
echo '  {"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
echo '  {"jsonrpc":"2.0","method":"list_tools","params":{},"id":2}'
echo '  {"jsonrpc":"2.0","method":"call_tool","params":{"name":"list_tasks","arguments":{}},"id":3}'
echo ""
echo "Starting MCP server..."

docker exec -i chronotask python -m src.mcp.scheduler_server