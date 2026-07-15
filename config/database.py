import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load the shared DevOps environment file from the repository root.
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
project_root = os.path.abspath(os.path.join(backend_dir, ".."))
env_path = os.path.join(project_root, "DevOps", ".env")

load_dotenv(dotenv_path=env_path)

# In production, this dynamically fetches the DATABASE_URL key from your secure .env file
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("CRITICAL ERROR: DATABASE_URL is not set inside the .env file.")

# Create SQLAlchemy engine with optimized production connection pooling
pool_size = int(os.getenv("DATABASE_POOL_SIZE", "20"))
max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
pool_recycle = int(os.getenv("DATABASE_POOL_RECYCLE", "1800"))

engine = create_engine(
    DATABASE_URL,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_pre_ping=True,
    pool_recycle=pool_recycle
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
