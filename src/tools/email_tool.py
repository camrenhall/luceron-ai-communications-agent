"""
Consolidated email tool that handles both composition and sending
"""
import json
import logging
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client
from src.services.prompt_loader import load_email_templates
from src.services.backend_api import get_case_with_documents

logger = logging.getLogger(__name__)


class EmailTool(BaseTool):
    name: str = "compose_and_send_email"
    description: str = "Compose and send email based on case context. Input: JSON with case_id, email_type (use: initial_reminder, follow_up_reminder, or urgent_reminder)"
    
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
            
            logger.info(f"✍️ Composing and sending {email_type} email for case {case_id}")
            
            # COMPOSE EMAIL
            # Get case data with enhanced document information
            case_data = await get_case_with_documents(case_id)
            
            # Load templates
            templates = load_email_templates()
            
            if email_type not in templates:
                raise ValueError(f"Email template '{email_type}' not found in prompts/email_templates.md. Available templates: {list(templates.keys())}")
            
            template = templates[email_type]
            
            # Document functionality has been removed from the backend
            doc_list = "Please refer to your case for document requirements"
            
            # Format email
            subject = template["subject_template"].format(client_name=case_data["client_name"])
            body = template["body_template"].format(
                client_name=case_data["client_name"],
                requested_documents=doc_list
            )
            
            email_payload = {
                "recipient_email": case_data["client_email"],
                "subject": subject,
                "body": body,
                "case_id": case_id,
                "email_type": email_type
            }
            
            logger.info(f"✍️ Successfully composed {email_type} email for {case_data['client_name']}")
            
            # SEND EMAIL
            logger.info(f"📧 Sending {email_type} email to {case_data['client_name']} at {case_data['client_email']}")
            
            http_client = get_http_client()
            response = await http_client.post(f"{BACKEND_URL}/api/send-email", json=email_payload)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"📧 Successfully sent {email_type} email to {case_data['client_name']} (Message ID: {result.get('message_id', 'N/A')})")
            
            return json.dumps({
                "status": "composed_and_sent",
                "message_id": result["message_id"],
                "recipient": result["recipient"],
                "subject": subject,
                "email_type": email_type,
                "case_id": case_id
            }, indent=2)
            
        except Exception as e:
            error_msg = f"Email composition and sending failed: {str(e)}"
            logger.error(f"📧 Email ERROR: {error_msg}")
            raise Exception(error_msg)