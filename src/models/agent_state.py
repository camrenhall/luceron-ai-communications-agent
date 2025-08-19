"""
Agent state management data models
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
from pydantic import BaseModel


class ConversationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user" 
    ASSISTANT = "assistant"
    FUNCTION = "function"


class AgentType(str, Enum):
    COMMUNICATIONS_AGENT = "CommunicationsAgent"
    ANALYSIS_AGENT = "AnalysisAgent"


class AgentConversation(BaseModel):
    """Agent conversation for state tracking"""
    conversation_id: str
    case_id: str
    agent_type: AgentType
    status: ConversationStatus
    total_tokens_used: int = 0
    created_at: datetime
    updated_at: datetime


class AgentMessage(BaseModel):
    """Message within an agent conversation"""
    message_id: str
    conversation_id: str
    role: MessageRole
    content: Dict[str, Any]
    sequence_number: int
    total_tokens: Optional[int] = None
    model_used: str = "claude-3-5-sonnet-20241022"
    
    # Function call details
    function_name: Optional[str] = None
    function_arguments: Optional[Dict[str, Any]] = None
    function_response: Optional[Dict[str, Any]] = None
    
    created_at: datetime


class AgentContext(BaseModel):
    """Persistent context storage for agents"""
    context_id: str
    case_id: str
    agent_type: AgentType
    context_key: str
    context_value: Dict[str, Any]
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AgentSummary(BaseModel):
    """Conversation summary for token management"""
    summary_id: str
    conversation_id: str
    summary_content: str
    messages_summarized: int
    tokens_saved: Optional[int] = None
    created_at: datetime


class ConversationWithMessages(BaseModel):
    """Complete conversation with messages and summaries"""
    conversation: AgentConversation
    messages: List[AgentMessage]
    summaries: List[AgentSummary] = []


# Context value schemas for type safety
class ClientPreferences(BaseModel):
    """Client communication preferences context"""
    communication_style: Literal["formal", "casual", "professional"]
    preferred_contact_method: Literal["email", "phone", "both"]
    best_contact_times: List[str] = []
    language_preference: str = "English"
    document_format_preference: str = "PDF"
    urgency_threshold: Literal["low", "medium", "high"] = "medium"


class DocumentFindings(BaseModel):
    """Document analysis findings context"""
    document_type: str
    key_findings: Dict[str, Any]
    risk_factors: List[str] = []
    analysis_confidence: float
    analysis_date: datetime
    reviewer_notes: Optional[str] = None


class EmailHistory(BaseModel):
    """Email communication history context"""
    last_email_sent: datetime
    email_count: int = 0
    email_types_sent: List[str] = []
    client_responses: List[Dict[str, Any]] = []
    effectiveness_score: Optional[float] = None


class CaseProgress(BaseModel):
    """Case progress tracking context"""
    tasks_completed: List[str] = []
    pending_tasks: List[str] = []
    next_actions: List[str] = []
    progress_percentage: float = 0.0
    last_activity: datetime
    milestones_reached: List[str] = []