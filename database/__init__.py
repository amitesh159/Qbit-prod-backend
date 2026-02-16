"""
Database package for Qbit backend
Includes MongoDB and Redis clients
"""
from database.connection import get_database, close_database_connection
from database.redis_client import get_redis_client, close_redis_connection

__all__ = [
    "get_database",
    "close_database_connection",
    "get_redis_client",
    "close_redis_connection",
]
