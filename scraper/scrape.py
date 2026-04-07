"""
Main scraper for Amsterdam Strain Finder.

Entry point: run_scraper() → list[ScrapeJob]
"""

from __future__ import annotations

import logging
import time
import os
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from db.models import SessionLocal
from db import crud

from .models import ScrapeJob
from .utils import get_http_client, download_image, parse_last_date, parse_contributor

logger = logging.getLogger(__name__)

BASE_URL = "https://www.coffeeshopmenus.org"
INDEX_URL = "https://www.coffeeshopmenus.org/ams_index.html"

# Matches filenames like "cs-paradox.html"
_CS_HREF_RE = re.compile(r"^cs-.+\.html$", re.IGNORECASE)

# Date pattern used when scanning raw text nodes near an image
_DATE_SCAN_RE = re.compile(
    r"""
    (?:
        (?:\d{1,2}\s+)?
        (?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|
           Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|
           Dec(?:ember)?)
        [\.\s]\s*\d{4}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug_from_href(href: str) -> str:
    """'cs-paradox.html' → 'paradox'"""
    name = os.path.basename(href)          # strip any path component
    name = re.sub(r"^cs-", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.html$", "", name, flags=re.IGNORECASE)
    return name


def _is_amsterdam(anchor_text: str) -> bool:
    """
    Return True when the text after the last comma contains 'Amsterdam'.

    Typical format: "Shop Name, Street, Amsterdam"
    """
    parts = anchor_text.split(",")
    if len(parts) < 2:
        return False
    city_part = parts[-1]
    return "amsterdam" in city_part.lower()


def _extract_address(soup: BeautifulSoup) -> Optional[str]:
    """
    Shop pages look like:
        <strong>Shop Name</strong>, Street Address, Postcode City

    We grab the text of the parent element that follows </strong> and
    strip leading whitespace / commas to produce a clean address string.
    """
    strong = soup.find("strong")
    if strong is None:
        return None
    parent = strong.parent
    if parent is None:
        return None

    # Collect all text *after* the <strong> tag within the parent
    full_text = parent.get_text()
    strong_text = strong.get_text()
    # Remove the shop name portion at the start
    after = full_text[full_text.find(strong_text) + len(strong_text):]
    # Strip leading comma / whitespace
    address = after.lstrip(", \t\n\r").split("\n")[0].strip().rstrip(",").strip()
    return address if address else None


def _find_img_after_hr(soup: BeautifulSoup) -> Optional[any]:
    """
    Locate the first <img> that appears after the <hr> tag.

    Walks next siblings; if a sibling has children it searches within them.
    """
    hr = soup.find("hr")
    if hr is None:
        return None

    img = None
    for sibling in hr.next_siblings:
        if hasattr(sibling, "name") and sibling.name == "img":
            img = sibling
            break
        elif hasattr(sibling, "name") and sibling.name is not None:
            img = sibling.find("img")
            if img:
                break
    return img


def _extract_date_and_contributor(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """
    Scan text nodes that appear after the <hr> tag for a date and a
    contributor credit ("by Name").

    Returns (menu_date, contributor) — either may be None.
    """
    hr = soup.find("hr")
    if hr is None:
        return None, None

    collected_text_parts: list[str] = []

    for sibling in hr.next_siblings:
        if isinstance(sibling, str):
            collected_text_parts.append(sibling)
        elif hasattr(sibling, "get_text"):
            collected_text_parts.append(sibling.get_text(separator=" "))

    combined = " ".join(collected_text_parts)

    menu_date = parse_last_date(combined)
    contributor = parse_contributor(combined)
    return menu_date, contributor


# Closed or rebranded shops — skip these entirely so they don't get re-added
_SKIP_SLUGS = frozenset({
    "andalucia", "ricks-cafe", "rickscafe", "terminator", "rockland",
    "baba", "funky-munkey", "funkymunkey", "softland", "amsterdamned",
})

# Pattern to extract end date from index text like "59 menus: Dec.2003 to Mar.2026"
_INDEX_END_DATE_RE = re.compile(
    r"to\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\.\s]*(\d{4})",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_index_end_date(anchor_text: str) -> Optional[datetime]:
    """Parse the end date from index page text like '59 menus: Dec.2003 to Mar.2026'."""
    m = _INDEX_END_DATE_RE.search(anchor_text)
    if not m:
        return None
    month = _MONTH_MAP.get(m.group(1).lower()[:3])
    year = int(m.group(2))
    if month is None:
        return None
    return datetime(year, month, 1)


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def run_scraper(full: bool = False) -> list[ScrapeJob]:
    """
    Scrape coffeeshopmenus.org for Amsterdam coffeeshop menu images.

    By default only visits shops whose latest menu date on the index page
    is newer than the last scrape. Pass full=True to visit all shops.

    Returns a list of ScrapeJob instances — one per new menu image found.
    """
    results: list[ScrapeJob] = []
    session = SessionLocal()

    try:
        client = get_http_client()

        # ------------------------------------------------------------------
        # Step 1 & 2: Fetch and parse index page
        # ------------------------------------------------------------------
        logger.info("Fetching index: %s", INDEX_URL)
        try:
            resp = client.get(INDEX_URL)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Failed to fetch index page: %s", exc)
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        # ------------------------------------------------------------------
        # Step 3: Find all <a> tags linking to "cs-*.html"
        # ------------------------------------------------------------------
        anchors = [
            a for a in soup.find_all("a", href=True)
            if _CS_HREF_RE.match(os.path.basename(a["href"]))
        ]
        logger.info("Found %d cs-*.html links on index page", len(anchors))

        # Build list of Amsterdam shops to visit
        shops_to_visit: list[tuple[str, str, str]] = []  # (slug, name, href)

        # Determine cutoff date for incremental mode
        cutoff = None
        if not full:
            last_scrape = crud.get_status(session).get("last_scrape_at")
            if last_scrape:
                last_scrape_dt = datetime.fromisoformat(last_scrape)
                cutoff = datetime(last_scrape_dt.year, last_scrape_dt.month, 1)
                logger.info("Incremental mode: only scraping menus updated since %s",
                            cutoff.strftime("%b %Y"))
            else:
                logger.info("No previous scrape found — running full scrape")

        for anchor in anchors:
            href = anchor["href"]
            full_text = anchor.get_text()

            # Step 4d: Skip closed / converted venues
            lowered = full_text.lower()
            if "(closed)" in lowered or "(now a bar)" in lowered:
                logger.debug("Skipping closed/bar entry: %s", full_text.strip())
                continue

            slug = _slug_from_href(href)

            # Skip shops we've removed from the database
            if slug in _SKIP_SLUGS:
                logger.debug("Skipping closed/rebranded shop: %s", slug)
                continue

            # In incremental mode, skip shops not updated since last scrape
            if cutoff is not None:
                end_date = _parse_index_end_date(full_text)
                if end_date is None or end_date < cutoff:
                    continue

            # Extract shop name — try <strong> first, fall back to first text line
            strong_tag = anchor.find("strong")
            if strong_tag is not None:
                name = strong_tag.get_text().strip()
            else:
                # Name is the first non-empty line, before the city comma
                first_line = next(
                    (l.strip() for l in full_text.splitlines() if l.strip()), ""
                )
                # Strip ", Amsterdam" suffix if present
                name = re.split(r",\s*amsterdam", first_line, flags=re.IGNORECASE)[0].strip()
                if not name:
                    logger.debug("Skipping anchor with no name: %s", href)
                    continue

            shops_to_visit.append((slug, name, href))

        mode_label = "full" if full else "incremental"
        logger.info("%d Amsterdam shops queued for scraping (%s)", len(shops_to_visit), mode_label)

        # ------------------------------------------------------------------
        # Step 5: Visit each shop page
        # ------------------------------------------------------------------
        for slug, name, href in shops_to_visit:
            time.sleep(1.5)  # crawl delay

            shop_url = f"{BASE_URL}/{href.lstrip('/')}"
            logger.info("Scraping shop: %s (%s)", name, shop_url)

            try:
                shop_resp = client.get(shop_url)
                shop_resp.raise_for_status()
            except Exception as exc:
                logger.warning("HTTP error for shop %s: %s", slug, exc)
                continue

            shop_soup = BeautifulSoup(shop_resp.text, "html.parser")

            # Step 5d-f: Find first <img> after <hr>
            img_tag = _find_img_after_hr(shop_soup)
            if img_tag is None:
                logger.warning("No img found after <hr> for shop: %s", slug)
                continue

            # Step 5g-h: Build absolute image URL
            img_src = img_tag.get("src", "")
            if not img_src:
                logger.warning("img tag has no src for shop: %s", slug)
                continue

            image_url = BASE_URL + "/" + img_src.lstrip("/")

            # Step 5i-j: Extract date and contributor from surrounding text
            menu_date, contributor = _extract_date_and_contributor(shop_soup)

            # Step 5k: Extract address
            address = _extract_address(shop_soup)

            # Step 5l: Skip if image already known
            if not crud.is_new_image(session, slug, image_url):
                logger.info("Image already in DB for %s — skipping", slug)
                continue

            # Download image into project menus/ directory
            menus_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "menus")
            os.makedirs(menus_dir, exist_ok=True)
            dest_path = os.path.join(menus_dir, f"{slug}_{int(time.time())}.jpg")
            try:
                download_image(client, image_url, dest_path)
                logger.info("Downloaded menu image for %s → %s", slug, dest_path)
            except Exception as exc:
                logger.warning("Failed to download image for %s: %s", slug, exc)
                continue

            # Step 5m: Append to results
            job = ScrapeJob(
                shop_slug=slug,
                shop_name=name,
                address=address,
                image_url=image_url,
                image_path=dest_path,
                menu_date=menu_date,
                contributor=contributor,
            )
            results.append(job)
            logger.info(
                "Queued ScrapeJob: slug=%s date=%s contributor=%s",
                slug,
                menu_date,
                contributor,
            )

    finally:
        session.close()

    logger.info("Scraper finished. %d new jobs collected.", len(results))
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    full_mode = "--full" in sys.argv
    jobs = run_scraper(full=full_mode)
    for job in jobs:
        print(job)
