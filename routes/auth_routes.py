"""
Authentication API Routes
User registration, login, and GitHub OAuth
"""
import uuid
import structlog
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from database.connection import get_database
from database.schemas import UserModel
from auth.jwt_utils import create_access_token
from auth.password import hash_password, verify_password
from auth.github_oauth import github_oauth
from config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================
class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    name: str | None = Field(None, description="Optional user display name")


class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Authentication response"""
    access_token: str
    token_type: str = "bearer"
    user: dict


# ============================================================================
# EMAIL/PASSWORD AUTHENTICATION
# ============================================================================
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """
    Register a new user with email and password.
    
    Returns JWT access token.
    """
    db = await get_database()
    
    # Check if user already exists
    existing_user = await db.users.find_one({"email": request.email})
    
    if existing_user:
        logger.warning(
            "registration_failed_email_exists",
            email=request.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(request.password)
    
    user = UserModel(
        user_id=user_id,
        email=request.email,
        display_name=request.name,
        password_hash=password_hash,
        credits=settings.default_user_credits,
        tier="free",
        created_at=datetime.utcnow(),
        last_login=datetime.utcnow()
    )
    
    await db.users.insert_one(user.model_dump())
    
    # Create access token
    token_data = {
        "user_id": user_id,
        "email": request.email,
        "tier": "free"
    }
    access_token = create_access_token(token_data)
    
    logger.info(
        "user_registered",
        user_id=user_id,
        email=request.email
    )
    
    return AuthResponse(
        access_token=access_token,
        user={
            "user_id": user_id,
            "email": request.email,
            "name": request.name,
            "credits": settings.default_user_credits,
            "tier": "free"
        }
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Login with email and password.
    
    Returns JWT access token.
    """
    db = await get_database()
    
    # Find user
    user = await db.users.find_one({"email": request.email})
    
    if not user:
        logger.warning(
            "login_failed_user_not_found",
            email=request.email
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Verify password
    if not user.get("password_hash") or not verify_password(request.password, user["password_hash"]):
        logger.warning(
            "login_failed_invalid_password",
            email=request.email
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Update last login
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_login": datetime.utcnow()}}
    )
    
    # Create access token
    token_data = {
        "user_id": user["user_id"],
        "email": user["email"],
        "tier": user.get("tier", "free")
    }
    access_token = create_access_token(token_data)
    
    logger.info(
        "user_logged_in",
        user_id=user["user_id"]
    )
    
    return AuthResponse(
        access_token=access_token,
        user={
            "user_id": user["user_id"],
            "email": user["email"],
            "credits": user.get("credits", 0),
            "tier": user.get("tier", "free")
        }
    )


# ============================================================================
# GITHUB OAUTH
# ============================================================================
@router.get("/github/login")
async def github_login():
    """
    Initiate GitHub OAuth flow.
    Redirects user to GitHub authorization page.
    """
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    
    # TODO: Store state in Redis for validation (optional enhancement)
    
    authorization_url = github_oauth.get_authorization_url(state=state)
    
    logger.info("github_oauth_initiated")
    
    return RedirectResponse(url=authorization_url)


@router.get("/github/callback")
async def github_callback(code: str = Query(...), state: str | None = Query(None)):
    """
    GitHub OAuth callback.
    Exchanges code for access token and creates/logs in user.
    """
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No authorization code provided"
        )
    
    # Exchange code for token
    access_token = await github_oauth.exchange_code_for_token(code)
    
    if not access_token:
        logger.error("github_token_exchange_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate with GitHub"
        )
    
    # Get user profile
    github_user = await github_oauth.get_user_profile(access_token)
    
    if not github_user:
        logger.error("github_user_profile_fetch_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to fetch GitHub profile"
        )
    
    db = await get_database()
    
    # Check if user exists by GitHub ID
    github_id = str(github_user.get("id"))
    user = await db.users.find_one({"github_id": github_id})
    
    if user:
        # Existing user - update token and last login
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {
                "$set": {
                    "github_access_token": access_token,
                    "last_login": datetime.utcnow()
                }
            }
        )
        user_id = user["user_id"]
        logger.info(
            "github_user_logged_in",
            user_id=user_id
        )
    else:
        # New user - create account
        user_id = str(uuid.uuid4())
        email = github_user.get("email") or f"{github_user.get('login')}@github.user"
        
        new_user = UserModel(
            user_id=user_id,
            email=email,
            github_username=github_user.get("login"),
            github_id=github_id,
            github_access_token=access_token,
            credits=settings.default_user_credits,
            tier="free",
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow()
        )
        
        await db.users.insert_one(new_user.model_dump())
        
        logger.info(
            "github_user_created",
            user_id=user_id,
            github_username=github_user.get("login")
        )
    
    # Create JWT token
    user_doc = await db.users.find_one({"user_id": user_id})
    token_data = {
        "user_id": user_id,
        "email": user_doc["email"],
        "tier": user_doc.get("tier", "free")
    }
    jwt_token = create_access_token(token_data)
    
    # Redirect to frontend with token
    # In production, redirect to frontend URL with token as query param
    frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:3000"
    redirect_url = f"{frontend_url}/auth/callback?token={jwt_token}"
    
    return RedirectResponse(url=redirect_url)
