#!/bin/bash
# Knowledge Ingestor - Initial Setup Script
# Prepares the environment and creates necessary directories and files

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root is not recommended for development"
        read -p "Continue anyway? (y/N): " -r
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available. Please install Docker Compose."
        exit 1
    fi
    
    # Check available disk space (need at least 10GB)
    available_space=$(df . | awk 'NR==2 {print $4}')
    required_space=10485760  # 10GB in KB
    
    if [[ $available_space -lt $required_space ]]; then
        log_warning "Less than 10GB disk space available. Docker images may consume significant space."
    fi
    
    log_success "System requirements check passed"
}

# Create directory structure
create_directories() {
    log_info "Creating directory structure..."
    
    directories=(
        "data"
        "logs"
        "backups"
        "volumes/redis"
        "volumes/postgres" 
        "volumes/prometheus"
        "volumes/grafana"
        "nginx/ssl"
        "nginx/logs"
        "db/init"
        "monitoring/prometheus/rules"
        "notebooks"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log_info "Created directory: $dir"
        fi
    done
    
    log_success "Directory structure created"
}

# Set proper permissions
set_permissions() {
    log_info "Setting proper permissions..."
    
    # Make logs writable
    chmod 755 logs/
    
    # Make data directory writable
    chmod 755 data/
    
    # Make backup directory writable
    chmod 755 backups/
    
    # Make volumes writable
    chmod -R 755 volumes/
    
    # Make scripts executable
    if [[ -d "scripts" ]]; then
        find scripts/ -name "*.sh" -type f -exec chmod +x {} \;
    fi
    
    log_success "Permissions set"
}

# Create environment files
create_env_files() {
    log_info "Setting up environment files..."
    
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
            log_success "Created .env from .env.example"
            log_warning "Please edit .env with your actual configuration values"
        else
            log_error ".env.example not found"
            return 1
        fi
    else
        log_info ".env already exists"
    fi
    
    # Create development environment if it doesn't exist
    if [[ ! -f ".env.dev" ]] && [[ -f ".env.development" ]]; then
        cp .env.development .env.dev
        log_success "Created .env.dev from .env.development"
    fi
}

# Generate SSL certificates for development
generate_dev_ssl() {
    log_info "Generating development SSL certificates..."
    
    ssl_dir="nginx/ssl"
    cert_file="$ssl_dir/cert.pem"
    key_file="$ssl_dir/key.pem"
    
    if [[ ! -f "$cert_file" ]] || [[ ! -f "$key_file" ]]; then
        # Generate self-signed certificate for development
        openssl req -x509 -newkey rsa:2048 -keyout "$key_file" -out "$cert_file" \
            -days 365 -nodes -subj "/C=US/ST=Dev/L=Dev/O=Knowledge-Ingestor/CN=localhost" \
            2>/dev/null || {
            log_warning "OpenSSL not available. SSL certificates not generated."
            log_info "You can add certificates later or use HTTP only for development."
        }
        
        if [[ -f "$cert_file" ]]; then
            log_success "Development SSL certificates generated"
        fi
    else
        log_info "SSL certificates already exist"
    fi
}

# Initialize database
init_database() {
    log_info "Creating database initialization scripts..."
    
    init_sql="db/init/01_init.sql"
    if [[ ! -f "$init_sql" ]]; then
        cat > "$init_sql" << 'EOF'
-- Knowledge Ingestor Database Initialization
-- Creates necessary database structure for PostgreSQL

-- Create users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create API keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    key_name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- Create documents metadata table
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    url TEXT,
    content_type VARCHAR(100),
    file_size INTEGER,
    checksum VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create processing jobs table
CREATE TABLE IF NOT EXISTS processing_jobs (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_document_id ON processing_jobs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);

-- Create default admin user (password: admin123 - change in production!)
INSERT INTO users (username, email, hashed_password, is_admin) 
VALUES ('admin', 'admin@knowledge-ingestor.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj3Q7L3Q7L3Q', true)
ON CONFLICT (username) DO NOTHING;

COMMIT;
EOF
        log_success "Database initialization script created"
    else
        log_info "Database initialization script already exists"
    fi
}

# Create Redis configuration
create_redis_config() {
    log_info "Creating Redis configuration..."
    
    redis_conf="configs/redis.conf"
    if [[ ! -f "$redis_conf" ]]; then
        mkdir -p configs
        cat > "$redis_conf" << 'EOF'
# Knowledge Ingestor Redis Configuration
# Optimized for development and production use

# Network settings
bind 0.0.0.0
port 6379
timeout 300
keepalive 60

# Memory settings
maxmemory 256mb
maxmemory-policy allkeys-lru

# Persistence settings
save 900 1
save 300 10
save 60 10000
rdbcompression yes
dbfilename dump.rdb

# Security settings
# requirepass your-redis-password-here

# Logging
loglevel notice
syslog-enabled yes
syslog-ident redis

# Performance settings
databases 16
hash-max-ziplist-entries 512
hash-max-ziplist-value 64
list-max-ziplist-size -2
zset-max-ziplist-entries 128
zset-max-ziplist-value 64
EOF
        log_success "Redis configuration created"
    else
        log_info "Redis configuration already exists"
    fi
}

# Verify Docker setup
verify_docker_setup() {
    log_info "Verifying Docker setup..."
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    # Test Docker Compose
    if docker compose config -q; then
        log_success "Docker Compose configuration is valid"
    else
        log_error "Docker Compose configuration has errors"
        exit 1
    fi
}

# Main setup function
main() {
    echo ""
    log_info "Knowledge Ingestor - Initial Setup"
    echo "=================================="
    echo ""
    
    check_root
    check_requirements
    create_directories
    set_permissions
    create_env_files
    generate_dev_ssl
    init_database
    create_redis_config
    verify_docker_setup
    
    echo ""
    log_success "Setup completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Edit .env file with your API keys and configuration"
    echo "2. Run 'docker compose up -d' to start all services"
    echo "3. Run 'docker compose -f docker-compose.dev.yml up' for development"
    echo "4. Access the API at http://localhost:8000"
    echo ""
    log_info "For more information, see the README.md file"
}

# Run main function
main "$@"