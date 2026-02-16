"""
Cached Project Store
In-memory cache for project context (Knowledge Base) with invalidation on modifications
"""
import structlog
from typing import Dict, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = structlog.get_logger(__name__)


class CachedProjectStore:
    """
    Cache for project context (from Knowledge Base).
    
    Cache invalidated on: project file modifications
    
    Architecture:
    - Cache TTL: 60 minutes (projects change less frequently)
    - Force refresh on file modifications
    - Loads compressed context from KB
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize project store cache.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        self._cache: Dict[str, Dict] = {}  # {project_id: {context, cached_at}}
        self.cache_ttl_minutes = 60
        
        logger.info(
            "cached_project_store_initialized",
            cache_ttl=self.cache_ttl_minutes
        )
    
    async def get_context(
        self,
        project_id: str,
        user_intent: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict:
        """
        Get project context with caching.
        
        Args:
            project_id: Project identifier
            user_intent: Optional user intent for targeted context
            force_refresh: Force reload from DB
            
        Returns:
            Project context dict
        """
        # Check cache
        if not force_refresh and project_id in self._cache:
            cached = self._cache[project_id]
            age = datetime.utcnow() - cached["cached_at"]
            
            if age < timedelta(minutes=self.cache_ttl_minutes):
                logger.debug(
                    "project_store_cache_hit",
                    project_id=project_id,
                    age_seconds=age.total_seconds()
                )
                return cached["context"]
        
        # Cache miss or expired - load from KB
        logger.debug(
            "project_store_cache_miss",
            project_id=project_id,
            force_refresh=force_refresh
        )
        
        context = await self._load_from_kb(project_id, user_intent)
        
        # Cache it
        self._cache[project_id] = {
            "context": context,
            "cached_at": datetime.utcnow()
        }
        
        return context
    
    def invalidate(self, project_id: str) -> None:
        """
        Invalidate cache after file modifications.
        
        Args:
            project_id: Project identifier
        """
        if project_id in self._cache:
            del self._cache[project_id]
            logger.debug("project_cache_invalidated", project_id=project_id)
    
    def invalidate_all(self) -> None:
        """Invalidate all cached projects."""
        count = len(self._cache)
        self._cache.clear()
        logger.info("all_project_caches_invalidated", count=count)
    
    async def _load_from_kb(
        self,
        project_id: str,
        user_intent: Optional[str] = None
    ) -> Dict:
        """
        Load project context from Knowledge Base.
        
        Args:
            project_id: Project identifier
            user_intent: Optional user intent for targeted retrieval
            
        Returns:
            Compressed context from KB
        """
        try:
            from knowledge.kb_operations import get_compressed_context
            
            context = await get_compressed_context(
                project_id=project_id,
                user_intent=user_intent,
                max_tokens=4000  # Keep context compact for Central Hub
            )
            
            logger.debug(
                "context_loaded_from_kb",
                project_id=project_id,
                file_count=context.get("file_count", 0)
            )
            
            return context if context else {}
            
        except ImportError:
            logger.warning("kb_operations_not_available")
            return {}
        except Exception as e:
            logger.exception("kb_context_load_failed", error=str(e))
            return {}
    
    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        return {
            "cached_projects": len(self._cache),
            "cache_ttl_minutes": self.cache_ttl_minutes
        }
