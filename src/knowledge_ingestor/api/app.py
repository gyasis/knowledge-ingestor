"""
Production-ready FastAPI application for the Knowledge Ingestor API.

This module provides:
- Complete API application setup
- Middleware configuration
- Route registration
- Error handling
- OpenAPI documentation
- Startup/shutdown lifecycle management
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core.config import get_config
from ..utils.logging import setup_logging, get_logger
from .middleware import (
    RateLimitingMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    ErrorHandlingMiddleware,
    metrics_middleware
)
from .models import APIError, ErrorDetail, ErrorTypeEnum
from .auth import auth_manager
from .monitoring import monitoring_router, prometheus_metrics
from .v1 import api_v1_router

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown tasks.
    
    Handles:
    - Plugin system initialization
    - Database connections
    - Background tasks
    - Resource cleanup
    """
    config = get_config()
    logger.info("Knowledge Ingestor API starting up...")
    
    startup_start = time.time()
    startup_errors = []
    
    try:
        # Initialize plugin system
        logger.info("Initializing plugin system...")
        try:
            from ..plugins.plugin_manager import get_plugin_manager, initialize_plugin_system
            plugin_count = initialize_plugin_system()
            logger.info(f"Loaded {plugin_count} plugins")
        except Exception as e:
            error_msg = f"Plugin system initialization failed: {e}"
            logger.error(error_msg)
            startup_errors.append(error_msg)
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        try:
            plugin_manager = get_plugin_manager()
            database = plugin_manager.get_database()
            if database:
                if hasattr(database, 'connect'):
                    database.connect()
                logger.info(f"Database connection established: {database.__class__.__name__}")
            else:
                logger.warning("No database plugin configured")
        except Exception as e:
            error_msg = f"Database initialization failed: {e}"
            logger.error(error_msg)
            startup_errors.append(error_msg)
        
        # Initialize embedding service
        logger.info("Initializing embedding service...")
        try:
            embedding_provider = plugin_manager.get_embedding_provider()
            if embedding_provider:
                logger.info(f"Embedding service ready: {embedding_provider.__class__.__name__}")
            else:
                logger.warning("No embedding provider configured")
        except Exception as e:
            error_msg = f"Embedding service initialization failed: {e}"
            logger.error(error_msg)
            startup_errors.append(error_msg)
        
        # Initialize authentication system
        if config.api.auth_enabled:
            logger.info("Authentication system enabled")
        else:
            logger.info("Authentication system disabled")
        
        # Record startup metrics
        startup_time = time.time() - startup_start
        logger.info(f"Startup completed in {startup_time:.2f}s")
        
        if startup_errors:
            logger.warning(f"Startup completed with {len(startup_errors)} errors")
            for error in startup_errors:
                logger.warning(f"  - {error}")
        
        # Application is ready
        yield
        
    except Exception as e:
        logger.error(f"Critical startup error: {e}", exc_info=True)
        raise
    
    # Shutdown
    logger.info("Knowledge Ingestor API shutting down...")
    
    try:
        # Cleanup database connections
        try:
            plugin_manager = get_plugin_manager()
            database = plugin_manager.get_database()
            if database and hasattr(database, 'disconnect'):
                database.disconnect()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Database shutdown error: {e}")
        
        # Shutdown plugin manager
        try:
            plugin_manager.shutdown()
            logger.info("Plugin manager shutdown complete")
        except Exception as e:
            logger.error(f"Plugin manager shutdown error: {e}")
        
        logger.info("Knowledge Ingestor API shutdown complete")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)


def create_custom_openapi_schema(app: FastAPI) -> Dict[str, Any]:
    """Create enhanced OpenAPI schema with custom documentation."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Knowledge Ingestor API",
        version="1.0.0",
        description="""
## Knowledge Ingestor API

A comprehensive document processing and ingestion system with semantic search capabilities.

### Features

* **Document Ingestion**: Process various content types (articles, PDFs, videos, web pages)
* **Semantic Search**: AI-powered search using vector embeddings
* **Multi-format Support**: ArXiv papers, web articles, YouTube videos, PDFs
* **Vector Storage**: Integration with DeepLake, Pinecone, ChromaDB, and more
* **Authentication**: API key and OAuth 2.0 support
* **Rate Limiting**: Configurable request limits and throttling
* **Monitoring**: Prometheus metrics and health checks
* **Async Processing**: Background job processing for large datasets

### Authentication

The API supports two authentication methods:

1. **API Key Authentication**: Include `X-API-Key` header in requests
2. **JWT Token Authentication**: Include `Authorization: Bearer <token>` header

### Rate Limiting

API requests are subject to rate limiting:
- Default: 100 requests per minute per client
- Rate limit headers included in responses
- HTTP 429 returned when limits exceeded

### Error Handling

