"""
API request models
"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str