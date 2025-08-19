"""
Data models and schemas
"""
from .requests import ChatRequest
from .agent_state import (
    ConversationStatus, MessageRole, AgentType,
    AgentConversation, AgentMessage, AgentContext, AgentSummary, 
    ConversationWithMessages,
    ClientPreferences, DocumentFindings, EmailHistory, CaseProgress
)

__all__ = [
    "ChatRequest",
    # Agent State Enums
    "ConversationStatus", "MessageRole", "AgentType",
    # Agent State Models
    "AgentConversation", "AgentMessage", "AgentContext", "AgentSummary",
    "ConversationWithMessages",
    # Context Schemas  
    "ClientPreferences", "DocumentFindings", "EmailHistory", "CaseProgress"
]