All errors follow a consistent format:
```json
{
  "success": false,
  "error": {
    "type": "error_type",
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### Monitoring

- Health checks: `GET /monitoring/health`
- Metrics: `GET /monitoring/metrics` (Prometheus format)
- Liveness: `GET /monitoring/health/liveness`
- Readiness: `GET /monitoring/health/readiness`
        """,
        routes=app.routes,
    )
    
    # Add custom extensions
    openapi_schema["info"]["x-logo"] = {
        "url": "https://via.placeholder.com/120x120.png?text=KI",
        "altText": "Knowledge Ingestor"
    }
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for authentication"
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token for authentication"
        }
    }
    
    # Add global security
    openapi_schema["security"] = [
        {"ApiKeyAuth": []},
        {"BearerAuth": []}
    ]
    
    # Add custom tags
    openapi_schema["tags"] = [
        {
            "name": "ingestion",
            "description": "Document ingestion and processing endpoints"
        },
        {
            "name": "search",
            "description": "Document search and retrieval endpoints"
        },
        {
            "name": "documents",
            "description": "Document management endpoints"
        },
        {
            "name": "authentication",
            "description": "Authentication and API key management"
        },
        {
            "name": "monitoring",
            "description": "System monitoring and health checks"
        },
        {
            "name": "admin",
            "description": "Administrative endpoints"
        }
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        FastAPI: Configured application instance
    """
    config = get_config()
    
    # Create FastAPI app with lifespan management
    app = FastAPI(
        title="Knowledge Ingestor API",
        description="REST API for the Knowledge Ingestor document processing system",
        version="1.0.0",
        debug=config.api.debug,
        lifespan=lifespan,
        docs_url=None,  # Disable default docs to use custom
        redoc_url=None,  # Disable default redoc to use custom
        openapi_url="/api/openapi.json"
    )
    
    # Configure trusted hosts (security)
    if not config.is_development():
        app.add_middleware(
            TrustedHostMiddleware, 
            allowed_hosts=["localhost", "127.0.0.1", config.api.host]
        )
    
    # Add security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Add CORS middleware
    if config.api.cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.api.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Processing-Time", "X-RateLimit-*"]
        )
    
    # Add custom middleware
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestLoggingMiddleware, log_body=config.api.debug)
    
    # Add rate limiting middleware
    if config.api.rate_limit_enabled:
        app.add_middleware(
            RateLimitingMiddleware,
            requests_per_minute=config.api.rate_limit_requests
        )
    
    # Add metrics middleware
    metrics_middleware.app = app
    app.add_middleware(type(metrics_middleware))
    
    # Register routers
    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(monitoring_router)
    
    # Custom OpenAPI schema
    app.openapi = lambda: create_custom_openapi_schema(app)
    
    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Knowledge Ingestor API",
            "version": "1.0.0",
            "description": "Document processing and ingestion system",
            "status": "operational",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/api/openapi.json",
            "health": "/monitoring/health"
        }
    
    # Custom documentation endpoints
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        """Custom Swagger UI with enhanced styling."""
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title="Knowledge Ingestor API - Documentation",
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
            swagger_favicon_url="https://via.placeholder.com/32x32.png?text=KI"
        )
    
    @app.get("/redoc", include_in_schema=False)
    async def custom_redoc_html():
        """Custom ReDoc with enhanced styling."""
        return get_redoc_html(
            openapi_url="/api/openapi.json",
            title="Knowledge Ingestor API - Documentation",
            redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
            redoc_favicon_url="https://via.placeholder.com/32x32.png?text=KI"
        )
    
    # Global exception handlers
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions with consistent error format."""
        
        # Record metrics
        prometheus_metrics.record_error("http_error", "api")
        
        error_type_map = {
            400: ErrorTypeEnum.VALIDATION_ERROR,
            401: ErrorTypeEnum.AUTHENTICATION_ERROR,
            403: ErrorTypeEnum.AUTHORIZATION_ERROR,
            404: ErrorTypeEnum.NOT_FOUND_ERROR,
            429: ErrorTypeEnum.RATE_LIMIT_ERROR,
            500: ErrorTypeEnum.INTERNAL_SERVER_ERROR
        }
        
        error_response = APIError(
            error=ErrorDetail(
                type=error_type_map.get(exc.status_code, ErrorTypeEnum.INTERNAL_SERVER_ERROR),
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                details={"status_code": exc.status_code}
            ),
            request_id=getattr(request.state, 'request_id', None)
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.dict()
        )
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        
        # Record metrics
        prometheus_metrics.record_error("unhandled_exception", "api")
        
        request_id = getattr(request.state, 'request_id', 'unknown')
        logger.error(f"Unhandled exception in request {request_id}: {str(exc)}", exc_info=True)
        
        error_response = APIError(
            error=ErrorDetail(
                type=ErrorTypeEnum.INTERNAL_SERVER_ERROR,
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred" if not config.api.debug else str(exc),
                details={"exception_type": type(exc).__name__} if config.api.debug else None
            ),
            request_id=request_id,
            help_url="mailto:support@knowledge-ingestor.local"
        )
        
        return JSONResponse(
            status_code=500,
            content=error_response.dict()
        )
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    config = get_config()
    
    # Run configuration
    run_config = {
        "host": config.api.host,
        "port": config.api.port,
        "log_level": "info" if not config.api.debug else "debug",
        "access_log": True,
        "server_header": False,
        "date_header": False
    }
    
    # Development-specific settings
    if config.is_development():
        run_config.update({
            "reload": True,
            "reload_dirs": ["src/knowledge_ingestor"],
            "reload_excludes": ["*.log", "*.tmp", "__pycache__"]
        })
    
    # Production-specific settings
    if config.is_production():
        run_config.update({
            "workers": min(4, (os.cpu_count() or 1) + 1),
            "loop": "uvloop",  # Requires uvloop to be installed
            "http": "httptools",  # Requires httptools to be installed
            "lifespan": "on"
        })
    
    logger.info(f"Starting Knowledge Ingestor API on {run_config['host']}:{run_config['port']}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Debug mode: {config.api.debug}")
    
    uvicorn.run("knowledge_ingestor.api.app:app", **run_config)