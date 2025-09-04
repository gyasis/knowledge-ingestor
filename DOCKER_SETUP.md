# Knowledge Ingestor - Docker Setup Guide

This guide provides comprehensive instructions for running the Knowledge Ingestor using Docker with multi-service orchestration.

## Quick Start

### Prerequisites

- Docker Engine 20.10+ with Docker Compose
- At least 4GB available RAM
- At least 10GB available disk space
- OpenAI API key

### One-Command Setup

```bash
# 1. Clone and navigate to the project
cd knowledge-ingestor

# 2. Run initial setup
./scripts/setup.sh

# 3. Configure your environment
cp .env.example .env
# Edit .env with your API keys and configuration

# 4. Start development environment
./scripts/dev.sh start
```

That's it! The API will be available at `http://localhost:8000`.

## Architecture Overview

The Docker setup includes multiple configurations for different use cases:

### Multi-Stage Dockerfile
- **Builder stage**: Compiles dependencies and builds the application wheel
- **Production stage**: Minimal runtime image with security best practices
- **Development stage**: Full development environment with hot reloading
- **Worker stage**: Background task processing with Redis integration

### Service Architecture
- **API Service**: FastAPI application with authentication and monitoring
- **Worker Service**: Background processing for document ingestion
- **Redis**: Caching and job queue management
- **PostgreSQL**: User management and metadata storage
- **Nginx**: Reverse proxy with SSL termination (production)
- **Prometheus**: Metrics collection (optional)
- **Grafana**: Monitoring dashboards (optional)

## Configuration Options

### Environment Profiles

#### Development (`docker-compose.dev.yml`)
```bash
# Start development with all tools
./scripts/dev.sh start --worker --jupyter --test

# Available services:
# - API with hot reloading: http://localhost:8000
# - PostgreSQL Admin: http://localhost:8080
# - Redis Commander: http://localhost:8081
# - Jupyter Lab: http://localhost:8888
```

#### Production (`docker-compose.yml`)
```bash
# Deploy production with monitoring
./scripts/prod.sh deploy --monitoring --backup

# Available services:
# - Load-balanced API behind Nginx
# - Prometheus metrics: http://localhost:9091
# - Grafana dashboards: http://localhost:3001
```

### Service Profiles

Use Docker Compose profiles to start only needed services:

```bash
# Core services only
docker compose up -d

# With monitoring stack
docker compose --profile monitoring up -d

# Production with reverse proxy
docker compose --profile production up -d

# Development with tools
docker compose -f docker-compose.dev.yml --profile tools up -d
```

## Development Workflow

### Common Development Commands

```bash
# Start development environment
./scripts/dev.sh start

# View logs (follow)
./scripts/dev.sh logs -f api-dev

# Open shell in container
./scripts/dev.sh shell

# Run tests
./scripts/dev.sh test

# Run linting
./scripts/dev.sh lint

# Database operations
./scripts/dev.sh db shell        # PostgreSQL shell
./scripts/dev.sh db migrate      # Run migrations
./scripts/dev.sh db backup       # Create backup

# Service management
./scripts/dev.sh status          # Show service status
./scripts/dev.sh restart         # Restart all services
./scripts/dev.sh clean           # Clean up containers and images
```

### Hot Reloading

The development setup includes automatic code reloading:

- Source code is mounted as volumes
- FastAPI auto-reloads on file changes
- Worker processes restart on code updates
- Configuration changes trigger service restarts

### Debugging

Debug support is built-in for development:

```bash
# Debug port is exposed on 5678
# Connect your IDE debugger to localhost:5678

# VS Code launch.json example:
{
    "name": "Docker Debug",
    "type": "python",
    "request": "attach",
    "connect": {
        "host": "localhost",
        "port": 5678
    },
    "pathMappings": [
        {
            "localRoot": "${workspaceFolder}/src",
            "remoteRoot": "/app/src"
        }
    ]
}
```

## Production Deployment

### Security Considerations

1. **Environment Variables**: Never use default secrets in production
   ```bash
   # Required changes in .env:
   JWT_SECRET_KEY=your-secure-random-key-here
   POSTGRES_PASSWORD=your-secure-password
   API_KEY_SALT=your-unique-salt
   ```

2. **SSL Certificates**: Configure proper SSL certificates
   ```bash
   # Place certificates in nginx/ssl/
   nginx/ssl/cert.pem
   nginx/ssl/key.pem
   ```

3. **Network Security**: Configure firewall rules
   ```bash
   # Only expose necessary ports:
   # - 80/443 for HTTP/HTTPS
   # - 22 for SSH (if needed)
   ```

### Production Deployment

```bash
# 1. Prepare environment
./scripts/setup.sh
cp .env.example .env
# Edit .env with production values

# 2. Deploy with monitoring
./scripts/prod.sh deploy --monitoring --backup

# 3. Verify deployment
./scripts/prod.sh health
./scripts/prod.sh status

# 4. Monitor logs
./scripts/prod.sh logs -f
```

### Scaling Services

```bash
# Scale worker instances
./scripts/prod.sh scale worker=5

# Scale multiple services
./scripts/prod.sh scale api=2 worker=4
```

### Rolling Updates

```bash
# Update API service with zero downtime
./scripts/prod.sh update api

# Update all services
./scripts/prod.sh update
```

