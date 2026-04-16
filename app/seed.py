"""Seed a default admin user.

Usage:
    .venv/bin/python -m app.seed
Env overrides:
    SEED_EMAIL, SEED_NAME, SEED_PASSWORD
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.services.auth_service import hash_password


DEFAULT_EMAIL = os.getenv("SEED_EMAIL", "admin@orionmano.local")
DEFAULT_NAME = os.getenv("SEED_NAME", "Admin")
DEFAULT_PASSWORD = os.getenv("SEED_PASSWORD", "admin123")


async def seed_user(email: str, name: str, password: str) -> None:
    async with async_session() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"user already exists: {email}")
            return

        user = User(
            email=email,
            name=name,
            password_hash=hash_password(password),
            role="admin",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"seeded user: {email} / {password}  (id={user.id})")


def main() -> int:
    asyncio.run(seed_user(DEFAULT_EMAIL, DEFAULT_NAME, DEFAULT_PASSWORD))
    return 0


if __name__ == "__main__":
    sys.exit(main())
