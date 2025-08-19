"""
Backend API integration service
"""
from typing import Optional, List, Dict, Any

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client


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
