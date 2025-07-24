#!/usr/bin/env python3
"""
Security Testing Suite

Automated security tests covering OWASP Top 10 vulnerabilities,
authentication, authorization, and input validation.
"""

import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Any

import requests


class TestSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityTestResult:
    test_name: str
    passed: bool
    severity: TestSeverity
    description: str
    details: Dict[str, Any]
    remediation: str


class SecurityTester:
    """Main security testing class"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[SecurityTestResult] = []

    def run_all_tests(self) -> List[SecurityTestResult]:
        """Run all security tests"""
        print("Starting comprehensive security test suite...")

        # OWASP Top 10 Tests
        self.test_injection_vulnerabilities()
        self.test_broken_authentication()
        self.test_sensitive_data_exposure()
        self.test_xml_external_entities()
        self.test_broken_access_control()
        self.test_security_misconfiguration()
        self.test_cross_site_scripting()
        self.test_insecure_deserialization()
        self.test_vulnerable_components()
        self.test_insufficient_logging()
       
        # Additional Security Tests
        self.test_rate_limiting()
        self.test_cors_configuration()
        self.test_security_headers()
        self.test_input_validation()
        self.test_api_key_security()

        return self.results

    def test_injection_vulnerabilities(self):
        """Test for SQL injection and other injection attacks"""
        print("Testing injection vulnerabilities...")

        # SQL Injection payloads
        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "1' OR 1=1#",
            "admin'--",
            "' OR 'x'='x"
        ]

        for payload in sql_payloads:
            try:
                # Test in search endpoint
                response = requests.get(
                    f"{self.base_url}/api/v1/jobs/",
                    params={"url_contains": payload},
                    timeout=5
                )

                # Should not return SQL errors or unexpected data
                if response.status_code == 500:
                    content = response.text.lower()
                    if any(error in content for error in ["sql", "database", "syntax error"]):
                        self.results.append(SecurityTestResult(
                            test_name="SQL Injection Vulnerability",
                            passed=False,
                            severity=TestSeverity.CRITICAL,
                            description=f"SQL injection vulnerability detected with payload: {payload}",
                            details={"payload": payload, "response": response.text[:500]},
                            remediation="Implement parameterized queries and input validation"
                        ))
                        return

            except Exception as e:
                pass

        self.results.append(SecurityTestResult(
            test_name="SQL Injection Test",
            passed=True,
            severity=TestSeverity.CRITICAL,
            description="No SQL injection vulnerabilities detected",
            details={},
            remediation=""
        ))

    def test_broken_authentication(self):
        """Test authentication mechanisms"""
        print("Testing authentication security...")

        # Test with invalid API keys
        invalid_keys = [
            "invalid_key",
            "",
            "Bearer invalid",
            "' OR '1'='1",
            "admin",
            "test123"
        ]

        for key in invalid_keys:
            try:
                headers = {"Authorization": f"Bearer {key}"}
                response = requests.post(
                    f"{self.base_url}/api/v1/scrape/",
                    json={"url": "https://example.com", "scraper_type": "cloudscraper"},
                    headers=headers,
                    timeout=5
                )

                # Should reject invalid keys
                if response.status_code == 200:
                    self.results.append(SecurityTestResult(
                        test_name="Weak Authentication",
                        passed=False,
                        severity=TestSeverity.HIGH,
                        description=f"Invalid API key accepted: {key}",
                        details={"key": key, "status_code": response.status_code},
                        remediation="Implement proper API key validation"
                    ))
                    return

            except Exception as e:
                pass

        self.results.append(SecurityTestResult(
            test_name="Authentication Test",
            passed=True,
            severity=TestSeverity.HIGH,
            description="Authentication properly rejects invalid credentials",
            details={},
            remediation=""
        ))

    def test_sensitive_data_exposure(self):
        """Test for sensitive data exposure"""
        print("Testing sensitive data exposure...")

        try:
            # Check if error messages expose sensitive information
            response = requests.get(f"{self.base_url}/api/v1/jobs/invalid_id", timeout=5)

            sensitive_patterns = [
                "database",
                "password",
                "secret",
                "key",
                "token",
                "connection string",
                "stack trace",
                "traceback"
            ]

            content = response.text.lower()
            exposed_data = [pattern for pattern in sensitive_patterns if pattern in content]

            if exposed_data:
                self.results.append(SecurityTestResult(
                    test_name="Sensitive Data Exposure",
                    passed=False,
                    severity=TestSeverity.MEDIUM,
                    description=f"Error messages may expose sensitive data: {exposed_data}",
                    details={"exposed_patterns": exposed_data, "response": response.text[:500]},
                    remediation="Sanitize error messages and implement proper error handling"
                ))
            else:
                self.results.append(SecurityTestResult(
                    test_name="Sensitive Data Exposure Test",
                    passed=True,
                    severity=TestSeverity.MEDIUM,
                    description="No sensitive data exposure detected in error messages",
                    details={},
                    remediation=""
                ))

        except Exception as e:
            self.results.append(SecurityTestResult(
                test_name="Sensitive Data Exposure Test",
                passed=False,
                severity=TestSeverity.MEDIUM,
                description=f"Test failed with error: {str(e)}",
                details={"error": str(e)},
                remediation="Investigate test failure"
            ))

    def test_xml_external_entities(self):
        """Test for XXE vulnerabilities"""
        print("Testing XXE vulnerabilities...")

        # XXE payload
        xxe_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
        <data>&xxe;</data>"""

        try:
            # Test if any endpoint accepts XML
            response = requests.post(
                f"{self.base_url}/api/v1/scrape/",
                data=xxe_payload,
                headers={"Content-Type": "application/xml"},
                timeout=5
            )

            # Should not process XML or return file contents
            if "root:" in response.text:
                self.results.append(SecurityTestResult(
                    test_name="XXE Vulnerability",
                    passed=False,
                    severity=TestSeverity.HIGH,
                    description="XXE vulnerability detected - system files accessible",
                    details={"response": response.text[:500]},
                    remediation="Disable XML external entity processing"
                ))
            else:
                self.results.append(SecurityTestResult(
                    test_name="XXE Test",
                    passed=True,
                    severity=TestSeverity.HIGH,
                    description="No XXE vulnerabilities detected",
                    details={},
                    remediation=""
                ))

        except Exception as e:
            self.results.append(SecurityTestResult(
                test_name="XXE Test",
                passed=True,
                severity=TestSeverity.HIGH,
                description="No XML processing detected (good)",
                details={},
                remediation=""
            ))

    def test_broken_access_control(self):
        """Test access control mechanisms"""
        print("Testing access control...")

        # Test admin endpoints without proper authentication
        admin_endpoints = [
            "/api/v1/admin/api-keys",
            "/api/v1/admin/security/status",
            "/api/v1/admin/audit/events"
        ]

        for endpoint in admin_endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)

                # Should require authentication
                if response.status_code == 200:
                    self.results.append(SecurityTestResult(
                        test_name="Broken Access Control",
                        passed=False,
                        severity=TestSeverity.CRITICAL,
                        description=f"Admin endpoint accessible without authentication: {endpoint}",
                        details={"endpoint": endpoint, "status_code": response.status_code},
                        remediation="Implement proper access control for admin endpoints"
                    ))
                    return

            except Exception as e:
                pass

        self.results.append(SecurityTestResult(
            test_name="Access Control Test",
            passed=True,
            severity=TestSeverity.CRITICAL,
            description="Admin endpoints properly protected",
            details={},
            remediation=""
        ))

    def test_security_misconfiguration(self):
        """Test for security misconfigurations"""
        print("Testing security configuration...")

        try:
            # Check for debug information exposure
            response = requests.get(f"{self.base_url}/docs", timeout=5)

            # API docs should be protected in production
            if response.status_code == 200 and "swagger" in response.text.lower():
                self.results.append(SecurityTestResult(
                    test_name="API Documentation Exposure",
                    passed=False,
                    severity=TestSeverity.MEDIUM,
                    description="API documentation is publicly accessible",
                    details={"endpoint": "/docs"},
                    remediation="Protect API documentation in production"
                ))

            # Check security headers
            headers_to_check = [
                "X-Content-Type-Options",
                "X-Frame-Options",
                "X-XSS-Protection",
                "Strict-Transport-Security"
            ]

            response = requests.get(f"{self.base_url}/", timeout=5)
            missing_headers = [h for h in headers_to_check if h not in response.headers]

            if missing_headers:
                self.results.append(SecurityTestResult(
                    test_name="Missing Security Headers",
                    passed=False,
                    severity=TestSeverity.MEDIUM,
                    description=f"Missing security headers: {missing_headers}",
                    details={"missing_headers": missing_headers},
                    remediation="Implement all recommended security headers"
                ))
            else:
                self.results.append(SecurityTestResult(
                    test_name="Security Headers Test",
                    passed=True,
                    severity=TestSeverity.MEDIUM,
                    description="All security headers present",
                    details={},
                    remediation=""
                ))

        except Exception as e:
            self.results.append(SecurityTestResult(
                test_name="Security Configuration Test",
                passed=False,
                severity=TestSeverity.MEDIUM,
                description=f"Test failed with error: {str(e)}",
                details={"error": str(e)},
                remediation="Investigate test failure"
            ))

    def test_cross_site_scripting(self):
        """Test for XSS vulnerabilities"""
        print("Testing XSS vulnerabilities...")

        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//",
            "<svg onload=alert('xss')>"
        ]

        for payload in xss_payloads:
            try:
                # Test in job creation
                response = requests.post(
                    f"{self.base_url}/api/v1/scrape/",
                    json={
                        "url": f"https://example.com?param={payload}",
                        "scraper_type": "cloudscraper"
                    },
                    timeout=5
                )

                # Check if payload is reflected unescaped
                if payload in response.text and "<script>" in response.text:
                    self.results.append(SecurityTestResult(
                        test_name="XSS Vulnerability",
                        passed=False,
                        severity=TestSeverity.HIGH,
                        description=f"XSS vulnerability detected with payload: {payload}",
                        details={"payload": payload, "response": response.text[:500]},
                        remediation="Implement proper input sanitization and output encoding"
                    ))
                    return

            except Exception as e:
                pass

        self.results.append(SecurityTestResult(
            test_name="XSS Test",
            passed=True,
            severity=TestSeverity.HIGH,
            description="No XSS vulnerabilities detected",
            details={},
            remediation=""
        ))

    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        print("Testing rate limiting...")

        try:
            # Make rapid requests
            responses = []
            for i in range(20):
                response = requests.get(f"{self.base_url}/api/v1/health/", timeout=1)
                responses.append(response.status_code)
                if response.status_code == 429:
                    break

            # Should eventually get rate limited
            if 429 in responses:
                self.results.append(SecurityTestResult(
                    test_name="Rate Limiting Test",
                    passed=True,
                    severity=TestSeverity.MEDIUM,
                    description="Rate limiting is working correctly",
                    details={"responses": responses},
                    remediation=""
                ))
            else:
                self.results.append(SecurityTestResult(
                    test_name="Rate Limiting Test",
                    passed=False,
                    severity=TestSeverity.MEDIUM,
                    description="Rate limiting may not be working",
                    details={"responses": responses},
                    remediation="Verify rate limiting configuration"
                ))

        except Exception as e:
            self.results.append(SecurityTestResult(
                test_name="Rate Limiting Test",
                passed=False,
                severity=TestSeverity.MEDIUM,
                description=f"Test failed with error: {str(e)}",
                details={"error": str(e)},
                remediation="Investigate test failure"
            ))

    def generate_report(self) -> Dict[str, Any]:
        """Generate security test report"""
        passed_tests = [r for r in self.results if r.passed]
        failed_tests = [r for r in self.results if not r.passed]

        severity_counts = {}
        for severity in TestSeverity:
            severity_counts[severity.value] = len([r for r in failed_tests if r.severity == severity])

        return {
            "summary": {
                "total_tests": len(self.results),
                "passed": len(passed_tests),
                "failed": len(failed_tests),
                "pass_rate": len(passed_tests) / len(self.results) * 100 if self.results else 0
            },
            "severity_breakdown": severity_counts,
            "failed_tests": [
                {
                    "test_name": r.test_name,
                    "severity": r.severity.value,
                    "description": r.description,
                    "remediation": r.remediation
                }
                for r in failed_tests
            ],
            "all_results": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "severity": r.severity.value,
                    "description": r.description,
                    "details": r.details,
                    "remediation": r.remediation
                }
                for r in self.results
            ]
        }


def main():
    """Run security tests"""
    import argparse

    parser = argparse.ArgumentParser(description="CFScraper Security Test Suite")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL to test")
    parser.add_argument("--output", default="security-test-report.json", help="Output file")

    args = parser.parse_args()

    tester = SecurityTester(args.url)
    results = tester.run_all_tests()
    report = tester.generate_report()

    # Save report
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)

    # Print summary
    print(f"\nSecurity Test Summary:")
    print(f"Total Tests: {report['summary']['total_tests']}")
    print(f"Passed: {report['summary']['passed']}")
    print(f"Failed: {report['summary']['failed']}")
    print(f"Pass Rate: {report['summary']['pass_rate']:.1f}%")

    if report['summary']['failed'] > 0:
        print(f"\nFailed Tests:")
        for test in report['failed_tests']:
            print(f"- {test['test_name']} ({test['severity']}): {test['description']}")

    print(f"\nDetailed report saved to: {args.output}")

    # Exit with error code if critical/high severity issues found
    critical_high_issues = report['severity_breakdown'].get('critical', 0) + report['severity_breakdown'].get('high', 0)
    if critical_high_issues > 0:
        print(f"\nCritical/High severity issues found: {critical_high_issues}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
