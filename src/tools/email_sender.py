"""
Email sender tool implementation
"""
import json
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client


class SendEmailTool(BaseTool):
    name: str = "send_email"
    description: str = "Send email via backend. Input: JSON with recipient_email, subject, body, case_id, email_type"
    
    def _run(self, email_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, email_data: str) -> str:
        data = json.loads(email_data)
        
        http_client = get_http_client()
        response = await http_client.post(f"{BACKEND_URL}/api/send-email", json=data)
        response.raise_for_status()
        result = response.json()
        
        return json.dumps({
            "status": "sent",
            "message_id": result["message_id"],
            "recipient": result["recipient"]
        }, indent=2)