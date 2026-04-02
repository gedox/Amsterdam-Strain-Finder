"""
FastAPI application for Amsterdam Strain Finder.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.models import Base, engine, DATABASE_URL
from api.routes import strains, coffeeshops, admin
from mangum import Mangum  # <-- Vercel ASGI adapter

# Only auto-create tables for local dev; Vercel sets VERCEL=1 automatically
if not os.environ.get("VERCEL"):
    Base.metadata.create_all(bind=engine)

app = FastAPI(title="Amsterdam Strain Finder", version="1.0.0")

# CORS — allow all origins for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(strains.router)
app.include_router(coffeeshops.router)
app.include_router(admin.router)

@app.get("/")
def root():
    return {"service": "Amsterdam Strain Finder", "docs": "/docs"}
