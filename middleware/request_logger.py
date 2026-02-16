"""
Request Logging Middleware
Logs all incoming requests with timing
"""
import time
import structlog
import uuid
from fastapi import Request

logger = structlog.get_logger(__name__)


async def request_logging_middleware(request: Request, call_next):
    """
    Log all incoming requests with timing and request ID.
    """
    # Generate request ID
    request_id = str(uuid.uuid4())
    
    # Start timer
    start_time = time.time()
    
    # Log incoming request
    logger.info(
        "request_received",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else None
    )
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Log response
    logger.info(
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=int(duration * 1000)
    )
    
    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    
    return response
