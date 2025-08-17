"""
Document manager tool implementation for managing requested documents
"""
import json
import logging
from langchain.tools import BaseTool

from src.services.backend_api import (
    get_case_with_documents,
    update_requested_document,
    get_pending_reminders
)

logger = logging.getLogger(__name__)


class UpdateDocumentStatusTool(BaseTool):
    name: str = "update_document_status"
    description: str = "Update status of a requested document. Input: JSON with requested_doc_id, and optional fields: document_name, description, is_completed, is_flagged_for_review, notes"
    
    def _run(self, update_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, update_data: str) -> str:
        try:
            data = json.loads(update_data)
            requested_doc_id = data["requested_doc_id"]
            
            # Extract update fields
            updates = {}
            if "document_name" in data:
                updates["document_name"] = data["document_name"]
            if "description" in data:
                updates["description"] = data["description"]
            if "is_completed" in data:
                updates["is_completed"] = data["is_completed"]
            if "is_flagged_for_review" in data:
                updates["is_flagged_for_review"] = data["is_flagged_for_review"]
            if "notes" in data:
                updates["notes"] = data["notes"]
            
            logger.info(f"📄 Updating document {requested_doc_id} with: {updates}")
            
            result = await update_requested_document(requested_doc_id, updates)
            
            logger.info(f"📄 Successfully updated document {requested_doc_id}")
            
            return json.dumps({
                "status": "success",
                "requested_doc_id": requested_doc_id,
                "updated_fields": updates,
                "result": result
            }, indent=2)
            
        except Exception as e:
            error_msg = f"Document update failed: {str(e)}"
            logger.error(f"📄 Document update ERROR: {error_msg}")
            raise Exception(error_msg)


class GetDocumentStatusTool(BaseTool):
    name: str = "get_document_status"
    description: str = "Get detailed document status for a case. Input: case_id"
    
    def _run(self, case_id: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, case_id: str) -> str:
        try:
            logger.info(f"📄 Getting document status for case {case_id}")
            
            case_data = await get_case_with_documents(case_id)
            requested_documents = case_data.get("requested_documents", [])
            
            # Format document status summary
            total_docs = len(requested_documents)
            completed_docs = sum(1 for doc in requested_documents if doc.get("is_completed", False))
            flagged_docs = sum(1 for doc in requested_documents if doc.get("is_flagged_for_review", False))
            
            result = {
                "case_id": case_id,
                "client_name": case_data.get("client_name"),
                "client_email": case_data.get("client_email"),
                "document_summary": {
                    "total_documents": total_docs,
                    "completed_documents": completed_docs,
                    "pending_documents": total_docs - completed_docs,
                    "flagged_for_review": flagged_docs
                },
                "requested_documents": requested_documents
            }
            
            logger.info(f"📄 Retrieved {total_docs} documents for case {case_id} ({completed_docs} completed)")
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_msg = f"Document status retrieval failed: {str(e)}"
            logger.error(f"📄 Document status ERROR: {error_msg}")
            raise Exception(error_msg)


class GetPendingRemindersTool(BaseTool):
    name: str = "get_pending_reminders"
    description: str = "Get all cases that need reminder emails for pending documents. No input required."
    
    def _run(self, input_data: str = "") -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, input_data: str = "") -> str:
        try:
            logger.info("📄 Getting cases with pending document reminders")
            
            pending_cases = await get_pending_reminders()
            
            result = {
                "total_cases_needing_reminders": len(pending_cases),
                "pending_cases": pending_cases
            }
            
            logger.info(f"📄 Found {len(pending_cases)} cases needing reminders")
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_msg = f"Pending reminders retrieval failed: {str(e)}"
            logger.error(f"📄 Pending reminders ERROR: {error_msg}")
            raise Exception(error_msg)