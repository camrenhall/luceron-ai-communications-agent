"""
Client Communications Agent MVP
A containerized AI agent that autonomously manages client reminder communications for Family Law document discovery.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import asyncpg
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # Supabase PostgreSQL connection string

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Database models
class CaseRecord(BaseModel):
    case_id: str
    client_email: str
    client_name: str
    status: str
    last_communication_date: Optional[datetime]
    documents_requested: str

# FastAPI models
class ProcessRemindersRequest(BaseModel):
    dry_run: bool = Field(default=False, description="If true, only log actions without sending emails")

class ProcessRemindersResponse(BaseModel):
    processed_cases: int
    emails_sent: int
    summary: List[str]

# Database connection pool
db_pool = None

async def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed")

# Custom LangChain Tools
class CheckCaseStatusTool(BaseTool):
    """Tool to check cases that need reminder communications"""
    name: str = "check_case_status"
    description: str = """
    Check for cases that are awaiting documents and haven't been contacted in the last 3 days.
    Returns a list of cases that need reminder emails.
    No input parameters required.
    """
    
    def _run(self, query: str = "") -> str:
        """Synchronous version - not used in async context"""
        raise NotImplementedError("Use async version")
    
    async def _arun(self, query: str = "") -> str:
        """Check database for cases needing reminders"""
        try:
            async with db_pool.acquire() as conn:
                # Query cases that are awaiting documents and haven't been contacted recently
                query_sql = """
                SELECT case_id, client_email, client_name, status, last_communication_date, documents_requested
                FROM cases 
                WHERE status = 'awaiting_documents' 
                AND (last_communication_date IS NULL OR last_communication_date < $1)
                ORDER BY last_communication_date ASC NULLS FIRST
                """
                
                cutoff_date = datetime.now() - timedelta(days=3)
                rows = await conn.fetch(query_sql, cutoff_date)
                
                cases = []
                for row in rows:
                    case_data = {
                        "case_id": row['case_id'],
                        "client_email": row['client_email'],
                        "client_name": row['client_name'],
                        "status": row['status'],
                        "last_communication_date": row['last_communication_date'].isoformat() if row['last_communication_date'] else None,
                        "documents_requested": row['documents_requested']
                    }
                    cases.append(case_data)
                
                result = {
                    "found_cases": len(cases),
                    "cases": cases
                }
                
                logger.info(f"Found {len(cases)} cases needing reminders")
                return json.dumps(result, indent=2)
                
        except Exception as e:
            error_msg = f"Error checking case status: {str(e)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

class SendEmailTool(BaseTool):
    """Tool to send reminder emails to clients"""
    name: str = "send_email"
    description: str = """
    Send a reminder email to a client about overdue documents.
    Input should be a JSON string with keys: recipient_email, subject, body, case_id
    Example: {"recipient_email": "client@example.com", "subject": "Document Reminder", "body": "Dear client...", "case_id": "12345"}
    """
    
    def __init__(self, dry_run: bool = False):
        super().__init__()
        self.dry_run = dry_run
    
    def _run(self, email_data: str) -> str:
        """Synchronous version - not used in async context"""
        raise NotImplementedError("Use async version")
    
    async def _arun(self, email_data: str) -> str:
        """Send email and update database"""
        try:
            # Parse the email data
            try:
                data = json.loads(email_data)
                required_fields = ["recipient_email", "subject", "body", "case_id"]
                for field in required_fields:
                    if field not in data:
                        return f"Error: Missing required field '{field}' in email data"
            except json.JSONDecodeError as e:
                return f"Error: Invalid JSON format in email data: {str(e)}"
            
            recipient_email = data["recipient_email"]
            subject = data["subject"]
            body = data["body"]
            case_id = data["case_id"]
            
            if self.dry_run:
                # In dry run mode, just log the email content
                logger.info(f"[DRY RUN] Would send email to {recipient_email}")
                logger.info(f"[DRY RUN] Subject: {subject}")
                logger.info(f"[DRY RUN] Body: {body}")
                return f"DRY RUN: Email logged for case {case_id}"
            else:
                # For MVP, log the email content instead of actually sending
                logger.info(f"📧 SENDING EMAIL TO: {recipient_email}")
                logger.info(f"📧 SUBJECT: {subject}")
                logger.info(f"📧 BODY:\n{body}")
                logger.info("📧 [Note: In production, this would use a real email service]")
            
            # Update the last_communication_date in the database
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE cases SET last_communication_date = $1 WHERE case_id = $2",
                    datetime.now(),
                    case_id
                )
            
            logger.info(f"Updated communication date for case {case_id}")
            return f"Email sent successfully to {recipient_email} for case {case_id}"
            
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"

# Agent setup
def create_agent_executor(dry_run: bool = False) -> AgentExecutor:
    """Create the LangChain agent with tools"""
    
    # Initialize LLM
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=ANTHROPIC_API_KEY,
        temperature=0.1
    )
    
    # Create tools
    tools = [
        CheckCaseStatusTool(),
        SendEmailTool(dry_run=dry_run)
    ]
    
    # Create prompt template
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="""You are the Client Communications Agent for a Family Law firm specializing in financial discovery.

Your primary responsibility is to autonomously manage client reminder communications for document collection.

WORKFLOW:
1. Use check_case_status to identify cases that need reminder emails
2. For each case found, compose and send a professional, empathetic reminder email
3. Always update the communication date after sending

EMAIL GUIDELINES:
- Be professional yet warm and understanding
- Acknowledge that document gathering can be overwhelming
- Clearly state what documents are needed
- Provide a reasonable timeline for submission
- Offer assistance if they have questions
- Use the client's name when available

DECISION MAKING:
- Always send reminders for cases returned by check_case_status (they already meet the 3-day criteria)
- Compose personalized emails based on the specific documents requested
- Be empathetic - divorce and family law matters are emotionally challenging

Remember: You are helping families through difficult legal processes. Your communication should be supportive, clear, and professional."""),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad")
    ])
    
    # Create agent
    agent = create_openai_tools_agent(llm, tools, prompt)
    
    # Create agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10
    )
    
    return agent_executor

# FastAPI application
app = FastAPI(
    title="Client Communications Agent",
    description="AI-powered client reminder system for Family Law document discovery",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    await init_db_pool()

@app.on_event("shutdown") 
async def shutdown_event():
    """Clean up resources on shutdown"""
    await close_db_pool()

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Client Communications Agent",
        "status": "operational",
        "timestamp": datetime.now().isoformat()
    }

class ChatRequest(BaseModel):
    message: str
    dry_run: bool = False

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """
    Natural language chat interface with the agent.
    The agent can use tools based on your request.
    """
    try:
        agent_executor = create_agent_executor(dry_run=request.dry_run)
        result = await agent_executor.ainvoke({"input": request.message})
        return ChatResponse(response=result["output"])
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/process-reminders", response_model=ProcessRemindersResponse)
async def process_reminders(request: ProcessRemindersRequest = ProcessRemindersRequest()):
    """Automated reminder processing endpoint"""
    try:
        agent_executor = create_agent_executor(dry_run=request.dry_run)
        
        task_prompt = """Check for cases that need reminder emails and send appropriate communications."""
        
        result = await agent_executor.ainvoke({"input": task_prompt})
        
        summary = [result["output"]] if "output" in result else []
        
        response = ProcessRemindersResponse(
            processed_cases=0,
            emails_sent=0,
            summary=summary
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing reminders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        # Test database connection
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)