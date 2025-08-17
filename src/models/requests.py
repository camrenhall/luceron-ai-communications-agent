"""
API request models
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    message: str


class RequestedDocumentUpdate(BaseModel):
    """Model for updating requested document fields"""
    document_name: Optional[str] = None
    description: Optional[str] = None
    is_completed: Optional[bool] = None
    is_flagged_for_review: Optional[bool] = None
    notes: Optional[str] = None


class RequestedDocumentResponse(BaseModel):
    """Model for requested document response from backend"""
    requested_doc_id: str
    document_name: str
    description: Optional[str] = None
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    is_flagged_for_review: bool = False
    notes: Optional[str] = None
    requested_at: datetime
    updated_at: datetime
    case_id: str