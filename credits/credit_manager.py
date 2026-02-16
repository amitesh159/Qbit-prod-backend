"""
Credit Manager
Handles credit deduction, rollback, and transaction logging with atomic operations
"""
import structlog
from datetime import datetime
from database.connection import get_database
from database.schemas import CreditHistoryModel

logger = structlog.get_logger(__name__)


async def check_credits(user_id: str, required_credits: int) -> bool:
    """
    Check if user has sufficient credits without deducting.
    
    Args:
        user_id: User identifier
        required_credits: Credits required
        
    Returns:
        bool: True if sufficient credits, False otherwise
    """
    db = await get_database()
    
    try:
        user = await db.users.find_one({"user_id": user_id})
        
        if not user:
            logger.warning(
                "credit_check_user_not_found",
                user_id=user_id
            )
            return False
        
        user_credits = user.get("credits", 0)
        has_sufficient = user_credits >= required_credits
        
        logger.debug(
            "credit_check_completed",
            user_id=user_id,
            required=required_credits,
            available=user_credits,
            sufficient=has_sufficient
        )
        
        return has_sufficient
        
    except Exception as e:
        logger.exception(
            "credit_check_failed",
            user_id=user_id,
            error=str(e)
        )
        return False


async def deduct_credits(
    user_id: str,
    amount: int,
    operation: str,
    project_id: str | None = None
) -> bool:
    """
    Deduct credits from user account with atomic operation.
    Creates transaction log entry.
    
    Args:
        user_id: User identifier
        amount: Credits to deduct (positive number)
        operation: Description of operation
        project_id: Optional project identifier
        
    Returns:
        bool: True if deduction successful, False if insufficient credits or error
    """
    db = await get_database()
    
    try:
        from pymongo import ReturnDocument
        import uuid
        
        # Atomic deduction using MongoDB find_one_and_update
        # Returns the document AFTER update
        updated_user = await db.users.find_one_and_update(
            {
                "user_id": user_id,
                "credits": {"$gte": amount}  # Only update if credits >= amount
            },
            {
                "$inc": {"credits": -amount}
            },
            return_document=ReturnDocument.AFTER
        )
        
        if not updated_user:
            # Either user not found or insufficient credits
            user = await db.users.find_one({"user_id": user_id})
            
            if not user:
                logger.warning(
                    "credit_deduction_user_not_found",
                    user_id=user_id
                )
            else:
                logger.warning(
                    "credit_deduction_insufficient",
                    user_id=user_id,
                    required=amount,
                    available=user.get("credits", 0)
                )
            
            return False
        
        # Log transaction
        transaction = CreditHistoryModel(
            transaction_id=str(uuid.uuid4()),
            user_id=user_id,
            amount=-amount,  # Negative for deduction
            operation=operation,
            project_id=project_id,
            balance_after=updated_user.get("credits", 0),
            created_at=datetime.utcnow()
        )
        
        await db.credit_history.insert_one(transaction.model_dump())
        
        logger.info(
            "credits_deducted",
            user_id=user_id,
            amount=amount,
            operation=operation,
            balance=updated_user.get("credits", 0)
        )
        
        return True
        
    except Exception as e:
        logger.exception(
            "credit_deduction_failed",
            user_id=user_id,
            amount=amount,
            error=str(e)
        )
        return False


async def rollback_credits(
    user_id: str,
    amount: int,
    reason: str,
    project_id: str | None = None
) -> bool:
    """
    Rollback (refund) credits to user account.
    Used when operations fail after credit deduction.
    
    Args:
        user_id: User identifier
        amount: Credits to refund (positive number)
        reason: Reason for rollback
        project_id: Optional project identifier
        
    Returns:
        bool: True if rollback successful, False otherwise
    """
    db = await get_database()
    
    try:
        from pymongo import ReturnDocument
        import uuid
        
        # Add credits back to user and get new balance
        updated_user = await db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"credits": amount}},
            return_document=ReturnDocument.AFTER
        )
        
        if not updated_user:
            logger.warning(
                "credit_rollback_user_not_found",
                user_id=user_id
            )
            return False
        
        # Log refund transaction
        transaction = CreditHistoryModel(
            transaction_id=str(uuid.uuid4()),
            user_id=user_id,
            amount=amount,  # Positive for refund
            operation=f"refund: {reason}",
            project_id=project_id,
            balance_after=updated_user.get("credits", 0),
            created_at=datetime.utcnow()
        )
        
        await db.credit_history.insert_one(transaction.model_dump())
        
        logger.info(
            "credits_refunded",
            user_id=user_id,
            amount=amount,
            reason=reason,
            balance=updated_user.get("credits", 0)
        )
        
        return True
        
    except Exception as e:
        logger.exception(
            "credit_rollback_failed",
            user_id=user_id,
            amount=amount,
            error=str(e)
        )
        return False


async def get_credit_balance(user_id: str) -> int:
    """
    Get current credit balance for a user.
    
    Args:
        user_id: User identifier
        
    Returns:
        int: Current credit balance (0 if user not found)
    """
    db = await get_database()
    
    try:
        user = await db.users.find_one({"user_id": user_id})
        
        if not user:
            logger.warning(
                "credit_balance_user_not_found",
                user_id=user_id
            )
            return 0
        
        return user.get("credits", 0)
        
    except Exception as e:
        logger.exception(
            "credit_balance_check_failed",
            user_id=user_id,
            error=str(e)
        )
        return 0


async def get_transaction_history(
    user_id: str,
    limit: int = 50
) -> list:
    """
    Get credit transaction history for a user.
    
    Args:
        user_id: User identifier
        limit: Maximum number of transactions to return
        
    Returns:
        list: List of credit transactions (most recent first)
    """
    db = await get_database()
    
    try:
        transactions = await db.credit_history.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        logger.debug(
            "credit_history_fetched",
            user_id=user_id,
            transaction_count=len(transactions)
        )
        
        return transactions
        
    except Exception as e:
        logger.exception(
            "credit_history_fetch_failed",
            user_id=user_id,
            error=str(e)
        )
        return []
