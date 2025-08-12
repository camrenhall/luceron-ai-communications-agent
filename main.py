"""
Client Communications Agent - Refactored
AI-powered client reminder system that orchestrates backend API calls
"""

import os
import logging
import json
import asyncio
from datetime import datetime
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL")
PORT = int(os.getenv("PORT", 8080))

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
if not BACKEND_URL:
    raise ValueError("BACKEND_URL environment variable is required")

# HTTP client for backend calls
http_client = None

# Request models
class ChatRequest(BaseModel):
    message: str
    dry_run: bool = False

class ProcessRemindersRequest(BaseModel):
    dry_run: bool = False

class ProcessRemindersResponse(BaseModel):
    status: str
    cases_processed: int
    summary: str

# HTTP client management
async def init_http_client():
    """Initialize HTTP client"""
    global http_client
    http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("HTTP client initialized")

async def close_http_client():
    """Close HTTP client"""
    global http_client
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")

# LangChain Tools that call backend APIs
class CheckCaseStatusTool(BaseTool):
    """Tool to check cases needing reminder communications via backend API"""
    name: str = "check_case_status"
    description: str = "Check for cases awaiting documents that haven't been contacted in the last 3 days. Returns list of cases requiring reminder emails."
    
    def _run(self, query: str = "") -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, query: str = "") -> str:
        try:
            logger.info("🔍 CheckCaseStatus: Calling backend API...")
            
            response = await http_client.get(f"{BACKEND_URL}/api/cases/pending-reminders")
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"🔍 CheckCaseStatus: Backend returned {data['found_cases']} cases")
            
            return json.dumps(data, indent=2)
            
        except httpx.HTTPError as e:
            error_msg = f"Backend API error: {str(e)}"
            logger.error(f"🔍 CheckCaseStatus ERROR: {error_msg}")
            return json.dumps({"error": error_msg})
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"🔍 CheckCaseStatus ERROR: {error_msg}")
            return json.dumps({"error": error_msg})

