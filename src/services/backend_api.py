"""
Backend API integration service
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client

logger = logging.getLogger(__name__)


# Requested Documents API Functions

async def get_case_with_documents(case_id: str) -> Dict[str, Any]:
    """Get case details including requested documents from the backend"""
    http_client = get_http_client()
    response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}")
    response.raise_for_status()
    return response.json()


async def update_requested_document(requested_doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a requested document using the backend API"""
    http_client = get_http_client()
    response = await http_client.put(
        f"{BACKEND_URL}/api/cases/documents/{requested_doc_id}",
        json=updates
    )
    response.raise_for_status()
    return response.json()




async def get_pending_reminders() -> List[Dict[str, Any]]:
    """Get cases that need reminder emails"""
    http_client = get_http_client()
    response = await http_client.get(f"{BACKEND_URL}/api/cases/pending-reminders")
    response.raise_for_status()
    return response.json()


async def search_cases_by_name(
    client_name: str, 
    status: Optional[str] = "OPEN",
    use_fuzzy: bool = True,
    fuzzy_threshold: float = 0.3,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Search for cases by client name with intelligent fuzzy matching"""
    http_client = get_http_client()
    
    search_payload = {
        "client_name": client_name,
        "use_fuzzy_matching": use_fuzzy,
        "fuzzy_threshold": fuzzy_threshold,
        "limit": limit
    }
    
    if status:
        search_payload["status"] = status
    
    response = await http_client.post(
        f"{BACKEND_URL}/api/cases/search",
        json=search_payload
    )
    response.raise_for_status()
    result = response.json()
    return result.get("cases", [])


# Agent State Management API Functions

# ============================================================================
# Agent Conversations API
# ============================================================================

async def create_conversation(agent_type: str = "CommunicationsAgent", status: str = "ACTIVE") -> Dict[str, Any]:
    """Create a new agent conversation for state tracking"""
    http_client = get_http_client()
    
    conversation_data = {
        "agent_type": agent_type,
        "status": status
    }
    
    response = await http_client.post(
        f"{BACKEND_URL}/api/agent/conversations",
        json=conversation_data
    )
    response.raise_for_status()
    return response.json()


async def get_conversation_with_messages(
    conversation_id: str, 
    include_summaries: bool = True,
    include_function_calls: bool = True
) -> Dict[str, Any]:
    """Get conversation with full message history and summaries"""
    http_client = get_http_client()
    
    params = {
        "include_summaries": str(include_summaries).lower(),
        "include_function_calls": str(include_function_calls).lower()
    }
    
    response = await http_client.get(
        f"{BACKEND_URL}/api/agent/conversations/{conversation_id}/full",
        params=params
    )
    response.raise_for_status()
    return response.json()


async def get_or_create_conversation(
    agent_type: str = "CommunicationsAgent",
    conversation_id: Optional[str] = None
) -> str:
    """Get existing conversation by ID or create new one for agent"""
    http_client = get_http_client()
    
    # If conversation_id is provided, validate it exists and is active
    if conversation_id:
        response = await http_client.get(
            f"{BACKEND_URL}/api/agent/conversations/{conversation_id}"
        )
        
        if response.status_code == 404:
            raise ValueError(f"Conversation {conversation_id} not found")
        elif response.status_code != 200:
            response.raise_for_status()  # This will raise the HTTP error
            
        conversation = response.json()
        
        # Verify conversation is active and matches agent type
        if conversation.get("status") != "ACTIVE":
            raise ValueError(f"Conversation {conversation_id} is not active (status: {conversation.get('status')})")
        
        if conversation.get("agent_type") != agent_type:
            raise ValueError(f"Conversation {conversation_id} agent type mismatch. Expected: {agent_type}, Got: {conversation.get('agent_type')}")
        
        # Conversation is valid, return it
        return conversation_id
    
    # Only create new conversation if no conversation_id was provided
    new_conversation = await create_conversation(agent_type)
    return new_conversation["conversation_id"]


# ============================================================================
# Agent Messages API  
# ============================================================================

async def add_message(
    conversation_id: str,
    role: str,
    content: Dict[str, Any],
    model_used: str = "claude-3-5-sonnet-20241022",
    total_tokens: Optional[int] = None,
    function_name: Optional[str] = None,
    function_arguments: Optional[Dict[str, Any]] = None,
    function_response: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Add a message to an agent conversation"""
    http_client = get_http_client()
    
    message_data = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "model_used": model_used
    }
    
    # Add optional fields if provided
    if total_tokens is not None:
        message_data["total_tokens"] = total_tokens
    if function_name:
        message_data["function_name"] = function_name
    if function_arguments:
        message_data["function_arguments"] = function_arguments  
    if function_response:
        message_data["function_response"] = function_response
    
    response = await http_client.post(
        f"{BACKEND_URL}/api/agent/messages",
        json=message_data
    )
    response.raise_for_status()
    return response.json()


