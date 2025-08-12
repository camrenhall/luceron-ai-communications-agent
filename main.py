"""
Event-Driven Client Communications Agent
Durable execution workflow using backend APIs for all persistence
"""

import os
import logging
import json
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
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

# Global HTTP client
http_client = None

# Workflow State Models - Updated for consistency
class WorkflowStatus(str, Enum):
    # Original statuses
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    AWAITING_SCHEDULE = "AWAITING_SCHEDULE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # Document Analysis Agent statuses (for consistency)
    PENDING_PLANNING = "PENDING_PLANNING"
    AWAITING_BATCH_COMPLETION = "AWAITING_BATCH_COMPLETION"
    SYNTHESIZING_RESULTS = "SYNTHESIZING_RESULTS"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"

class ReasoningStep(BaseModel):
    timestamp: datetime
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    action_output: Optional[str] = None

class WorkflowState(BaseModel):
    workflow_id: str
    agent_type: str = "CommunicationsAgent"
    case_id: Optional[str] = None
    status: WorkflowStatus
    initial_prompt: str
    reasoning_chain: List[ReasoningStep]
    scheduled_for: Optional[datetime] = None
    # Enhanced fields for consistency (Communications Agent will use basic values)
    document_ids: List[str] = []
    case_context: Optional[str] = None
    priority: str = "standard"
    created_at: datetime
    updated_at: datetime

# Request/Response Models
class TriggerWorkflowRequest(BaseModel):
    case_id: Optional[str] = None
    prompt: str = "Execute automated client reminder workflow"
    schedule_for: Optional[datetime] = None
    priority: str = "standard"

class WorkflowResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    message: str

class ChatRequest(BaseModel):
    message: str
    dry_run: bool = False

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

# Backend API calls for workflow state management
async def create_workflow_state(state: WorkflowState) -> WorkflowState:
    """Create workflow state via backend API"""
    try:
        # Convert to format expected by backend
        workflow_data = {
            "workflow_id": state.workflow_id,
            "agent_type": state.agent_type,
            "case_id": state.case_id,
            "status": state.status.value,
            "initial_prompt": state.initial_prompt,
            "scheduled_for": state.scheduled_for.isoformat() if state.scheduled_for else None,
            "document_ids": state.document_ids,
            "case_context": state.case_context,
            "priority": state.priority
        }
        
        response = await http_client.post(
            f"{BACKEND_URL}/api/workflows",
            json=workflow_data
        )
        response.raise_for_status()
        # Convert to format expected by backend  
        reasoning_chain = [ReasoningStep(**step) for step in data.get("reasoning_chain", [])]
        
        return WorkflowState(
            workflow_id=data['workflow_id'],
            agent_type=data['agent_type'],
            case_id=data.get('case_id'),
            status=WorkflowStatus(data['status']),
            initial_prompt=data['initial_prompt'],
            reasoning_chain=reasoning_chain,
            scheduled_for=datetime.fromisoformat(data['scheduled_for']) if data.get('scheduled_for') else None,
            document_ids=data.get('document_ids', []),
            case_context=data.get('case_context'),
            priority=data.get('priority', 'standard'),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at'])
        )
    except Exception as e:
        logger.error(f"Failed to create workflow state: {e}")
        raise

async def load_workflow_state(workflow_id: str) -> Optional[WorkflowState]:
    """Load workflow state via backend API"""
    try:
        response = await http_client.get(f"{BACKEND_URL}/api/workflows/{workflow_id}")
        
        if response.status_code == 404:
            return None
            
        response.raise_for_status()
        return WorkflowState(**response.json())
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        logger.error(f"Failed to load workflow state: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load workflow state: {e}")
        raise

