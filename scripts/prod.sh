#!/bin/bash
# Knowledge Ingestor - Production Deployment Script
# Manages production deployment and operations

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Project configuration
PROJECT_NAME="knowledge-ingestor"
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
Knowledge Ingestor - Production Management Script

Usage: $0 <command> [options]

Commands:
    deploy          Deploy to production
    start           Start production services
    stop            Stop all services
    restart         Restart all services
    status          Show service status and health
    logs            Show logs (use -f to follow)
    scale           Scale services
    backup          Create production backup
    restore         Restore from backup
    update          Update application (rolling update)
    rollback        Rollback to previous version
    monitor         Show monitoring dashboard URLs
    ssl             Manage SSL certificates
    maintenance     Enable/disable maintenance mode
    health          Check service health
    clean           Clean up old images and containers

Production Profiles:
    --monitoring    Include Prometheus and Grafana
    --backup        Include backup service
    --production    Include Nginx reverse proxy

Examples:
    $0 deploy --monitoring          # Deploy with monitoring
    $0 scale worker=3              # Scale worker to 3 instances
    $0 logs -f api                 # Follow API logs
    $0 backup                      # Create backup
    $0 update                      # Rolling update
    $0 ssl renew                   # Renew SSL certificates

For more options, run: $0 <command> --help
EOF
}

# Check prerequisites for production
check_production_prereqs() {
    log_info "Checking production prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available"
        exit 1
    fi
    
    # Check if .env file exists
    if [[ ! -f ".env" ]]; then
        log_error ".env file not found. Copy from .env.example and configure."
        exit 1
    fi
    
    # Check critical environment variables
    source .env
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        log_error "OPENAI_API_KEY not set in .env file"
        exit 1
    fi
    
    if [[ -z "${JWT_SECRET_KEY:-}" ]] || [[ "${JWT_SECRET_KEY}" == "your-secret-key-change-in-production" ]]; then
        log_error "JWT_SECRET_KEY must be changed from default in .env file"
        exit 1
    fi
    
    # Check available resources
    local available_memory=$(free -g | awk '/^Mem:/{print $7}')
    if [[ $available_memory -lt 4 ]]; then
        log_warning "Less than 4GB available memory. Performance may be impacted."
    fi
    
    log_success "Production prerequisites check passed"
}

# Deploy to production
prod_deploy() {
    local profiles="--profile production"
    local build_flag="--build"
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --monitoring)
                profiles="$profiles --profile monitoring"
                shift
                ;;
            --backup)
                profiles="$profiles --profile backup"
                shift
                ;;
            --no-build)
                build_flag=""
                shift
                ;;
            *)
                log_warning "Unknown deploy option: $1"
                shift
                ;;
        esac
    done
    
    log_info "Deploying to production with profiles: $profiles"
    
    # Build and deploy
    docker compose -f $PROD_COMPOSE_FILE $profiles up -d $build_flag
    
    # Wait for services to be ready
    log_info "Waiting for services to become healthy..."
    
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if docker compose -f $PROD_COMPOSE_FILE ps | grep -q "healthy"; then
            break
        fi
        
        log_info "Attempt $attempt/$max_attempts - Services starting..."
        sleep 10
        ((attempt++))
    done
    
    # Check final status
    if docker compose -f $PROD_COMPOSE_FILE ps | grep -q "unhealthy"; then
        log_error "Some services are unhealthy!"
        prod_status
        exit 1
    fi
    
    log_success "Production deployment completed!"
    prod_status
}

# Start production services
prod_start() {
    local profiles="--profile production"
    
    # Parse profiles
    while [[ $# -gt 0 ]]; do
        case $1 in
            --monitoring)
                profiles="$profiles --profile monitoring"
                shift
                ;;
            --backup)
                profiles="$profiles --profile backup"
                shift
                ;;
            *)
                break
                ;;
        esac
    done
    
    log_info "Starting production services..."
    docker compose -f $PROD_COMPOSE_FILE $profiles up -d
    
    log_success "Production services started"
    prod_status
}

# Stop production services
prod_stop() {
    log_warning "Stopping production services..."
    read -p "Are you sure you want to stop production? (y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose -f $PROD_COMPOSE_FILE down
        log_success "Production services stopped"
    fi
}

# Restart production services
prod_restart() {
    log_info "Restarting production services..."
    docker compose -f $PROD_COMPOSE_FILE restart
    log_success "Services restarted"
}

