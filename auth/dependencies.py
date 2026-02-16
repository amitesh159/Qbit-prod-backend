"""
FastAPI Authentication Dependencies
Dependency injection for protected routes
"""
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any
from auth.jwt_utils import decode_access_token
from database.connection import get_database
from database.schemas import UserModel

logger = structlog.get_logger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user from JWT token.
    Validates token and returns user data.
    
    Args:
        credentials: Bearer token from Authorization header
        
    Returns:
        Dict[str, Any]: User data
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    
    # Decode JWT token
    payload = decode_access_token(token)
    
    if not payload:
        logger.warning("authentication_failed_invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("user_id")
    
    if not user_id:
        logger.warning("authentication_failed_no_user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user from database
    db = await get_database()
    user_doc = await db.users.find_one({"user_id": user_id})
    
    if not user_doc:
        logger.warning(
            "authentication_failed_user_not_found",
            user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(
        "user_authenticated",
        user_id=user_id
    )
    
    return user_doc


async def require_auth(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to require authentication.
    Alias for get_current_user for semantic clarity.
    
    Args:
        user: User data from get_current_user dependency
        
    Returns:
        Dict[str, Any]: User data
    """
    return user


async def require_credits(
    required_credits: int,
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to check if user has sufficient credits.
    
    Args:
        required_credits: Minimum credits required
        user: User data from get_current_user dependency
        
    Returns:
        Dict[str, Any]: User data
        
    Raises:
        HTTPException: If insufficient credits
    """
    user_credits = user.get("credits", 0)
    
    if user_credits < required_credits:
        logger.warning(
            "insufficient_credits",
            user_id=user.get("user_id"),
            required=required_credits,
            available=user_credits
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {required_credits}, Available: {user_credits}"
        )
    
    return user
