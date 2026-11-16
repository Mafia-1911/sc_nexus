"""Accounts for the deployed site (A-118): people who sign up on the landing page.

Not domain data (no lineage). Only the web app reads and writes it (sign-up, login); passwords
are scrypt hashes (`apps/web/lib/auth.ts`), never stored or logged in clear.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from cportal_core.models.base import Base, pk


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[UUID] = pk()
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-cased
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]
