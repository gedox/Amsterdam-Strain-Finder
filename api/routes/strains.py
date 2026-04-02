"""
Strain search and popular endpoints.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from db import crud

router = APIRouter(prefix="/strains", tags=["strains"])


@router.get("/search")
def search_strains(
    q: str = Query(..., min_length=1),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return crud.search_strains(db, q, category)


@router.get("/popular")
def popular_strains(db: Session = Depends(get_db)):
    return crud.get_popular_strains(db)