## Monitoring and Observability

### Built-in Monitoring

- **Health Checks**: All services include health endpoints
- **Prometheus Metrics**: Application and infrastructure metrics
- **Grafana Dashboards**: Pre-configured monitoring dashboards
- **Structured Logging**: JSON logs with correlation IDs

### Accessing Monitoring

```bash
# Start with monitoring enabled
docker compose --profile monitoring up -d

# Access monitoring services:
# - Prometheus: http://localhost:9091
# - Grafana: http://localhost:3001 (admin:admin123)
# - API Metrics: http://localhost:8000/metrics
```

### Log Management

```bash
# View service logs
./scripts/prod.sh logs api          # API logs
./scripts/prod.sh logs worker       # Worker logs
./scripts/prod.sh logs -f nginx     # Follow nginx logs

# Aggregate logs
docker compose logs -f --tail=100
```

## Backup and Disaster Recovery

### Automated Backups

```bash
# Create backup
./scripts/prod.sh backup

# Backups include:
# - PostgreSQL database dump
# - Redis data snapshot  
# - Application data files
# - Configuration files
```

### Disaster Recovery

```bash
# List available backups
ls -la backups/

# Restore from backup
./scripts/prod.sh restore backups/prod_20240831_120000
```

## Performance Optimization

### Resource Allocation

Default resource limits are configured in docker-compose.yml:

```yaml
# API Service
deploy:
  resources:
    limits:
      memory: 2G
      cpus: "1.0"
    reservations:
      memory: 1G
      cpus: "0.5"
```

### Caching Strategy

- **Redis**: Application caching and session storage
- **Nginx**: Static file caching and gzip compression
- **Docker**: Multi-stage builds with layer caching

### Database Performance

- **PostgreSQL**: Optimized configuration for the workload
- **Connection Pooling**: Built-in connection management
- **Indexing**: Proper indexes for query performance

## Troubleshooting

### Common Issues

1. **Out of Memory**
   ```bash
   # Check memory usage
   docker stats
   
   # Increase memory limits
   # Edit docker-compose.yml resource limits
   ```

2. **Port Conflicts**
   ```bash
   # Check port usage
   ./scripts/dev.sh status
   
   # Change ports in .env file
   API_PORT=8001
   POSTGRES_PORT=5433
   ```

3. **Permission Issues**
   ```bash
   # Fix permissions
   sudo chown -R $USER:$USER data/ logs/
   chmod -R 755 volumes/
   ```

4. **Service Health Checks Failing**
   ```bash
   # Check service logs
   ./scripts/dev.sh logs api-dev
   
   # Verify service is responding
   curl http://localhost:8000/health
   ```

### Debug Commands

```bash
# Service status
./scripts/dev.sh status

# Container inspection
docker compose ps
docker compose logs service-name

# Network debugging
docker network ls
docker network inspect knowledge-dev-net

# Volume inspection
docker volume ls
docker volume inspect knowledge-ingestor_postgres_data
```

## Advanced Configuration

### Custom Networks

Services communicate over isolated networks:
- `knowledge-net`: Production network (172.20.0.0/16)
- `knowledge-dev-net`: Development network (172.21.0.0/16)

### Volume Management

Persistent data is stored in Docker volumes:
- `postgres_data`: Database files
- `redis_data`: Cache data
- `prometheus_data`: Metrics data
- `grafana_data`: Dashboard configurations

### SSL/TLS Configuration

For production HTTPS:

1. Place certificates in `nginx/ssl/`
2. Configure domain names in `nginx/conf.d/default.conf`
3. Update CORS origins in `.env`

### Load Balancing

Nginx is configured for load balancing:
- Health checks for backend services  
- Session affinity for stateful connections
- Rate limiting for API protection

## Integration Examples

### CI/CD Pipeline

```yaml
# GitHub Actions example
name: Deploy to Production
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to production
        run: |
          ./scripts/setup.sh
          ./scripts/prod.sh deploy --monitoring
          ./scripts/prod.sh health
```

### External Services

Configure external integrations in `.env`:

```bash
# AWS S3 for file storage
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_S3_BUCKET=your-bucket

# Email notifications
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=your-email@gmail.com

# Monitoring services
DATADOG_API_KEY=your-datadog-key
```

## Support and Maintenance

### Regular Maintenance

```bash
# Weekly tasks
./scripts/prod.sh backup           # Create backups
./scripts/prod.sh clean            # Clean unused images
docker system prune -f             # Clean system

# Monthly tasks  
./scripts/prod.sh update           # Update services
./scripts/prod.sh health           # Health audit
```

### Performance Monitoring

Monitor these metrics:
- API response times
- Database query performance
- Memory and CPU utilization  
- Disk space usage
- Network throughput

### Security Updates

Keep the system secure:
1. Regular Docker image updates
2. Security patch application
3. SSL certificate renewal
4. Access log monitoring
5. Vulnerability scanning

## Getting Help

- Check service logs: `./scripts/dev.sh logs -f`
- Verify service health: `./scripts/dev.sh status`
- Review configuration: `docker compose config`
- Test connectivity: `curl http://localhost:8000/health`

For more detailed information, see the main README.md and API documentation at `/docs` when the service is running.