async def get_conversation_history(
    conversation_id: str,
    limit: int = 50,
    include_function_calls: bool = True
) -> List[Dict[str, Any]]:
    """Get recent conversation history with optional function call details"""
    http_client = get_http_client()
    
    params = {
        "limit": limit,
        "include_function_calls": str(include_function_calls).lower()
    }
    
    response = await http_client.get(
        f"{BACKEND_URL}/api/agent/messages/conversation/{conversation_id}/history",
        params=params
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# Agent Context API
# ============================================================================

async def store_agent_context(
    case_id: str,
    agent_type: str,
    context_key: str,
    context_value: Dict[str, Any],
    expires_at: Optional[datetime] = None
) -> Dict[str, Any]:
    """Store persistent context for an agent working on a case"""
    http_client = get_http_client()
    
    context_data = {
        "case_id": case_id,
        "agent_type": agent_type,
        "context_key": context_key,
        "context_value": context_value
    }
    
    if expires_at:
        context_data["expires_at"] = expires_at.isoformat()
    
    response = await http_client.post(
        f"{BACKEND_URL}/api/agent/context",
        json=context_data
    )
    response.raise_for_status()
    return response.json()


async def get_case_agent_context(
    case_id: str,
    agent_type: str = "CommunicationsAgent"
) -> Dict[str, Any]:
    """Retrieve all persistent context for agent working on case"""
    http_client = get_http_client()
    
    response = await http_client.get(
        f"{BACKEND_URL}/api/agent/context/case/{case_id}/agent/{agent_type}"
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# Agent Summaries API
# ============================================================================

async def create_auto_summary(
    conversation_id: str,
    messages_to_summarize: int = 15
) -> Dict[str, Any]:
    """Create automatic summary of older conversation messages"""
    http_client = get_http_client()
    
    params = {"messages_to_summarize": messages_to_summarize}
    
    response = await http_client.post(
        f"{BACKEND_URL}/api/agent/summaries/conversation/{conversation_id}/auto-summary",
        params=params
    )
    response.raise_for_status()
    return response.json()


async def get_latest_summary(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get the most recent summary for a conversation"""
    http_client = get_http_client()
    
    response = await http_client.get(
        f"{BACKEND_URL}/api/agent/summaries/conversation/{conversation_id}/latest"
    )
    
    if response.status_code == 404:
        return None
    
    response.raise_for_status()
    return response.json()


async def get_message_count(conversation_id: str) -> int:
    """Get total number of messages in a conversation"""
    http_client = get_http_client()
    
    response = await http_client.get(
        f"{BACKEND_URL}/api/agent/conversations/{conversation_id}/message-count"
    )
    response.raise_for_status()
    result = response.json()
    return result.get("message_count", 0)


async def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get conversation details by ID"""
    http_client = get_http_client()
    
    try:
        response = await http_client.get(
            f"{BACKEND_URL}/api/agent/conversations/{conversation_id}"
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            response.raise_for_status()
            return None
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}")
        return None


