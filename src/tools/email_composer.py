"""
Email composer tool implementation
"""
import json
import logging
from langchain.tools import BaseTool

from src.config.settings import BACKEND_URL
from src.services.http_client import get_http_client
from src.services.prompt_loader import load_email_templates
from src.services.backend_api import get_case_with_documents

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
            
            # Get case data with enhanced document information
            case_data = await get_case_with_documents(case_id)
            
            # Load templates
            templates = load_email_templates()
            
            if email_type not in templates:
                # Default to initial_reminder if type not found
                email_type = "initial_reminder"
            
            template = templates[email_type]
            
            # Format documents list for email with enhanced context
            requested_docs = case_data.get("requested_documents", [])
            if requested_docs:
                # Enhanced document formatting with completion status
                doc_lines = []
                pending_docs = []
                completed_docs = []
                
                for doc in requested_docs:
                    if isinstance(doc, dict):
                        doc_name = doc.get('document_name', 'Unknown Document')
                        is_completed = doc.get('is_completed', False)
                        description = doc.get('description', '')
                        
                        if is_completed:
                            completed_docs.append(doc_name)
                        else:
                            pending_docs.append(doc_name)
                            # Add description if available for pending documents
                            if description and description != f"Required document: {doc_name}":
                                doc_lines.append(f"• {doc_name} - {description}")
                            else:
                                doc_lines.append(f"• {doc_name}")
                    else:
                        # Fallback for string format
                        pending_docs.append(str(doc))
                        doc_lines.append(f"• {doc}")
                
                # Create contextual document list based on email type
                if email_type in ["follow_up_reminder", "urgent_reminder"] and completed_docs:
                    # For follow-up emails, focus on remaining documents
                    doc_list = "\n".join(doc_lines)
                    if completed_docs:
                        doc_list += f"\n\nThank you for already providing: {', '.join(completed_docs)}"
                else:
                    # For initial emails, show all requested documents
                    doc_list = "\n".join(doc_lines) if doc_lines else "\n".join([f"• {doc}" for doc in pending_docs])
            else:
                doc_list = "No specific documents listed"
            
            # Format email
            subject = template["subject_template"].format(client_name=case_data["client_name"])
            body = template["body_template"].format(
                client_name=case_data["client_name"],
                requested_documents=doc_list
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