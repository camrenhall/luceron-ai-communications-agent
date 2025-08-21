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
from typing import Optional, Dict, Any

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import PORT, BACKEND_URL
from src.models.requests import ChatRequest
from src.models.agent_state import MessageRole, AgentType
from src.services.http_client import init_http_client, close_http_client, get_http_client
from src.services.agent_state_manager import AgentStateManager
from src.agents.callbacks import ConversationCallbackHandler

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
    if request.conversation_id:
        logger.info(f"📨 Incoming chat message: {request.message} (continuing conversation: {request.conversation_id})")
    else:
        logger.info(f"📨 Incoming chat message: {request.message}")
    
    async def generate_stateful_response():
        """Generate response with conversation tracking and context awareness"""
        from src.agents.communications import create_communications_agent
        
        try:
            logger.info(f"🚀 Starting chat processing for message: '{request.message[:100]}...' with conversation_id: {request.conversation_id}")
            
            # Initialize agent state manager
            logger.info(f"🔧 Initializing AgentStateManager")
            state_manager = AgentStateManager()
            logger.info(f"✅ AgentStateManager initialized successfully")
            
            # Phase 1: Determine case context (if possible from message)
            logger.info(f"🔍 Phase 1: Extracting case_id from message")
            case_id = await _extract_case_id_from_message(request.message)
            logger.info(f"✅ Phase 1 complete: case_id = {case_id}")
            
            # Phase 2: Start agent session with conversation and context loading
            logger.info(f"🎯 Phase 2: Starting agent session")
            conversation_id, existing_context = await state_manager.start_agent_session(
                user_message=request.message,
                case_id=case_id,
                conversation_id=request.conversation_id
            )
            logger.info(f"✅ Phase 2 complete: conversation_id = {conversation_id}, context_keys = {list(existing_context.keys()) if existing_context else []}")
            
            # Phase 3: Manage conversation length with intelligent summarization
            logger.info(f"📊 Phase 3: Managing conversation length")
            await state_manager.manage_conversation_length(conversation_id)
            logger.info(f"✅ Phase 3 complete: Conversation length managed")
            
            # Phase 4: Prepare comprehensive agent context
            logger.info(f"🧠 Phase 4: Preparing agent context")
            agent_context = await state_manager.prepare_agent_context(
                conversation_id, existing_context
            )
            logger.info(f"✅ Phase 4 complete: Agent context prepared with keys: {list(agent_context.keys())}")
            
            # Phase 5: Execute agent with conversation tracking and enhanced context
            logger.info(f"🎭 Phase 5: Creating agent and preparing execution")
            callback_handler = ConversationCallbackHandler(
                conversation_id=conversation_id,
                track_to_backend=True
            )
            
            agent = create_communications_agent()
            logger.info(f"✅ Communications agent created successfully")
            
            # Extract and format conversation history from agent_context
            conversation_messages = []
            if agent_context.get("recent_conversation"):
                logger.info(f"📖 Extracting {len(agent_context['recent_conversation'])} messages from conversation history")
                for msg in agent_context["recent_conversation"]:
                    if msg["role"] == "user":
                        conversation_messages.append(("human", msg["content"].get("text", "")))
                    elif msg["role"] == "assistant":
                        conversation_messages.append(("assistant", msg["content"].get("text", "")))
                logger.info(f"✅ Formatted {len(conversation_messages)} conversation messages")
            else:
                logger.info(f"ℹ️ No recent conversation history found")
            
            # Enhanced agent input with conversation history
            agent_input = {
                "input": request.message,
                "conversation_history": conversation_messages
            }
            logger.info(f"🎯 Agent input prepared with {len(conversation_messages)} history messages")
            
            logger.info(f"🚀 Invoking agent with input...")
            result = await agent.ainvoke(
                agent_input,
                config={"callbacks": [callback_handler]}
            )
            logger.info(f"✅ Agent execution completed successfully")
            
            # Phase 6: Extract and store final response
            final_response = _extract_agent_response(result)
            await callback_handler.store_final_response(final_response)
            
            # Phase 7: Store interaction results and update context
            await state_manager.store_interaction_results(
                case_id, final_response, result
            )
            
            # Phase 8: Get conversation metrics
            metrics = await state_manager.get_conversation_metrics(conversation_id)
            
            logger.info(f"✅ Agent completed with response length: {len(final_response)}")
            
            # Send enhanced response event with metrics
            response_data = {
                'type': 'agent_response',
                'conversation_id': conversation_id,
                'case_id': case_id,
                'timestamp': datetime.now().isoformat(),
                'response': final_response,
                'has_context': bool(existing_context),
                'context_keys': list(existing_context.keys()) if existing_context else [],
                'metrics': metrics
            }
            yield f"data: {json.dumps(response_data)}\n\n"
                
        except Exception as e:
            logger.error(f"❌ Agent execution failed: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            error_data = {
                'type': 'agent_error',
                'timestamp': datetime.now().isoformat(),
                'error_message': str(e),
                'error_type': type(e).__name__,
                'recovery_suggestion': "Please try again or rephrase your request"
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_stateful_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


# ============================================================================
# Helper Functions for Stateful Agent Processing
# ============================================================================

async def _extract_case_id_from_message(message: str) -> Optional[str]:
    """Extract case_id from user message using basic heuristics"""
    return None


def _extract_agent_response(result) -> str:
    """Extract the final response from agent output"""
    if not result:
        return ""
    
    agent_output = result.get("output", "") if result else ""
    
    # Handle case where output is an array of message objects
    if isinstance(agent_output, list) and len(agent_output) > 0:
        # Extract text from the first message object
        first_message = agent_output[0]
        if isinstance(first_message, dict) and "text" in first_message:
            return first_message["text"]
        else:
            return str(agent_output)
    else:
        # Output is already a string or empty
        return str(agent_output) if agent_output else ""


# Context management is now handled by AgentStateManager


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)