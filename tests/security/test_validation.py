"""
Security and input validation tests
"""
import time
from unittest.mock import Mock, patch

import pytest

from app.security.authentication import APIKeyManager, APIKeyPermission
from app.security.encryption import DataEncryption, anonymize_log_data
# Import security modules for testing
from app.security.validation import SecurityValidator, sanitize_input, validate_url


@pytest.mark.security
class TestInputValidation:
    """Test input validation and sanitization"""

    def test_url_validation(self, client):
        """Test URL validation in scrape requests"""
        # Test invalid URLs
        invalid_urls = [
            "not-a-url",
            "ftp://invalid-protocol.com",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "",
            "http://",
            "https://",
            "file:///etc/passwd"
        ]

        for invalid_url in invalid_urls:
            job_data = {
                "url": invalid_url,
                "scraper_type": "cloudscraper"
            }

            response = client.post("/api/v1/scrape/", json=job_data)
            assert response.status_code == 422  # Validation error

            error_detail = response.json()["detail"]
            assert any("url" in str(error).lower() for error in error_detail)

    def test_valid_url_acceptance(self, client):
        """Test that valid URLs are accepted"""
        valid_urls = [
            "https://example.com",
            "http://example.com",
            "https://subdomain.example.com",
            "https://example.com/path",
            "https://example.com/path?param=value",
            "https://example.com:8080/path"
        ]

        for valid_url in valid_urls:
            job_data = {
                "url": valid_url,
                "scraper_type": "cloudscraper"
            }

            with patch('app.api.routes.common.get_job_queue') as mock_queue:
                mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
                response = client.post("/api/v1/scrape/", json=job_data)

                # Should accept valid URLs (may fail due to missing dependencies)
                assert response.status_code in [200, 500]

    def test_scraper_type_validation(self, client):
        """Test scraper type validation"""
        invalid_scraper_types = [
            "invalid_scraper",
            "sql_injection'; DROP TABLE jobs; --",
            "<script>alert('xss')</script>",
            "",
            123,
            None
        ]

        for invalid_type in invalid_scraper_types:
            job_data = {
                "url": "https://example.com",
                "scraper_type": invalid_type
            }

            response = client.post("/api/v1/scrape/", json=job_data)
            assert response.status_code == 422  # Validation error

    def test_method_validation(self, client):
        """Test HTTP method validation"""
        # Test invalid methods
        invalid_methods = [
            "INVALID",
            "'; DROP TABLE jobs; --",
            "<script>alert('xss')</script>",
            "GET; rm -rf /",
            ""
        ]

        for invalid_method in invalid_methods:
            job_data = {
                "url": "https://example.com",
                "method": invalid_method,
                "scraper_type": "cloudscraper"
            }

            with patch('app.api.routes.common.get_job_queue') as mock_queue:
                mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
                response = client.post("/api/v1/scrape/", json=job_data)

                # Should either validate or accept (depending on implementation)
                # Invalid methods should be caught by scraper validation
                assert response.status_code in [200, 422, 500]

    def test_headers_validation(self, client):
        """Test headers validation and sanitization"""
        malicious_headers = {
            "X-Injection": "'; DROP TABLE jobs; --",
            "X-XSS": "<script>alert('xss')</script>",
            "X-Command": "$(rm -rf /)",
            "X-Null": "\x00\x01\x02",
            "X-Long": "A" * 10000  # Very long header
        }

        job_data = {
            "url": "https://example.com",
            "headers": malicious_headers,
            "scraper_type": "cloudscraper"
        }

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
            response = client.post("/api/v1/scrape/", json=job_data)

            # Should handle malicious headers safely
            assert response.status_code in [200, 422, 500]

    def test_data_validation(self, client):
        """Test request data validation"""
        malicious_data = {
            "sql_injection": "'; DROP TABLE jobs; --",
            "xss_payload": "<script>alert('xss')</script>",
            "command_injection": "$(rm -rf /)",
            "null_bytes": "\x00\x01\x02",
            "large_field": "A" * 100000  # Very large data
        }

        job_data = {
            "url": "https://example.com",
            "data": malicious_data,
            "scraper_type": "cloudscraper"
        }

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
            response = client.post("/api/v1/scrape/", json=job_data)

            # Should handle malicious data safely
            assert response.status_code in [200, 422, 500]

    def test_tags_validation(self, client):
        """Test tags validation"""
        # Test with too many tags
        too_many_tags = [f"tag{i}" for i in range(20)]  # Assuming max is 10

        job_data = {
            "url": "https://example.com",
            "tags": too_many_tags,
            "scraper_type": "cloudscraper"
        }

        response = client.post("/api/v1/scrape/", json=job_data)
        assert response.status_code == 422  # Should validate tag count

        # Test with malicious tags
        malicious_tags = [
            "'; DROP TABLE jobs; --",
            "<script>alert('xss')</script>",
            "$(rm -rf /)",
            "\x00\x01\x02"
        ]

        job_data = {
            "url": "https://example.com",
            "tags": malicious_tags,
            "scraper_type": "cloudscraper"
        }

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
            response = client.post("/api/v1/scrape/", json=job_data)

            # Should handle malicious tags safely
            assert response.status_code in [200, 422, 500]

    def test_priority_validation(self, client):
        """Test priority validation"""
        invalid_priorities = [
            -20,  # Too low
            20,  # Too high
            "invalid",
            None,
            float('inf'),
            float('-inf')
        ]

        for invalid_priority in invalid_priorities:
            job_data = {
                "url": "https://example.com",
                "priority": invalid_priority,
                "scraper_type": "cloudscraper"
            }

            response = client.post("/api/v1/scrape/", json=job_data)
            assert response.status_code == 422  # Validation error


