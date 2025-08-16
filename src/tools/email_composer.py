"""
Email composer tool implementation
"""
import json
import logging
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client
from src.services.prompt_loader import load_email_templates

logger = logging.getLogger(__name__)


class ComposeEmailTool(BaseTool):
    name: str = "compose_email"
    description: str = "Compose email based on case context. Input: JSON with case_id, email_type (use: initial_reminder, follow_up_reminder, or urgent_reminder)"
    
    def _run(self, email_data: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, email_data: str) -> str:
        try:
            data = json.loads(email_data)
            case_id = data["case_id"]
            email_type = data.get("email_type", "initial_reminder")
            
            # Normalize email type to supported types
            if email_type in ["initial_document_request", "initial_contact", "initial"]:
                email_type = "initial_reminder"
            elif email_type in ["followup", "follow_up", "reminder"]:
                email_type = "follow_up_reminder"
            elif email_type in ["urgent", "urgent_request"]:
                email_type = "urgent_reminder"
            
            logger.info(f"✍️ Composing {email_type} email for case {case_id}")
            
            # Get case data
            http_client = get_http_client()
            case_response = await http_client.get(f"{BACKEND_URL}/api/cases/{case_id}")
            case_response.raise_for_status()
            case_data = case_response.json()
            
            # Load templates
            templates = load_email_templates()
            
            if email_type not in templates:
                # Default to initial_reminder if type not found
                email_type = "initial_reminder"
            
            template = templates[email_type]
            
            # Format documents list for email
            requested_docs = case_data.get("requested_documents", [])
            if requested_docs:
                # If it's the new format (array of objects)
                if isinstance(requested_docs[0], dict):
                    doc_list = "\n".join([f"• {doc['document_name']}" for doc in requested_docs])
                else:
                    # If it's an array of strings
                    doc_list = "\n".join([f"• {doc}" for doc in requested_docs])
            else:
                doc_list = "No specific documents listed"
            
            # Format email
            subject = template["subject_template"].format(client_name=case_data["client_name"])
            body = template["body_template"].format(
                client_name=case_data["client_name"],
                documents_requested=doc_list
            )
            
            result = {
                "subject": subject,
                "body": body,
                "html_body": body.replace("\n", "<br>"),
                "recipient": case_data["client_email"],
                "case_id": case_id,
                "email_type": email_type
            }
            
            logger.info(f"✍️ Successfully composed {email_type} email for {case_data['client_name']}")
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            error_msg = f"Email composition failed: {str(e)}"
            logger.error(f"✍️ Composition ERROR: {error_msg}")
            raise Exception(error_msg)