#!/usr/bin/env python3
"""Simple test without database to verify basic functionality."""

from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "ChronoTask Test", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    print("Starting test server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)