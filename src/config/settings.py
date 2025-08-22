"""
Application configuration and environment settings
"""
import os
from typing import Dict, Any, Optional

# Environment configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL")
PORT = int(os.getenv("PORT", 8082))

# OAuth2 configuration - private key from environment, service details static
COMMUNICATIONS_AGENT_PRIVATE_KEY = os.getenv("COMMUNICATIONS_AGENT_PRIVATE_KEY")

# Static Luceron service configuration
LUCERON_SERVICE_ID = "luceron_ai_communications_agent"

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
if not BACKEND_URL:
    raise ValueError("BACKEND_URL environment variable is required")


def get_luceron_config() -> Optional[Dict[str, Any]]:
    """
    Get Luceron OAuth2 configuration with private key from environment
    
    Returns:
        Configuration dictionary or None if private key not available
    """
    if not COMMUNICATIONS_AGENT_PRIVATE_KEY:
        return None
        
    return {
        'service_id': LUCERON_SERVICE_ID,
        'private_key': COMMUNICATIONS_AGENT_PRIVATE_KEY,
        'base_url': BACKEND_URL
    }