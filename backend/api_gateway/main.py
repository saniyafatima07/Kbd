from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from typing import Dict, Any, List
import uvicorn
import pika
import json

app = FastAPI(
    title="KubeMinder API Gateway",
    description="Unified API gateway for all KubeMinder agents",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:8080",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent endpoints mapping
AGENT_ENDPOINTS = {
    "planner": "http://localhost:8001",
    "collaborator": "http://localhost:8002", 
    "actor": "http://localhost:8003",
    "learner": "http://localhost:8004"
}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "KubeMinder API Gateway",
        "version": "1.0.0",
        "agents": list(AGENT_ENDPOINTS.keys())
    }

@app.get("/api/health")
async def health_check():
    """Check health of all agents"""
    health_status = {}
    async with httpx.AsyncClient() as client:
        for agent, url in AGENT_ENDPOINTS.items():
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                health_status[agent] = {
                    "status": "healthy",
                    "response": response.json()
                }
            except Exception as e:
                health_status[agent] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
    return {
        "gateway": "healthy",
        "agents": health_status,
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/api/incidents")
async def get_incidents():
    """Get incidents from planner agent"""
    # This will be implemented when you add incident storage
    return {
        "incidents": [],
        "message": "Incident storage not yet implemented",
        "status": "success"
    }

@app.post("/api/query")
async def submit_query(query: Dict[str, Any]):
    """Submit natural language query to collaborator"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_ENDPOINTS['collaborator']}/api/query",
                json=query,
                timeout=30.0
            )
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/api/stats")
async def get_stats():
    """Get learner agent statistics"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AGENT_ENDPOINTS['learner']}/stats")
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")

@app.get("/api/agents")
async def get_agents():
    """Get information about all agents"""
    return {
        "agents": [
            {
                "name": "planner",
                "url": AGENT_ENDPOINTS["planner"],
                "description": "Analyzes incidents and creates remediation plans"
            },
            {
                "name": "collaborator", 
                "url": AGENT_ENDPOINTS["collaborator"],
                "description": "Handles user interactions and approvals"
            },
            {
                "name": "actor",
                "url": AGENT_ENDPOINTS["actor"],
                "description": "Executes approved remediation plans"
            },
            {
                "name": "learner",
                "url": AGENT_ENDPOINTS["learner"],
                "description": "Documents incidents and updates knowledge base"
            }
        ]
    }

RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"

@app.post("/api/plans/forward-to-approved")
async def forward_plans_to_approved():
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()

        forwarded_count = 0
        while True:
            method, properties, body = channel.basic_get(queue="q.plans.proposed", auto_ack=False)
            if not method:
                break

            try:
                plan = json.loads(body)
            except Exception as e:
                channel.basic_ack(delivery_tag=method.delivery_tag)
                print("❌ Failed to decode plan:", body, e)
                continue

            plan["status"] = "approved"
            plan["approved_by"] = "gateway"

            # ✅ Properly aligned with plan update
            channel.basic_publish(
                exchange="",   # default direct exchange
                routing_key="q.plans.approved",  # forward directly to the approved queue
                body=json.dumps(plan),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2
                )
            )

            channel.basic_ack(delivery_tag=method.delivery_tag)
            forwarded_count += 1

        connection.close()
        return {"status": "success", "forwarded_count": forwarded_count}

    except Exception as e:
        print("🔥 Forwarding error:", e)
        raise HTTPException(status_code=500, detail=f"Failed to forward plans: {str(e)}")


if __name__ == "__main__":
    print("🚀 Starting KubeMinder API Gateway on port 8005...")
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
