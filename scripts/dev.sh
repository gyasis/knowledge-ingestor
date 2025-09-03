#!/bin/bash
# Knowledge Ingestor - Development Workflow Script
# Simplified commands for common development tasks

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Project configuration
PROJECT_NAME="knowledge-ingestor"
DEV_COMPOSE_FILE="docker-compose.dev.yml"
PROD_COMPOSE_FILE="docker-compose.yml"

# Logging functions
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

# Show usage information
show_usage() {
    cat << EOF
Knowledge Ingestor - Development Script

Usage: $0 <command> [options]

Commands:
    setup           Run initial setup
    start           Start development services
    stop            Stop all services  
    restart         Restart all services
    logs            Show logs (use -f to follow)
    shell           Open shell in API container
    test            Run tests
    lint            Run linting
    build           Build development images
    clean           Clean up containers and images
    status          Show service status
    db              Database management commands
    backup          Create backup
    restore         Restore from backup

Examples:
    $0 start                    # Start all development services
    $0 logs -f api-dev          # Follow logs for API service
    $0 shell                    # Open shell in main container
    $0 test                     # Run all tests
    $0 db migrate              # Run database migrations
    $0 backup                  # Create backup

For more options, run: $0 <command> --help
EOF
}

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available"
        exit 1
    fi
}

# Setup development environment
dev_setup() {
    log_info "Setting up development environment..."
    ./scripts/setup.sh
}

# Start development services
dev_start() {
    log_info "Starting development services..."
    
    # Parse options
    local profiles="--profile tools"  # Default to include dev tools
    local services=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-tools)
                profiles=""
                shift
                ;;
            --worker)
                profiles="$profiles --profile worker"
                shift
                ;;
            --jupyter)
                profiles="$profiles --profile jupyter"
                shift
                ;;
            --test)
                profiles="$profiles --profile test"
                shift
                ;;
            --*)
                log_warning "Unknown option: $1"
                shift
                ;;
            *)
                services="$services $1"
                shift
                ;;
        esac
    done
    
    # Start services
    docker compose -f $DEV_COMPOSE_FILE $profiles up -d $services
    
    # Wait for health checks
    log_info "Waiting for services to become healthy..."
    sleep 5
    
    # Show status
    docker compose -f $DEV_COMPOSE_FILE ps
    
    log_success "Development environment started!"
    echo ""
    echo "Available services:"
    echo "  API: http://localhost:8000"
    echo "  API Docs: http://localhost:8000/docs"
    echo "  Adminer: http://localhost:8080"
    echo "  Redis Commander: http://localhost:8081"
    if [[ "$profiles" == *"jupyter"* ]]; then
        echo "  Jupyter: http://localhost:8888"
    fi
}

# Stop services
dev_stop() {
    log_info "Stopping development services..."
    docker compose -f $DEV_COMPOSE_FILE down
    log_success "Services stopped"
}

# Restart services
dev_restart() {
    log_info "Restarting development services..."
    dev_stop
    sleep 2
    dev_start "$@"
}

# Show logs
dev_logs() {
    local service=""
    local follow=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--follow)
                follow="-f"
                shift
                ;;
            *)
                service="$1"
                shift
                ;;
        esac
    done
    
    if [[ -z "$service" ]]; then
        docker compose -f $DEV_COMPOSE_FILE logs $follow
    else
        docker compose -f $DEV_COMPOSE_FILE logs $follow "$service"
    fi
}

# Open shell in container
dev_shell() {
    local service="${1:-api-dev}"
    local shell_cmd="${2:-bash}"
    
    log_info "Opening shell in $service container..."
    
    if docker compose -f $DEV_COMPOSE_FILE ps --services | grep -q "^$service$"; then
        docker compose -f $DEV_COMPOSE_FILE exec "$service" "$shell_cmd"
    else
        log_error "Service $service not found or not running"
        docker compose -f $DEV_COMPOSE_FILE ps
        exit 1
    fi
}

# Run tests
dev_test() {
    local test_args="$*"
    
    log_info "Running tests..."
    
    # Start test runner
    docker compose -f $DEV_COMPOSE_FILE --profile test run --rm test-runner \
        python -m pytest tests/ -v --cov=src/knowledge_ingestor $test_args
}

# Run linting
dev_lint() {
    log_info "Running linting..."
    
    docker compose -f $DEV_COMPOSE_FILE exec api-dev bash -c "
        echo 'Running Black...' &&
        black --check src/ tests/ &&
        echo 'Running isort...' &&
        isort --check src/ tests/ &&
        echo 'Running flake8...' &&
        flake8 src/ tests/ &&
        echo 'Running mypy...' &&
        mypy src/
    "
    
    log_success "Linting completed"
}

# Build development images
dev_build() {
    log_info "Building development images..."
    
    docker compose -f $DEV_COMPOSE_FILE build --no-cache
    
    log_success "Images built successfully"
}

