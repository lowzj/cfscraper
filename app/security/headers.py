"""
Security Headers Middleware

Implements security headers to protect against common web vulnerabilities
including clickjacking, MIME sniffing, XSS, and more.
"""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses"""

    def __init__(
            self,
            app,
            hsts_max_age: int = 31536000,  # 1 year
            hsts_include_subdomains: bool = True,
            hsts_preload: bool = True,
            csp_policy: str = None,
            frame_options: str = "DENY",
            content_type_options: str = "nosniff",
            referrer_policy: str = "strict-origin-when-cross-origin",
            permissions_policy: str = None
    ):
        super().__init__(app)
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.csp_policy = csp_policy or self._default_csp_policy()
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.referrer_policy = referrer_policy
        self.permissions_policy = permissions_policy or self._default_permissions_policy()

    def _default_csp_policy(self) -> str:
        """Default Content Security Policy"""
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    def _default_permissions_policy(self) -> str:
        """Default Permissions Policy"""
        return (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response"""
        response = await call_next(request)

        # Only add security headers if enabled
        if not settings.security_headers_enabled:
            return response

        # HSTS (HTTP Strict Transport Security)
        if request.url.scheme == "https":
            hsts_value = f"max-age={self.hsts_max_age}"
            if self.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            if self.hsts_preload:
                hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Content Security Policy - use endpoint-specific policy
        csp_policy = get_csp_policy_for_endpoint(str(request.url.path))
        response.headers["Content-Security-Policy"] = csp_policy

        # X-Frame-Options (clickjacking protection)
        response.headers["X-Frame-Options"] = self.frame_options

        # X-Content-Type-Options (MIME sniffing protection)
        response.headers["X-Content-Type-Options"] = self.content_type_options

        # Referrer Policy
        response.headers["Referrer-Policy"] = self.referrer_policy

        # Permissions Policy
        response.headers["Permissions-Policy"] = self.permissions_policy

        # X-XSS-Protection (legacy, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Cross-Origin Embedder Policy
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

        # Cross-Origin Opener Policy
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        # Cross-Origin Resource Policy
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        # Server header removal (security through obscurity)
        if "server" in response.headers:
            del response.headers["server"]

        # X-Powered-By header removal
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response


def add_security_headers(response: Response) -> Response:
    """Add security headers to a specific response"""
    if not settings.security_headers_enabled:
        return response

    # Basic security headers
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "frame-ancestors 'none'"
        )
    }

    for header, value in headers.items():
        response.headers[header] = value

    return response


class CSPViolationReporter:
    """Handle CSP violation reports"""

    @staticmethod
    async def handle_csp_report(request: Request):
        """Handle CSP violation report"""
        try:
            report_data = await request.json()
            logger.warning(
                "CSP Violation Report",
                extra={
                    "csp_report": report_data,
                    "user_agent": request.headers.get("user-agent"),
                    "ip": request.client.host if request.client else "unknown"
                }
            )
        except Exception as e:
            logger.error(f"Failed to process CSP report: {e}")


def get_csp_policy_for_endpoint(endpoint: str) -> str:
    """Get CSP policy tailored for specific endpoints"""

    # API endpoints can have more restrictive CSP
    if endpoint.startswith("/api/"):
        return (
            "default-src 'none'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'"
        )

    # Documentation endpoints might need more permissive CSP
    if endpoint.startswith("/docs") or endpoint.startswith("/redoc"):
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: https: https://fastapi.tiangolo.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )

    # Default policy
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )


class SecurityHeadersConfig:
    """Configuration for security headers"""

    def __init__(
            self,
            hsts_enabled: bool = True,
            hsts_max_age: int = 31536000,
            hsts_include_subdomains: bool = True,
            hsts_preload: bool = True,
            csp_enabled: bool = True,
            csp_report_only: bool = False,
            frame_options: str = "DENY",
            content_type_options: bool = True,
            xss_protection: bool = True,
            referrer_policy: str = "strict-origin-when-cross-origin"
    ):
        self.hsts_enabled = hsts_enabled
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.csp_enabled = csp_enabled
        self.csp_report_only = csp_report_only
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.xss_protection = xss_protection
        self.referrer_policy = referrer_policy


def create_security_headers_middleware(config: SecurityHeadersConfig = None) -> SecurityHeadersMiddleware:
    """Create security headers middleware with configuration"""
    if config is None:
        config = SecurityHeadersConfig()

    return SecurityHeadersMiddleware(
        app=None,  # Will be set by FastAPI
        hsts_max_age=config.hsts_max_age,
        hsts_include_subdomains=config.hsts_include_subdomains,
        hsts_preload=config.hsts_preload,
        frame_options=config.frame_options,
        referrer_policy=config.referrer_policy
    )
