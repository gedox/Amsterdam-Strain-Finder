"""
SQLAlchemy ORM models for Amsterdam Strain Finder.

All four tables are declared here: Coffeeshop, MenuSnapshot, Strain, ScrapeLog.
The module exposes `engine`, `SessionLocal`, and `Base` for use throughout the app.
"""

import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

engine = create_engine(
    DATABASE_URL,
    # Needed for SQLite so the same connection can be used across threads
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Coffeeshops
# ---------------------------------------------------------------------------

class Coffeeshop(Base):
    __tablename__ = "coffeeshops"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    slug       = Column(Text, unique=True, nullable=False)
    name       = Column(Text, nullable=False)
    address    = Column(Text, nullable=True)
    city       = Column(Text, default="Amsterdam")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    snapshots = relationship("MenuSnapshot", back_populates="coffeeshop", cascade="all, delete-orphan")
    strains   = relationship("Strain",       back_populates="coffeeshop", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Coffeeshop slug={self.slug!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Menu Snapshots
# ---------------------------------------------------------------------------

class MenuSnapshot(Base):
    __tablename__ = "menu_snapshots"
    __table_args__ = (
        UniqueConstraint("coffeeshop_id", "image_url", name="uq_snapshot_shop_image"),
    )

    id            = Column(Integer, primary_key=True, autoincrement=True)
    coffeeshop_id = Column(Integer, ForeignKey("coffeeshops.id"), nullable=True)
    image_url     = Column(Text, nullable=False)
    menu_date     = Column(Text,      nullable=True)
    contributor   = Column(Text,      nullable=True)
    scraped_at    = Column(DateTime, nullable=False)
    processed_at  = Column(DateTime, nullable=True)
    raw_json      = Column(Text,      nullable=True)
    is_active     = Column(Boolean,   default=True)

    # Relationships
    coffeeshop = relationship("Coffeeshop",  back_populates="snapshots")
    strains    = relationship("Strain",      back_populates="snapshot", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<MenuSnapshot id={self.id} coffeeshop_id={self.coffeeshop_id} is_active={self.is_active}>"


# ---------------------------------------------------------------------------
# Strains
# ---------------------------------------------------------------------------

VALID_CATEGORIES = ("sativa", "indica", "hybrid", "hash", "edible", "pre-roll", "other")


class Strain(Base):
    __tablename__ = "strains"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    coffeeshop_id   = Column(Integer, ForeignKey("coffeeshops.id"),    nullable=True)
    snapshot_id     = Column(Integer, ForeignKey("menu_snapshots.id"), nullable=True)
    name            = Column(Text,    nullable=False)
    name_normalized = Column(Text,    nullable=False)
    category        = Column(Text,    nullable=False)
    price_per_gram  = Column(Float,    nullable=True)
    notes           = Column(Text,    nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Relationships
    coffeeshop = relationship("Coffeeshop",   back_populates="strains")
    snapshot   = relationship("MenuSnapshot", back_populates="strains")

    def __repr__(self) -> str:
        return f"<Strain name={self.name!r} category={self.category!r}>"


# Explicit indexes mirroring schema.sql (SQLAlchemy will create them via
# create_all; they are also defined in schema.sql for raw SQL migrations).
Index("idx_strains_name",     Strain.name_normalized)
Index("idx_strains_category", Strain.category)
Index("idx_strains_shop",     Strain.coffeeshop_id)


# ---------------------------------------------------------------------------
# Scrape Log
# ---------------------------------------------------------------------------

class ScrapeLog(Base):
    __tablename__ = "scrape_log"

    id            = Column(Integer,   primary_key=True, autoincrement=True)
    started_at    = Column(DateTime, nullable=True)
    finished_at   = Column(DateTime, nullable=True)
    shops_checked = Column(Integer,   default=0)
    shops_updated = Column(Integer,   default=0)
    errors        = Column(Text,      nullable=True)

    def __repr__(self) -> str:
        return f"<ScrapeLog id={self.id} started_at={self.started_at}>"
