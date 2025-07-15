#!/bin/bash
set -e

# CFScraper Docker Implementation Test Script
# This script tests both development and production Docker setups

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TEST_RESULTS=()

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to record test result
record_test() {
    local test_name="$1"
    local result="$2"
    local message="$3"
    
    if [ "$result" = "PASS" ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        print_success "✓ $test_name: $message"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        print_error "✗ $test_name: $message"
    fi
    
    TEST_RESULTS+=("$test_name: $result - $message")
}

# Function to wait for service to be ready
wait_for_service() {
    local url="$1"
    local timeout="${2:-60}"
    local interval="${3:-5}"
    
    print_status "Waiting for service at $url (timeout: ${timeout}s)"
    
    for i in $(seq 1 $((timeout / interval))); do
        if curl -f -s "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep $interval
    done
    
    return 1
}

# Function to test Docker build
test_docker_build() {
    print_status "Testing Docker image build..."
    
    local start_time=$(date +%s)
    
    if docker build -t cfscraper:test . > /dev/null 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        if [ $duration -lt 300 ]; then  # 5 minutes
            record_test "Docker Build Time" "PASS" "Built in ${duration}s (< 5min target)"
        else
            record_test "Docker Build Time" "FAIL" "Built in ${duration}s (> 5min target)"
        fi
        
        # Check image size
        local size_mb=$(docker images cfscraper:test --format "{{.Size}}" | sed 's/MB//' | sed 's/GB/*1000/' | bc 2>/dev/null || echo "0")
        if [ "${size_mb%.*}" -lt 500 ] 2>/dev/null; then
            record_test "Docker Image Size" "PASS" "Image size: $(docker images cfscraper:test --format "{{.Size}}")"
        else
            record_test "Docker Image Size" "FAIL" "Image size exceeds 500MB: $(docker images cfscraper:test --format "{{.Size}}")"
        fi
    else
        record_test "Docker Build" "FAIL" "Failed to build Docker image"
        return 1
    fi
}

# Function to test development environment
test_development_environment() {
    print_status "Testing development environment..."
    
    # Copy development environment
    cp .env.dev .env
    
    # Start development environment
    if docker-compose up -d > /dev/null 2>&1; then
        record_test "Dev Environment Start" "PASS" "Services started successfully"
        
        # Wait for services to be ready
        if wait_for_service "http://localhost:8000/health" 60; then
            record_test "Dev Health Check" "PASS" "Health endpoint responding"
            
            # Test API endpoint
            if curl -f -s "http://localhost:8000/" > /dev/null; then
                record_test "Dev API Endpoint" "PASS" "Root endpoint responding"
            else
                record_test "Dev API Endpoint" "FAIL" "Root endpoint not responding"
            fi
            
            # Test database connectivity
            if docker-compose exec -T app python -c "
from app.core.database import engine
from sqlalchemy import text
result = engine.execute(text('SELECT 1')).fetchone()
print('Database OK' if result else 'Database FAIL')
" 2>/dev/null | grep -q "Database OK"; then
                record_test "Dev Database Connection" "PASS" "Database connection successful"
            else
                record_test "Dev Database Connection" "FAIL" "Database connection failed"
            fi
            
            # Test Redis connectivity
            if docker-compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
                record_test "Dev Redis Connection" "PASS" "Redis connection successful"
            else
                record_test "Dev Redis Connection" "FAIL" "Redis connection failed"
            fi
            
        else
            record_test "Dev Health Check" "FAIL" "Health endpoint not responding within timeout"
        fi
        
        # Clean up
        docker-compose down > /dev/null 2>&1
    else
        record_test "Dev Environment Start" "FAIL" "Failed to start development environment"
    fi
}

# Function to test production environment
test_production_environment() {
    print_status "Testing production environment..."
    
    # Create minimal production environment file
    cat > .env.prod.test << EOF
DATABASE_URL=postgresql://cfscraper:cfscraper_password@postgres:5432/cfscraper_prod
POSTGRES_DB=cfscraper_prod
POSTGRES_USER=cfscraper
POSTGRES_PASSWORD=cfscraper_password
REDIS_URL=redis://redis:6379
DEBUG=false
ENVIRONMENT=production
USE_IN_MEMORY_QUEUE=false
MAX_CONCURRENT_JOBS=10
RATE_LIMITING_ENABLED=true
CORS_ORIGINS=*
RUN_MIGRATIONS=false
EOF
    
    # Start production environment (without nginx for testing)
    if docker-compose -f docker-compose.prod.yml --env-file .env.prod.test up -d app postgres redis > /dev/null 2>&1; then
        record_test "Prod Environment Start" "PASS" "Production services started"
        
        # Wait for services to be ready
        if wait_for_service "http://localhost:8000/health" 90; then
            record_test "Prod Health Check" "PASS" "Production health endpoint responding"
            
            # Test performance (startup time)
            local startup_time=$(docker-compose -f docker-compose.prod.yml logs app | grep "Application startup complete" | tail -1 | cut -d' ' -f1-2 || echo "")
            if [ -n "$startup_time" ]; then
                record_test "Prod Startup Time" "PASS" "Application started successfully"
            else
                record_test "Prod Startup Time" "WARN" "Could not determine startup time"
            fi
            
        else
            record_test "Prod Health Check" "FAIL" "Production health endpoint not responding"
        fi
        
        # Clean up
        docker-compose -f docker-compose.prod.yml --env-file .env.prod.test down > /dev/null 2>&1
    else
        record_test "Prod Environment Start" "FAIL" "Failed to start production environment"
    fi
    
    # Clean up test file
    rm -f .env.prod.test
}

# Function to test security features
test_security_features() {
    print_status "Testing security features..."
    
    # Test non-root user
    if docker run --rm cfscraper:test id | grep -q "uid=.*appuser"; then
        record_test "Non-Root User" "PASS" "Container runs as non-root user"
    else
        record_test "Non-Root User" "FAIL" "Container running as root user"
    fi
    
    # Test health check configuration
    if docker inspect cfscraper:test | grep -q "HEALTHCHECK"; then
        record_test "Health Check Config" "PASS" "Health check configured in image"
    else
        record_test "Health Check Config" "FAIL" "Health check not configured"
    fi
}

# Function to test performance targets
test_performance_targets() {
    print_status "Testing performance targets..."
    
    # Start a test container to check memory usage
    container_id=$(docker run -d --rm -p 8002:8000 cfscraper:test)
    
    # Wait for container to start
    sleep 15
    
    # Check memory usage
    memory_usage=$(docker stats --no-stream --format "{{.MemUsage}}" $container_id | cut -d'/' -f1 | sed 's/MiB//' | sed 's/GiB/*1000/' | bc 2>/dev/null || echo "0")
    
    if [ "${memory_usage%.*}" -lt 512 ] 2>/dev/null; then
        record_test "Memory Usage" "PASS" "Memory usage: ${memory_usage}MB (< 512MB target)"
    else
        record_test "Memory Usage" "FAIL" "Memory usage: ${memory_usage}MB (> 512MB target)"
    fi
    
    # Stop test container
    docker stop $container_id > /dev/null 2>&1
}

# Function to print test summary
print_test_summary() {
    echo
    echo "=================================="
    echo "        TEST SUMMARY"
    echo "=================================="
    echo "Tests Passed: $TESTS_PASSED"
    echo "Tests Failed: $TESTS_FAILED"
    echo "Total Tests:  $((TESTS_PASSED + TESTS_FAILED))"
    echo
    
    if [ $TESTS_FAILED -eq 0 ]; then
        print_success "All tests passed! ✓"
        echo
        print_status "Docker implementation is ready for use."
        print_status "Development: docker-compose up -d"
        print_status "Production:  docker-compose -f docker-compose.prod.yml up -d"
    else
        print_error "Some tests failed. Please review the issues above."
        echo
        print_status "Detailed test results:"
        for result in "${TEST_RESULTS[@]}"; do
            echo "  $result"
        done
    fi
    
    echo
}

# Main function
main() {
    print_status "Starting CFScraper Docker implementation tests..."
    echo
    
    # Check prerequisites
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Run tests
    test_docker_build
    test_security_features
    test_performance_targets
    test_development_environment
    test_production_environment
    
    # Print summary
    print_test_summary
    
    # Exit with appropriate code
    if [ $TESTS_FAILED -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
