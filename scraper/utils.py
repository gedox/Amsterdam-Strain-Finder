"""
Utility helpers for the Amsterdam Strain Finder scraper.
"""

from __future__ import annotations

import os
import re
from typing import Optional

import httpx


def get_http_client() -> httpx.Client:
    """Return a configured httpx.Client ready for scraping."""
    return httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible; StrainFinder/1.0)"},
        timeout=30,
        follow_redirects=True,
    )


def download_image(client: httpx.Client, url: str, dest_path: str) -> str:
    """
    Download image bytes from *url* and save to *dest_path*.

    Creates parent directories if they do not already exist.
    Returns *dest_path* on success.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    response = client.get(url)
    response.raise_for_status()
    with open(dest_path, "wb") as fh:
        fh.write(response.content)
    return dest_path


# Matches date tokens like "Oct.2014", "Feb.2026", "February 2026", "15 February 2026"
_DATE_TOKEN_RE = re.compile(
    r"""
    (?:
        # "15 February 2026" or "February 2026"
        (?:\d{1,2}\s+)?
        (?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|
           Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|
           Dec(?:ember)?)
        [\.\s]\s*\d{4}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_last_date(text: str) -> Optional[str]:
    """
    Extract the *last* date reference from *text*.

    Examples:
        "Oct.2014 to Feb.2026"  →  "Feb.2026"
        "Updated 15 February 2026 by John"  →  "15 February 2026"
        "no date here"  →  None
    """
    matches = _DATE_TOKEN_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()


# Matches "by Name" where Name is one or more capitalised words
_CONTRIBUTOR_RE = re.compile(r"\bby\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)", re.IGNORECASE)


def parse_contributor(text: str) -> Optional[str]:
    """
    Extract contributor name from text like "by Liam" → "Liam".

    Returns None if no match is found.
    """
    match = _CONTRIBUTOR_RE.search(text)
    if not match:
        return None
    return match.group(1).strip()
