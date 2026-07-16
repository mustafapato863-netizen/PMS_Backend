"""Error Handling Middleware
Intercepts all unhandled exceptions, records them in the database,
and maps them to standard JSON error responses.
"""

import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from config.database import SessionLocal
from services.error_tracker import ErrorTracker
from config.logging_config import request_id_ctx

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Intercepts and records exceptions, returning clean JSON responses"""

    async def dispatch(self, request: Request, call_next):
        # 1. Generate request ID and attach to request state
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Set logging contextvar
        token = request_id_ctx.set(request_id)
        
        try:
            # 2. Track total request count for sliding window metrics
            # Exclude health check from metrics to prevent skewing
            if not request.url.path.endswith("/health"):
                ErrorTracker.register_request()

            response = await call_next(request)
            
            # Catch responses with 5xx status codes that didn't raise exceptions (e.g. returned directly)
            if response.status_code >= 500 and not request.url.path.endswith("/health"):
                # Register an error count
                ErrorTracker.register_error()
                
            return response
            
        except Exception as exc:
            # 3. Log to database via ErrorTracker service
            status_code = 500
            is_critical = True
            
            if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
                status_code = exc.status_code
                if status_code < 500:
                    is_critical = False
            elif isinstance(exc, ValueError):
                status_code = 400
                is_critical = False

            # Exclude health check errors from metric calculations
            if request.url.path.endswith("/health"):
                is_critical = False

            # Log to DB if it's critical or if it is unhandled (which resolves to 500)
            if status_code >= 500 or is_critical:
                try:
                    with SessionLocal() as db:
                        ErrorTracker.log_error(db, request, exc, request_id)
                except Exception:
                    logger.exception("Error handling middleware failed to write to database")

            # Keep detailed logs on stdout/stderr
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

            # Return a consistent structured response
            error_message = "An internal server error occurred."
            if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
                error_message = exc.detail
            elif isinstance(exc, ValueError):
                # Return standard 400 bad request for ValueErrors if they escape services
                status_code = 400
                error_message = str(exc)

            return JSONResponse(
                status_code=status_code,
                content={
                    "success": False,
                    "message": error_message,
                    "request_id": request_id
                }
            )
        finally:
            request_id_ctx.reset(token)
