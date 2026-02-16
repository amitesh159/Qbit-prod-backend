"""
Qbit Backend - Main FastAPI Application
Production-ready FastAPI app with all routes, middleware, and lifespan management
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from database.connection import get_database, close_database_connection, create_indexes
from database.redis_client import get_redis_client, close_redis_connection

# Import routers
from routes.auth_routes import router as auth_router
from routes.user_routes import router as user_router
from routes.project_routes import router as project_router
from routes.generation_routes import router as generation_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if settings.log_format == "json" 
        else structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # STARTUP
    logger.info(
        "application_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment
    )
    
    try:
        # Initialize database connections
        try:
            db = await get_database()
            await create_indexes()
            logger.info("mongodb_initialized")
        except Exception as e:
            logger.error(
                "mongodb_initialization_failed",
                error=str(e)
            )
            # MongoDB is critical - raise error
            raise
        
        # Initialize Central Hub with Memory
        try:
            from hub.hub import initialize_hub
            await initialize_hub(db)
            logger.info("central_hub_initialized_with_memory")
        except Exception as e:
            logger.error(
                "central_hub_initialization_failed",
                error=str(e)
            )
            # Central Hub is critical
            raise
        
        # Initialize Fullstack Agent with LangChain Tools
        try:
            from agents.fullstack_agent.fullstack_agent import initialize_agent
            initialize_agent(db)
            logger.info("fullstack_agent_initialized_with_tools")
        except Exception as e:
            logger.error(
                "fullstack_agent_initialization_failed",
                error=str(e)
            )
            # Fullstack Agent is critical
            raise
        
        # Initialize Redis (optional - app can run without it)
        try:
            redis_client = await get_redis_client()
            if redis_client:
                logger.info("redis_initialized")
            else:
                logger.warning("redis_unavailable_continuing_without_cache")
        except Exception as e:
            logger.warning(
                "redis_initialization_failed_continuing",
                error=str(e)
            )
        
        logger.info("application_started")
        
    except Exception as e:
        logger.exception(
            "application_startup_failed",
            error=str(e)
        )
        raise
    
    yield
    
    # SHUTDOWN
    logger.info("application_shutting_down")
    
    try:
        # Shutdown Central Hub (flush memory)
        try:
            from hub.hub import shutdown_hub
            await shutdown_hub()
            logger.info("central_hub_shutdown")
        except Exception as e:
            logger.warning(
                "central_hub_shutdown_error",
                error=str(e)
            )
        
        await close_database_connection()
        await close_redis_connection()
        logger.info("application_shutdown_complete")
        
    except Exception as e:
        logger.exception(
            "application_shutdown_error",
            error=str(e)
        )


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Qbit - AI-Powered Full-Stack Application Generator",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None
)


# ============================================================================
# MIDDLEWARE
# ============================================================================
# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods.split(",") if settings.cors_allow_methods != "*" else ["*"],
    allow_headers=settings.cors_allow_headers.split(",") if settings.cors_allow_headers != "*" else ["*"],
)

# Custom Middleware
from middleware.request_logger import request_logging_middleware
from middleware.error_handler import error_handler_middleware

app.middleware("http")(request_logging_middleware)
app.middleware("http")(error_handler_middleware)


# ============================================================================
# ROUTERS
# ============================================================================
# Include all routes with API prefix
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(user_router, prefix=settings.api_v1_prefix)
app.include_router(project_router, prefix=settings.api_v1_prefix)
app.include_router(generation_router)  # WebSocket routes (no prefix)


# ============================================================================
# ROOT & HEALTH CHECK
# ============================================================================
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "environment": settings.environment,
        "docs": "/docs" if settings.enable_docs else None
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.
    Verifies database and Redis connectivity.
    """
    health = {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment
    }
    
    # Check MongoDB
    try:
        db = await get_database()
        await db.command("ping")
        health["mongodb"] = "connected"
    except Exception as e:
        health["mongodb"] = f"error: {str(e)}"
        health["status"] = "unhealthy"
    
    # Check Redis
    try:
        redis = await get_redis_client()
        if redis is None:
            health["redis"] = "unavailable (optional)"
        else:
            await redis.ping()
            health["redis"] = "connected"
    except Exception as e:
        health["redis"] = f"error: {str(e)}"
        # Redis is optional - don't mark as unhealthy
    
    return health


# ============================================================================
# ERROR HANDLERS
# ============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler.
    Logs all unhandled exceptions.
    """
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc)
    )
    
    if settings.show_error_details:
        return {
            "error": "Internal server error",
            "detail": str(exc),
            "path": request.url.path
        }
    else:
        return {
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }


# ============================================================================
# DEVELOPMENT NOTES
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    
    logger.info(
        "starting_development_server",
        host=settings.host,
        port=settings.port,
        reload=settings.reload
    )
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )
