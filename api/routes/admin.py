"""
Admin endpoints — protected by X-Admin-Key header.
"""

import threading
import uuid

from fastapi import APIRouter, Depends

from api.deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


def _run_pipeline():
    """Import and run the full pipeline in a background thread."""
    from scheduler.runner import run_pipeline
    run_pipeline()


@router.post("/trigger-scrape")
def trigger_scrape(_key: str = Depends(require_admin)):
    job_id = str(uuid.uuid4())
    thread = threading.Thread(target=_run_pipeline, name=f"scrape-{job_id}", daemon=True)
    thread.start()
    return {"status": "triggered", "job_id": job_id}
