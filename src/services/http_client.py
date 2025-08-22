"""
HTTP client management service
"""
import httpx
import logging
from src.config.settings import get_luceron_config
from src.services.oauth2_client import LuceronClient

logger = logging.getLogger(__name__)

# Global HTTP client and OAuth client
http_client = None
oauth_client = None


async def init_http_client():
    global http_client, oauth_client
    
    # Initialize OAuth2 client
    luceron_config = get_luceron_config()
    if not luceron_config:
        raise ValueError("OAuth2 configuration not available - check COMMUNICATIONS_AGENT_PRIVATE_KEY environment variable")
    
    oauth_client = LuceronClient(
        service_id=luceron_config['service_id'],
        private_key_pem=luceron_config['private_key'],
        base_url=luceron_config['base_url']
    )
    
    # Test OAuth connection
    if not oauth_client.health_check():
        logger.warning("OAuth2 health check failed, but continuing...")
    
    # Create HTTP client without authorization header (we'll add tokens per request)
    http_client = httpx.AsyncClient(timeout=30.0)


async def close_http_client():
    global http_client
    if http_client:
        await http_client.aclose()


class AuthenticatedHTTPClient:
    """HTTP client wrapper that automatically adds OAuth2 authentication"""
    
    def __init__(self, base_client: httpx.AsyncClient, oauth_client: LuceronClient):
        self.base_client = base_client
        self.oauth_client = oauth_client
    
    def _get_auth_headers(self) -> dict:
        """Get authentication headers with current access token"""
        try:
            token = self.oauth_client._get_access_token()
            return {"Authorization": f"Bearer {token}"}
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            return {}
    
    async def get(self, url: str, **kwargs):
        """GET request with OAuth2 authentication"""
        headers = kwargs.get('headers', {})
        headers.update(self._get_auth_headers())
        kwargs['headers'] = headers
        return await self.base_client.get(url, **kwargs)
    
    async def post(self, url: str, **kwargs):
        """POST request with OAuth2 authentication"""
        headers = kwargs.get('headers', {})
        headers.update(self._get_auth_headers())
        kwargs['headers'] = headers
        return await self.base_client.post(url, **kwargs)
    
    async def put(self, url: str, **kwargs):
        """PUT request with OAuth2 authentication"""
        headers = kwargs.get('headers', {})
        headers.update(self._get_auth_headers())
        kwargs['headers'] = headers
        return await self.base_client.put(url, **kwargs)
    
    async def delete(self, url: str, **kwargs):
        """DELETE request with OAuth2 authentication"""
        headers = kwargs.get('headers', {})
        headers.update(self._get_auth_headers())
        kwargs['headers'] = headers
        return await self.base_client.delete(url, **kwargs)
    
    async def patch(self, url: str, **kwargs):
        """PATCH request with OAuth2 authentication"""
        headers = kwargs.get('headers', {})
        headers.update(self._get_auth_headers())
        kwargs['headers'] = headers
        return await self.base_client.patch(url, **kwargs)


def get_http_client() -> AuthenticatedHTTPClient:
    """Get authenticated HTTP client"""
    if http_client is None or oauth_client is None:
        raise RuntimeError("HTTP client not initialized - call init_http_client() first")
    return AuthenticatedHTTPClient(http_client, oauth_client)