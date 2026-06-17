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

# Ensure Backend directory is on the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routers import router as api_router
from services.seeding_service import DatabaseSeeder

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run database seeder on startup
    seeder = DatabaseSeeder()
    seeder.seed_database()
    yield

app = FastAPI(
    title="PMS Dashboard API",
    description="Backend Clean Architecture API for Saudi German Hospital Performance Management System",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware — allow frontend dev servers
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
