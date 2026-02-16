"""
MongoDB Atlas Connection Manager
Uses Motor for async MongoDB operations with connection pooling
"""
import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure
from config.settings import settings

logger = structlog.get_logger(__name__)

# Global MongoDB client instance
_mongo_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def get_database() -> AsyncIOMotorDatabase:
    """
    Get MongoDB database instance with connection pooling.
    Creates connection on first call, reuses for subsequent calls.
    
    Returns:
        AsyncIOMotorDatabase: MongoDB database instance
        
    Raises:
        ConnectionFailure: If unable to connect to MongoDB
    """
    global _mongo_client, _database
    
    if _database is not None:
        return _database
    
    try:
        logger.info(
            "connecting_to_mongodb",
            database=settings.mongodb_db_name,
            min_pool_size=settings.mongodb_min_pool_size,
            max_pool_size=settings.mongodb_max_pool_size
        )
        
        _mongo_client = AsyncIOMotorClient(
            settings.mongodb_uri,
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
        )
        
        # Verify connection
        await _mongo_client.admin.command("ping")
        
        _database = _mongo_client[settings.mongodb_db_name]
        
        logger.info(
            "mongodb_connected",
            database=settings.mongodb_db_name
        )
        
        return _database
        
    except ConnectionFailure as e:
        logger.exception(
            "mongodb_connection_failed",
            error=str(e)
        )
        raise


async def close_database_connection() -> None:
    """
    Close MongoDB connection and cleanup resources.
    Should be called on application shutdown.
    """
    global _mongo_client, _database
    
    if _mongo_client is not None:
        logger.info("closing_mongodb_connection")
        _mongo_client.close()
        _mongo_client = None
        _database = None
        logger.info("mongodb_connection_closed")


async def create_indexes() -> None:
    """
    Create MongoDB indexes for optimal query performance.
    Should be called on application startup after database connection.
    """
    db = await get_database()
    
    logger.info("creating_mongodb_indexes")
    
    async def safe_create_index(collection, keys, **kwargs):
        """
        Helper to create index only if it doesn't already exist.
        Handles both simple field names and compound index specifications.
        """
        try:
            await collection.create_index(keys, **kwargs)
        except Exception as e:
            # If index already exists (with any name), just log and continue
            if "IndexOptionsConflict" in str(e) or "already exists" in str(e):
                logger.debug(
                    "index_already_exists",
                    collection=collection.name,
                    keys=keys,
                    error=str(e)
                )
            else:
                # Re-raise other errors
                raise
    
    try:
        # Users collection indexes
        await safe_create_index(db.users, "user_id", unique=True)
        await safe_create_index(db.users, "email", unique=True)
        await safe_create_index(db.users, "github_username")
        
        # Projects collection indexes
        await safe_create_index(db.projects, "project_id", unique=True)
        await safe_create_index(db.projects, [("user_id", 1), ("created_at", -1)])
        await safe_create_index(db.projects, "name")
        
        # Modules collection indexes
        await safe_create_index(db.modules, [("project_id", 1), ("path", 1)])
        await safe_create_index(db.modules, "name")
        
        # Files collection indexes
        await safe_create_index(db.files, [("project_id", 1), ("path", 1)], unique=True)
        await safe_create_index(db.files, "language")
        
        # Code blobs collection indexes
        await safe_create_index(db.code_blobs, "file_id")
        
        # Operation log collection indexes
        await safe_create_index(db.operation_log, [("project_id", 1), ("timestamp", -1)])
        await safe_create_index(db.operation_log, "operation_id", unique=True)
        
        # Snapshots collection indexes
        await safe_create_index(db.snapshots, [("project_id", 1), ("timestamp", -1)])
        await safe_create_index(db.snapshots, "snapshot_id", unique=True)
        
        # Conversations collection indexes
        await safe_create_index(db.conversations, [("project_id", 1), ("session_id", 1)])
        await safe_create_index(db.conversations, [("project_id", 1), ("timestamp", -1)])
        
        # SCP versions collection indexes
        await safe_create_index(db.scp_versions, [("project_id", 1), ("version", 1)])
        
        # Credit transactions collection indexes
        await safe_create_index(db.credit_transactions, [("user_id", 1), ("timestamp", -1)])
        
        # Sandbox sessions collection indexes (for E2B auto-reconnection)
        await safe_create_index(db.sandbox_sessions, "project_id", unique=True)
        await safe_create_index(db.sandbox_sessions, [("status", 1), ("last_active", -1)])
        
        # Improved code_blobs index pattern for recreation queries
        await safe_create_index(db.code_blobs, [("file_id", 1), ("path", 1)])
        
        # Text search indexes for semantic queries
        # Note: Use language_override to avoid conflict with our 'language' field
        # which stores programming language names (javascript, html, etc.)
        # MongoDB text search only supports natural languages (english, spanish, etc.)
        await safe_create_index(db.modules, [("description", "text")])
        
        # For files collection, we need special handling because 'language' field
        # conflicts with MongoDB's text search language detection
        try:
            # First, try to drop any existing text index on files collection
            existing_indexes = await db.files.index_information()
            for idx_name, idx_info in existing_indexes.items():
                if any(k[1] == 'text' for k in idx_info.get('key', [])):
                    await db.files.drop_index(idx_name)
                    logger.info("dropped_existing_text_index", index_name=idx_name)
        except Exception as drop_err:
            logger.warning("could_not_drop_text_index", error=str(drop_err))
        
        # Create text index with proper language settings
        await safe_create_index(
            db.files,
            [("summary", "text")],
            default_language="none",
            language_override="_text_lang"
        )
        
        logger.info("mongodb_indexes_created")
        
    except Exception as e:
        logger.exception(
            "mongodb_index_creation_failed",
            error=str(e)
        )
        raise

