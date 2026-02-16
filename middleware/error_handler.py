"""
Error Handler Middleware
Global error handling and logging
"""
import structlog
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse
from config.settings import settings

logger = structlog.get_logger(__name__)


async def error_handler_middleware(request: Request, call_next):
    """
    Global error handler middleware.
    Catches all unhandled exceptions and returns structured error responses.
    """
    try:
        response = await call_next(request)
        return response
        
    except Exception as exc:
        # Log the exception with full traceback
        logger.exception(
            "unhandled_exception_in_middleware",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            traceback=traceback.format_exc()
        )
        
        # Return appropriate error response
        error_response = {
            "error": "Internal server error",
            "path": request.url.path
        }
        
        # Include details in development
        if settings.show_error_details:
            error_response["detail"] = str(exc)
            error_response["traceback"] = traceback.format_exc().split("\n")
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response
        )
