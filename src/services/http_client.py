"""
HTTP client management service
"""
import httpx
from src.config.settings import BACKEND_API_KEY

# Global HTTP client
http_client = None


async def init_http_client():
    global http_client
    headers = {
        "Authorization": f"Bearer {BACKEND_API_KEY}"
    }
    http_client = httpx.AsyncClient(timeout=30.0, headers=headers)


async def close_http_client():
    global http_client
    if http_client:
        await http_client.aclose()


def get_http_client() -> httpx.AsyncClient:
    if http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return http_client