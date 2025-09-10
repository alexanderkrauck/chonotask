#!/usr/bin/env python3
"""Full MCP protocol test."""

import requests
import json

url = "http://localhost:8000/api/v1/mcp"

# Test 1: Initialize
print("1. Testing initialize...")
init_req = {
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
        "protocolVersion": "0.1.0",
        "capabilities": {
            "roots": {},
            "sampling": {}
        },
        "clientInfo": {
            "name": "test-client",
            "version": "1.0.0"
        }
    },
    "id": 1
}

response = requests.post(url, json=init_req)
print(f"Status: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

session_id = response.headers.get("mcp-session-id")
print(f"\nSession ID: {session_id}")

# Test 2: List tools with session
print("\n2. Testing list_tools with session...")
list_req = {
    "jsonrpc": "2.0",
    "method": "list_tools",
    "params": {},
    "id": 2
}

headers = {"Content-Type": "application/json"}
if session_id:
    headers["Mcp-Session-Id"] = session_id

response = requests.post(url, json=list_req, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)[:500]}...")

# Test 3: Test GET endpoint
print("\n3. Testing GET endpoint...")
response = requests.get(url)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 4: Test OPTIONS
print("\n4. Testing OPTIONS...")
response = requests.options(url)
print(f"Status: {response.status_code}")
print(f"Allow header: {response.headers.get('Allow')}")
print(f"CORS headers: {response.headers.get('Access-Control-Allow-Methods')}")