class SendEmailTool(BaseTool):
    """Tool to send reminder emails to clients via backend API"""
    name: str = "send_email"
    description: str = "Send reminder email to client. Input: JSON with recipient_email, subject, body, case_id"
    dry_run: bool = False
    
    def __init__(self, dry_run: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.dry_run = dry_run
    
    def _run(self, email_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, email_data: str) -> str:
        try:
            logger.info("📧 SendEmail: Parsing email data...")
            data = json.loads(email_data)
            required_fields = ["recipient_email", "subject", "body", "case_id"]
            
            for field in required_fields:
                if field not in data:
                    error_msg = f"Missing required field '{field}'"
                    logger.error(f"📧 SendEmail ERROR: {error_msg}")
                    return f"Error: {error_msg}"
            
            if self.dry_run:
                logger.info(f"📧 SendEmail: [DRY RUN] Email queued for case {data['case_id']}")
                return f"[DRY RUN] Email queued for case {data['case_id']} to {data['recipient_email']}"
            
            logger.info(f"📧 SendEmail: Calling backend API for case {data['case_id']}")
            
            # Call backend email API
            response = await http_client.post(
                f"{BACKEND_URL}/api/send-email",
                json=data
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"📧 SendEmail: Backend response - Message ID: {result['message_id']}")
            
            # Update case communication date
            update_response = await http_client.put(
                f"{BACKEND_URL}/api/cases/{data['case_id']}/communication-date",
                json={
                    "case_id": data['case_id'],
                    "last_communication_date": datetime.now().isoformat()
                }
            )
            update_response.raise_for_status()
            
            logger.info(f"📧 SendEmail: Successfully sent email for case {data['case_id']}")
            return f"Email sent successfully to {data['recipient_email']} for case {data['case_id']} (Message ID: {result['message_id']})"
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format - {str(e)}"
            logger.error(f"📧 SendEmail JSON ERROR: {error_msg}")
            return f"Error: {error_msg}"
        except httpx.HTTPError as e:
            error_msg = f"Backend API error - {str(e)}"
            logger.error(f"📧 SendEmail API ERROR: {error_msg}")
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"Unexpected error - {str(e)}"
            logger.error(f"📧 SendEmail ERROR: {error_msg}")
            return f"Error: {error_msg}"

# Streaming support with real LangChain callbacks
class StreamingCallbackHandler(BaseCallbackHandler):
    """Captures real LangChain agent reasoning steps"""
    
    def __init__(self, stream_queue):
        self.stream_queue = stream_queue
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        """Called when LLM starts processing"""
        await self.stream_queue.put({
            'type': 'thinking', 
            'message': 'Agent is analyzing the request and planning actions...'
        })
    
    async def on_llm_end(self, response: LLMResult, **kwargs):
        """Called when LLM finishes processing"""
        if response.generations and response.generations[0]:
            text = response.generations[0][0].text
            await self.stream_queue.put({
                'type': 'llm_response', 
                'message': f'Agent reasoning: {text[:200]}...' if len(text) > 200 else text
            })
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when agent starts using a tool"""
        tool_name = serialized.get('name', 'Unknown tool')
        await self.stream_queue.put({
            'type': 'tool_start',
            'tool': tool_name,
            'message': f'Executing {tool_name}: {str(input_str)[:100]}...'
        })
    
    async def on_tool_end(self, output, **kwargs):
        """Called when tool execution completes"""
        await self.stream_queue.put({
            'type': 'tool_end',
            'message': f'Tool completed: {str(output)[:200]}...' if len(str(output)) > 200 else str(output)
        })
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        """Called when agent decides on an action"""
        await self.stream_queue.put({
            'type': 'agent_action',
            'tool': action.tool,
            'message': f'Agent decided to use {action.tool}. Reasoning: {action.log[:300]}...'
        })
    
    async def on_agent_finish(self, finish: AgentFinish, **kwargs):
        """Called when agent completes all actions"""
        await self.stream_queue.put({
            'type': 'agent_finish',
            'message': 'Agent has completed all planned actions'
        })

class AgentStreamHandler:
    """Handles streaming of agent execution with real callbacks"""
    
    def __init__(self):
        self.stream_queue = asyncio.Queue()
        self.callback_handler = StreamingCallbackHandler(self.stream_queue)
    
    async def execute_with_streaming(self, agent: AgentExecutor, input_message: str):
        """Execute agent with real streaming callbacks"""
        
        async def run_agent():
            try:
                result = await agent.ainvoke(
                    {"input": input_message}, 
                    config={"callbacks": [self.callback_handler]}
                )
                await self.stream_queue.put({'type': 'execution_complete', 'result': result})
            except Exception as e:
                await self.stream_queue.put({'type': 'execution_error', 'error': str(e)})
        
        # Start agent execution
        agent_task = asyncio.create_task(run_agent())
        
        # Stream the real reasoning steps
        while True:
            try:
                data = await asyncio.wait_for(self.stream_queue.get(), timeout=3.0)
                
                if data['type'] == 'execution_complete':
                    yield {'type': 'agent_result', 'result': data['result']}
                    break
                elif data['type'] == 'execution_error':
                    yield {'type': 'error', 'message': data['error']}
                    break
                else:
                    yield data
                    
            except asyncio.TimeoutError:
                if agent_task.done():
                    break
                yield {'type': 'status', 'message': 'Processing...'}
                continue

# Agent creation
def create_agent(dry_run: bool = False) -> AgentExecutor:
    """Create LangChain agent with API tools"""
    
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=ANTHROPIC_API_KEY,
        temperature=0.1
    )
    
    tools = [
        CheckCaseStatusTool(),
        SendEmailTool(dry_run=dry_run)
    ]
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="""You are a Client Communications Agent for a Family Law firm specializing in financial discovery.

CORE RESPONSIBILITY:
Check for cases requiring document reminders and send professional, empathetic communication to clients.

WORKFLOW:
1. Use check_case_status to identify cases needing attention
2. For each case, analyze the specific documents required
3. Compose personalized, professional reminder emails using send_email
4. Ensure all identified cases receive appropriate communication

EMAIL REQUIREMENTS:
- Professional yet warm and understanding tone
- Acknowledge the emotional difficulty of family law proceedings
- Clearly specify the exact documents needed
- Provide reasonable timeframe for document submission
- Offer assistance and support
- Include contact information for questions

DECISION MAKING:
- Process ALL cases returned by check_case_status
- Personalize each email based on client name and document requirements
- Maintain consistency in professional standards while adapting tone appropriately
- Prioritize clarity and empathy in all communications

Execute systematically and thoroughly to ensure no cases are overlooked."""),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad")
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=15,
        return_intermediate_steps=True
    )

# FastAPI application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_http_client()
    yield
    # Shutdown
    await close_http_client()

app = FastAPI(
    title="Client Communications Agent",
    description="AI-powered client reminder system for Family Law",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def health_check():
    """Service health check"""
    try:
        # Test backend connectivity
        response = await http_client.get(f"{BACKEND_URL}/")
        response.raise_for_status()
        
        return {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "backend": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Backend unavailable: {str(e)}")

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """Streaming natural language interface for agent interaction"""
    
    async def generate_stream():
        try:
            stream_handler = AgentStreamHandler()
            agent = create_agent(dry_run=request.dry_run)
            
            yield f"data: {json.dumps({'type': 'status', 'message': 'Initializing agent execution'})}\n\n"
            
            # Execute with streaming and capture final result
            final_result = None
            async for update in stream_handler.execute_with_streaming(agent, request.message):
                if update['type'] == 'agent_result':
                    final_result = update['result']
                else:
                    yield f"data: {json.dumps(update)}\n\n"
            
            # Process and yield final response
            if final_result:
                output = final_result.get("output", "Execution completed")
                
                if isinstance(output, list) and output:
                    if isinstance(output[0], dict) and "text" in output[0]:
                        response_text = output[0]["text"]
                    else:
                        response_text = str(output[0])
                else:
                    response_text = str(output)
                
                yield f"data: {json.dumps({'type': 'final_response', 'response': response_text})}\n\n"
            
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

@app.post("/tasks/process-reminders", response_model=ProcessRemindersResponse)
async def process_reminders(request: ProcessRemindersRequest = ProcessRemindersRequest()):
    """Execute automated reminder processing workflow"""
    try:
        agent = create_agent(dry_run=request.dry_run)
        
        task_prompt = """Execute the complete reminder workflow:
1. Check for all cases requiring document reminders
2. Process each case individually with personalized communication
3. Ensure all identified cases receive appropriate reminder emails
4. Provide summary of actions taken"""
        
        result = await agent.ainvoke({"input": task_prompt})
        
        # Extract summary from result
        output = result.get("output", "Processing completed")
        if isinstance(output, list) and output:
            summary = str(output[0]) if isinstance(output[0], dict) and "text" in output[0] else str(output[0])
        else:
            summary = str(output)
        
        return ProcessRemindersResponse(
            status="completed",
            cases_processed=0,  # Extract from agent logs in production
            summary=summary
        )
        
    except Exception as e:
        logger.error(f"Reminder processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

# Application startup
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Client Communications Agent on port {PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )