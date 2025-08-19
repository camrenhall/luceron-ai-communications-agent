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
from src.services.http_client import init_http_client, close_http_client, get_http_client
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
    
    async def generate_response():
        """Generate direct response without workflow tracking"""
        from src.agents.communications import create_communications_agent
        
        try:
            # Execute agent directly without workflow persistence
            agent = create_communications_agent()
            result = await agent.ainvoke({"input": request.message})
            
            # Extract the final response from the agent's output
            if not result:
                final_response = ""
            else:
                agent_output = result.get("output", "") if result else ""
                
                # Handle case where output is an array of message objects
                if isinstance(agent_output, list) and len(agent_output) > 0:
                    # Extract text from the first message object
                    first_message = agent_output[0]
                    if isinstance(first_message, dict) and "text" in first_message:
                        final_response = first_message["text"]
                    else:
                        final_response = str(agent_output)
                else:
                    # Output is already a string or empty
                    final_response = str(agent_output) if agent_output else ""
            
            logger.info(f"Agent completed with response length: {len(final_response)}")
            
            # Send simple response event
            response_data = {
                'type': 'agent_response',
                'timestamp': datetime.now().isoformat(),
                'response': final_response
            }
            yield f"data: {json.dumps(response_data)}\n\n"
                
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            error_data = {
                'type': 'agent_error',
                'timestamp': datetime.now().isoformat(),
                'error_message': str(e),
                'error_type': type(e).__name__
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)