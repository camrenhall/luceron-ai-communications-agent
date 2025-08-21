"""
Data models and schemas
"""
from .requests import ChatRequest
from .agent_state import (
    MessageRole, AgentType,
    ClientPreferences, EmailHistory, CaseProgress
)

__all__ = [
    "ChatRequest",
    # Agent State Enums
    "MessageRole", "AgentType",
    # Context Schemas  
    "ClientPreferences", "EmailHistory", "CaseProgress"
]