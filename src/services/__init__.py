"""
Business services and external integrations
"""
from .http_client import init_http_client, close_http_client, get_http_client
from .backend_api import create_workflow_state, update_workflow_status
from .prompt_loader import load_prompt, load_email_templates
from .workflow_service import execute_workflow

__all__ = [
    "init_http_client", "close_http_client", "get_http_client",
    "create_workflow_state", "update_workflow_status",
    "load_prompt", "load_email_templates",
    "execute_workflow"
]