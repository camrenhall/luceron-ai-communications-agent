"""
Case analysis tool implementation
"""
import json
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client
from src.services.backend_api import get_case_with_documents


class GetCaseAnalysisTool(BaseTool):
    name: str = "get_case_analysis"
    description: str = "Get case details and communication history. Input: case_id"
    
    def _run(self, case_id: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, case_id: str) -> str:
        http_client = get_http_client()
        
        # Get enhanced case details with documents
        case_data = await get_case_with_documents(case_id)
        
        # Try to get communication history
        try:
            comm_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}/communications")
            if comm_response.status_code == 200:
                comm_data = comm_response.json()
                # Enhance with document summary
                requested_docs = case_data.get("requested_documents", [])
                total_docs = len(requested_docs)
                completed_docs = sum(1 for doc in requested_docs if doc.get("is_completed", False))
                
                enhanced_response = {
                    **comm_data,
                    "document_summary": {
                        "total_documents": total_docs,
                        "completed_documents": completed_docs,
                        "pending_documents": total_docs - completed_docs,
                        "completion_rate": f"{(completed_docs/total_docs*100):.1f}%" if total_docs > 0 else "0%"
                    }
                }
                return json.dumps(enhanced_response, indent=2)
        except:
            pass
        
        # Return enhanced case data with document analysis
        requested_docs = case_data.get("requested_documents", [])
        total_docs = len(requested_docs)
        completed_docs = sum(1 for doc in requested_docs if doc.get("is_completed", False))
        flagged_docs = sum(1 for doc in requested_docs if doc.get("is_flagged_for_review", False))
        
        return json.dumps({
            "case_id": case_id,
            "client_name": case_data["client_name"],
            "client_email": case_data["client_email"],
            "client_phone": case_data.get("client_phone"),
            "status": case_data.get("status", "unknown"),
            "requested_documents": requested_docs,
            "document_summary": {
                "total_documents": total_docs,
                "completed_documents": completed_docs,
                "pending_documents": total_docs - completed_docs,
                "flagged_for_review": flagged_docs,
                "completion_rate": f"{(completed_docs/total_docs*100):.1f}%" if total_docs > 0 else "0%"
            },
            "last_communication_date": case_data.get("last_communication_date"),
            "communication_summary": {"total_communications": 0, "total_emails": 0}
        }, indent=2)