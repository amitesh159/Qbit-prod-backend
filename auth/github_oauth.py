"""
GitHub OAuth Integration
OAuth2 flow for GitHub authentication
"""
import httpx
import structlog
from typing import Dict, Any
from config.settings import settings

logger = structlog.get_logger(__name__)


class GitHubOAuth:
    """GitHub OAuth client for authentication"""
    
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_API_URL = "https://api.github.com/user"
    
    def __init__(self):
        self.client_id = settings.github_client_id
        self.client_secret = settings.github_client_secret
        self.callback_url = settings.github_callback_url
    
    def get_authorization_url(self, state: str | None = None) -> str:
        """
        Generate GitHub OAuth authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            str: Authorization URL to redirect user to
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.callback_url,
            "scope": "read:user user:email",
        }
        
        if state:
            params["state"] = state
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.AUTHORIZE_URL}?{query_string}"
        
        logger.info(
            "github_authorization_url_generated",
            callback_url=self.callback_url
        )
        
        return url
    
    async def exchange_code_for_token(self, code: str) -> str | None:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from GitHub callback
            
        Returns:
            str | None: Access token if successful, None otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.ACCESS_TOKEN_URL,
                    json={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": self.callback_url,
                    },
                    headers={"Accept": "application/json"},
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    logger.error(
                        "github_token_exchange_failed",
                        status_code=response.status_code,
                        response=response.text
                    )
                    return None
                
                data = response.json()
                access_token = data.get("access_token")
                
                if not access_token:
                    logger.error(
                        "github_token_not_in_response",
                        response=data
                    )
                    return None
                
                logger.info("github_token_exchanged")
                return access_token
                
        except httpx.TimeoutException:
            logger.error("github_token_exchange_timeout")
            return None
            
        except Exception as e:
            logger.exception(
                "github_token_exchange_error",
                error=str(e)
            )
            return None
    
    async def get_user_profile(self, access_token: str) -> Dict[str, Any] | None:
        """
        Get user profile from GitHub API.
        
        Args:
            access_token: GitHub access token
            
        Returns:
            Dict[str, Any] | None: User profile data or None if failed
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.USER_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    logger.error(
                        "github_user_profile_failed",
                        status_code=response.status_code
                    )
                    return None
                
                user_data = response.json()
                
                logger.info(
                    "github_user_profile_fetched",
                    github_id=user_data.get("id"),
                    username=user_data.get("login")
                )
                
                return user_data
                
        except httpx.TimeoutException:
            logger.error("github_user_profile_timeout")
            return None
            
        except Exception as e:
            logger.exception(
                "github_user_profile_error",
                error=str(e)
            )
            return None


# Global OAuth client instance
github_oauth = GitHubOAuth()
