"""Data access for the single user profile."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserProfile

USER_ID = 1  # single-user app; the DB pins this with a CHECK constraint


def get(db: Session) -> UserProfile | None:
    return db.execute(select(UserProfile).where(UserProfile.id == USER_ID)).scalar_one_or_none()


def get_or_create(db: Session, defaults: dict | None = None) -> UserProfile:
    profile = get(db)
    if profile:
        return profile
    profile = UserProfile(id=USER_ID, name=(defaults or {}).get("name", "Me"), **{
        k: v for k, v in (defaults or {}).items() if k != "name"
    })
    db.add(profile)
    db.flush()
    return profile


def update(db: Session, fields: dict) -> UserProfile:
    profile = get_or_create(db)
    for key, value in fields.items():
        if value is not None and hasattr(profile, key):
            setattr(profile, key, value)
    db.flush()
    return profile


def set_embedding(db: Session, vector: list[float]) -> None:
    profile = get_or_create(db)
    profile.cv_embedding = vector
    db.flush()