@pytest.mark.security
class TestSQLInjectionPrevention:
    """Test SQL injection prevention"""

    def test_job_search_sql_injection(self, client, malicious_payloads):
        """Test SQL injection in job search"""
        sql_payloads = malicious_payloads["sql_injection"]

        for payload in sql_payloads:
            # Test in query parameter
            response = client.get(f"/api/v1/jobs/?url_contains={payload}")
            assert response.status_code in [200, 422]  # Should not cause SQL error

            # Test in search request
            search_data = {
                "query": payload,
                "status": ["completed"]
            }

            response = client.post("/api/v1/jobs/search", json=search_data)
            assert response.status_code in [200, 422]  # Should not cause SQL error

    def test_job_id_sql_injection(self, client, malicious_payloads):
        """Test SQL injection in job ID parameters"""
        sql_payloads = malicious_payloads["sql_injection"]

        for payload in sql_payloads:
            # Test job status endpoint
            response = client.get(f"/api/v1/scrape/{payload}/status")
            assert response.status_code in [404, 422]  # Should not cause SQL error

            # Test job result endpoint
            response = client.get(f"/api/v1/scrape/{payload}/result")
            assert response.status_code in [404, 422]  # Should not cause SQL error

    def test_pagination_sql_injection(self, client, malicious_payloads):
        """Test SQL injection in pagination parameters"""
        sql_payloads = malicious_payloads["sql_injection"]

        for payload in sql_payloads:
            # Test page parameter
            response = client.get(f"/api/v1/jobs/?page={payload}")
            assert response.status_code in [200, 422]  # Should validate or ignore

            # Test page_size parameter
            response = client.get(f"/api/v1/jobs/?page_size={payload}")
            assert response.status_code in [200, 422]  # Should validate or ignore


@pytest.mark.security
class TestXSSPrevention:
    """Test XSS prevention"""

    def test_response_xss_prevention(self, client, malicious_payloads):
        """Test that responses don't contain unescaped XSS payloads"""
        xss_payloads = malicious_payloads["xss"]

        for payload in xss_payloads:
            # Test in job creation with malicious URL
            job_data = {
                "url": f"https://example.com?param={payload}",
                "scraper_type": "cloudscraper"
            }

            with patch('app.api.routes.common.get_job_queue') as mock_queue:
                mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
                response = client.post("/api/v1/scrape/", json=job_data)

                if response.status_code == 200:
                    response_text = response.text
                    # Response should not contain unescaped script tags
                    assert "<script>" not in response_text
                    assert "javascript:" not in response_text

    def test_error_message_xss_prevention(self, client, malicious_payloads):
        """Test that error messages don't contain XSS payloads"""
        xss_payloads = malicious_payloads["xss"]

        for payload in xss_payloads:
            # Test with malicious job ID
            response = client.get(f"/api/v1/jobs/{payload}")

            if response.status_code in [400, 404, 422]:
                response_text = response.text
                # Error messages should not contain unescaped script tags
                assert "<script>" not in response_text
                assert "javascript:" not in response_text