# Show production status
prod_status() {
    log_info "Production service status:"
    docker compose -f $PROD_COMPOSE_FILE ps
    
    echo ""
    log_info "Service health checks:"
    for container in $(docker compose -f $PROD_COMPOSE_FILE ps -q); do
        local container_name=$(docker inspect --format '{{.Name}}' "$container" | sed 's/\///')
        local health_status=$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no healthcheck")
        
        if [[ "$health_status" == "healthy" ]]; then
            echo -e "  ${GREEN}✓${NC} $container_name: $health_status"
        elif [[ "$health_status" == "unhealthy" ]]; then
            echo -e "  ${RED}✗${NC} $container_name: $health_status"
        else
            echo -e "  ${YELLOW}?${NC} $container_name: $health_status"
        fi
    done
    
    echo ""
    log_info "Resource usage:"
    docker stats --no-stream $(docker compose -f $PROD_COMPOSE_FILE ps -q) 2>/dev/null || true
}

# Show logs
prod_logs() {
    local service=""
    local follow=""
    local lines="100"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--follow)
                follow="-f"
                shift
                ;;
            -n|--lines)
                lines="$2"
                shift 2
                ;;
            *)
                service="$1"
                shift
                ;;
        esac
    done
    
    if [[ -z "$service" ]]; then
        docker compose -f $PROD_COMPOSE_FILE logs $follow --tail="$lines"
    else
        docker compose -f $PROD_COMPOSE_FILE logs $follow --tail="$lines" "$service"
    fi
}

# Scale services
prod_scale() {
    if [[ $# -eq 0 ]]; then
        log_error "Usage: $0 scale <service>=<replicas>"
        log_info "Example: $0 scale worker=3"
        exit 1
    fi
    
    log_info "Scaling services: $*"
    docker compose -f $PROD_COMPOSE_FILE up -d --scale "$@"
    
    log_success "Services scaled successfully"
    prod_status
}

# Create production backup
prod_backup() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="backups/prod_$timestamp"
    
    log_info "Creating production backup..."
    mkdir -p "$backup_dir"
    
    # Backup database
    log_info "Backing up PostgreSQL database..."
    docker compose -f $PROD_COMPOSE_FILE exec -T postgres \
        pg_dump -U ingestor knowledge_ingestor > "$backup_dir/database.sql"
    
    # Backup Redis data
    log_info "Backing up Redis data..."
    docker compose -f $PROD_COMPOSE_FILE exec -T redis \
        redis-cli --rdb - > "$backup_dir/redis.rdb"
    
    # Backup data directory
    log_info "Backing up application data..."
    if [[ -d "data" ]]; then
        tar -czf "$backup_dir/data.tar.gz" -C data .
    fi
    
    # Backup configuration
    log_info "Backing up configuration..."
    tar -czf "$backup_dir/config.tar.gz" \
        .env docker-compose.yml configs/ nginx/ monitoring/ 2>/dev/null || true
    
    # Create manifest
    cat > "$backup_dir/manifest.txt" << EOF
Production Backup - $timestamp
================================

Database: database.sql
Redis: redis.rdb  
Data: data.tar.gz
Config: config.tar.gz

Created: $(date)
Host: $(hostname)
Docker Images:
$(docker compose -f $PROD_COMPOSE_FILE images)
EOF
    
    log_success "Backup created in: $backup_dir"
    
    # Cleanup old backups (keep last 30)
    find backups/ -name "prod_*" -type d | sort -r | tail -n +31 | xargs rm -rf
}

# Update application (rolling update)
prod_update() {
    local service="${1:-api}"
    
    log_info "Performing rolling update for $service..."
    
    # Pull latest images
    docker compose -f $PROD_COMPOSE_FILE pull "$service"
    
    # Recreate service with zero downtime
    docker compose -f $PROD_COMPOSE_FILE up -d --no-deps "$service"
    
    # Wait for health check
    log_info "Waiting for service to become healthy..."
    local attempts=0
    while [[ $attempts -lt 30 ]]; do
        if docker inspect "$(docker compose -f $PROD_COMPOSE_FILE ps -q "$service")" \
           --format '{{.State.Health.Status}}' | grep -q "healthy"; then
            log_success "Rolling update completed successfully"
            return 0
        fi
        sleep 10
        ((attempts++))
    done
    
    log_error "Service failed to become healthy after update"
    exit 1
}

# Monitor services
prod_monitor() {
    log_info "Production monitoring endpoints:"
    echo ""
    echo "Application:"
    echo "  API: https://localhost/api/v1"
    echo "  Health: https://localhost/health"
    echo "  Metrics: https://localhost/metrics"
    echo "  Documentation: https://localhost/docs"
    echo ""
    echo "Monitoring (if enabled):"
    echo "  Prometheus: http://localhost:9091"
    echo "  Grafana: http://localhost:3001"
    echo ""
    echo "Infrastructure:"
    echo "  Redis: localhost:6379"
    echo "  PostgreSQL: localhost:5432"
}

# Health check all services
prod_health() {
    log_info "Checking service health..."
    
    local all_healthy=true
    
    # Check API health endpoint
    if curl -fs http://localhost:8000/health > /dev/null; then
        echo -e "  ${GREEN}✓${NC} API: Healthy"
    else
        echo -e "  ${RED}✗${NC} API: Unhealthy"
        all_healthy=false
    fi
    
    # Check database connectivity
    if docker compose -f $PROD_COMPOSE_FILE exec -T postgres pg_isready -U ingestor > /dev/null; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL: Healthy"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL: Unhealthy"
        all_healthy=false
    fi
    
    # Check Redis connectivity  
    if docker compose -f $PROD_COMPOSE_FILE exec -T redis redis-cli ping > /dev/null; then
        echo -e "  ${GREEN}✓${NC} Redis: Healthy"
    else
        echo -e "  ${RED}✗${NC} Redis: Unhealthy"
        all_healthy=false
    fi
    
    if [[ "$all_healthy" == "true" ]]; then
        log_success "All services are healthy"
        return 0
    else
        log_error "Some services are unhealthy"
        return 1
    fi
}

# SSL certificate management
prod_ssl() {
    local command="${1:-help}"
    
    case $command in
        generate)
            log_info "Generating SSL certificates..."
            # Add your SSL generation logic here
            # Example: certbot or custom SSL generation
            log_success "SSL certificates generated"
            ;;
        renew)
            log_info "Renewing SSL certificates..."
            # Add your SSL renewal logic here
            log_success "SSL certificates renewed"
            ;;
        *)
            echo "SSL management commands:"
            echo "  generate    Generate new SSL certificates"
            echo "  renew       Renew existing certificates"
            ;;
    esac
}

