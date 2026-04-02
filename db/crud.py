"""
CRUD helpers for Amsterdam Strain Finder.

All functions accept an active SQLAlchemy Session as their first argument.
They never commit — callers are responsible for session lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Coffeeshop, MenuSnapshot, ScrapeLog, Strain


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Return the canonical lowercase-stripped form of a strain name."""
    return name.strip().lower()


def _get_shop_by_slug(session: Session, slug: str) -> Coffeeshop | None:
    return session.query(Coffeeshop).filter(Coffeeshop.slug == slug).first()


def _get_snapshot(session: Session, coffeeshop_id: int, image_url: str) -> MenuSnapshot | None:
    return (
        session.query(MenuSnapshot)
        .filter(
            MenuSnapshot.coffeeshop_id == coffeeshop_id,
            MenuSnapshot.image_url == image_url,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_shop(
    session: Session,
    slug: str,
    name: str,
    address: str = None,
    city: str = "Amsterdam",
) -> Coffeeshop:
    """Insert or update a coffeeshop row. Never delete. Return the row."""
    shop = _get_shop_by_slug(session, slug)
    if shop is None:
        shop = Coffeeshop(slug=slug, name=name, address=address, city=city)
        session.add(shop)
        session.flush()  # populate shop.id without committing
    else:
        # Update mutable fields but never overwrite created_at or id
        shop.name = name
        if address is not None:
            shop.address = address
        shop.city = city
        session.flush()
    return shop


def is_new_image(session: Session, slug: str, image_url: str) -> bool:
    """Return True if this image_url has NOT been seen for this shop before."""
    shop = _get_shop_by_slug(session, slug)
    if shop is None:
        return True
    existing = _get_snapshot(session, shop.id, image_url)
    return existing is None


def upsert_snapshot(
    session: Session,
    coffeeshop_id: int,
    image_url: str,
    menu_date: str = None,
    contributor: str = None,
) -> MenuSnapshot:
    """Insert new snapshot row (scraped_at = now). Return it."""
    snapshot = _get_snapshot(session, coffeeshop_id, image_url)
    if snapshot is None:
        snapshot = MenuSnapshot(
            coffeeshop_id=coffeeshop_id,
            image_url=image_url,
            menu_date=menu_date,
            contributor=contributor,
            scraped_at=datetime.utcnow(),
            is_active=True,
        )
        session.add(snapshot)
        session.flush()
    else:
        # Refresh metadata without resetting processed_at or raw_json
        if menu_date is not None:
            snapshot.menu_date = menu_date
        if contributor is not None:
            snapshot.contributor = contributor
        session.flush()
    return snapshot


def refresh_strains(
    session: Session,
    shop_slug: str,
    image_url: str,
    menu_date: str,
    contributor: str,
    strains: list[dict[str, Any]],
    raw_json: str = None,
) -> None:
    """
    Full refresh for a shop.

    Steps:
      1. Upsert the shop row.
      2. Upsert the snapshot row (scraped_at = now, is_active = True).
      3. Delete old *active* strains for this shop.
      4. Bulk-insert new strains linked to the new snapshot.
      5. Mark all other snapshots for this shop as is_active = False.
      6. Set snapshot.processed_at = now and store raw_json.

    Each dict in `strains` must contain at minimum:
      - "name"     (str)
      - "category" (str, one of the valid CHECK values)
    Optional keys:
      - "price_per_gram" (float)
      - "notes"          (str)
    """
    # 1. Upsert shop — name falls back to slug when caller hasn't provided it
    shop = upsert_shop(session, shop_slug, shop_slug, city="Amsterdam")
    # Re-fetch to ensure we have the persisted row (upsert_shop may have just
    # flushed).  The caller must have already upserted or we use the returned obj.
    shop = _get_shop_by_slug(session, shop_slug)

    # 2. Upsert snapshot
    new_snapshot = upsert_snapshot(
        session,
        coffeeshop_id=shop.id,
        image_url=image_url,
        menu_date=menu_date,
        contributor=contributor,
    )

    # 3. Delete old active strains for this shop
    (
        session.query(Strain)
        .filter(Strain.coffeeshop_id == shop.id)
        .delete(synchronize_session="fetch")
    )

    # 4. Bulk-insert new strains
    now = datetime.utcnow()
    for strain_data in strains:
        raw_name = strain_data["name"]
        strain = Strain(
            coffeeshop_id=shop.id,
            snapshot_id=new_snapshot.id,
            name=raw_name,
            name_normalized=_normalize(raw_name),
            category=strain_data["category"],
            price_per_gram=strain_data.get("price_per_gram"),
            notes=strain_data.get("notes"),
            created_at=now,
        )
        session.add(strain)

    # 5. Deactivate all other snapshots for this shop
    (
        session.query(MenuSnapshot)
        .filter(
            MenuSnapshot.coffeeshop_id == shop.id,
            MenuSnapshot.id != new_snapshot.id,
        )
        .update({"is_active": False}, synchronize_session="fetch")
    )

    # 6. Mark new snapshot as processed
    new_snapshot.processed_at = datetime.utcnow()
    new_snapshot.raw_json = raw_json
    new_snapshot.is_active = True

    session.flush()


def log_run(
    session: Session,
    started_at: datetime,
    finished_at: datetime = None,
    shops_checked: int = 0,
    shops_updated: int = 0,
    errors: str = None,
) -> ScrapeLog:
    """Insert a scrape_log row."""
    entry = ScrapeLog(
        started_at=started_at,
        finished_at=finished_at,
        shops_checked=shops_checked,
        shops_updated=shops_updated,
        errors=errors,
    )
    session.add(entry)
    session.flush()
    return entry


def get_active_strains_for_shop(session: Session, slug: str) -> list[Strain]:
    """Return all strains from the active snapshot for a shop."""
    shop = _get_shop_by_slug(session, slug)
    if shop is None:
        return []

    active_snapshot = (
        session.query(MenuSnapshot)
        .filter(
            MenuSnapshot.coffeeshop_id == shop.id,
            MenuSnapshot.is_active == True,
        )
        .order_by(MenuSnapshot.scraped_at.desc())
        .first()
    )
    if active_snapshot is None:
        return []

    return (
        session.query(Strain)
        .filter(Strain.snapshot_id == active_snapshot.id)
        .order_by(Strain.category, Strain.name_normalized)
        .all()
    )


def search_strains(session: Session, query: str, category: str = None) -> list[dict[str, Any]]:
    """
    Search strains by name_normalized (LIKE %query%).
    Optional category filter.
    Return joined rows with shop info as dicts.
    """
    pattern = f"%{_normalize(query)}%"

    q = (
        session.query(Strain, Coffeeshop)
        .join(Coffeeshop, Strain.coffeeshop_id == Coffeeshop.id)
        .filter(Strain.name_normalized.like(pattern))
    )

    if category:
        q = q.filter(Strain.category == category.lower())

    rows = q.order_by(Strain.name_normalized, Coffeeshop.name).all()

    results = []
    for strain, shop in rows:
        results.append(
            {
                "strain_id":      strain.id,
                "name":           strain.name,
                "name_normalized": strain.name_normalized,
                "category":       strain.category,
                "price_per_gram": strain.price_per_gram,
                "notes":          strain.notes,
                "shop_slug":      shop.slug,
                "shop_name":      shop.name,
                "shop_city":      shop.city,
            }
        )
    return results


def get_popular_strains(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Return top strains by count of distinct shops carrying them."""
    rows = (
        session.query(
            Strain.name_normalized,
            Strain.category,
            func.count(func.distinct(Strain.coffeeshop_id)).label("shop_count"),
        )
        .group_by(Strain.name_normalized, Strain.category)
        .order_by(func.count(func.distinct(Strain.coffeeshop_id)).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "name_normalized": row.name_normalized,
            "category":        row.category,
            "shop_count":      row.shop_count,
        }
        for row in rows
    ]


def get_all_shops(session: Session) -> list[dict[str, Any]]:
    """Return all shops with last_menu_date and strain_count."""
    shops = session.query(Coffeeshop).order_by(Coffeeshop.name).all()

    results = []
    for shop in shops:
        active_snapshot = (
            session.query(MenuSnapshot)
            .filter(
                MenuSnapshot.coffeeshop_id == shop.id,
                MenuSnapshot.is_active == True,
            )
            .order_by(MenuSnapshot.scraped_at.desc())
            .first()
        )

        strain_count = (
            session.query(func.count(Strain.id))
            .filter(
                Strain.coffeeshop_id == shop.id,
                Strain.snapshot_id == (active_snapshot.id if active_snapshot else None),
            )
            .scalar()
            or 0
        )

        results.append(
            {
                "id":             shop.id,
                "slug":           shop.slug,
                "name":           shop.name,
                "address":        shop.address,
                "city":           shop.city,
                "last_menu_date": active_snapshot.menu_date if active_snapshot else None,
                "strain_count":   strain_count,
            }
        )
    return results


def get_shop_menu(session: Session, slug: str) -> dict[str, Any] | None:
    """Return shop info + active strains grouped by category."""
    shop = _get_shop_by_slug(session, slug)
    if shop is None:
        return None

    active_snapshot = (
        session.query(MenuSnapshot)
        .filter(
            MenuSnapshot.coffeeshop_id == shop.id,
            MenuSnapshot.is_active == True,
        )
        .order_by(MenuSnapshot.scraped_at.desc())
        .first()
    )

    strains = (
        session.query(Strain)
        .filter(
            Strain.snapshot_id == (active_snapshot.id if active_snapshot else -1)
        )
        .order_by(Strain.category, Strain.name_normalized)
        .all()
    )

    # Group strains by category
    by_category: dict[str, list[dict[str, Any]]] = {}
    for strain in strains:
        by_category.setdefault(strain.category, []).append(
            {
                "id":             strain.id,
                "name":           strain.name,
                "name_normalized": strain.name_normalized,
                "price_per_gram": strain.price_per_gram,
                "notes":          strain.notes,
            }
        )

    return {
        "id":             shop.id,
        "slug":           shop.slug,
        "name":           shop.name,
        "address":        shop.address,
        "city":           shop.city,
        "last_menu_date": active_snapshot.menu_date if active_snapshot else None,
        "scraped_at":     active_snapshot.scraped_at.isoformat() if active_snapshot and active_snapshot.scraped_at else None,
        "menu":           by_category,
    }


def get_category_counts(session: Session) -> dict[str, int]:
    """Return count of active strains per category."""
    # Only count strains attached to an active snapshot
    active_snapshot_ids = (
        session.query(MenuSnapshot.id)
        .filter(MenuSnapshot.is_active == True)
        .subquery()
    )

    rows = (
        session.query(Strain.category, func.count(Strain.id).label("cnt"))
        .filter(Strain.snapshot_id.in_(active_snapshot_ids))
        .group_by(Strain.category)
        .all()
    )

    return {row.category: row.cnt for row in rows}


def get_status(session: Session) -> dict[str, Any]:
    """Return last_scrape_at, shops_indexed, strains_indexed, shops_updated_last_run."""
    last_log = (
        session.query(ScrapeLog)
        .order_by(ScrapeLog.started_at.desc())
        .first()
    )

    active_snapshot_ids = (
        session.query(MenuSnapshot.id)
        .filter(MenuSnapshot.is_active == True)
        .subquery()
    )

    shops_indexed = session.query(func.count(Coffeeshop.id)).scalar() or 0

    strains_indexed = (
        session.query(func.count(Strain.id))
        .filter(Strain.snapshot_id.in_(active_snapshot_ids))
        .scalar()
        or 0
    )

    return {
        "last_scrape_at":        last_log.started_at.isoformat() if last_log and last_log.started_at else None,
        "shops_indexed":         shops_indexed,
        "strains_indexed":       strains_indexed,
        "shops_updated_last_run": last_log.shops_updated if last_log else 0,
    }
