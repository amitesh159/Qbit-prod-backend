"""
User API Routes
User profile and credits management
"""
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from database.connection import get_database
from auth.dependencies import require_auth
from credits.credit_manager import get_credit_balance, get_transaction_history

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================
class UserProfileResponse(BaseModel):
    """User profile response"""
    user_id: str
    email: str
    github_username: str | None
    credits: int
    tier: str
    created_at: str
    last_login: str | None


class CreditBalanceResponse(BaseModel):
    """Credit balance response"""
    user_id: str
    credits: int
    tier: str


class CreditTransaction(BaseModel):
    """Credit transaction model"""
    amount: int
    operation: str
    timestamp: str
    project_id: str | None


class CreditHistoryResponse(BaseModel):
    """Credit history response"""
    transactions: List[CreditTransaction]
    current_balance: int


# ============================================================================
# USER ROUTES
# ============================================================================
@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(user: Dict[str, Any] = Depends(require_auth)):
    """
    Get current authenticated user's profile.
    """
    logger.info(
        "user_profile_fetched",
        user_id=user["user_id"]
    )
    
    return UserProfileResponse(
        user_id=user["user_id"],
        email=user["email"],
        github_username=user.get("github_username"),
        credits=user.get("credits", 0),
        tier=user.get("tier", "free"),
        created_at=user["created_at"].isoformat(),
        last_login=user.get("last_login").isoformat() if user.get("last_login") else None
    )


@router.get("/credits", response_model=CreditBalanceResponse)
async def get_credits(user: Dict[str, Any] = Depends(require_auth)):
    """
    Get current credit balance.
    """
    balance = await get_credit_balance(user["user_id"])
    
    logger.info(
        "credit_balance_fetched",
        user_id=user["user_id"],
        balance=balance
    )
    
    return CreditBalanceResponse(
        user_id=user["user_id"],
        credits=balance,
        tier=user.get("tier", "free")
    )


@router.get("/credits/history", response_model=CreditHistoryResponse)
async def get_credit_history(user: Dict[str, Any] = Depends(require_auth)):
    """
    Get credit transaction history (last 50 transactions).
    """
    transactions = await get_transaction_history(user["user_id"], limit=50)
    balance = await get_credit_balance(user["user_id"])
    
    logger.info(
        "credit_history_fetched",
        user_id=user["user_id"],
        transaction_count=len(transactions)
    )
    
    return CreditHistoryResponse(
        transactions=[
            CreditTransaction(
                amount=t["amount"],
                operation=t["operation"],
                timestamp=t["timestamp"].isoformat(),
                project_id=t.get("project_id")
            )
            for t in transactions
        ],
        current_balance=balance
    )
