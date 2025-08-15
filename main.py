"""
Communications Agent - Clean, Essential Implementation
"""

import os
import logging
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL")
PORT = int(os.getenv("PORT", 8082))

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
if not BACKEND_URL:
    raise ValueError("BACKEND_URL environment variable is required")

# Global HTTP client
http_client = None

# Models
class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

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
    created_at: datetime
    updated_at: datetime

class ChatRequest(BaseModel):
    message: str

# Prompt loading
def load_prompt(filename: str) -> str:
    """Load prompt from markdown file"""
    prompt_path = os.path.join("prompts", filename)
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_email_templates() -> Dict[str, Dict[str, str]]:
    """Load email templates from markdown file"""
    template_content = load_prompt("email_templates.md")
    
    # Simple parsing - extract templates between ## headers
    templates = {}
    lines = template_content.split('\n')
    current_template = None
    current_body = []
    in_body = False
    
    for line in lines:
        if line.startswith('## ') and 'Template' in line:
            # Save previous template
            if current_template and current_body:
                templates[current_template]['body_template'] = '\n'.join(current_body).strip()
            
            # Start new template
            template_name = line.replace('## ', '').replace(' Template', '').lower().replace(' ', '_').replace('-', '_')
            current_template = template_name
            templates[current_template] = {}
            current_body = []
            in_body = False
            
        elif line.startswith('**Subject**:') and current_template:
            subject = line.replace('**Subject**:', '').strip()
            templates[current_template]['subject_template'] = subject
            
        elif line.startswith('**Body**:') and current_template:
            in_body = True
            current_body = []
            
        elif line.startswith('**Tone**:') and current_template:
            tone = line.replace('**Tone**:', '').strip()
            templates[current_template]['tone'] = tone
            in_body = False
            
        elif in_body and line.strip() and not line.startswith('```'):
            current_body.append(line)
    
    # Save last template
    if current_template and current_body:
        templates[current_template]['body_template'] = '\n'.join(current_body).strip()
    
    # Add aliases for common variations
    if 'initial_reminder' in templates:
        templates['initial_document_request'] = templates['initial_reminder']
        templates['initial_contact'] = templates['initial_reminder']
    
    return templates

# HTTP client management
async def init_http_client():
    global http_client
    http_client = httpx.AsyncClient(timeout=30.0)

async def close_http_client():
    global http_client
    if http_client:
        await http_client.aclose()

# Backend API calls
async def create_workflow_state(state: WorkflowState) -> None:
    workflow_data = {
        "workflow_id": state.workflow_id,
        "agent_type": state.agent_type,
        "case_id": state.case_id,
        "status": state.status.value,
        "initial_prompt": state.initial_prompt
    }
    
    response = await http_client.post(f"{BACKEND_URL}/api/workflows", json=workflow_data)
    response.raise_for_status()

async def update_workflow_status(workflow_id: str, status: WorkflowStatus) -> None:
    response = await http_client.put(
        f"{BACKEND_URL}/api/workflows/{workflow_id}/status",
        json={"status": status.value}
    )
    response.raise_for_status()

async def add_reasoning_step(workflow_id: str, step: ReasoningStep) -> None:
    step_data = step.model_dump()
    if 'timestamp' in step_data:
        step_data['timestamp'] = step_data['timestamp'].isoformat()
    
    response = await http_client.post(
        f"{BACKEND_URL}/api/workflows/{workflow_id}/reasoning-step",
        json=step_data
    )
    response.raise_for_status()

# Tools
class GetCaseAnalysisTool(BaseTool):
    name: str = "get_case_analysis"
    description: str = "Get case details and communication history. Input: case_id"
    
    def _run(self, case_id: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, case_id: str) -> str:
        # Get basic case details
        case_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}")
        case_response.raise_for_status()
        case_data = case_response.json()
        
        # Try to get communication history
        try:
            comm_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}/communications")
            if comm_response.status_code == 200:
                return json.dumps(comm_response.json(), indent=2)
        except:
            pass
        
        # Return basic case data
        return json.dumps({
            "case_id": case_id,
            "client_name": case_data["client_name"],
            "client_email": case_data["client_email"],
            "documents_requested": case_data["documents_requested"],
            "communication_summary": {"total_emails": 0}
        }, indent=2)

