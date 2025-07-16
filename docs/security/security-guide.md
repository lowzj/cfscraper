# CFScraper API Security Guide

## Overview

This document provides comprehensive security guidance for the CFScraper API, covering authentication, authorization, input validation, and security best practices.

## Security Features

### 1. API Key Authentication

The CFScraper API uses API key authentication with different permission levels:

#### Permission Levels
- **READ**: Access to read-only endpoints (job status, health checks)
- **WRITE**: Access to create and modify resources (scraping jobs)
- **ADMIN**: Full administrative access (API key management, security settings)

#### API Key Format
- Format: `cfsk_<32-character-random-string>`
- Keys are securely hashed using HMAC-SHA256
- Configurable expiration (default: 30 days)

#### Usage
```bash
# Using Authorization header (recommended)
curl -H "Authorization: Bearer cfsk_your_api_key_here" \
     https://api.example.com/api/v1/scrape/

# Using X-API-Key header
curl -H "X-API-Key: cfsk_your_api_key_here" \
     https://api.example.com/api/v1/scrape/
```

### 2. Input Validation and Sanitization

#### Comprehensive Validation
- **URL Validation**: Ensures only HTTP/HTTPS protocols
- **SQL Injection Prevention**: Parameterized queries and input sanitization
- **XSS Prevention**: HTML escaping and content sanitization
- **Path Traversal Protection**: Blocks directory traversal attempts
- **Command Injection Prevention**: Filters dangerous command patterns

#### Validation Rules
- URLs must use HTTP or HTTPS protocols
- Headers are sanitized and length-limited
- Request data is recursively sanitized
- File uploads (if implemented) are validated for type and size

### 3. Rate Limiting

#### Features
- IP-based rate limiting with Redis backend
- Configurable limits per endpoint
- IP whitelisting for trusted sources
- Bypass tokens for special cases
- Detailed rate limit headers in responses

#### Default Limits
- 60 requests per minute per IP
- 1000 requests per hour per IP
- Burst limit of 10 requests

#### Rate Limit Headers
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1640995200
Retry-After: 15
```

### 4. Security Headers

#### Implemented Headers
- **HSTS**: HTTP Strict Transport Security
- **CSP**: Content Security Policy
- **X-Frame-Options**: Clickjacking protection
- **X-Content-Type-Options**: MIME sniffing prevention
- **X-XSS-Protection**: XSS filter activation
- **Referrer-Policy**: Referrer information control

#### Content Security Policy
```
default-src 'self'; 
script-src 'self' 'unsafe-inline'; 
style-src 'self' 'unsafe-inline'; 
img-src 'self' data: https:; 
frame-ancestors 'none'; 
base-uri 'self'
```

### 5. Data Encryption and Privacy

#### Encryption Features
- AES-256 encryption for sensitive data
- PBKDF2 key derivation with 100,000 iterations
- Secure random salt generation
- Data anonymization for logs

#### Privacy Protection
- IP address anonymization in logs
- Email address masking
- URL parameter removal in logs
- Sensitive header redaction

### 6. Audit Logging

#### Logged Events
- Authentication attempts (success/failure)
- API access with response codes
- Security violations
- Rate limit exceeded events
- Administrative actions

#### Log Format
```json
{
  "event_type": "authentication_success",
  "severity": "low",
  "timestamp": "2023-12-01T10:30:00Z",
  "ip_address": "192.168.xxx.xxx",
  "user_agent": "Mozilla/5.0...",
  "endpoint": "/api/v1/scrape",
  "message": "User authenticated successfully",
  "integrity_hash": "sha256_hash"
}
```

## Configuration

### Environment Variables

#### Required Security Settings
```bash
# API Key Security
API_KEY_SECRET=your-strong-secret-key-32-chars-min
API_KEY_EXPIRY_DAYS=30
ADMIN_API_KEYS=cfsk_admin_key_1,cfsk_admin_key_2

# Encryption
ENCRYPTION_KEY=your-encryption-key-32-chars-min

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Security Features
SECURITY_HEADERS_ENABLED=true
AUDIT_LOGGING_ENABLED=true
RATE_LIMITING_ENABLED=true

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_HOUR=1000
ADMIN_IPS=192.168.1.100,10.0.0.50
```

#### Optional Settings
```bash
# Rate Limiting Bypass
RATE_LIMIT_BYPASS_TOKENS=bypass_token_1,bypass_token_2

