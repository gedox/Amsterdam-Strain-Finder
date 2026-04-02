import anthropic
import base64
import json
import logging
import os
import re
from pathlib import Path

from ocr.validate import StrainItem, MenuParseResult
from ocr.preprocess import image_to_base64, enhance_image

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a cannabis menu parser. Given a photo of a Dutch coffeeshop menu board or printed menu,
extract every product listed. Return ONLY a valid JSON array — no markdown, no explanation, no preamble.

Each item must follow this exact shape:
{
  "name": str,
  "category": str,
  "price_per_gram": float | null,
  "notes": str | null
}

Rules:
- Infer category from context or common knowledge if not stated explicitly on the menu
- Hash / charas / pollen / moroccan / afghani → "hash"
- Space cake / brownie / cookie / edible → "edible"
- Pre-rolled joint / blunt → "pre-roll"
- category must be one of: sativa, indica, hybrid, hash, edible, pre-roll, other
- If a product has a price per gram listed, extract it as a float (e.g. "€12" → 12.0)
- If pricing is per item or not listed → null
- Normalize all strain names to Title Case
- Skip section headers, shop name, totals, prices for non-cannabis items, and decorative text
- If the image is too blurry or illegible to parse, return an empty array: []
"""

MODEL = "claude-sonnet-4-20250514"


def _call_claude(b64: str, media_type: str) -> str:
    """Send a vision request to Claude and return the raw text response."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Parse this coffeeshop menu.",
                    },
                ],
            }
        ],
    )

    return message.content[0].text


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that Claude sometimes wraps JSON in."""
    return re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()


def _parse_response(raw: str, shop_slug: str) -> tuple[list[StrainItem], str | None]:
    """
    Parse the raw Claude response into a list of StrainItems.
    Returns (items, parse_error). parse_error is None on success.
    """
    cleaned = _strip_code_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"OCR parse error for {shop_slug}: {e}")
        return [], str(e)

    if not isinstance(data, list):
        err = f"Expected JSON array, got {type(data).__name__}"
        logger.error(f"OCR parse error for {shop_slug}: {err}")
        return [], err

    items: list[StrainItem] = []
    for raw_item in data:
        try:
            item = StrainItem.model_validate(raw_item)
            items.append(item)
        except Exception as e:
            logger.warning(
                f"Skipping invalid item for {shop_slug} — {raw_item!r}: {e}"
            )

    return items, None


def extract_strains(image_path: str, shop_slug: str = "unknown") -> MenuParseResult:
    """
    Main entry point. Takes path to a menu image.
    Returns MenuParseResult with parsed StrainItems.

    Pipeline:
    1. image_to_base64(image_path) — handles PDF conversion
    2. Claude API call with vision
    3. Strip markdown code fences from response
    4. JSON parse
    5. Pydantic validate each item
    6. On malformed JSON: log error, return empty MenuParseResult with parse_error set
    7. On low-quality / empty result: retry ONCE with enhance_image, then re-call Claude
    8. Return MenuParseResult
    """
    # Step 1: encode image
    b64, media_type = image_to_base64(image_path)

    # Step 2: call Claude
    raw = _call_claude(b64, media_type)

    # Steps 3-5: parse and validate
    items, parse_error = _parse_response(raw, shop_slug)

    # Step 6: propagate hard parse failure immediately
    if parse_error is not None:
        return MenuParseResult(
            shop_slug=shop_slug,
            items=[],
            raw_response=raw,
            parse_error=parse_error,
        )

    # Step 7: empty result — retry once with enhanced image
    if not items:
        logger.info(
            f"Empty parse result for {shop_slug}; retrying with enhanced image."
        )
        enhanced_path = enhance_image(image_path)
        b64_enhanced, media_type_enhanced = image_to_base64(enhanced_path)
        raw = _call_claude(b64_enhanced, media_type_enhanced)
        items, parse_error = _parse_response(raw, shop_slug)

        if parse_error is not None:
            return MenuParseResult(
                shop_slug=shop_slug,
                items=[],
                raw_response=raw,
                parse_error=parse_error,
            )

    # Step 8: return result
    return MenuParseResult(
        shop_slug=shop_slug,
        items=items,
        raw_response=raw,
        parse_error=None,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = extract_strains(sys.argv[1], "test")
        for item in result.items:
            print(f"{item.name} | {item.category} | €{item.price_per_gram}")