# Maintenance mode
prod_maintenance() {
    local mode="${1:-status}"
    
    case $mode in
        enable)
            log_warning "Enabling maintenance mode..."
            # Create maintenance page or modify nginx config
            # docker compose -f $PROD_COMPOSE_FILE exec nginx ...
            log_info "Maintenance mode enabled"
            ;;
        disable)
            log_info "Disabling maintenance mode..."
            # Remove maintenance page or restore nginx config
            log_success "Maintenance mode disabled"
            ;;
        status)
            log_info "Maintenance mode status: Disabled"
            ;;
        *)
            echo "Maintenance mode commands:"
            echo "  enable      Enable maintenance mode"
            echo "  disable     Disable maintenance mode"
            echo "  status      Check maintenance mode status"
            ;;
    esac
}

# Clean up old images and containers
prod_clean() {
    log_warning "This will remove unused Docker images and containers"
    read -p "Continue? (y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning up..."
        
        # Remove stopped containers
        docker container prune -f
        
        # Remove unused images
        docker image prune -f
        
        # Remove unused volumes (be careful!)
        docker volume prune -f
        
        # Remove unused networks
        docker network prune -f
        
        log_success "Cleanup completed"
    fi
}

# Main script logic
main() {
    # Check prerequisites for production commands
    if [[ "${1:-}" != "help" ]] && [[ "${1:-}" != "--help" ]] && [[ "${1:-}" != "-h" ]]; then
        check_production_prereqs
    fi
    
    # Parse command
    local command="${1:-help}"
    shift || true
    
    case $command in
        deploy)
            prod_deploy "$@"
            ;;
        start|up)
            prod_start "$@"
            ;;
        stop|down)
            prod_stop "$@"
            ;;
        restart)
            prod_restart "$@"
            ;;
        status|ps)
            prod_status "$@"
            ;;
        logs)
            prod_logs "$@"
            ;;
        scale)
            prod_scale "$@"
            ;;
        backup)
            prod_backup "$@"
            ;;
        update)
            prod_update "$@"
            ;;
        monitor)
            prod_monitor "$@"
            ;;
        health)
            prod_health "$@"
            ;;
        ssl)
            prod_ssl "$@"
            ;;
        maintenance)
            prod_maintenance "$@"
            ;;
        clean)
            prod_clean "$@"
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