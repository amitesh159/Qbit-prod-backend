"""
Authentication package for Qbit backend
JWT authentication, password hashing, and GitHub OAuth
"""
from auth.jwt_utils import create_access_token, decode_access_token
from auth.password import hash_password, verify_password
from auth.dependencies import get_current_user, require_auth

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
    "get_current_user",
    "require_auth",
]
