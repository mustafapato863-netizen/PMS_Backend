"""
FastAPI backend server for PMS Dashboard.
Provides clean endpoints for PMS Dashboard following Clean Architecture.

Run with:  cd Backend && uvicorn app:app --reload --port 8000
"""
import sys
import os
import io

# Force UTF-8 encoding for console output (Windows compatibility)
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from socketio import ASGIApp

# Ensure Backend directory is on the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routers import router as api_router
from config.socket_config import sio
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.error_handling_middleware import ErrorHandlingMiddleware
from config.database import SessionLocal
from config.logging_config import setup_logging

# Initialize structured logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lazy imports for startup performance
    from services.seeding_service import DatabaseSeeder
    from services.permission_seed import seed_role_permissions

    # Run database seeder on startup
    seeder = DatabaseSeeder()
    seeder.seed_database()
    
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

# Register AuthMiddleware
app.add_middleware(AuthMiddleware)

# Register ErrorHandlingMiddleware (to catch database/internal exceptions)
app.add_middleware(ErrorHandlingMiddleware)

# CORS Middleware — allow frontend dev servers (outermost to wrap errors and auth responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open to all origins for easier dashboard connections
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

# Wrap FastAPI app with Socket.io ASGI app for production/dev
app = ASGIApp(sio, app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

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
