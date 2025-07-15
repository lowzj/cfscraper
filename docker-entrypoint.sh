#!/bin/bash
set -e

# CFScraper Docker Entrypoint Script
# This script handles initialization and security setup for the container

# Function to log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if we're running as root (security check)
check_user() {
    if [ "$(id -u)" = "0" ]; then
        log "ERROR: Container is running as root user. This is a security risk."
        exit 1
    fi
    log "Running as user: $(whoami) (UID: $(id -u))"
}

# Function to validate environment variables
validate_environment() {
    log "Validating environment configuration..."
    
    # Check if required environment variables are set
    if [ -z "$DATABASE_URL" ]; then
        log "WARNING: DATABASE_URL not set, using default SQLite"
    fi
    
    if [ -z "$REDIS_URL" ] && [ "$USE_IN_MEMORY_QUEUE" != "true" ]; then
        log "WARNING: REDIS_URL not set and not using in-memory queue"
    fi
    
    log "Environment validation completed"
}

# Function to wait for database to be ready
wait_for_db() {
    if [[ "$DATABASE_URL" == postgresql* ]]; then
        log "Waiting for PostgreSQL to be ready..."
        
        # Extract host and port from DATABASE_URL
        # Format: postgresql://user:pass@host:port/db
        DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\):.*/\1/p')
        DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
        
        if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
            while ! nc -z "$DB_HOST" "$DB_PORT"; do
                log "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
                sleep 2
            done
            log "PostgreSQL is ready!"
        fi
    fi
}

# Function to wait for Redis to be ready
wait_for_redis() {
    if [ "$USE_IN_MEMORY_QUEUE" != "true" ] && [ -n "$REDIS_URL" ]; then
        log "Waiting for Redis to be ready..."
        
        # Extract host and port from REDIS_URL
        # Format: redis://host:port
        REDIS_HOST=$(echo "$REDIS_URL" | sed -n 's/redis:\/\/\([^:]*\):.*/\1/p')
        REDIS_PORT=$(echo "$REDIS_URL" | sed -n 's/redis:\/\/[^:]*:\([0-9]*\).*/\1/p')
        
        if [ -n "$REDIS_HOST" ] && [ -n "$REDIS_PORT" ]; then
            while ! nc -z "$REDIS_HOST" "$REDIS_PORT"; do
                log "Waiting for Redis at $REDIS_HOST:$REDIS_PORT..."
                sleep 2
            done
            log "Redis is ready!"
        fi
    fi
}

# Function to run database migrations
run_migrations() {
    if [ "$RUN_MIGRATIONS" = "true" ]; then
        log "Running database migrations..."
        alembic upgrade head
        log "Database migrations completed"
    fi
}

# Function to set up Chrome for Selenium (security hardening)
setup_chrome() {
    log "Setting up Chrome security configuration..."
    
    # Create Chrome user data directory with proper permissions
    mkdir -p /app/chrome-user-data
    chmod 755 /app/chrome-user-data
    
    # Set Chrome flags for security and headless operation
    export CHROME_FLAGS="--no-sandbox --disable-dev-shm-usage --disable-gpu --headless --remote-debugging-port=9222 --user-data-dir=/app/chrome-user-data"
    
    log "Chrome security configuration completed"
}

# Function to create necessary directories
setup_directories() {
    log "Setting up application directories..."
    
    # Ensure log and data directories exist with proper permissions
    mkdir -p /app/logs /app/data /app/temp
    chmod 755 /app/logs /app/data /app/temp
    
    log "Application directories setup completed"
}

# Main execution
main() {
    log "Starting CFScraper container initialization..."
    
    # Security checks
    check_user
    
    # Environment validation
    validate_environment
    
    # Setup directories
    setup_directories
    
    # Setup Chrome
    setup_chrome
    
    # Wait for dependencies
    wait_for_db
    wait_for_redis
    
    # Run migrations if requested
    run_migrations
    
    log "Container initialization completed successfully"
    log "Starting application: $@"
    
    # Execute the main command
    exec "$@"
}

# Run main function with all arguments
main "$@"
