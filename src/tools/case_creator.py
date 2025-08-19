"""
Case creator tool implementation
"""
import json
import logging
import uuid
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client
from src.services.prompt_loader import load_email_templates

logger = logging.getLogger(__name__)


class CreateCaseTool(BaseTool):
    name: str = "create_case"
    description: str = "Create a new case for a client. Input: JSON with client_name, client_email, documents_requested (REQUIRED: string or array of document names), client_phone (optional)"
    
    def _run(self, case_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, case_data: str) -> str:
        try:
            data = json.loads(case_data)
            client_name = data["client_name"]
            client_email = data["client_email"]
            # documents_requested is REQUIRED - this is the core purpose of the platform
            if "documents_requested" not in data:
                raise Exception("documents_requested is required - this is a document collection platform!")
            documents_requested = data["documents_requested"]
            client_phone = data.get("client_phone")
            
            logger.info(f"🆕 Creating new case for client: {client_name} ({client_email})")
            
            # Process documents_requested - convert to standardized array format
            if isinstance(documents_requested, str):
                # Split by common delimiters and clean up
                doc_names = [doc.strip() for doc in documents_requested.replace(',', '\n').replace(';', '\n').split('\n') if doc.strip()]
            elif isinstance(documents_requested, list):
                doc_names = [str(doc).strip() for doc in documents_requested if str(doc).strip()]
            else:
                doc_names = [str(documents_requested).strip()] if str(documents_requested).strip() else []
            
            # Validate that we have at least one document
            if not doc_names:
                raise Exception("At least one document must be requested - this is a document collection platform!")
            
            # Create requested documents array in the format expected by backend
            requested_documents = []
            for doc_name in doc_names:
                requested_documents.append({
                    "document_name": doc_name,
                    "description": f"Required document: {doc_name}"
                })
            
            # Create case payload matching new backend schema
            case_payload = {
                "client_name": client_name,
                "client_email": client_email,
                "client_phone": client_phone,
                "requested_documents": requested_documents
            }
            
            http_client = get_http_client()
            response = await http_client.post(f"{BACKEND_URL}/api/cases", json=case_payload)
            response.raise_for_status()
            case_result = response.json()
            created_case_id = case_result["case_id"]
            
            logger.info(f"🆕 Successfully created case {created_case_id} for {client_name}")
            
            # Automatically send initial email to client
            logger.info(f"📧 Automatically sending initial email to {client_name}")
            
            # Load templates and compose email
            templates = load_email_templates()
            template = templates.get("initial_reminder", templates.get("initial_contact"))
            
            if template:
                # Format documents list for email
                doc_list = "\n".join([f"• {doc_name}" for doc_name in doc_names])
                
                subject = template["subject_template"].format(client_name=client_name)
                body = template["body_template"].format(
                    client_name=client_name,
                    documents_requested=doc_list
                )
                
                # Send email via backend
                email_payload = {
                    "recipient_email": client_email,
                    "subject": subject,
                    "body": body,
                    "case_id": created_case_id,
                    "email_type": "initial_contact"
                }
                
                email_response = await http_client.post(f"{BACKEND_URL}/api/send-email", json=email_payload)
                email_response.raise_for_status()
                email_result = email_response.json()
                
                logger.info(f"📧 Successfully sent initial email to {client_name} (Message ID: {email_result.get('message_id')})")
                
                return json.dumps({
                    "status": "success",
                    "case_id": created_case_id,
                    "client_name": client_name,
                    "client_email": client_email,
                    "client_phone": client_phone,
                    "requested_documents": requested_documents,
                    "email_sent": True,
                    "email_message_id": email_result.get("message_id")
                }, indent=2)
            else:
                logger.warning(f"⚠️ No email template found, case created but no email sent")
                return json.dumps({
                    "status": "success",
                    "case_id": created_case_id,
                    "client_name": client_name,
                    "client_email": client_email,
                    "client_phone": client_phone,
                    "requested_documents": requested_documents,
                    "email_sent": False,
                    "warning": "No email template available"
                }, indent=2)
                
        except Exception as e:
            error_msg = f"Case creation failed: {str(e)}"
            logger.error(f"🆕 Case creation ERROR: {error_msg}")
            raise Exception(error_msg)