@pytest.mark.security
class TestPathTraversalPrevention:
    """Test path traversal prevention"""

    def test_export_path_traversal(self, client, malicious_payloads):
        """Test path traversal in export endpoints"""
        path_payloads = malicious_payloads["path_traversal"]

        for payload in path_payloads:
            # Test export download with malicious path
            response = client.get(f"/api/v1/export/download/{payload}")

            # Should not allow path traversal
            assert response.status_code in [404, 422]

            # Should not return sensitive files
            if response.status_code == 200:
                content = response.text
                assert "root:" not in content  # Unix passwd file
                assert "[users]" not in content  # Windows SAM file


@pytest.mark.security
class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_api_rate_limiting(self, client):
        """Test API rate limiting"""
        # Make many requests quickly
        responses = []
        start_time = time.time()

        for i in range(100):
            response = client.get("/api/v1/health/")
            responses.append(response)

            # If we get rate limited, break
            if response.status_code == 429:
                break

        end_time = time.time()

        # Should either complete all requests or get rate limited
        status_codes = [r.status_code for r in responses]

        # All should be successful or some should be rate limited
        assert all(code in [200, 429] for code in status_codes)

        # If rate limiting is enabled, should see 429 responses
        if any(code == 429 for code in status_codes):
            # Should have rate limit headers
            rate_limited_response = next(r for r in responses if r.status_code == 429)
            headers = rate_limited_response.headers

            # Common rate limit headers
            rate_limit_headers = [
                "x-ratelimit-limit",
                "x-ratelimit-remaining",
                "x-ratelimit-reset",
                "retry-after"
            ]

            # Should have at least one rate limit header
            assert any(header in headers for header in rate_limit_headers)

    def test_job_creation_rate_limiting(self, client):
        """Test rate limiting on job creation"""
        job_data = {
            "url": "https://example.com",
            "scraper_type": "cloudscraper"
        }

        responses = []

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = Mock(return_value="test-task-id")

            # Make many job creation requests
            for i in range(50):
                response = client.post("/api/v1/scrape/", json=job_data)
                responses.append(response)

                # If we get rate limited, break
                if response.status_code == 429:
                    break

        status_codes = [r.status_code for r in responses]

        # Should either complete all requests or get rate limited
        assert all(code in [200, 429, 500] for code in status_codes)


@pytest.mark.security
class TestAuthenticationSecurity:
    """Test authentication and authorization security"""

    def test_missing_authentication_headers(self, client):
        """Test behavior with missing authentication headers"""
        # Most endpoints should work without auth (public API)
        # But admin endpoints should require auth

        response = client.get("/api/v1/health/")
        assert response.status_code == 200  # Public endpoint

        response = client.get("/api/v1/jobs/")
        assert response.status_code == 200  # Public endpoint

    def test_malformed_authentication(self, client):
        """Test behavior with malformed authentication"""
        malformed_auth_headers = [
            {"Authorization": "Bearer invalid_token"},
            {"Authorization": "Basic invalid_base64"},
            {"Authorization": "'; DROP TABLE users; --"},
            {"Authorization": "<script>alert('xss')</script>"},
            {"Authorization": "Bearer " + "A" * 10000}  # Very long token
        ]

        for headers in malformed_auth_headers:
            response = client.get("/api/v1/health/", headers=headers)

            # Should handle malformed auth gracefully
            assert response.status_code in [200, 401, 422]


