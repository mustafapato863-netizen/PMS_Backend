import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("PMS_DATA_DIR", os.path.join(BASE_DIR, "data"))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, "DevOps", ".env")

load_dotenv(dotenv_path=ENV_PATH)

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_FILE_PATH = os.environ.get("PMS_DEFAULT_FILE_PATH", r"D:\Trend\PMS_Trend_All.xlsx")

# Security Roles definitions
ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_EXECUTIVE = "Executive"
ROLE_VIEWER = "Viewer"

ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EXECUTIVE, ROLE_VIEWER]

# JWT & Security settings
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET must be set in DevOps/.env or the environment.")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# Redis settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

