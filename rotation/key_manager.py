"""
API Key Pool Manager
Round-robin rotation with health checks and blacklisting
Prevents rate limit failures across multiple free-tier API keys
"""
import structlog
from datetime import datetime, timedelta
from typing import List
from config.settings import settings

logger = structlog.get_logger(__name__)


class KeyPool:
    """
    API Key Pool with round-robin rotation and health tracking.
    Manages multiple API keys to distribute load and avoid rate limits.
    """
    
    def __init__(self, provider: str, keys: List[str], rpm_limit: int):
        """
        Initialize key pool.
        
        Args:
            provider: Provider name (e.g., "groq", "cerebras")
            keys: List of API keys
            rpm_limit: Requests per minute limit per key
        """
        self.provider = provider
        self.keys = keys
        self.rpm_limit = rpm_limit
        self.current_index = 0
        self.request_counts = {key: 0 for key in keys}
        self.last_rotation = {key: datetime.utcnow() for key in keys}
        self.blacklist = set()
        
        logger.info(
            "key_pool_initialized",
            provider=provider,
            key_count=len(keys),
            rpm_limit=rpm_limit
        )
    
    def get_next_key(self) -> str:
        """
        Get next healthy API key using round-robin rotation.
        Skips blacklisted keys and keys approaching rate limits.
        
        Returns:
            str: Next available API key
            
        Raises:
            Exception: If no healthy keys available
        """
        attempts = 0
        max_attempts = len(self.keys) * 2  # Try all keys twice
        
        while attempts < max_attempts:
            candidate = self.keys[self.current_index]
            
            # Skip blacklisted keys
            if candidate in self.blacklist:
                logger.debug(
                    "key_skipped_blacklisted",
                    provider=self.provider,
                    key_prefix=candidate[:10]
                )
                self.current_index = (self.current_index + 1) % len(self.keys)
                attempts += 1
                continue
            
            # Check if approaching rate limit
            current_count = self.request_counts[candidate]
            time_since_rotation = datetime.utcnow() - self.last_rotation[candidate]
            
            if current_count >= self.rpm_limit - 5:  # Buffer of 5 requests
                # Check if minute has passed (reset window)
                if time_since_rotation < timedelta(seconds=60):
                    logger.debug(
                        "key_skipped_rate_limit",
                        provider=self.provider,
                        current_count=current_count,
                        rpm_limit=self.rpm_limit
                    )
                    self.current_index = (self.current_index + 1) % len(self.keys)
                    attempts += 1
                    continue
                else:
                    # Reset counter after minute
                    self.request_counts[candidate] = 0
                    self.last_rotation[candidate] = datetime.utcnow()
                    logger.debug(
                        "key_counter_reset",
                        provider=self.provider
                    )
            
            # Use this key
            self.request_counts[candidate] += 1
            next_index = (self.current_index + 1) % len(self.keys)
            
            logger.debug(
                "key_selected",
                provider=self.provider,
                key_prefix=candidate[:10],
                request_count=self.request_counts[candidate],
                next_index=next_index
            )
            
            self.current_index = next_index
            return candidate
        
        # No healthy keys available
        logger.error(
            "no_healthy_keys_available",
            provider=self.provider,
            blacklisted_count=len(self.blacklist),
            total_keys=len(self.keys)
        )
        raise Exception(f"No healthy API keys available for {self.provider}")
    
    def mark_unhealthy(self, key: str, error: Exception) -> None:
        """
        Mark a key as unhealthy based on error type.
        
        Args:
            key: API key that failed
            error: Exception that occurred
        """
        error_str = str(error).lower()
        
        if "rate_limit" in error_str or "429" in error_str:
            # Temporary rate limit - will recover after minute
            logger.warning(
                "key_rate_limited",
                provider=self.provider,
                key_prefix=key[:10]
            )
            # Don't blacklist, just let the counter handle it
            
        elif "invalid" in error_str or "unauthorized" in error_str or "401" in error_str:
            # Invalid key - permanent blacklist
            self.blacklist.add(key)
            logger.error(
                "key_blacklisted",
                provider=self.provider,
                key_prefix=key[:10],
                reason="invalid_key"
            )
            
        else:
            # Other error - log but don't blacklist
            logger.warning(
                "key_error",
                provider=self.provider,
                key_prefix=key[:10],
                error=error_str
            )
    
    def get_health_status(self) -> dict:
        """
        Get health status of key pool.
        
        Returns:
            dict: Health status information
        """
        healthy_count = len(self.keys) - len(self.blacklist)
        
        return {
            "provider": self.provider,
            "total_keys": len(self.keys),
            "healthy_keys": healthy_count,
            "blacklisted_keys": len(self.blacklist),
            "current_index": self.current_index,
            "rpm_limit": self.rpm_limit,
        }


# ============================================================================
# GLOBAL KEY POOL INSTANCES
# ============================================================================

# Groq Key Pool (Central Hub)
groq_pool = KeyPool(
    provider="groq",
    keys=settings.groq_api_keys_list,
    rpm_limit=settings.groq_rpm_limit
)

# Cerebras Key Pool (Full Stack Agent)
cerebras_pool = KeyPool(
    provider="cerebras",
    keys=settings.cerebras_api_keys_list,
    rpm_limit=settings.cerebras_rpm_limit
)
