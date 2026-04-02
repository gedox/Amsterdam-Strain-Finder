"""
Coffeeshop, category, and status endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from db import crud

router = APIRouter(tags=["coffeeshops"])


@router.get("/coffeeshops")
def list_coffeeshops(db: Session = Depends(get_db)):
    return crud.get_all_shops(db)


@router.get("/coffeeshops/{slug}")
def get_coffeeshop(slug: str, db: Session = Depends(get_db)):
    result = crud.get_shop_menu(db, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Coffeeshop not found")
    return result


@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    return crud.get_category_counts(db)


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    return crud.get_status(db)
