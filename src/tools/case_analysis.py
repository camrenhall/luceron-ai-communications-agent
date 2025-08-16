"""
Case analysis tool implementation
"""
import json
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client


class GetCaseAnalysisTool(BaseTool):
    name: str = "get_case_analysis"
    description: str = "Get case details and communication history. Input: case_id"
    
    def _run(self, case_id: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, case_id: str) -> str:
        http_client = get_http_client()
        
        # Get basic case details
        case_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}")
        case_response.raise_for_status()
        case_data = case_response.json()
        
        # Try to get communication history
        try:
            comm_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}/communications")
            if comm_response.status_code == 200:
                return json.dumps(comm_response.json(), indent=2)
        except:
            pass
        
        # Return basic case data with new schema format
        return json.dumps({
            "case_id": case_id,
            "client_name": case_data["client_name"],
            "client_email": case_data["client_email"],
            "client_phone": case_data.get("client_phone"),
            "status": case_data.get("status", "unknown"),
            "requested_documents": case_data.get("requested_documents", []),
            "last_communication_date": case_data.get("last_communication_date"),
            "communication_summary": {"total_communications": 0, "total_emails": 0}
        }, indent=2)