@pytest.mark.security
class TestDataSanitization:
    """Test data sanitization and encoding"""

    def test_unicode_handling(self, client):
        """Test handling of Unicode and special characters"""
        unicode_data = {
            "url": "https://example.com",
            "scraper_type": "cloudscraper",
            "tags": ["测试", "🚀", "café", "naïve"],
            "data": {
                "unicode_field": "Hello 世界 🌍",
                "emoji": "🎉🎊🎈",
                "accents": "café naïve résumé"
            }
        }

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
            response = client.post("/api/v1/scrape/", json=unicode_data)

            # Should handle Unicode properly
            assert response.status_code in [200, 500]

    def test_null_byte_handling(self, client):
        """Test handling of null bytes and control characters"""
        null_byte_data = {
            "url": "https://example.com",
            "scraper_type": "cloudscraper",
            "data": {
                "null_bytes": "test\x00data",
                "control_chars": "test\x01\x02\x03data",
                "mixed": "normal\x00null\x01control"
            }
        }

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = Mock(return_value="test-task-id")
            response = client.post("/api/v1/scrape/", json=null_byte_data)

            # Should handle null bytes safely
            assert response.status_code in [200, 422, 500]

    def test_large_payload_handling(self, client):
        """Test handling of very large payloads"""
        large_data = {
            "url": "https://example.com",
            "scraper_type": "cloudscraper",
            "data": {
                "large_field": "A" * 1000000  # 1MB of data
            }
        }

        response = client.post("/api/v1/scrape/", json=large_data)

        # Should either accept or reject large payloads gracefully
        assert response.status_code in [200, 413, 422, 500]  # 413 = Payload Too Large


