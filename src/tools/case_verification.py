"""
Case verification tool for confirming case details before taking actions
"""
import json
from langchain.tools import BaseTool

from src.services.backend_api import get_case_with_documents


class VerifyCaseDetailsTool(BaseTool):
    name: str = "verify_case_details"
    description: str = """Verify case details before taking any actions. Use this tool to confirm 
    that you have the correct case before sending emails or making updates. 
    Input: case_id (UUID) to verify."""
    
    def _run(self, case_id: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, case_id: str) -> str:
        """
        Verify and display case details for confirmation
        """
        try:
            case_data = await get_case_with_documents(case_id)
            
            # Extract key verification information
            verification_info = {
                "case_id": case_id,
                "client_name": case_data.get("client_name"),
                "client_email": case_data.get("client_email"), 
                "client_phone": case_data.get("client_phone"),
                "status": case_data.get("status"),
                "created_at": case_data.get("created_at"),
                "last_communication_date": case_data.get("last_communication_date"),
                "requested_documents": case_data.get("requested_documents", [])
            }
            
            # Calculate document summary
            docs = verification_info["requested_documents"]
            total_docs = len(docs)
            completed_docs = sum(1 for doc in docs if doc.get("is_completed", False))
            pending_docs = total_docs - completed_docs
            
            # Create human-readable verification summary
            summary = {
                "verification_status": "confirmed",
                "case_details": {
                    "client_name": verification_info["client_name"],
                    "email": verification_info["client_email"],
                    "phone": verification_info["client_phone"] or "Not provided",
                    "case_status": verification_info["status"],
                    "created": verification_info["created_at"]
                },
                "document_summary": {
                    "total_documents": total_docs,
                    "completed": completed_docs,
                    "pending": pending_docs,
                    "completion_rate": f"{(completed_docs/total_docs*100):.1f}%" if total_docs > 0 else "0%"
                },
                "communication_status": {
                    "last_communication": verification_info["last_communication_date"] or "No previous communications"
                },
                "verification_message": f"✅ Case verified for {verification_info['client_name']} ({verification_info['client_email']}). Ready to proceed with communications."
            }
            
            return json.dumps(summary, indent=2)
            
        except Exception as e:
            return json.dumps({
                "verification_status": "failed",
                "error": str(e),
                "message": f"❌ Could not verify case {case_id}. Please check the case ID and try again."
            }, indent=2)


class RequestClarificationTool(BaseTool):
    name: str = "request_user_clarification"
    description: str = """Request clarification from the user when case identification is ambiguous.
    Use this when multiple cases match a name or when you need additional information.
    Input should be a clear question for the user with available options."""
    
    def _run(self, clarification_question: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, clarification_question: str) -> str:
        """
        Request clarification from the user
        """
        return json.dumps({
            "action": "request_clarification",
            "question": clarification_question,
            "status": "waiting_for_user_input",
            "message": "🤔 I need additional information to proceed. Please provide clarification."
        }, indent=2)