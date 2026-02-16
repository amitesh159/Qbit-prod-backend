"""
Password Hashing Utilities
Secure password hashing and verification using bcrypt
"""
import structlog
import bcrypt

logger = structlog.get_logger(__name__)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        str: Hashed password
        
    Note:
        Bcrypt only processes the first 72 bytes of a password.
        Longer passwords are truncated to ensure compatibility.
    """
    try:
        # Bcrypt has a 72-byte limit - encode and truncate to 72 bytes
        password_bytes = password.encode('utf-8')[:72]
        
        # Generate salt and hash
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        # Return as string (bcrypt returns bytes)
        hashed_str = hashed.decode('utf-8')
        logger.debug("password_hashed")
        return hashed_str
        
    except Exception as e:
        logger.exception(
            "password_hashing_failed",
            error=str(e)
        )
        raise


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against
        
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        # Apply same truncation as during hashing
        password_bytes = plain_password.encode('utf-8')[:72]
        hashed_bytes = hashed_password.encode('utf-8')
        
        # Verify password
        is_valid = bcrypt.checkpw(password_bytes, hashed_bytes)
        
        if is_valid:
            logger.debug("password_verified")
        else:
            logger.debug("password_verification_failed")
            
        return is_valid
        
    except Exception as e:
        logger.error(
            "password_verification_error",
            error=str(e)
        )
        return False
