from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db
from app.core.middleware import setup_exception_handlers, log_requests


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up cfscraper API...")
    init_db()  # Initialize database tables
    yield
    # Shutdown
    print("Shutting down cfscraper API...")


app = FastAPI(
    title="CFScraper API",
    description="A comprehensive scraper API service with FastAPI, SeleniumBase, and Cloudscraper",
    version="1.0.0",
    lifespan=lifespan
)

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request logging middleware
app.middleware("http")(log_requests)

# Setup exception handlers
setup_exception_handlers(app)

# Import and include API routes
from app.api.routes import api_router
app.include_router(api_router, prefix="/api/v1")

# Keep backward compatibility with old routes
try:
    from app.api.routes import router as old_router
    app.include_router(old_router, prefix="/api/v1", tags=["legacy"])
except ImportError:
    pass


@app.get("/")
async def root():
    return {"message": "CFScraper API is running"}


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={
            "status": "healthy",
            "version": "1.0.0",
            "service": "cfscraper-api"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)