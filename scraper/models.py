from dataclasses import dataclass
from typing import Optional


@dataclass
class ScrapeJob:
    shop_slug: str
    shop_name: str
    address: Optional[str]
    image_url: str
    image_path: str          # local path where image was downloaded
    menu_date: Optional[str]
    contributor: Optional[str]
