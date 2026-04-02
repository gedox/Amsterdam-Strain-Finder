"""
One-off script: OCR all menu images in menus/ and populate the database.
Skips the scraper entirely — assumes images are already downloaded.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from db.models import SessionLocal
from db.crud import refresh_strains
from ocr.extract import extract_strains

MENUS_DIR = Path(__file__).parent / "menus"


def main():
    images = sorted(MENUS_DIR.glob("*.jpg"))
    logger.info("Found %d menu images", len(images))

    total = len(images)
    success = 0
    errors = []

    for i, img_path in enumerate(images, 1):
        # Extract slug from filename: "abraxas_1775146270.jpg" -> "abraxas"
        slug = re.sub(r"_\d+\.jpg$", "", img_path.name)

        logger.info("[%d/%d] OCR for %s ...", i, total, slug)

        try:
            result = extract_strains(str(img_path), slug)
        except Exception as exc:
            logger.error("OCR failed for %s: %s", slug, exc)
            errors.append(slug)
            continue

        if result.parse_error:
            logger.warning("Parse error for %s: %s", slug, result.parse_error)
            strain_dicts = []
        else:
            strain_dicts = [
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
                shop_slug=slug,
                image_url=f"local://{img_path.name}",
                menu_date=None,
                contributor=None,
                strains=strain_dicts,
                raw_json=result.raw_response,
            )
            session.commit()
            success += 1
            logger.info("Saved %d strains for %s", len(strain_dicts), slug)
        except Exception as exc:
            session.rollback()
            logger.error("DB error for %s: %s", slug, exc)
            errors.append(slug)
        finally:
            session.close()

    logger.info("Done: %d/%d succeeded, %d errors", success, total, len(errors))
    if errors:
        logger.info("Failed shops: %s", ", ".join(errors))


if __name__ == "__main__":
    main()