# Debug Mode (disable in production)
DEBUG=false
```

### Security Validation

The system automatically validates security configuration on startup:

- Checks for default secrets
- Validates CORS configuration
- Ensures admin keys are configured
- Verifies security features are enabled

## API Endpoints

### Admin Endpoints (Require Admin API Key)

#### Create API Key
```bash
POST /api/v1/admin/api-keys
Content-Type: application/json
Authorization: Bearer cfsk_admin_key

{
  "permissions": ["read", "write"],
  "expires_in_days": 30,
  "description": "Client API key"
}
```

#### List API Keys
```bash
GET /api/v1/admin/api-keys
Authorization: Bearer cfsk_admin_key
```

#### Security Status
```bash
GET /api/v1/admin/security/status
Authorization: Bearer cfsk_admin_key
```

#### Test Security Features
```bash
POST /api/v1/admin/security/test
Authorization: Bearer cfsk_admin_key
```

### Protected Endpoints (Require API Key)

#### Create Scraping Job
```bash
POST /api/v1/scrape/
Content-Type: application/json
Authorization: Bearer cfsk_your_api_key

{
  "url": "https://example.com",
  "scraper_type": "cloudscraper"
}
```

## Security Testing

### Automated Security Tests

Run the security test suite:
```bash
python security/security-tests.py --url http://localhost:8000
```

### Manual Security Testing

#### Test API Key Authentication
```bash
# Should fail without API key
curl -X POST http://localhost:8000/api/v1/scrape/ \
     -H "Content-Type: application/json" \
     -d '{"url": "https://example.com", "scraper_type": "cloudscraper"}'

# Should succeed with valid API key
curl -X POST http://localhost:8000/api/v1/scrape/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer cfsk_your_api_key" \
     -d '{"url": "https://example.com", "scraper_type": "cloudscraper"}'
```

#### Test Rate Limiting
```bash
# Make rapid requests to trigger rate limiting
for i in {1..100}; do
  curl http://localhost:8000/api/v1/health/
done
```

#### Test Input Validation
```bash
# Should reject malicious input
curl -X POST http://localhost:8000/api/v1/scrape/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer cfsk_your_api_key" \
     -d '{"url": "javascript:alert(\"xss\")", "scraper_type": "cloudscraper"}'
```

### Vulnerability Scanning

#### Dependency Scanning
```bash
# Install security tools
pip install safety bandit

# Check for vulnerable dependencies
safety check

# Static code analysis
bandit -r app/
```

#### Container Scanning
```bash
# Scan Docker image for vulnerabilities
trivy image cfscraper:latest
```

## Security Best Practices

### Deployment Security

1. **Use HTTPS**: Always deploy with TLS/SSL certificates
2. **Environment Variables**: Store secrets in environment variables, not code
3. **Regular Updates**: Keep dependencies updated
4. **Monitoring**: Monitor security logs and alerts
5. **Backup**: Regular backups of configuration and data

### API Key Management

1. **Rotation**: Regularly rotate API keys
2. **Least Privilege**: Grant minimum required permissions
3. **Monitoring**: Monitor API key usage
4. **Revocation**: Immediately revoke compromised keys
5. **Secure Storage**: Store keys securely on client side

### Network Security

1. **Firewall**: Configure firewall rules
2. **VPN**: Use VPN for admin access
3. **IP Whitelisting**: Restrict access by IP when possible
4. **Load Balancer**: Use load balancer with security features

## Incident Response

### Security Incident Handling

1. **Detection**: Monitor logs for security events
2. **Assessment**: Evaluate severity and impact
3. **Containment**: Isolate affected systems
4. **Eradication**: Remove threats and vulnerabilities
5. **Recovery**: Restore normal operations
6. **Lessons Learned**: Update security measures

### Emergency Contacts

- Security Team: security@yourcompany.com
- DevOps Team: devops@yourcompany.com
- Management: management@yourcompany.com

## Compliance

### Standards Compliance

- **OWASP Top 10**: Protection against common vulnerabilities
- **GDPR**: Data privacy and protection measures
- **SOC 2**: Security controls and monitoring
- **ISO 27001**: Information security management

### Audit Requirements

- Security logs retained for 90 days minimum
- Regular security assessments
- Penetration testing annually
- Vulnerability scanning monthly

## Support

For security-related questions or to report vulnerabilities:

- Email: security@yourcompany.com
- Security Portal: https://security.yourcompany.com
- Emergency Hotline: +1-555-SECURITY

---

**Last Updated**: December 2023  
**Version**: 1.0  
**Classification**: Internal Use
