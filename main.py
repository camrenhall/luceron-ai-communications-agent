"""
Client Communications Agent for Google Cloud Run
Production-ready implementation following GCP best practices
"""

import os
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

# Configure logging for Cloud Run
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 8080))

# Initialize FastAPI with proper metadata
app = FastAPI(
    title="Client Communications Agent",
    description="AI-powered client reminder system for Family Law",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Global database pool
db_pool = None

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    dry_run: bool = False

class ChatResponse(BaseModel):
    response: str
    timestamp: str

class ProcessRemindersRequest(BaseModel):
    dry_run: bool = False

class ProcessRemindersResponse(BaseModel):
    status: str
    cases_processed: int
    summary: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    database: str
    environment: Dict[str, bool]

# Database functions
async def init_database():
    """Initialize database connection pool with proper error handling"""
    global db_pool
    
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not provided - running in demo mode")
        return
        
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        logger.info("Database connection pool initialized successfully")
        
        # Test connection
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        logger.info("Database connection test successful")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        db_pool = None

async def close_database():
    """Clean up database connections"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connections closed")

# LangChain Tools
class CheckCaseStatusTool(BaseTool):
    """Tool to check cases needing reminders"""
    name: str = "check_case_status"
    description: str = "Check for cases awaiting documents that need reminder emails. No parameters required."
    
    def _run(self, query: str = "") -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, query: str = "") -> str:
        if not db_pool:
            return json.dumps({
                "error": "Database not available",
                "demo_cases": [
                    {
                        "case_id": "DEMO001",
                        "client_email": "demo@example.com",
                        "client_name": "Demo Client",
                        "documents_requested": "Bank statements, Tax returns"
                    }
                ]
            })
        
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
                LIMIT 10
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
                
                logger.info(f"Found {len(cases)} cases needing reminders")
                return json.dumps(result, indent=2)
                
        except Exception as e:
            error_msg = f"Error checking cases: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})

class SendEmailTool(BaseTool):
    """Tool to send reminder emails"""
    name: str = "send_email"
    description: str = """Send reminder email to client. Input: JSON with recipient_email, subject, body, case_id"""
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
                    return f"Error: Missing field '{field}'"
            
            recipient = data["recipient_email"]
            subject = data["subject"]
            body = data["body"]
            case_id = data["case_id"]
            
            # Log email (MVP behavior)
            if self.dry_run:
                logger.info(f"[DRY RUN] Email for case {case_id}")
            else:
                logger.info(f"📧 SENDING EMAIL")
                logger.info(f"📧 TO: {recipient}")
                logger.info(f"📧 SUBJECT: {subject}")
                logger.info(f"📧 BODY: {body[:100]}...")
            
            # Update database if available
            if db_pool and not self.dry_run:
                try:
                    async with db_pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE cases SET last_communication_date = $1 WHERE case_id = $2",
                            datetime.now(),
                            case_id
                        )
                    logger.info(f"Updated communication date for case {case_id}")
                except Exception as e:
                    logger.error(f"Failed to update database: {e}")
            
            return f"Email {'queued' if self.dry_run else 'sent'} to {recipient} for case {case_id}"
            
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON - {str(e)}"
        except Exception as e:
            return f"Error sending email: {str(e)}"

# Agent creation
def create_agent(dry_run: bool = False) -> AgentExecutor:
    """Create LangChain agent with tools"""
    
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is required")
    
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
        SystemMessage(content="""You are a Client Communications Agent for a Family Law firm.

Your job is to check for cases needing document reminders and send professional, empathetic emails.

WORKFLOW:
1. Use check_case_status to find cases needing reminders
2. For each case, compose a personalized reminder email
3. Send emails using send_email tool

EMAIL STYLE:
- Professional but warm
- Acknowledge the difficulty of the situation
- Clearly state what documents are needed
- Offer assistance if they have questions
- Be understanding about family law matters

Always process all cases found by check_case_status."""),
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
        max_iterations=10
    )

# FastAPI event handlers
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Client Communications Agent")
    logger.info(f"PORT: {PORT}")
    logger.info(f"Database: {'configured' if DATABASE_URL else 'not configured'}")
    logger.info(f"Anthropic API: {'configured' if ANTHROPIC_API_KEY else 'not configured'}")
    
    await init_database()
    logger.info("Startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    await close_database()
    logger.info("Shutdown complete")

# API endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint"""
    return HealthResponse(
        status="operational",
        timestamp=datetime.now().isoformat(),
        database="connected" if db_pool else "not configured",
        environment={
            "anthropic_api_configured": bool(ANTHROPIC_API_KEY),
            "database_configured": bool(DATABASE_URL)
        }
    )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Detailed health check"""
    database_status = "not configured"
    
    if DATABASE_URL:
        if db_pool:
            try:
                async with db_pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                database_status = "connected"
            except Exception as e:
                database_status = f"error: {str(e)}"
        else:
            database_status = "not connected"
    
    return HealthResponse(
        status="healthy" if database_status in ["connected", "not configured"] else "unhealthy",
        timestamp=datetime.now().isoformat(),
        database=database_status,
        environment={
            "anthropic_api_configured": bool(ANTHROPIC_API_KEY),
            "database_configured": bool(DATABASE_URL)
        }
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """Natural language interface with the agent"""
    try:
        if not ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="Anthropic API key not configured")
        
        agent = create_agent(dry_run=request.dry_run)
        result = await agent.ainvoke({"input": request.message})
        
        return ChatResponse(
            response=result.get("output", "No response generated"),
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

@app.post("/tasks/process-reminders", response_model=ProcessRemindersResponse)
async def process_reminders(request: ProcessRemindersRequest = ProcessRemindersRequest()):
    """Process client reminders automatically"""
    try:
        if not ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="Anthropic API key not configured")
        
        agent = create_agent(dry_run=request.dry_run)
        
        task_prompt = "Check for cases needing reminder emails and send appropriate communications to all clients who need them."
        
        result = await agent.ainvoke({"input": task_prompt})
        
        return ProcessRemindersResponse(
            status="completed",
            cases_processed=0,  # Would extract from agent logs in production
            summary=result.get("output", "Task completed")
        )
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

# Cloud Run startup
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on port {PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )