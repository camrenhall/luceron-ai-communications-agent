"""
Business services and external integrations
"""
from .http_client import init_http_client, close_http_client, get_http_client
from .prompt_loader import load_prompt, load_email_templates
from .backend_api import (
    # Agent State Management
    create_conversation, get_or_create_conversation,
    add_message, get_conversation_history,
    store_agent_context, get_case_agent_context,
    create_auto_summary, get_latest_summary, get_message_count,
    # Case Management  
    get_case_with_documents
)
from .agent_state_manager import AgentStateManager
from .token_manager import TokenManager

__all__ = [
    # HTTP Client
    "init_http_client", "close_http_client", "get_http_client",
    # Prompt Management
    "load_prompt", "load_email_templates",
    # Agent State Management
    "create_conversation", "get_or_create_conversation", 
    "add_message", "get_conversation_history",
    "store_agent_context", "get_case_agent_context",
    "create_auto_summary", "get_latest_summary", "get_message_count",
    "AgentStateManager", "TokenManager",
    # Case Management
    "get_case_with_documents"
]