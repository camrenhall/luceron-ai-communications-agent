"""
Business services and external integrations
"""
from .http_client import init_http_client, close_http_client, get_http_client
from .prompt_loader import load_prompt, load_email_templates

__all__ = [
    "init_http_client", "close_http_client", "get_http_client",
    "load_prompt", "load_email_templates"
]