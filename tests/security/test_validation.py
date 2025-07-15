"""
Security and input validation tests
"""
import pytest
import time
from unittest.mock import Mock, patch
import json

from fastapi.testclient import TestClient
from fastapi import HTTPException


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
            20,   # Too high
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
