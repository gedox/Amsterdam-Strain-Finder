from pydantic import BaseModel, field_validator
from typing import Optional, List

VALID_CATEGORIES = {"sativa", "indica", "hybrid", "hash", "edible", "pre-roll", "other"}


class StrainItem(BaseModel):
    name: str
    category: str
    price_per_gram: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        v = v.lower().strip()
        if v not in VALID_CATEGORIES:
            return "other"
        return v

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v):
        # Title Case
        return v.strip().title()


class MenuParseResult(BaseModel):
    shop_slug: str
    items: List[StrainItem]
    raw_response: str
    parse_error: Optional[str] = None