class ComposeEmailTool(BaseTool):
    name: str = "compose_email"
    description: str = "Compose email based on case context. Input: JSON with case_id, email_type (use: initial_reminder, follow_up_reminder, or urgent_reminder)"
    
    def _run(self, email_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, email_data: str) -> str:
        try:
            data = json.loads(email_data)
            case_id = data["case_id"]
            email_type = data.get("email_type", "initial_reminder")
            
            # Normalize email type to supported types
            if email_type in ["initial_document_request", "initial_contact", "initial"]:
                email_type = "initial_reminder"
            elif email_type in ["followup", "follow_up", "reminder"]:
                email_type = "follow_up_reminder"
            elif email_type in ["urgent", "urgent_request"]:
                email_type = "urgent_reminder"
            
            logger.info(f"✍️ Composing {email_type} email for case {case_id}")
            
            # Get case data
            case_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}")
            case_response.raise_for_status()
            case_data = case_response.json()
            
            # Load templates
            templates = load_email_templates()
            
            if email_type not in templates:
                # Default to initial_reminder if type not found
                email_type = "initial_reminder"
            
            template = templates[email_type]
            
            # Format email
            subject = template["subject_template"].format(client_name=case_data["client_name"])
            body = template["body_template"].format(
                client_name=case_data["client_name"],
                documents_requested=case_data["documents_requested"]
            )
            
            result = {
                "subject": subject,
                "body": body,
                "html_body": body.replace("\n", "<br>"),
                "recipient": case_data["client_email"],
                "case_id": case_id,
                "email_type": email_type
            }
            
            logger.info(f"✍️ Successfully composed {email_type} email for {case_data['client_name']}")
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_msg = f"Email composition failed: {str(e)}"
            logger.error(f"✍️ Composition ERROR: {error_msg}")
            raise Exception(error_msg)

class SendEmailTool(BaseTool):
    name: str = "send_email"
    description: str = "Send email via backend. Input: JSON with recipient_email, subject, body, case_id, email_type"
    
    def _run(self, email_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, email_data: str) -> str:
        data = json.loads(email_data)
        
        response = await http_client.post(f"{BACKEND_URL}/api/send-email", json=data)
        response.raise_for_status()
        result = response.json()
        
        return json.dumps({
            "status": "sent",
            "message_id": result["message_id"],
            "recipient": result["recipient"]
        }, indent=2)

# Callback handler
class WorkflowCallbackHandler(BaseCallbackHandler):
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get('name', 'Unknown')
        await add_reasoning_step(self.workflow_id, ReasoningStep(
            timestamp=datetime.now(),
            thought=f"Executing {tool_name}",
            action=tool_name
        ))
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        await add_reasoning_step(self.workflow_id, ReasoningStep(
            timestamp=datetime.now(),
            thought=f"Agent using {action.tool}: {action.log[:100]}..."
        ))

# Agent creation
def create_communications_agent(workflow_id: str) -> AgentExecutor:
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=ANTHROPIC_API_KEY,
        temperature=0.1
    )
    
    tools = [
        GetCaseAnalysisTool(),
        ComposeEmailTool(),
        SendEmailTool()
    ]
    
    system_prompt = load_prompt("communications_agent_system_prompt.md")
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad")
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=10
    )

# Workflow execution
async def execute_workflow(workflow_id: str) -> None:
    # Load workflow state
    response = await http_client.get(f"{BACKEND_URL}/api/workflows/{workflow_id}")
    response.raise_for_status()
    data = response.json()
    
    # Update to processing
    await update_workflow_status(workflow_id, WorkflowStatus.PROCESSING)
    
    try:
        # Execute agent
        callback_handler = WorkflowCallbackHandler(workflow_id)
        agent = create_communications_agent(workflow_id)
        
        await agent.ainvoke(
            {"input": data["initial_prompt"]},
            config={"callbacks": [callback_handler]}
        )
        
        await update_workflow_status(workflow_id, WorkflowStatus.COMPLETED)
        
    except Exception as e:
        logger.error(f"Workflow {workflow_id} failed: {e}")
        await update_workflow_status(workflow_id, WorkflowStatus.FAILED)
        raise

# FastAPI app
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
    response = await http_client.get(f"{BACKEND_URL}/")
    response.raise_for_status()
    return {"status": "operational", "backend": "connected"}

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    workflow_id = f"wf_chat_{uuid.uuid4().hex[:8]}"
    
    # Create workflow
    state = WorkflowState(
        workflow_id=workflow_id,
        status=WorkflowStatus.PENDING,
        initial_prompt=request.message,
        reasoning_chain=[],
        created_at=datetime.now(),
        updated_at=datetime.now()
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