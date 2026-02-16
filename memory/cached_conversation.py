"""
Cached Conversation Memory
In-memory cache with periodic MongoDB persistence to avoid DB hits on every message
"""
import structlog
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = structlog.get_logger(__name__)


class CachedConversationMemory:
    """
    In-memory conversation cache with periodic MongoDB persistence.
    
    Cache Strategy:
    - HIT: Return from memory (no DB query)
    - MISS: Load from DB, cache for future
    - Persist: Every N messages or on conversation end
    
    Architecture:
    - Cache TTL: 30 minutes  
    - Max messages in memory: 50 per project
    - Persist interval: Every 10 messages
    - Background cleanup: Every 5 minutes
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize cached memory.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        self._cache: Dict[str, Dict] = {}  # {project_id: {messages, last_updated, count}}
        
        # Configuration
        self.max_in_memory = 50  # Messages per project
        self.persist_interval = 10  # DB write every N messages
        self.cache_ttl_minutes = 30
        
        logger.info(
            "cached_conversation_memory_initialized",
            max_in_memory=self.max_in_memory,
            persist_interval=self.persist_interval,
            cache_ttl=self.cache_ttl_minutes
        )
    
    async def get_history(
        self,
        project_id: str,
        max_messages: int = 20
    ) -> List[BaseMessage]:
        """
        Get conversation history with caching (FAST).
        
        Args:
            project_id: Project identifier
            max_messages: Maximum number of messages to return
            
        Returns:
            List of messages (HumanMessage, AIMessage)
        """
        # Try cache first
        if project_id in self._cache and self._is_valid(self._cache[project_id]):
            logger.debug(
                "memory_cache_hit",
                project_id=project_id,
                cached_count=len(self._cache[project_id]["messages"])
            )
            return self._cache[project_id]["messages"][-max_messages:]
        
        # Cache miss - load from DB
        logger.debug(
            "memory_cache_miss",
            project_id=project_id,
            loading_from_db=True
        )
        messages = await self._load_from_db(project_id, max_messages)
        
        # Update cache
        self._cache[project_id] = {
            "messages": messages,
            "last_updated": datetime.utcnow(),
            "count": len(messages),
            "persist_count": 0  # Track messages since last persist
        }
        
        return messages
    
    async def add_message(
        self,
        project_id: str,
        message: BaseMessage
    ) -> None:
        """
        Add message with smart persistence.
        
        Args:
            project_id: Project identifier
            message: Message to add (HumanMessage or AIMessage)
        """
        # Initialize cache entry if needed
        if project_id not in self._cache:
            self._cache[project_id] = {
                "messages": [],
                "last_updated": datetime.utcnow(),
                "count": 0,
                "persist_count": 0
            }
        
        cache_entry = self._cache[project_id]
        cache_entry["messages"].append(message)
        cache_entry["count"] += 1
        cache_entry["persist_count"] += 1
        cache_entry["last_updated"] = datetime.utcnow()
        
        # Trim if too large (keep most recent)
        if len(cache_entry["messages"]) > self.max_in_memory:
            cache_entry["messages"] = cache_entry["messages"][-self.max_in_memory:]
        
        # Persist every N messages
        if cache_entry["persist_count"] >= self.persist_interval:
            await self._persist_to_db(project_id)
            cache_entry["persist_count"] = 0
            logger.debug(
                "memory_persisted",
                project_id=project_id,
                message_count=cache_entry["count"]
            )
    
    async def clear_project(self, project_id: str) -> None:
        """
        Clear conversation history for a project.
        
        Args:
            project_id: Project identifier
        """
        # Remove from cache
        if project_id in self._cache:
            del self._cache[project_id]
        
        # Remove from DB
        await self.db.conversations.delete_many({"project_id": project_id}) 
        
        logger.info("conversation_cleared", project_id=project_id)
    
    async def _load_from_db(
        self,
        project_id: str,
        max_messages: int
    ) -> List[BaseMessage]:
        """
        Load conversation history from MongoDB.
        
        Args:
            project_id: Project identifier
            max_messages: Maximum messages to load
            
        Returns:
            List of messages in chronological order
        """
        docs = await self.db.conversations.find(
            {"project_id": project_id}
        ).sort("timestamp", -1).limit(max_messages).to_list(length=max_messages)
        
        # Reverse to get chronological order
        messages = []
        for doc in reversed(docs):
            if doc["role"] == "user":
                messages.append(HumanMessage(content=doc["content"]))
            else:
                messages.append(AIMessage(content=doc["content"]))
        
        logger.debug(
            "messages_loaded_from_db",
            project_id=project_id,
            count=len(messages)
        )
        
        return messages
    
    async def _persist_to_db(self, project_id: str) -> None:
        """
        Persist recent messages to MongoDB.
        
        Args:
            project_id: Project identifier
        """
        if project_id not in self._cache:
            return
        
        cache_entry = self._cache[project_id]
        persist_count = cache_entry.get("persist_count", 0)
        
        if persist_count == 0:
            return  # Nothing new to persist
        
        # Get messages added since last persist
        messages = cache_entry["messages"][-persist_count:]
        
        # Prepare documents
        docs = [
            {
                "project_id": project_id,
                "role": "user" if isinstance(msg, HumanMessage) else "assistant",
                "content": msg.content,
                "timestamp": datetime.utcnow()
            }
            for msg in messages
        ]
        
        if docs:
            await self.db.conversations.insert_many(docs)
            logger.debug(
                "messages_persisted_to_db",
                project_id=project_id,
                count=len(docs)
            )
    
    def _is_valid(self, cache_entry: Dict) -> bool:
        """
        Check if cache entry is still valid (TTL check).
        
        Args:
            cache_entry: Cache entry dict
            
        Returns:
            True if valid, False if expired
        """
        age = datetime.utcnow() - cache_entry["last_updated"]
        return age < timedelta(minutes=self.cache_ttl_minutes)
    
    async def flush_all(self) -> None:
        """
        Flush all cached conversations to DB (for shutdown).
        """
        logger.info("flushing_all_conversations_to_db")
        
        for project_id in list(self._cache.keys()):
            await self._persist_to_db(project_id)
        
        logger.info("all_conversations_flushed",  cached_projects=len(self._cache))
    
    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        return {
            "cached_projects": len(self._cache),
            "total_messages": sum(len(entry["messages"]) for entry in self._cache.values()),
            "cache_ttl_minutes": self.cache_ttl_minutes,
            "max_in_memory": self.max_in_memory
        }