async def update_workflow_status(workflow_id: str, status: WorkflowStatus) -> None:
    """Update workflow status via backend API"""
    try:
        response = await http_client.put(
            f"{BACKEND_URL}/api/workflows/{workflow_id}/status",
            json={"status": status.value}
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to update workflow status: {e}")
        raise

async def add_reasoning_step(workflow_id: str, step: ReasoningStep) -> None:
    """Add reasoning step via backend API"""
    try:
        response = await http_client.post(
            f"{BACKEND_URL}/api/workflows/{workflow_id}/reasoning",
            json=step.dict()
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to add reasoning step: {e}")
        raise

async def get_pending_workflows() -> List[str]:
    """Get pending workflows via backend API"""
    try:
        response = await http_client.get(f"{BACKEND_URL}/api/workflows/pending")
        response.raise_for_status()
        data = response.json()
        return data.get("workflow_ids", [])
    except Exception as e:
        logger.error(f"Failed to get pending workflows: {e}")
        return []

# LangChain Tools (same as before)
class CheckCaseStatusTool(BaseTool):
    """Tool to check cases needing reminder communications via backend API"""
    name: str = "check_case_status"
    description: str = "Check for cases awaiting documents that haven't been contacted in the last 3 days."
    
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
            
        except Exception as e:
            error_msg = f"Backend API error: {str(e)}"
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
            data = json.loads(email_data)
            required_fields = ["recipient_email", "subject", "body", "case_id"]
            
            for field in required_fields:
                if field not in data:
                    return f"Error: Missing required field '{field}'"
            
            if self.dry_run:
                logger.info(f"📧 SendEmail: [DRY RUN] Email queued for case {data['case_id']}")
                return f"[DRY RUN] Email queued for case {data['case_id']} to {data['recipient_email']}"
            
            # Call backend email API
            response = await http_client.post(f"{BACKEND_URL}/api/send-email", json=data)
            response.raise_for_status()
            
            result = response.json()
            
            # Update case communication date
            update_response = await http_client.put(
                f"{BACKEND_URL}/api/cases/{data['case_id']}/communication-date",
                json={
                    "case_id": data['case_id'],
                    "last_communication_date": datetime.now().isoformat()
                }
            )
            update_response.raise_for_status()
            
            return f"Email sent successfully to {data['recipient_email']} for case {data['case_id']} (Message ID: {result['message_id']})"
            
        except Exception as e:
            return f"Error: {str(e)}"

# Workflow execution engine
class WorkflowStatePersistenceHandler(BaseCallbackHandler):
    """Callback handler that persists reasoning steps via backend API"""
    
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
    
    async def on_llm_start(self, serialized, prompts, **kwargs):
        """Record when agent starts thinking"""
        await self._add_reasoning_step("Agent is analyzing the request and planning actions...")
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        """Record tool execution start"""
        tool_name = serialized.get('name', 'Unknown tool')
        await self._add_reasoning_step(
            f"Executing {tool_name}",
            action=tool_name,
            action_input={"input": str(input_str)[:200]}
        )
    
    async def on_tool_end(self, output, **kwargs):
        """Record tool execution completion"""
        await self._add_reasoning_step(
            "Tool execution completed",
            action_output=str(output)[:500]
        )
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        """Record agent decision making"""
        await self._add_reasoning_step(
            f"Agent decided to use {action.tool}. Reasoning: {action.log[:200]}..."
        )
    
    async def _add_reasoning_step(self, thought: str, action: str = None, 
                                action_input: Dict = None, action_output: str = None):
        """Add reasoning step via backend API"""
        try:
            step = ReasoningStep(
                timestamp=datetime.now(),
                thought=thought,
                action=action,
                action_input=action_input,
                action_output=action_output
            )
            await add_reasoning_step(self.workflow_id, step)
        except Exception as e:
            logger.error(f"Failed to add reasoning step: {e}")
            # Continue execution even if logging fails

async def execute_workflow(workflow_id: str, dry_run: bool = False) -> WorkflowState:
    """Execute a workflow with state persistence via backend API"""
    
    # Load workflow state
    state = await load_workflow_state(workflow_id)
    if not state:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    # Update status to processing
    await update_workflow_status(workflow_id, WorkflowStatus.PROCESSING)
    
    try:
        # Create agent with persistence callback
        persistence_handler = WorkflowStatePersistenceHandler(workflow_id)
        
        llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.1
        )
        
        tools = [CheckCaseStatusTool(), SendEmailTool(dry_run=dry_run)]
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a Client Communications Agent for a Family Law firm.

CORE RESPONSIBILITY:
Execute automated client reminder workflows based on case triggers and schedules.

WORKFLOW:
1. Use check_case_status to identify cases needing attention
2. For each case, compose personalized, professional reminder emails
3. Send emails using send_email tool
4. Provide summary of actions taken

EMAIL REQUIREMENTS:
- Professional yet warm and understanding tone
- Acknowledge the emotional difficulty of family law proceedings
- Clearly specify the exact documents needed
- Provide reasonable timeframe for document submission
- Offer assistance and support

Execute systematically and thoroughly to ensure no cases are overlooked."""),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad")
        ])
        
        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=15
        )
        
        # Execute with callback
        result = await executor.ainvoke(
            {"input": state.initial_prompt},
            config={"callbacks": [persistence_handler]}
        )
        
        # Add final reasoning step
        final_step = ReasoningStep(
            timestamp=datetime.now(),
            thought=f"Workflow completed successfully. Result: {result.get('output', 'No output')[:200]}..."
        )
        await add_reasoning_step(workflow_id, final_step)
        
        # Update final status
        await update_workflow_status(workflow_id, WorkflowStatus.COMPLETED)
        
        # Return updated state
        final_state = await load_workflow_state(workflow_id)
        
        logger.info(f"Workflow {workflow_id} completed successfully")
        return final_state
        
    except Exception as e:
        logger.error(f"Workflow {workflow_id} failed: {e}")
        
        # Add failure reasoning step
        failure_step = ReasoningStep(
            timestamp=datetime.now(),
            thought=f"Workflow failed with error: {str(e)}"
        )
        await add_reasoning_step(workflow_id, failure_step)
        
        # Update failure status
        await update_workflow_status(workflow_id, WorkflowStatus.FAILED)
        
        raise

# Background task processor
async def process_pending_workflows():
    """Background task to process pending workflows"""
    try:
        pending_workflows = await get_pending_workflows()
        
        for workflow_id in pending_workflows:
            try:
                logger.info(f"Processing workflow {workflow_id}")
                await execute_workflow(workflow_id)
            except Exception as e:
                logger.error(f"Failed to process workflow {workflow_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in workflow processor: {e}")

# FastAPI application
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_http_client()
    yield
    await close_http_client()

app = FastAPI(
    title="Event-Driven Communications Agent",
    description="Durable execution workflow for client communications",
    version="2.0.0",
    lifespan=lifespan
)

@app.get("/")
async def health_check():
    """Service health check"""
    try:
        response = await http_client.get(f"{BACKEND_URL}/")
        response.raise_for_status()
        
        return {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "backend": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Backend unavailable: {str(e)}")

@app.post("/workflows/trigger", response_model=WorkflowResponse)
async def trigger_workflow(request: TriggerWorkflowRequest, background_tasks: BackgroundTasks):
    """Trigger a new workflow execution"""
    
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    
    # Determine status based on scheduling
    if request.schedule_for and request.schedule_for > datetime.now():
        status = WorkflowStatus.AWAITING_SCHEDULE
    else:
        status = WorkflowStatus.PENDING
    
    # Create workflow state
    state = WorkflowState(
        workflow_id=workflow_id,
        case_id=request.case_id,
        status=status,
        initial_prompt=request.prompt,
        reasoning_chain=[],
        scheduled_for=request.schedule_for,
        priority=request.priority,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    await create_workflow_state(state)
    
    # If not scheduled, trigger immediate processing
    if status == WorkflowStatus.PENDING:
        background_tasks.add_task(process_pending_workflows)
    
    return WorkflowResponse(
        workflow_id=workflow_id,
        status=status,
        message=f"Workflow {workflow_id} {'scheduled' if request.schedule_for else 'triggered'}"
    )

@app.get("/workflows/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """Get workflow status and reasoning chain"""
    state = await load_workflow_state(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {
        "workflow_id": state.workflow_id,
        "status": state.status,
        "reasoning_chain": state.reasoning_chain,
        "created_at": state.created_at,
        "updated_at": state.updated_at
    }

@app.post("/workflows/process-pending")
async def manual_process_pending(background_tasks: BackgroundTasks):
    """Manually trigger processing of pending workflows"""
    background_tasks.add_task(process_pending_workflows)
    return {"message": "Pending workflow processing triggered"}

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """Interactive chat that creates a workflow"""
    
    workflow_id = f"wf_chat_{uuid.uuid4().hex[:8]}"
    
    state = WorkflowState(
        workflow_id=workflow_id,
        status=WorkflowStatus.PENDING,
        initial_prompt=request.message,
        reasoning_chain=[],
        priority="interactive",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    await create_workflow_state(state)
    
    async def generate_stream():
        try:
            yield f"data: {json.dumps({'type': 'workflow_started', 'workflow_id': workflow_id})}\n\n"
            
            # Execute workflow and stream updates
            final_state = await execute_workflow(workflow_id, dry_run=request.dry_run)
            
            # Stream reasoning chain
            for step in final_state.reasoning_chain:
                yield f"data: {json.dumps({'type': 'reasoning_step', 'step': step.dict()})}\n\n"
            
            yield f"data: {json.dumps({'type': 'workflow_complete', 'status': final_state.status.value})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

# Webhook endpoints for external triggers
@app.post("/webhooks/case-created")
async def webhook_case_created(case_data: dict, background_tasks: BackgroundTasks):
    """Webhook for when a new case is created"""
    
    workflow_id = f"wf_case_{case_data.get('case_id', uuid.uuid4().hex[:8])}"
    
    state = WorkflowState(
        workflow_id=workflow_id,
        case_id=case_data.get('case_id'),
        status=WorkflowStatus.PENDING,
        initial_prompt=f"New case created: {case_data.get('case_id')}. Check if initial client communication is needed.",
        reasoning_chain=[],
        priority="standard",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    await create_workflow_state(state)
    background_tasks.add_task(process_pending_workflows)
    
    return {"workflow_id": workflow_id, "message": "Case creation workflow triggered"}

@app.post("/webhooks/documents-uploaded")
async def webhook_documents_uploaded(upload_data: dict, background_tasks: BackgroundTasks):
    """Webhook for when client uploads documents"""
    
    workflow_id = f"wf_docs_{upload_data.get('case_id', uuid.uuid4().hex[:8])}"
    
    state = WorkflowState(
        workflow_id=workflow_id,
        case_id=upload_data.get('case_id'),
        status=WorkflowStatus.PENDING,
        initial_prompt=f"Documents uploaded for case {upload_data.get('case_id')}. Send acknowledgment and check if additional documents needed.",
        reasoning_chain=[],
        document_ids=upload_data.get('document_ids', []),
        case_context=f"Document upload acknowledgment for case {upload_data.get('case_id')}",
        priority="standard",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    await create_workflow_state(state)
    background_tasks.add_task(process_pending_workflows)
    
    return {"workflow_id": workflow_id, "message": "Document upload workflow triggered"}

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Event-Driven Communications Agent on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")