import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("PMS_DATA_DIR", os.path.join(BASE_DIR, "data"))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, "DevOps", ".env")
LOCAL_ENV_PATH = os.path.join(PROJECT_ROOT, "DevOps", ".env.local")

load_dotenv(dotenv_path=LOCAL_ENV_PATH)
load_dotenv(dotenv_path=ENV_PATH)

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_FILE_PATH = os.environ.get("PMS_DEFAULT_FILE_PATH", r"D:\Trend\PMS_Trend_All.xlsx")
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
PORT = int(os.environ.get("PORT", "8000"))
PMS_AUTO_SEED = os.environ.get(
    "PMS_AUTO_SEED",
    "true" if APP_ENV == "development" else "false",
).strip().lower() == "true"
PMS_SEED_PERMISSIONS_ON_STARTUP = os.environ.get(
    "PMS_SEED_PERMISSIONS_ON_STARTUP",
    "true" if APP_ENV == "development" else "false",
).strip().lower() == "true"

# Comma-separated list of allowed origins. Do not use wildcards in production with credentials.
_cors_origins = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,https://pms-frontend-iota-dusky.vercel.app",
)
CORS_ORIGINS = tuple(origin.strip().rstrip('/') for origin in _cors_origins.split(",") if origin.strip())
if APP_ENV == "production" and "*" in CORS_ORIGINS:
    raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit origins when credentials are enabled in production.")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
if MAX_UPLOAD_BYTES <= 0:
    raise ValueError("MAX_UPLOAD_BYTES must be greater than zero.")

# Security Roles definitions
ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_EXECUTIVE = "Executive"
ROLE_VIEWER = "Viewer"

ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EXECUTIVE, ROLE_VIEWER]

# JWT & Security settings
JWT_SECRET = os.environ.get("JWT_SECRET") or "pms-default-jwt-secret-key-2026-safe-fallback"
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# Redis settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class _SettingsCompatibility:
    """Attribute-style access retained for existing runtime/tests callers."""

    MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES


settings = _SettingsCompatibility()

