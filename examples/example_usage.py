#!/usr/bin/env python3
"""
Example usage of the CF Scraper API.

This script demonstrates how to use all three scraping methods.
"""

import asyncio
import httpx
import json


async def test_scraper_api():
    """Test all scraper endpoints."""
    base_url = "http://localhost:8000"
    
    # Test URLs (replace with real URLs when testing)
    test_urls = [
        "https://httpbin.org/get",  # Simple API
        "https://example.com",      # Basic website
        # Add more URLs to test different scenarios
    ]
    
    async with httpx.AsyncClient(timeout=60) as client:
        print("=== CF Scraper API Test ===\n")
        
        # Test server health
        try:
            response = await client.get(f"{base_url}/health")
            print(f"Health check: {response.status_code} - {response.json()}")
        except Exception as e:
            print(f"Server not running or unreachable: {e}")
            return
        
        # Test each scraping method
        methods = [
            ("basic", "Basic Requests"),
            ("cloudscraper", "CloudScraper"),
            ("seleniumbase", "SeleniumBase")
        ]
        
        for url in test_urls:
            print(f"\n--- Testing URL: {url} ---")
            
            for method, name in methods:
                try:
                    print(f"\n{name}:")
                    response = await client.post(
                        f"{base_url}/scrape/{method}",
                        json={
                            "url": url,
                            "timeout": 30,
                            "headers": {
                                "User-Agent": "CF-Scraper-Test/1.0"
                            }
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        print(f"  ✓ Status: {data['status_code']}")
                        print(f"  ✓ Content length: {len(data['content'])} chars")
                        print(f"  ✓ Method: {data['method']}")
                        
                        # Show first 200 chars of content
                        content_preview = data['content'][:200].replace('\n', ' ')
                        print(f"  ✓ Preview: {content_preview}...")
                    else:
                        print(f"  ✗ Error: {response.status_code}")
                        print(f"  ✗ Details: {response.text}")
                        
                except Exception as e:
                    print(f"  ✗ Exception: {e}")


async def single_scrape_example():
    """Example of scraping a single URL."""
    url = "https://example.com"  # Replace with target URL
    
    async with httpx.AsyncClient() as client:
        try:
            # Use CloudScraper for Cloudflare protection
            response = await client.post(
                "http://localhost:8000/scrape/cloudscraper",
                json={
                    "url": url,
                    "headers": {
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                    },
                    "timeout": 30
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print("Scraping successful!")
                print(f"Final URL: {data['url']}")
                print(f"Status Code: {data['status_code']}")
                print(f"Content Length: {len(data['content'])}")
                
                # Save content to file
                with open("/tmp/scraped_content.html", "w") as f:
                    f.write(data['content'])
                print("Content saved to /tmp/scraped_content.html")
                
            else:
                print(f"Scraping failed: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    print("Choose an option:")
    print("1. Test all methods with multiple URLs")
    print("2. Single scrape example")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        asyncio.run(test_scraper_api())
    elif choice == "2":
        asyncio.run(single_scrape_example())
    else:
        print("Invalid choice. Running full test...")
        asyncio.run(test_scraper_api())