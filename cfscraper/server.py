"""FastAPI server with scraper endpoints."""

import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import cloudscraper
import requests
from seleniumbase import Driver

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CF Scraper API",
    description="A scraper API server with SeleniumBase, cloudscraper, and FastAPI for bypassing Cloudflare protection",
    version="0.1.0"
)


class ScrapeRequest(BaseModel):
    """Request model for scraping operations."""
    url: HttpUrl
    headers: Optional[Dict[str, str]] = None
    timeout: Optional[int] = 30


class ScrapeResponse(BaseModel):
    """Response model for scraping operations."""
    url: str
    status_code: int
    content: str
    headers: Dict[str, str]
    method: str


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "CF Scraper API Server",
        "version": "0.1.0",
        "endpoints": {
            "cloudscraper": "/scrape/cloudscraper",
            "seleniumbase": "/scrape/seleniumbase",
            "basic": "/scrape/basic"
        }
    }


@app.post("/scrape/cloudscraper", response_model=ScrapeResponse)
async def scrape_with_cloudscraper(request: ScrapeRequest):
    """
    Scrape a URL using cloudscraper to bypass Cloudflare protection.
    
    This method is best for simple requests where Cloudflare protection
    can be bypassed without JavaScript execution.
    """
    try:
        logger.info(f"Scraping with cloudscraper: {request.url}")
        
        # Create cloudscraper session
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'linux',
                'desktop': True
            }
        )
        
        # Add custom headers if provided
        if request.headers:
            scraper.headers.update(request.headers)
            
        # Make the request
        response = scraper.get(str(request.url), timeout=request.timeout)
        
        return ScrapeResponse(
            url=str(request.url),
            status_code=response.status_code,
            content=response.text,
            headers=dict(response.headers),
            method="cloudscraper"
        )
        
    except Exception as e:
        logger.error(f"Error scraping with cloudscraper: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")


@app.post("/scrape/seleniumbase", response_model=ScrapeResponse)
async def scrape_with_seleniumbase(request: ScrapeRequest):
    """
    Scrape a URL using SeleniumBase for dynamic content and complex Cloudflare challenges.
    
    This method uses a real browser and is best for pages with JavaScript
    or complex Cloudflare protection.
    """
    driver = None
    try:
        logger.info(f"Scraping with seleniumbase: {request.url}")
        
        # Create SeleniumBase driver
        driver = Driver(
            browser="chrome",
            headless=True,
            incognito=True,
            block_images=True,
            do_not_track=True,
            page_load_strategy="eager"
        )
        
        # Add custom headers if provided
        if request.headers:
            for key, value in request.headers.items():
                driver.add_header(key, value)
        
        # Navigate to the URL
        driver.get(str(request.url))
        
        # Wait for page to load and check for Cloudflare
        driver.wait_for_ready_state_complete(timeout=request.timeout)
        
        # Get page content
        content = driver.get_page_source()
        current_url = driver.get_current_url()
        
        # Create response headers (simplified)
        response_headers = {
            "content-type": "text/html",
            "user-agent": driver.execute_script("return navigator.userAgent;")
        }
        
        return ScrapeResponse(
            url=current_url,
            status_code=200,  # SeleniumBase doesn't provide HTTP status codes directly
            content=content,
            headers=response_headers,
            method="seleniumbase"
        )
        
    except Exception as e:
        logger.error(f"Error scraping with seleniumbase: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


@app.post("/scrape/basic", response_model=ScrapeResponse)
async def scrape_basic(request: ScrapeRequest):
    """
    Basic scraping using requests library.
    
    This method is fastest but won't bypass Cloudflare protection.
    Use for testing or non-protected sites.
    """
    try:
        logger.info(f"Basic scraping: {request.url}")
        
        headers = request.headers or {}
        if "User-Agent" not in headers:
            headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        
        response = requests.get(
            str(request.url), 
            headers=headers, 
            timeout=request.timeout
        )
        
        return ScrapeResponse(
            url=str(request.url),
            status_code=response.status_code,
            content=response.text,
            headers=dict(response.headers),
            method="basic"
        )
        
    except Exception as e:
        logger.error(f"Error with basic scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "CF Scraper API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)