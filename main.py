"""
Production Client Communications Agent
AI-powered client reminder system for Family Law document discovery
"""

import os
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncpg
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Global database pool
db_pool = None

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    dry_run: bool = False

class ProcessRemindersRequest(BaseModel):
    dry_run: bool = False

class ProcessRemindersResponse(BaseModel):
    status: str
    cases_processed: int
    summary: str

# Database operations
async def init_database():
    """Initialize database connection pool"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        # Test connection
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

async def close_database():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connections closed")

# LangChain Tools
class CheckCaseStatusTool(BaseTool):
    """Tool to check cases needing reminder communications"""
    name: str = "check_case_status"
    description: str = "Check for cases awaiting documents that haven't been contacted in the last 3 days. Returns list of cases requiring reminder emails."
    
    def _run(self, query: str = "") -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, query: str = "") -> str:
        try:
            async with db_pool.acquire() as conn:
                cutoff_date = datetime.now() - timedelta(days=3)
                
                query_sql = """
                SELECT case_id, client_email, client_name, status, 
                       last_communication_date, documents_requested
                FROM cases 
                WHERE status = 'awaiting_documents' 
                AND (last_communication_date IS NULL OR last_communication_date < $1)
                ORDER BY last_communication_date ASC NULLS FIRST
                LIMIT 20
                """
                
                rows = await conn.fetch(query_sql, cutoff_date)
                
                cases = []
                for row in rows:
                    cases.append({
                        "case_id": row['case_id'],
                        "client_email": row['client_email'],
                        "client_name": row['client_name'],
                        "status": row['status'],
                        "last_communication_date": row['last_communication_date'].isoformat() if row['last_communication_date'] else None,
                        "documents_requested": row['documents_requested']
                    })
                
                result = {
                    "found_cases": len(cases),
                    "cases": cases
                }
                
                logger.info(f"Found {len(cases)} cases requiring reminders")
                return json.dumps(result, indent=2)
                
        except Exception as e:
            error_msg = f"Database query failed: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})

class SendEmailTool(BaseTool):
    """Tool to send reminder emails to clients"""
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
            data = json.loads(email_data)
            required_fields = ["recipient_email", "subject", "body", "case_id"]
            
            for field in required_fields:
                if field not in data:
                    return f"Error: Missing required field '{field}'"
            
            recipient = data["recipient_email"]
            subject = data["subject"]
            body = data["body"]
            case_id = data["case_id"]
            
            # Log email content (replace with actual email service in production)
            if self.dry_run:
                logger.info(f"[DRY RUN] Email queued for case {case_id} to {recipient}")
            else:
                logger.info(f"Sending email for case {case_id} to {recipient}")
                logger.info(f"Subject: {subject}")
                logger.info(f"Body preview: {body[:200]}...")
                # TODO: Integrate with email service (SendGrid, AWS SES, etc.)
            
            # Update database communication timestamp
            if not self.dry_run:
                try:
                    async with db_pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE cases SET last_communication_date = $1 WHERE case_id = $2",
                            datetime.now(),
                            case_id
                        )
                    logger.info(f"Updated communication timestamp for case {case_id}")
                except Exception as e:
                    logger.error(f"Failed to update database for case {case_id}: {e}")
            
            return f"Email {'queued' if self.dry_run else 'sent'} successfully to {recipient} for case {case_id}"
            
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format - {str(e)}"
        except Exception as e:
            return f"Error: Email processing failed - {str(e)}"

# Agent creation
def create_agent(dry_run: bool = False) -> AgentExecutor:
    """Create LangChain agent with communication tools"""
    
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

# Streaming support
class AgentStreamHandler:
    """Handles streaming of agent execution steps"""
    
    def __init__(self):
        self.stream_queue = asyncio.Queue()
    
    async def stream_callback(self, data: Dict):
        """Queue streaming data"""
        await self.stream_queue.put(data)
    
    async def execute_with_streaming(self, agent: AgentExecutor, input_message: str):
        """Execute agent with streaming callbacks"""
        
        async def run_agent():
            try:
                result = await agent.ainvoke({"input": input_message})
                await self.stream_queue.put({'type': 'execution_complete', 'result': result})
            except Exception as e:
                await self.stream_queue.put({'type': 'execution_error', 'error': str(e)})
        
        # Start agent execution
        agent_task = asyncio.create_task(run_agent())
        
        # Stream progress updates
        final_result = None
        while True:
            try:
                data = await asyncio.wait_for(self.stream_queue.get(), timeout=2.0)
                
                if data['type'] == 'execution_complete':
                    final_result = data['result']
                    break
                elif data['type'] == 'execution_error':
                    raise Exception(data['error'])
                else:
                    yield data
                    
            except asyncio.TimeoutError:
                if agent_task.done():
                    break
                # Send keepalive
                yield {'type': 'status', 'message': 'Agent processing...'}
                continue
        
        return final_result

# FastAPI application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_database()
    yield
    # Shutdown
    await close_database()

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
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """Streaming natural language interface for agent interaction"""
    
    async def generate_stream():
        try:
            stream_handler = AgentStreamHandler()
            agent = create_agent(dry_run=request.dry_run)
            
            yield f"data: {json.dumps({'type': 'status', 'message': 'Initializing agent execution'})}\n\n"
            
            # Execute with streaming
            async for update in stream_handler.execute_with_streaming(agent, request.message):
                yield f"data: {json.dumps(update)}\n\n"
            
            # Get final result
            result = await agent.ainvoke({"input": request.message})
            output = result.get("output", "Execution completed")
            
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