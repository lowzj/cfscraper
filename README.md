# CF Scraper

A powerful scraper API server that bypasses Cloudflare's anti-bot protection using multiple scraping methods.

## Features

- **FastAPI-based REST API** - Modern, fast, and well-documented API
- **Multiple scraping methods**:
  - **CloudScraper** - Bypass Cloudflare protection with TLS fingerprinting
  - **SeleniumBase** - Full browser automation for complex JavaScript sites
  - **Basic requests** - Simple HTTP requests for unprotected sites
- **Built with UV** - Fast, modern Python packaging and dependency management

## Installation

This project uses [UV](https://docs.astral.sh/uv/) for fast dependency management.

```bash
# Clone the repository
git clone https://github.com/peekapaw/cfscraper.git
cd cfscraper

# Install UV (if not already installed)
pip install uv

# Install dependencies
uv sync

# Run the server
uv run cfscraper
```

## Usage

### Starting the Server

```bash
# Start the API server
uv run cfscraper

# Or run directly
uv run python -m cfscraper.main
```

The server will start on `http://localhost:8000` with automatic reload enabled.

### API Endpoints

#### Root Endpoint
```bash
GET /
```
Returns API information and available endpoints.

#### Health Check
```bash
GET /health
```
Returns server health status.

#### Scraping Endpoints

All scraping endpoints accept POST requests with the following JSON payload:

```json
{
  "url": "https://example.com",
  "headers": {
    "Custom-Header": "value"
  },
  "timeout": 30
}
```

**1. CloudScraper (Recommended for Cloudflare)**
```bash
POST /scrape/cloudscraper
```
Uses cloudscraper library to bypass Cloudflare protection. Best for sites with Cloudflare anti-bot pages.

**2. SeleniumBase (For Complex JavaScript)**
```bash
POST /scrape/seleniumbase
```
Uses SeleniumBase with Chrome in headless mode. Best for sites with complex JavaScript or advanced Cloudflare protection.

**3. Basic Requests (Fastest)**
```bash
POST /scrape/basic
```
Simple HTTP requests using the requests library. Fastest but won't bypass any protection.

### Response Format

All scraping endpoints return a JSON response with the following format:

```json
{
  "url": "https://example.com",
  "status_code": 200,
  "content": "<html>...</html>",
  "headers": {
    "content-type": "text/html",
    "server": "cloudflare"
  },
  "method": "cloudscraper"
}
```

### Example Usage

#### Using curl

```bash
# Test with CloudScraper
curl -X POST -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' \
  http://localhost:8000/scrape/cloudscraper

# Test with custom headers
curl -X POST -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "headers": {"User-Agent": "Custom Bot"}}' \
  http://localhost:8000/scrape/seleniumbase
```

#### Using Python

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/scrape/cloudscraper",
        json={"url": "https://example.com"}
    )
    data = response.json()
    print(f"Status: {data['status_code']}")
    print(f"Content length: {len(data['content'])}")
```

#### Using JavaScript/Node.js

```javascript
const response = await fetch('http://localhost:8000/scrape/cloudscraper', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ url: 'https://example.com' })
});

const data = await response.json();
console.log(`Status: ${data.status_code}`);
console.log(`Content length: ${data.content.length}`);
```

## Method Comparison

| Method | Speed | Cloudflare Bypass | JavaScript Support | Memory Usage |
|--------|-------|-------------------|-------------------|--------------|
| Basic | ⭐⭐⭐⭐⭐ | ❌ | ❌ | ⭐⭐⭐⭐⭐ |
| CloudScraper | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ❌ | ⭐⭐⭐⭐ |
| SeleniumBase | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

## Configuration

The server can be configured through environment variables:

- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `LOG_LEVEL`: Logging level (default: info)

## Development

```bash
# Install development dependencies
uv sync --dev

# Run tests (if any)
uv run pytest

# Format code
uv run black .

# Type checking
uv run mypy .
```

## Docker Support

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install uv
RUN uv sync

EXPOSE 8000
CMD ["uv", "run", "cfscraper"]
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Disclaimer

This tool is for educational and legitimate testing purposes only. Always respect robots.txt and terms of service of websites you scrape. Use responsibly and in accordance with applicable laws and regulations.
