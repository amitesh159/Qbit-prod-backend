"""
JWT Token Utilities
Create and validate JWT tokens for authentication
"""
from datetime import datetime, timedelta
from typing import Dict, Any
import jwt
import structlog
from config.settings import settings

logger = structlog.get_logger(__name__)


def create_access_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT access token with expiration.
    
    Args:
        data: Payload data to encode in token (user_id, email, etc.)
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    
    expire = datetime.utcnow() + timedelta(days=settings.jwt_access_token_expire_days)
    to_encode.update({"exp": expire})
    
    try:
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        
        logger.debug(
            "jwt_token_created",
            user_id=data.get("user_id"),
            expires_at=expire.isoformat()
        )
        
        return encoded_jwt
        
    except Exception as e:
        logger.exception(
            "jwt_token_creation_failed",
            error=str(e)
        )
        raise


def decode_access_token(token: str) -> Dict[str, Any] | None:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        Dict[str, Any] | None: Decoded payload if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        logger.debug(
            "jwt_token_decoded",
            user_id=payload.get("user_id")
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("jwt_token_expired")
        return None
        
    except jwt.InvalidTokenError as e:
        logger.warning(
            "jwt_token_invalid",
            error=str(e)
        )
        return None
        
    except Exception as e:
        logger.exception(
            "jwt_token_decode_failed",
            error=str(e)
        )
        return None


def get_token_expiration(token: str) -> datetime | None:
    """
    Get expiration datetime from a JWT token without validating signature.
    Useful for checking if token needs refresh.
    
    Args:
        token: JWT token string
        
    Returns:
        datetime | None: Expiration datetime or None if unable to parse
    """
    try:
        # Decode without verification to get expiration
        payload = jwt.decode(
            token,
            options={"verify_signature": False}
        )
        
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            return datetime.fromtimestamp(exp_timestamp)
            
        return None
        
    except Exception as e:
        logger.error(
            "jwt_expiration_check_failed",
            error=str(e)
        )
        return None
