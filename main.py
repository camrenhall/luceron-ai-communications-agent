"""
Communications Agent - FastAPI Application
"""
import json
import logging
import sys
import os
import uuid
from datetime import datetime
from contextlib import asynccontextmanager

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import PORT
from src.models.requests import ChatRequest
from src.models.workflow import WorkflowState, WorkflowStatus
from src.services.http_client import init_http_client, close_http_client, get_http_client
from src.services.backend_api import create_workflow_state
from src.services.workflow_service import execute_workflow
from src.config.settings import BACKEND_URL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_http_client()
    yield
    await close_http_client()


app = FastAPI(
    title="Communications Agent",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://simple-s3-upload.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    http_client = get_http_client()
    response = await http_client.get(f"{BACKEND_URL}/")
    response.raise_for_status()
    return {"status": "operational", "backend": "connected"}


@app.get("/status")
async def status_check():
    """Status endpoint"""
    return {"status": "running", "service": "communications-agent"}


@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    logger.info(f"📨 Incoming chat message: {request.message}")
    workflow_id = f"wf_chat_{uuid.uuid4().hex[:8]}"
    
    # Create workflow
    state = WorkflowState(
        workflow_id=workflow_id,
        status=WorkflowStatus.PENDING,
        initial_prompt=request.message,
        reasoning_chain=[],
        created_at=datetime.now()
    )
    
    await create_workflow_state(state)
    
    async def generate_stream():
        try:
            yield f"data: {json.dumps({'type': 'started', 'workflow_id': workflow_id})}\n\n"
            
            await execute_workflow(workflow_id)
            
            yield f"data: {json.dumps({'type': 'completed'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)