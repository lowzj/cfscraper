#!/bin/bash
set -e

# CFScraper Docker Build Script
# This script builds optimized Docker images for different environments

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Function to check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi
    
    print_success "Docker is available"
}

# Function to build Docker image
build_image() {
    local tag=$1
    local dockerfile=${2:-Dockerfile}
    local context=${3:-.}
    
    print_status "Building Docker image: $tag"
    print_status "Using Dockerfile: $dockerfile"
    print_status "Build context: $context"
    
    # Record start time
    start_time=$(date +%s)
    
    # Build the image with optimizations
    docker build \
        --tag "$tag" \
        --file "$dockerfile" \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --progress=plain \
        "$context"
    
    # Record end time and calculate duration
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    print_success "Image built successfully in ${duration}s"
    
    # Check image size
    image_size=$(docker images --format "table {{.Size}}" "$tag" | tail -n 1)
    print_status "Image size: $image_size"
    
    # Warn if image is larger than 500MB
    size_mb=$(docker images --format "{{.Size}}" "$tag" | sed 's/MB//' | sed 's/GB/*1000/' | bc 2>/dev/null || echo "0")
    if [ "${size_mb%.*}" -gt 500 ] 2>/dev/null; then
        print_warning "Image size exceeds 500MB target"
    fi
    
    return 0
}

# Function to analyze image layers
analyze_image() {
    local tag=$1
    
    print_status "Analyzing image layers for: $tag"
    docker history "$tag" --format "table {{.CreatedBy}}\t{{.Size}}" | head -20
}

# Function to run security scan (if available)
security_scan() {
    local tag=$1
    
    if command -v docker scan &> /dev/null; then
        print_status "Running security scan for: $tag"
        docker scan "$tag" || print_warning "Security scan failed or found vulnerabilities"
    else
        print_warning "Docker scan not available. Consider installing Docker Desktop or Snyk CLI"
    fi
}

# Function to test image
test_image() {
    local tag=$1
    
    print_status "Testing image: $tag"
    
    # Test that the image can start
    container_id=$(docker run -d --rm -p 8001:8000 "$tag")
    
    # Wait for container to start
    sleep 10
    
    # Test health endpoint
    if curl -f http://localhost:8001/health &> /dev/null; then
        print_success "Health check passed"
    else
        print_error "Health check failed"
    fi
    
    # Stop container
    docker stop "$container_id" &> /dev/null || true
}

# Main function
main() {
    local environment=${1:-dev}
    local tag_prefix="cfscraper"
    local tag="${tag_prefix}:${environment}"
    
    print_status "Starting Docker build for environment: $environment"
    
    # Check prerequisites
    check_docker
    
    # Build image
    case $environment in
        "dev"|"development")
            build_image "$tag"
            ;;
        "prod"|"production")
            tag="${tag_prefix}:latest"
            build_image "$tag"
            ;;
        *)
            print_error "Unknown environment: $environment"
            print_status "Usage: $0 [dev|prod]"
            exit 1
            ;;
    esac
    
    # Analyze image
    analyze_image "$tag"
    
    # Run security scan
    security_scan "$tag"
    
    # Test image
    test_image "$tag"
    
    print_success "Docker build completed successfully!"
    print_status "Image tag: $tag"
    print_status "To run: docker run -p 8000:8000 $tag"
}

# Run main function with all arguments
main "$@"
