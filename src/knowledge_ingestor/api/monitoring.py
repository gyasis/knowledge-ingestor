"""
Monitoring and observability module for the Knowledge Ingestor API.

This module provides:
- Prometheus metrics collection
- Health check endpoints
- System monitoring
- Performance tracking
"""

import time
import psutil
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, generate_latest,
        CONTENT_TYPE_LATEST, REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from ..core.config import get_config
from ..utils.logging import get_logger
from .auth import get_current_user

logger = get_logger(__name__)


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str
    uptime_seconds: float
    components: Dict[str, Dict[str, Any]]


class MetricsResponse(BaseModel):
    """Metrics response model."""
    timestamp: datetime
    uptime_seconds: float
    system_metrics: Dict[str, Any]
    application_metrics: Dict[str, Any]
    business_metrics: Dict[str, Any]


class PrometheusMetrics:
    """
    Prometheus metrics collector for the Knowledge Ingestor API.
    
    Collects system, application, and business metrics
    for monitoring and alerting.
    """
    
    def __init__(self):
        self.enabled = PROMETHEUS_AVAILABLE
        self.start_time = time.time()
        
        if not self.enabled:
            logger.warning("Prometheus client not available. Metrics disabled.")
            return
        
        # HTTP Request metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code']
        )
        
        self.http_request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint']
        )
        
        # Application metrics
        self.documents_ingested_total = Counter(
            'documents_ingested_total',
            'Total number of documents ingested',
            ['status', 'content_type']
        )
        
        self.document_processing_duration = Histogram(
            'document_processing_duration_seconds',
            'Document processing duration in seconds',
            ['content_type']
        )
        
        self.search_requests_total = Counter(
            'search_requests_total',
            'Total number of search requests'
        )
        
        self.search_duration = Histogram(
            'search_duration_seconds',
            'Search request duration in seconds'
        )
        
        # System metrics
        self.system_cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'System CPU usage percentage'
        )
        
        self.system_memory_usage = Gauge(
            'system_memory_usage_bytes',
            'System memory usage in bytes'
        )
        
        self.system_memory_usage_percent = Gauge(
            'system_memory_usage_percent',
            'System memory usage percentage'
        )
        
        self.system_disk_usage = Gauge(
            'system_disk_usage_bytes',
            'System disk usage in bytes'
        )
        
        self.system_disk_usage_percent = Gauge(
            'system_disk_usage_percent',
            'System disk usage percentage'
        )
        
        # Database metrics
        self.database_connections = Gauge(
            'database_connections',
            'Number of active database connections'
        )
        
        self.database_query_duration = Histogram(
            'database_query_duration_seconds',
            'Database query duration in seconds',
            ['operation']
        )
        
        # API Key usage metrics
        self.api_key_requests_total = Counter(
            'api_key_requests_total',
            'Total requests by API key',
            ['key_name', 'status_code']
        )
        
        # Rate limiting metrics
        self.rate_limit_hits_total = Counter(
            'rate_limit_hits_total',
            'Total rate limit hits',
            ['client_type']
        )
        
        # Error metrics
        self.errors_total = Counter(
            'errors_total',
            'Total application errors',
            ['error_type', 'component']
        )
        
        logger.info("Prometheus metrics initialized")
    
    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics."""
        if not self.enabled:
            return
        
        self.http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        self.http_request_duration.labels(method=method, endpoint=endpoint).observe(duration)
    
    def record_document_ingestion(self, status: str, content_type: str, duration: float):
        """Record document ingestion metrics."""
        if not self.enabled:
            return
        
        self.documents_ingested_total.labels(status=status, content_type=content_type).inc()
        self.document_processing_duration.labels(content_type=content_type).observe(duration)
    
    def record_search_request(self, duration: float):
        """Record search request metrics."""
        if not self.enabled:
            return
        
        self.search_requests_total.inc()
        self.search_duration.observe(duration)
    
    def record_api_key_request(self, key_name: str, status_code: int):
        """Record API key usage metrics."""
        if not self.enabled:
            return
        
        self.api_key_requests_total.labels(key_name=key_name, status_code=status_code).inc()
    
    def record_rate_limit_hit(self, client_type: str):
        """Record rate limit hit."""
        if not self.enabled:
            return
        
        self.rate_limit_hits_total.labels(client_type=client_type).inc()
    
    def record_error(self, error_type: str, component: str):
        """Record application error."""
        if not self.enabled:
            return
        
        self.errors_total.labels(error_type=error_type, component=component).inc()
    
    def record_database_query(self, operation: str, duration: float):
        """Record database query metrics."""
        if not self.enabled:
            return
        
        self.database_query_duration.labels(operation=operation).observe(duration)
    
    def update_system_metrics(self):
        """Update system metrics."""
        if not self.enabled:
            return
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=None)
            self.system_cpu_usage.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_memory_usage.set(memory.used)
            self.system_memory_usage_percent.set(memory.percent)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_disk_usage.set(disk.used)
            self.system_disk_usage_percent.set((disk.used / disk.total) * 100)
            
        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")
    
    def get_registry_metrics(self) -> str:
        """Get Prometheus metrics in text format."""
        if not self.enabled:
            return "# Prometheus metrics not available\n"
        
        self.update_system_metrics()
        return generate_latest(REGISTRY).decode('utf-8')


class HealthChecker:
    """
    Health check system for monitoring component status.
    
    Performs health checks on various system components
    and provides detailed status information.
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.version = "1.0.0"
    
    async def check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            from ..plugins.plugin_manager import get_plugin_manager
            
            plugin_manager = get_plugin_manager()
            database = plugin_manager.get_database()
            
            if not database:
                return {
                    "status": "unhealthy",
                    "message": "No database plugin configured",
                    "response_time": None
                }
            
            # Test database connection with timeout
            start_time = time.time()
            health_result = await asyncio.wait_for(
                asyncio.create_task(self._check_db_connection(database)),
                timeout=5.0
            )
            response_time = time.time() - start_time
            
            return {
                "status": "healthy" if health_result else "unhealthy",
                "message": "Database connection successful" if health_result else "Database connection failed",
                "response_time": round(response_time, 3),
                "type": database.__class__.__name__
            }
            
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "message": "Database health check timeout",
                "response_time": None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Database health check error: {str(e)}",
                "response_time": None
            }
    
    async def _check_db_connection(self, database) -> bool:
        """Test basic database connectivity."""
        try:
            # Try a simple operation to test connectivity
            if hasattr(database, 'health_check'):
                return database.health_check()
            elif hasattr(database, 'get_stats'):
                stats = database.get_stats()
                return stats is not None
            else:
                # Fallback - assume healthy if no health check method
                return True
        except Exception:
            return False
    
    async def check_embedding_service_health(self) -> Dict[str, Any]:
        """Check embedding service connectivity."""
        try:
            from ..plugins.plugin_manager import get_plugin_manager
            
            plugin_manager = get_plugin_manager()
            embedding_provider = plugin_manager.get_embedding_provider()
            
            if not embedding_provider:
                return {
                    "status": "unhealthy",
                    "message": "No embedding provider configured",
                    "response_time": None
                }
            
            # Test embedding service with a simple request
            start_time = time.time()
            test_result = await asyncio.wait_for(
                asyncio.create_task(self._test_embedding_service(embedding_provider)),
                timeout=10.0
            )
            response_time = time.time() - start_time
            
            return {
                "status": "healthy" if test_result else "unhealthy",
                "message": "Embedding service operational" if test_result else "Embedding service failed",
                "response_time": round(response_time, 3),
                "type": embedding_provider.__class__.__name__
            }
            
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "message": "Embedding service timeout",
                "response_time": None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Embedding service error: {str(e)}",
                "response_time": None
            }
    
    async def _test_embedding_service(self, embedding_provider) -> bool:
        """Test embedding service with a simple request."""
        try:
            # Try generating embeddings for a test string
            embeddings = embedding_provider.generate_embeddings(["health check test"])
            return embeddings is not None and len(embeddings) > 0
        except Exception:
            return False
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        try:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Determine status based on resource usage
            status = "healthy"
            warnings = []
            
            if memory.percent > 90:
                status = "degraded"
                warnings.append("High memory usage")
            
            if (disk.used / disk.total) * 100 > 90:
                status = "degraded"
                warnings.append("High disk usage")
            
            if cpu_percent > 90:
                status = "degraded"
                warnings.append("High CPU usage")
            
            return {
                "status": status,
                "warnings": warnings,
                "memory": {
                    "used_percent": round(memory.percent, 2),
                    "used_bytes": memory.used,
                    "total_bytes": memory.total
                },
                "disk": {
                    "used_percent": round((disk.used / disk.total) * 100, 2),
                    "used_bytes": disk.used,
                    "total_bytes": disk.total
                },
                "cpu": {
                    "usage_percent": round(cpu_percent, 2)
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"System resource check error: {str(e)}"
            }
    
    async def perform_full_health_check(self) -> HealthStatus:
        """Perform comprehensive health check."""
        components = {}
        
        # Check database
        components["database"] = await self.check_database_health()
        
        # Check embedding service
        components["embedding_service"] = await self.check_embedding_service_health()
        
        # Check system resources
        components["system_resources"] = self.check_system_resources()
        
        # Determine overall status
        statuses = [comp.get("status", "unknown") for comp in components.values()]
        
        if all(status == "healthy" for status in statuses):
            overall_status = "healthy"
        elif any(status == "unhealthy" for status in statuses):
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"
        
        uptime = time.time() - self.start_time
        
        return HealthStatus(
            status=overall_status,
            timestamp=datetime.utcnow(),
            version=self.version,
            uptime_seconds=round(uptime, 2),
            components=components
        )


# Global instances
prometheus_metrics = PrometheusMetrics()
health_checker = HealthChecker()

# Create monitoring router
monitoring_router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@monitoring_router.get("/health", response_model=HealthStatus)
async def health_check():
    """Comprehensive health check endpoint."""
    return await health_checker.perform_full_health_check()


@monitoring_router.get("/health/liveness")
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive", "timestamp": datetime.utcnow()}


@monitoring_router.get("/health/readiness")
async def readiness_check():
    """Readiness probe for Kubernetes."""
    health_status = await health_checker.perform_full_health_check()
    
    if health_status.status in ["healthy", "degraded"]:
        return {"status": "ready", "timestamp": datetime.utcnow()}
    else:
        return Response(
            content='{"status": "not ready"}',
            status_code=503,
            media_type="application/json"
        )


@monitoring_router.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint."""
    if not prometheus_metrics.enabled:
        return Response(
            content="# Prometheus metrics not available\n",
            media_type="text/plain"
        )
    
    metrics_content = prometheus_metrics.get_registry_metrics()
    return Response(content=metrics_content, media_type=CONTENT_TYPE_LATEST)


@monitoring_router.get("/metrics/json", response_model=MetricsResponse)
async def get_metrics_json(current_user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    """Get metrics in JSON format (requires authentication)."""
    uptime = time.time() - prometheus_metrics.start_time
    
    # System metrics
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_percent = psutil.cpu_percent(interval=None)
        
        system_metrics = {
            "cpu_usage_percent": cpu_percent,
            "memory_usage_percent": memory.percent,
            "memory_used_bytes": memory.used,
            "memory_total_bytes": memory.total,
            "disk_usage_percent": (disk.used / disk.total) * 100,
            "disk_used_bytes": disk.used,
            "disk_total_bytes": disk.total
        }
    except Exception as e:
        system_metrics = {"error": f"Failed to collect system metrics: {str(e)}"}
    
    # Application metrics (basic - extend as needed)
    application_metrics = {
        "uptime_seconds": uptime,
        "prometheus_enabled": prometheus_metrics.enabled
    }
    
    # Business metrics (placeholder - extend with actual business logic)
    business_metrics = {
        "total_documents": 0,  # Replace with actual count
        "total_searches": 0,   # Replace with actual count
    }
    
    return MetricsResponse(
        timestamp=datetime.utcnow(),
        uptime_seconds=round(uptime, 2),
        system_metrics=system_metrics,
        application_metrics=application_metrics,
        business_metrics=business_metrics
    )


@monitoring_router.post("/metrics/reset")
async def reset_metrics(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Reset metrics (requires authentication)."""
    # Only allow admin users to reset metrics
    if current_user.get("auth_method") == "jwt":
        user = current_user.get("user")
        if not user or "admin" not in [role.value for role in user.roles]:
            return Response(status_code=403, content="Admin access required")
    elif current_user.get("auth_method") == "api_key":
        scopes = current_user.get("scopes", [])
        if "admin" not in scopes:
            return Response(status_code=403, content="Admin scope required")
    
    # Reset metrics (if using custom metrics collector)
    # Note: Prometheus metrics typically cannot be reset
    
    return {"message": "Metrics reset requested", "timestamp": datetime.utcnow()}