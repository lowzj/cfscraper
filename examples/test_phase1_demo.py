#!/usr/bin/env python3
"""
Demo script for CFScraper API

This script demonstrates the basic usage of the CFScraper API.
"""

import asyncio
import httpx
import json
import time
from typing import Dict, Any


class CFScraperClient:
    """Simple client for CFScraper API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if the API is healthy"""
        response = await self.client.get(f"{self.base_url}/health")
        return response.json()
    
    async def create_job(self, url: str, scraper_type: str = "cloudscraper") -> str:
        """Create a scraping job"""
        data = {
            "url": url,
            "scraper_type": scraper_type,
            "method": "GET"
        }
        response = await self.client.post(f"{self.base_url}/api/v1/scrape", json=data)
        result = response.json()
        return result["task_id"]
    
    async def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """Get job status"""
        response = await self.client.get(f"{self.base_url}/api/v1/jobs/{task_id}")
        return response.json()
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status"""
        response = await self.client.get(f"{self.base_url}/api/v1/queue/status")
        return response.json()
    
    async def wait_for_job(self, task_id: str, timeout: int = 60) -> Dict[str, Any]:
        """Wait for job completion"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = await self.get_job_status(task_id)
            if status["status"] in ["completed", "failed"]:
                return status
            await asyncio.sleep(1)
        raise TimeoutError(f"Job {task_id} did not complete within {timeout} seconds")
    
    async def close(self):
        """Close the client"""
        await self.client.aclose()


async def main():
    """Main demo function"""
    client = CFScraperClient()
    
    try:
        # Check API health
        print("1. Checking API health...")
        health = await client.health_check()
        print(f"   API Status: {health['status']}")
        
        # Check queue status
        print("\n2. Checking queue status...")
        queue = await client.get_queue_status()
        print(f"   Queue size: {queue['queue_size']}")
        print(f"   Running jobs: {queue['running_jobs']}")
        
        # Create a scraping job
        print("\n3. Creating a scraping job...")
        task_id = await client.create_job("https://httpbin.org/html")
        print(f"   Task ID: {task_id}")
        
        # Wait for job completion
        print("\n4. Waiting for job completion...")
        result = await client.wait_for_job(task_id)
        print(f"   Job Status: {result['status']}")
        
        if result["status"] == "completed":
            print("   Job completed successfully!")
            if result.get("result"):
                content_length = len(result["result"].get("content", ""))
                print(f"   Content length: {content_length} characters")
        else:
            print(f"   Job failed: {result.get('error_message', 'Unknown error')}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())