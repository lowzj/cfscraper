# API Documentation Security Configuration

## Overview

The CFScraper API includes configurable OpenAPI documentation endpoints that can be disabled in production environments for enhanced security.

## Configuration

### Environment Variable

```bash
ENABLE_DOCS=true|false
```

- **Default**: `true` (documentation enabled)
- **Production Recommendation**: `false` (documentation disabled)

### Affected Endpoints

When `ENABLE_DOCS=false`, the following endpoints are disabled:

- `/docs` - Swagger UI interface
- `/redoc` - ReDoc interface  
- `/openapi.json` - OpenAPI specification

## Environment-Specific Settings

### Development (.env.dev)
```bash
DEBUG=true
ENABLE_DOCS=true
```

### Production (.env.prod)
```bash
DEBUG=false
ENABLE_DOCS=false
```

## Security Benefits

### Why Disable Documentation in Production?

1. **Information Disclosure**: API documentation reveals:
   - Available endpoints and methods
   - Request/response schemas
   - Authentication requirements
   - Parameter validation rules

2. **Attack Surface Reduction**: Removes potential vectors for:
   - API enumeration
   - Schema discovery
   - Endpoint fuzzing

3. **Compliance**: Many security frameworks recommend:
   - Disabling debug features in production
   - Minimizing information exposure
   - Following principle of least privilege

## Implementation Details

### Automatic Validation

The system includes automatic validation that:

- Warns when documentation is enabled in production mode
- Includes documentation status in security configuration checks
- Logs security issues during startup

### FastAPI Integration

```python
app = FastAPI(
    title="CFScraper API",
    description="A comprehensive scraper API service",
    version="1.0.0",
    # Conditionally disable docs based on settings
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None
)
```

## Usage Examples

### Enable Documentation (Development)
```bash
export ENABLE_DOCS=true
# or in .env file
echo "ENABLE_DOCS=true" >> .env
```

### Disable Documentation (Production)
```bash
export ENABLE_DOCS=false
# or in .env.prod file
echo "ENABLE_DOCS=false" >> .env.prod
```

### Runtime Verification

Check if documentation is enabled:
```bash
# Should return 404 when disabled
curl http://localhost:8000/docs

# API endpoints still work
curl http://localhost:8000/health
```

## Best Practices

1. **Always disable in production**: Set `ENABLE_DOCS=false` for production deployments
2. **Use environment-specific configs**: Maintain separate `.env` files for different environments
3. **Monitor security warnings**: Review startup logs for security configuration issues
4. **Document for team**: Ensure team knows how to access docs in development

## Alternative Documentation Access

When documentation is disabled in production, consider:

1. **Separate documentation environment**: Deploy docs to a separate, secured environment
2. **Local development**: Keep documentation available for local development
3. **API client generation**: Generate client SDKs from OpenAPI spec during build
4. **External documentation**: Maintain separate documentation outside the API

## Security Headers

Documentation endpoints also respect Content Security Policy (CSP) settings:

- **Development**: Permissive CSP allowing external CDN resources
- **Production**: Restrictive CSP when docs are disabled
- **API endpoints**: Always use strict CSP regardless of docs setting
