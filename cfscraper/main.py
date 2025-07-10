"""Main entry point for the CF Scraper API server."""

import uvicorn
from .server import app


def main():
    """Start the FastAPI server."""
    uvicorn.run(
        "cfscraper.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()