"""Shared FastAPI dependencies."""
from app.core.database import get_db  # noqa: F401  (re-exported for routers)
