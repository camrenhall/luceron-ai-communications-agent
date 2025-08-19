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
from src.services.workflow_service import execute_workflow, execute_workflow_with_streaming
from src.services.streaming_coordinator import streaming_session, shutdown_streaming_coordinator
from src.config.settings import BACKEND_URL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_http_client()
    yield
    await close_http_client()
    await shutdown_streaming_coordinator()


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
    
    # Create workflow for auditing/tracking and get backend-generated workflow_id
    state = WorkflowState(
        status=WorkflowStatus.PENDING,
        initial_prompt=request.message,
        reasoning_chain=[],
        created_at=datetime.now()
    )
    
    workflow_id = await create_workflow_state(state)
    
    async def generate_enhanced_stream():
        """Enhanced streaming generator with real-time agent reasoning"""
        import asyncio
        from src.services.streaming_coordinator import get_streaming_coordinator
        
        try:
            # Get coordinator and create stream
            coordinator = await get_streaming_coordinator()
            
            # Execute workflow and stream events concurrently
            async def execute_workflow_task():
                try:
                    final_response = await execute_workflow_with_streaming(workflow_id, request.message)
                    logger.info(f"Workflow {workflow_id} execution completed")
                    return final_response
                except Exception as e:
                    logger.error(f"Workflow {workflow_id} execution failed: {e}")
                    raise
            
            # Start workflow execution
            workflow_task = asyncio.create_task(execute_workflow_task())
            
            # Stream events from coordinator
            try:
                async for event in coordinator.create_stream(workflow_id, request.message):
                    if event:
                        event_data = event.model_dump()
                        # Convert datetime to ISO string for JSON serialization
                        if 'timestamp' in event_data:
                            event_data['timestamp'] = event.timestamp.isoformat()
                        
                        yield f"data: {json.dumps(event_data)}\n\n"
                        
                        # Check if workflow completed
                        if event.type == "workflow_completed":
                            break
                        elif event.type == "workflow_error":
                            break
                            
            except Exception as e:
                logger.error(f"Error in event stream for workflow {workflow_id}: {e}")
                
                # Send error event
                error_data = {
                    'type': 'workflow_error',
                    'workflow_id': workflow_id,
                    'timestamp': datetime.now().isoformat(),
                    'error_message': str(e),
                    'error_type': type(e).__name__
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            
            # Ensure workflow task completes
            if not workflow_task.done():
                try:
                    await asyncio.wait_for(workflow_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Workflow {workflow_id} did not complete within timeout")
                    workflow_task.cancel()
                
        except Exception as e:
            logger.error(f"Critical error in chat streaming for workflow {workflow_id}: {e}")
            error_data = {
                'type': 'workflow_error',
                'workflow_id': workflow_id,
                'timestamp': datetime.now().isoformat(),
                'error_message': str(e),
                'error_type': type(e).__name__
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_enhanced_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow details and final response for fallback access"""
    try:
        logger.info(f"🔍 Retrieving workflow details for {workflow_id}")
        
        # Forward request to backend API
        http_client = get_http_client()
        response = await http_client.get(f"{BACKEND_URL}/api/workflows/{workflow_id}")
        response.raise_for_status()
        
        workflow_data = response.json()
        logger.info(f"✅ Retrieved workflow {workflow_id} with status: {workflow_data.get('status', 'unknown')}")
        
        return workflow_data
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve workflow {workflow_id}: {e}")
        from fastapi import HTTPException
        
        if hasattr(e, 'status_code'):
            if e.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
            elif e.status_code == 403:
                raise HTTPException(status_code=403, detail="Access denied to workflow data")
        
        raise HTTPException(status_code=500, detail=f"Failed to retrieve workflow: {str(e)}")


@app.get("/api/workflows/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """Get workflow status only (lightweight endpoint)"""
    try:
        logger.info(f"📊 Checking status for workflow {workflow_id}")
        
        # Forward request to backend API
        http_client = get_http_client()
        response = await http_client.get(f"{BACKEND_URL}/api/workflows/{workflow_id}")
        response.raise_for_status()
        
        workflow_data = response.json()
        
        # Return minimal status information
        status_info = {
            "workflow_id": workflow_id,
            "status": workflow_data.get("status", "UNKNOWN"),
            "created_at": workflow_data.get("created_at"),
            "updated_at": workflow_data.get("updated_at"),
            "has_final_response": bool(workflow_data.get("final_response"))
        }
        
        logger.info(f"📊 Workflow {workflow_id} status: {status_info['status']}")
        return status_info
        
    except Exception as e:
        logger.error(f"❌ Failed to get status for workflow {workflow_id}: {e}")
        from fastapi import HTTPException
        
        if hasattr(e, 'status_code') and e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)