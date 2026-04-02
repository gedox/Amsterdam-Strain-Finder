"""
FastAPI application for Amsterdam Strain Finder.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.models import Base, engine
from api.routes import strains, coffeeshops, admin

# Create all tables on startup
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
