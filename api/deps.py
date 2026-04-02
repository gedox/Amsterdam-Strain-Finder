"""
FastAPI dependencies: DB session and admin auth.
"""

import os
from typing import Generator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from db.models import SessionLocal

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(x_admin_key: str = Header(...)) -> str:
    """Validate the X-Admin-Key header against ADMIN_API_KEY env var."""
    if not ADMIN_API_KEY or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing admin key")
    return x_admin_key
