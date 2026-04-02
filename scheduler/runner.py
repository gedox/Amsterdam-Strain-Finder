"""
Scheduler module for Amsterdam Strain Finder.

Runs the full scrape -> OCR -> DB pipeline every 6 hours using APScheduler.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from db.models import SessionLocal
from db.crud import refresh_strains, log_run
from scraper.scrape import run_scraper
from ocr.extract import extract_strains

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Execute the full scrape -> OCR -> DB pipeline once."""
    started_at = datetime.utcnow()
    errors: list[str] = []
    shops_checked = 0
    shops_updated = 0

    logger.info("Pipeline started at %s", started_at.isoformat())

    # Step 1: Scrape
    try:
        jobs = run_scraper()
    except Exception as exc:
        logger.exception("Scraper failed")
        errors.append(f"Scraper error: {exc}")
        jobs = []

    shops_checked = len(jobs)

    # Step 2 & 3: OCR each job, then persist to DB
    for job in jobs:
        try:
            result = extract_strains(job.image_path, job.shop_slug)
        except Exception as exc:
            logger.exception("OCR failed for %s", job.shop_slug)
            errors.append(f"OCR error for {job.shop_slug}: {exc}")
            continue

        if result.parse_error:
            logger.warning(
                "Parse error for %s: %s", job.shop_slug, result.parse_error
            )
            errors.append(f"Parse error for {job.shop_slug}: {result.parse_error}")
            # Still persist with empty strains
            strains = []
        else:
            strains = [
                {
                    "name": item.name,
                    "category": item.category,
                    "price_per_gram": item.price_per_gram,
                    "notes": item.notes,
                }
                for item in result.items
            ]

        session = SessionLocal()
        try:
            refresh_strains(
                session,
                shop_slug=job.shop_slug,
                image_url=job.image_url,
                menu_date=job.menu_date,
                contributor=job.contributor,
                strains=strains,
                raw_json=result.raw_response,
            )
            session.commit()
            shops_updated += 1
            logger.info("Updated %s with %d strains", job.shop_slug, len(strains))
        except Exception as exc:
            session.rollback()
            logger.exception("DB error for %s", job.shop_slug)
            errors.append(f"DB error for {job.shop_slug}: {exc}")
        finally:
            session.close()

    # Log the run
    finished_at = datetime.utcnow()
    error_text = "\n".join(errors) if errors else None

    session = SessionLocal()
    try:
        log_run(
            session,
            started_at=started_at,
            finished_at=finished_at,
            shops_checked=shops_checked,
            shops_updated=shops_updated,
            errors=error_text,
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to write scrape log")
    finally:
        session.close()

    logger.info(
        "Pipeline finished: checked=%d updated=%d errors=%d",
        shops_checked,
        shops_updated,
        len(errors),
    )


def main() -> None:
    """Start the scheduler: run immediately, then every 6 hours."""
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "interval", hours=6, id="strain_pipeline")

    logger.info("Running initial pipeline...")
    run_pipeline()

    logger.info("Starting scheduler (every 6 hours)...")
    scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    main()
