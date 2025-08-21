"""
Agent state management data models
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
from pydantic import BaseModel


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user" 
    ASSISTANT = "assistant"
    FUNCTION = "function"


class AgentType(str, Enum):
    COMMUNICATIONS_AGENT = "CommunicationsAgent"
    ANALYSIS_AGENT = "AnalysisAgent"


# Context value schemas for type safety
class ClientPreferences(BaseModel):
    """Client communication preferences context"""
    communication_style: Literal["formal", "casual", "professional"]
    preferred_contact_method: Literal["email", "phone", "both"]
    best_contact_times: List[str] = []
    language_preference: str = "English"
    document_format_preference: str = "PDF"
    urgency_threshold: Literal["low", "medium", "high"] = "medium"


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