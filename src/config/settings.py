"""
Application configuration and environment settings
"""
import os

# Environment configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")
PORT = int(os.getenv("PORT", 8082))

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
if not BACKEND_URL:
    raise ValueError("BACKEND_URL environment variable is required")
if not BACKEND_API_KEY:
    raise ValueError("BACKEND_API_KEY environment variable is required")