# Clean up
dev_clean() {
    log_warning "This will remove all containers, images, and volumes for this project"
    read -p "Are you sure? (y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning up..."
        
        # Stop and remove containers
        docker compose -f $DEV_COMPOSE_FILE down -v --remove-orphans
        
        # Remove images
        docker images "${PROJECT_NAME}*" -q | xargs -r docker rmi -f
        
        # Remove dangling images
        docker image prune -f
        
        # Remove unused volumes
        docker volume prune -f
        
        log_success "Cleanup completed"
    fi
}

# Show status
dev_status() {
    log_info "Service status:"
    docker compose -f $DEV_COMPOSE_FILE ps
    
    echo ""
    log_info "Container resource usage:"
    docker stats --no-stream $(docker compose -f $DEV_COMPOSE_FILE ps -q) 2>/dev/null || true
    
    echo ""
    log_info "Volume usage:"
    docker system df
}

# Database management
dev_db() {
    local command="${1:-help}"
    
    case $command in
        shell|psql)
            log_info "Opening PostgreSQL shell..."
            docker compose -f $DEV_COMPOSE_FILE exec postgres-dev \
                psql -U ingestor -d knowledge_ingestor_dev
            ;;
        migrate)
            log_info "Running database migrations..."
            docker compose -f $DEV_COMPOSE_FILE exec api-dev \
                python -m knowledge_ingestor.cli db migrate
            ;;
        reset)
            log_warning "This will reset the development database"
            read -p "Are you sure? (y/N): " -r
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                docker compose -f $DEV_COMPOSE_FILE stop postgres-dev
                docker volume rm knowledge-ingestor_postgres_dev_data 2>/dev/null || true
                docker compose -f $DEV_COMPOSE_FILE up -d postgres-dev
                log_success "Database reset completed"
            fi
            ;;
        backup)
            local backup_file="backups/dev_backup_$(date +%Y%m%d_%H%M%S).sql"
            mkdir -p backups
            log_info "Creating database backup: $backup_file"
            docker compose -f $DEV_COMPOSE_FILE exec -T postgres-dev \
                pg_dump -U ingestor knowledge_ingestor_dev > "$backup_file"
            log_success "Backup created: $backup_file"
            ;;
        *)
            cat << EOF
Database management commands:

    shell       Open PostgreSQL shell
    migrate     Run database migrations  
    reset       Reset database (WARNING: destroys data)
    backup      Create database backup

Usage: $0 db <command>
EOF
            ;;
    esac
}

# Create backup
dev_backup() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="backups/dev_$timestamp"
    
    log_info "Creating development backup..."
    mkdir -p "$backup_dir"
    
    # Backup database
    docker compose -f $DEV_COMPOSE_FILE exec -T postgres-dev \
        pg_dump -U ingestor knowledge_ingestor_dev > "$backup_dir/database.sql"
    
    # Backup data directory
    if [[ -d "data" ]]; then
        tar -czf "$backup_dir/data.tar.gz" -C data .
    fi
    
    # Backup logs
    if [[ -d "logs" ]]; then
        tar -czf "$backup_dir/logs.tar.gz" -C logs .
    fi
    
    log_success "Backup created in: $backup_dir"
}

# Restore from backup
dev_restore() {
    local backup_dir="$1"
    
    if [[ -z "$backup_dir" ]] || [[ ! -d "$backup_dir" ]]; then
        log_error "Please specify a valid backup directory"
        echo "Available backups:"
        ls -la backups/ 2>/dev/null || echo "No backups found"
        exit 1
    fi
    
    log_warning "This will restore from backup and may overwrite current data"
    read -p "Continue? (y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Restoring from: $backup_dir"
        
        # Restore database
        if [[ -f "$backup_dir/database.sql" ]]; then
            docker compose -f $DEV_COMPOSE_FILE exec -T postgres-dev \
                psql -U ingestor -d knowledge_ingestor_dev < "$backup_dir/database.sql"
            log_success "Database restored"
        fi
        
        # Restore data
        if [[ -f "$backup_dir/data.tar.gz" ]]; then
            tar -xzf "$backup_dir/data.tar.gz" -C data/
            log_success "Data restored"
        fi
        
        log_success "Restore completed"
    fi
}

# Main script logic
main() {
    # Check prerequisites
    check_docker
    
    # Parse command
    local command="${1:-help}"
    shift || true
    
    case $command in
        setup)
            dev_setup "$@"
            ;;
        start|up)
            dev_start "$@"
            ;;
        stop|down)
            dev_stop "$@"
            ;;
        restart)
            dev_restart "$@"
            ;;
        logs)
            dev_logs "$@"
            ;;
        shell|exec)
            dev_shell "$@"
            ;;
        test)
            dev_test "$@"
            ;;
        lint)
            dev_lint "$@"
            ;;
        build)
            dev_build "$@"
            ;;
        clean)
            dev_clean "$@"
            ;;
        status|ps)
            dev_status "$@"
            ;;
        db)
            dev_db "$@"
            ;;
        backup)
            dev_backup "$@"
            ;;
        restore)
            dev_restore "$@"
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            log_error "Unknown command: $command"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"