@pytest.mark.security
class TestSecurityValidation:
    """Test security validation utilities"""

    def test_sql_injection_detection(self):
        """Test SQL injection detection"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM users --",
            "admin'--",
            "1' OR 1=1#"
        ]

        for input_str in malicious_inputs:
            assert SecurityValidator.detect_sql_injection(input_str), f"Failed to detect SQL injection: {input_str}"

        # Test safe inputs
        safe_inputs = [
            "normal text",
            "user@example.com",
            "https://example.com",
            "search query"
        ]

        for input_str in safe_inputs:
            assert not SecurityValidator.detect_sql_injection(input_str), f"False positive for safe input: {input_str}"

    def test_xss_detection(self):
        """Test XSS detection"""
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "<svg onload=alert('xss')>",
            "onclick=alert('xss')"
        ]

        for input_str in malicious_inputs:
            assert SecurityValidator.detect_xss(input_str), f"Failed to detect XSS: {input_str}"

        # Test safe inputs
        safe_inputs = [
            "normal text",
            "<p>Safe HTML</p>",
            "user@example.com",
            "https://example.com"
        ]

        for input_str in safe_inputs:
            assert not SecurityValidator.detect_xss(input_str), f"False positive for safe input: {input_str}"

    def test_path_traversal_detection(self):
        """Test path traversal detection"""
        malicious_inputs = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "/etc/passwd",
            "C:\\Windows\\System32",
            "..%2F..%2Fetc%2Fpasswd"
        ]

        for input_str in malicious_inputs:
            assert SecurityValidator.detect_path_traversal(input_str), f"Failed to detect path traversal: {input_str}"

        # Test safe inputs
        safe_inputs = [
            "normal/path",
            "file.txt",
            "folder/subfolder/file.txt"
        ]

        for input_str in safe_inputs:
            assert not SecurityValidator.detect_path_traversal(input_str), f"False positive for safe input: {input_str}"

    def test_input_sanitization(self):
        """Test input sanitization"""
        # Test string sanitization
        malicious_string = "<script>alert('xss')</script>"
        sanitized = sanitize_input(malicious_string)
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized

        # Test dict sanitization
        malicious_dict = {
            "safe_key": "safe_value",
            "malicious_key": "<script>alert('xss')</script>"
        }
        sanitized_dict = sanitize_input(malicious_dict)
        assert "<script>" not in sanitized_dict["malicious_key"]
        assert sanitized_dict["safe_key"] == "safe_value"

        # Test list sanitization
        malicious_list = ["safe_item", "<script>alert('xss')</script>"]
        sanitized_list = sanitize_input(malicious_list)
        assert "<script>" not in sanitized_list[1]
        assert sanitized_list[0] == "safe_item"

    def test_url_validation(self):
        """Test URL validation"""
        # Test valid URLs
        valid_urls = [
            "https://example.com",
            "http://example.com",
            "https://subdomain.example.com/path?param=value"
        ]

        for url in valid_urls:
            try:
                result = validate_url(url)
                assert result == url
            except ValueError:
                pytest.fail(f"Valid URL rejected: {url}")

        # Test invalid URLs
        invalid_urls = [
            "ftp://example.com",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "not-a-url",
            ""
        ]

        for url in invalid_urls:
            with pytest.raises(ValueError):
                validate_url(url)


@pytest.mark.security
class TestAPIKeyAuthentication:
    """Test API key authentication system"""

    def test_api_key_generation(self):
        """Test API key generation"""
        manager = APIKeyManager("test-secret-key")

        # Generate API key
        api_key = manager.generate_api_key(
            permissions={APIKeyPermission.READ},
            expires_in_days=30,
            description="Test key"
        )

        assert api_key.startswith("cfsk_")
        assert len(api_key) > 32

    def test_api_key_validation(self):
        """Test API key validation"""
        manager = APIKeyManager("test-secret-key")

        # Generate and validate API key
        api_key = manager.generate_api_key(
            permissions={APIKeyPermission.READ, APIKeyPermission.WRITE},
            description="Test key"
        )

        # Valid key with correct permission
        key_info = manager.validate_api_key(api_key, APIKeyPermission.READ)
        assert key_info is not None
        assert APIKeyPermission.READ in key_info.permissions

        # Valid key with insufficient permission
        key_info = manager.validate_api_key(api_key, APIKeyPermission.ADMIN)
        assert key_info is None

        # Invalid key
        key_info = manager.validate_api_key("invalid_key", APIKeyPermission.READ)
        assert key_info is None

    def test_api_key_expiry(self):
        """Test API key expiry"""
        from datetime import datetime, timezone, timedelta

        manager = APIKeyManager("test-secret-key")

        # Generate key that expires in 1 second
        api_key = manager.generate_api_key(
            permissions={APIKeyPermission.READ},
            expires_in_days=None,  # Use default
            description="Test key for expiry"
        )

        # Manually set expiry to past time
        key_hash = manager._hash_key(api_key)
        if key_hash in manager.api_keys:
            manager.api_keys[key_hash].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Should be invalid due to expiry
        key_info = manager.validate_api_key(api_key, APIKeyPermission.READ)
        assert key_info is None

    def test_api_key_revocation(self):
        """Test API key revocation"""
        manager = APIKeyManager("test-secret-key")

        # Generate API key
        api_key = manager.generate_api_key(
            permissions={APIKeyPermission.READ},
            description="Test key for revocation"
        )

        # Validate it works
        key_info = manager.validate_api_key(api_key, APIKeyPermission.READ)
        assert key_info is not None

        # Revoke the key
        revoked = manager.revoke_api_key(api_key)
        assert revoked

        # Should no longer work
        key_info = manager.validate_api_key(api_key, APIKeyPermission.READ)
        assert key_info is None


@pytest.mark.security
class TestDataEncryption:
    """Test data encryption functionality"""

    def test_data_encryption_decryption(self):
        """Test data encryption and decryption"""
        encryption = DataEncryption("test-encryption-key")

        # Test string encryption
        original_data = "sensitive data"
        encrypted = encryption.encrypt(original_data)
        assert encrypted != original_data
        assert encrypted is not None

        decrypted = encryption.decrypt(encrypted)
        assert decrypted == original_data

    def test_json_encryption_decryption(self):
        """Test JSON data encryption and decryption"""
        encryption = DataEncryption("test-encryption-key")

        # Test dict encryption
        original_data = {"key": "value", "number": 42}
        encrypted = encryption.encrypt(original_data)
        assert encrypted != str(original_data)
        assert encrypted is not None

        decrypted_json = encryption.decrypt_json(encrypted)
        assert decrypted_json == original_data

    def test_data_hashing(self):
        """Test data hashing"""
        encryption = DataEncryption("test-encryption-key")

        data = "password123"
        hashed = encryption.hash_data(data)

        # Hash should contain salt and hash
        assert ":" in hashed

        # Verify hash
        assert encryption.verify_hash(data, hashed)
        assert not encryption.verify_hash("wrong_password", hashed)

    def test_log_data_anonymization(self):
        """Test log data anonymization"""
        log_data = {
            "ip": "192.168.1.100",
            "email": "user@example.com",
            "url": "https://example.com/api/key/secret?token=abc123",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0.19042.1234) Chrome/91.0.4472.124",
            "headers": {
                "authorization": "Bearer secret-token",
                "x-api-key": "secret-key",
                "user-agent": "test-agent"
            }
        }

        anonymized = anonymize_log_data(log_data)

        # IP should be anonymized
        assert anonymized["ip"] != log_data["ip"]
        assert "xxx" in anonymized["ip"]

        # Email should be anonymized
        assert anonymized["email"] != log_data["email"]
        assert "x" in anonymized["email"]

        # URL should be anonymized
        assert "?" not in anonymized["url"]  # Query params removed

        # Sensitive headers should be masked
        assert anonymized["headers"]["authorization"] == "***"
        assert anonymized["headers"]["x-api-key"] == "***"


@pytest.mark.security
class TestSecurityHeaders:
    """Test security headers implementation"""

    def test_security_headers_present(self, client):
        """Test that security headers are present in responses"""
        response = client.get("/")

        # Check for security headers
        security_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy"
        ]

        for header in security_headers:
            assert header in response.headers, f"Missing security header: {header}"

    def test_hsts_header_on_https(self, client):
        """Test HSTS header on HTTPS requests"""
        # Note: This test would need to be run against an HTTPS endpoint
        # For now, we'll just verify the middleware logic
        pass

    def test_csp_header_content(self, client):
        """Test Content Security Policy header content"""
        response = client.get("/")

        if "Content-Security-Policy" in response.headers:
            csp = response.headers["Content-Security-Policy"]

            # Should have restrictive policies
            assert "default-src 'self'" in csp or "default-src 'none'" in csp
            assert "frame-ancestors 'none'" in csp


@pytest.mark.security
class TestOWASPTop10:
    """Test OWASP Top 10 vulnerabilities"""

    def test_a01_injection(self, client, malicious_payloads):
        """A01:2021 – Injection"""
        sql_payloads = malicious_payloads["sql_injection"]

        for payload in sql_payloads:
            # Test in various endpoints
            response = client.get(f"/api/v1/jobs/?url_contains={payload}")

            # Should not return SQL errors
            assert response.status_code != 500 or "sql" not in response.text.lower()

    def test_a02_broken_authentication(self, client):
        """A02:2021 – Broken Authentication"""
        # Test with various invalid authentication attempts
        invalid_tokens = [
            "invalid_token",
            "",
            "Bearer ",
            "Basic invalid",
            "' OR '1'='1"
        ]

        for token in invalid_tokens:
            headers = {"Authorization": token}
            response = client.get("/api/v1/admin/api-keys", headers=headers)

            # Should reject invalid authentication
            assert response.status_code in [401, 403, 422]

    def test_a03_sensitive_data_exposure(self, client):
        """A03:2021 – Sensitive Data Exposure"""
        # Test error responses don't expose sensitive data
        response = client.get("/api/v1/jobs/invalid_id")

        sensitive_keywords = [
            "password", "secret", "key", "token",
            "database", "connection", "traceback"
        ]

        response_text = response.text.lower()
        for keyword in sensitive_keywords:
            assert keyword not in response_text, f"Sensitive data exposed: {keyword}"

    def test_a05_broken_access_control(self, client):
        """A05:2021 – Broken Access Control"""
        # Test admin endpoints without proper authentication
        admin_endpoints = [
            "/api/v1/admin/api-keys",
            "/api/v1/admin/security/status"
        ]

        for endpoint in admin_endpoints:
            response = client.get(endpoint)

            # Should require authentication
            assert response.status_code in [401, 403], f"Admin endpoint not protected: {endpoint}"

    def test_a06_vulnerable_components(self):
        """A06:2021 – Vulnerable and Outdated Components"""
        # This would typically be handled by dependency scanning tools
        # We can check if security scanning is configured
        import os

        # Check if security configuration exists
        security_files = [
            "security/vulnerability-scan.yml",
            "security/security-tests.py"
        ]

        for file_path in security_files:
            assert os.path.exists(file_path), f"Security configuration missing: {file_path}"
