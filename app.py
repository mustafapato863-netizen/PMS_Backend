"""
FastAPI backend server for PMS Dashboard.
Provides clean endpoints for PMS Dashboard following Clean Architecture.

Run with:  cd Backend && uvicorn app:app --reload --port 8000
"""
import sys
import os
import io
import time
import logging

# Force UTF-8 encoding for console output (Windows compatibility)
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

try:
    from socketio import ASGIApp
except ImportError:
    ASGIApp = None

# Ensure Backend directory is on the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routers import router as api_router
from config.socket_config import SOCKETIO_AVAILABLE, sio
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.error_handling_middleware import ErrorHandlingMiddleware
from config.database import SessionLocal
from config.logging_config import setup_logging
from config import settings

# Initialize structured logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lazy imports for startup performance
    from services.seeding_service import DatabaseSeeder
    from services.permission_seed import seed_role_permissions

    # Seed only in explicitly enabled environments. Hosted production should
    # run migrations and controlled imports as separate release operations.
    seed_demo_levels = os.environ.get("PMS_SEED_DEMO_LEVELS", "").lower() == "true"
    seeder = DatabaseSeeder() if settings.PMS_AUTO_SEED or seed_demo_levels else None
    if settings.PMS_AUTO_SEED and seeder is not None:
        seeder.seed_database()
    if seed_demo_levels and seeder is not None:
        seeder.seed_demo_performance_levels()
    
    # Run role permissions seeder
    db = SessionLocal()
    try:
        seed_role_permissions(db)
    finally:
        db.close()
        
    yield

app = FastAPI(
    title="PMS Dashboard API",
    description="Backend Clean Architecture API for Saudi German Hospital Performance Management System",
    version="2.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def request_timing_middleware(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "request completed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status_code": getattr(response, "status_code", None),
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response

# Register AuthMiddleware
app.add_middleware(AuthMiddleware)

# Register ErrorHandlingMiddleware (to catch database/internal exceptions)
app.add_middleware(ErrorHandlingMiddleware)

# CORS Middleware — allow frontend dev servers (outermost to wrap errors and auth responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount Routers
app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "api": "PMS Dashboard API - Clean Architecture",
        "version": "2.0.0",
    }

# Wrap FastAPI with Socket.IO when the optional real-time runtime is available.
# Vercel can serve the REST ASGI app without this dependency.
if ASGIApp is not None and SOCKETIO_AVAILABLE:
    app = ASGIApp(sio, app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=settings.PORT, reload=True)

# ========== Cloudflare Workers Compatibility Layer ==========
# Export FastAPI app for Workers compatibility
handler = app

try:
    from workers import WorkerEntrypoint
    import asgi

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await asgi.fetch(app, request, self.env)
            
    # Make the entrypoint class available as default export
    default = Default
except ImportError:
    # Local execution or non-worker environment
    pass
