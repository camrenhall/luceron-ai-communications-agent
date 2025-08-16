"""
Workflow-related data models
"""
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel


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
    workflow_id: Optional[str] = None
    agent_type: str = "CommunicationsAgent"
    case_id: Optional[str] = None
    status: WorkflowStatus
    initial_prompt: str
    reasoning_chain: List[ReasoningStep]
    created_at: datetime