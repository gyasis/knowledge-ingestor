"""
Middleware components for the Knowledge Ingestor API.

This module provides various middleware for:
- Rate limiting
- Request/response logging  
- Performance monitoring
- Security headers
- Error handling
"""

import time
import json
import asyncio
from typing import Dict, Any, Optional, Callable
from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import uuid

from ..core.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window algorithm.
    
    Supports per-IP and per-API-key rate limiting with
    configurable windows and limits.
    """
    
    def __init__(self, app, requests_per_minute: int = 60, window_size: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_size = window_size
        self.request_history: Dict[str, deque] = defaultdict(deque)
        self.config = get_config()
        
        # Cleanup task to prevent memory leaks
        self._cleanup_task = asyncio.create_task(self._cleanup_old_entries())
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting if disabled
        if not self.config.api.rate_limit_enabled:
            return await call_next(request)
        
        # Determine client identifier (API key > IP address)
        client_id = self._get_client_identifier(request)
        
        # Check rate limit
        if not self._is_request_allowed(client_id):
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Maximum {self.requests_per_minute} requests per minute allowed",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )
        
        # Record the request
        self._record_request(client_id)
        
        # Add rate limit headers to response
        response = await call_next(request)
        remaining = self._get_remaining_requests(client_id)
        
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int((datetime.utcnow() + timedelta(seconds=60)).timestamp()))
        
        return response
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get unique client identifier for rate limiting."""
        # Check for API key first
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"apikey:{api_key[:10]}..."  # Use truncated key for logging
        
        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        return f"ip:{client_ip}"
    
    def _is_request_allowed(self, client_id: str) -> bool:
        """Check if request is within rate limit."""
        now = time.time()
        window_start = now - self.window_size
        
        # Clean old entries for this client
        client_history = self.request_history[client_id]
        while client_history and client_history[0] < window_start:
            client_history.popleft()
        
        # Check if within limit
        return len(client_history) < self.requests_per_minute
    
    def _record_request(self, client_id: str):
        """Record a request timestamp."""
        self.request_history[client_id].append(time.time())
    
    def _get_remaining_requests(self, client_id: str) -> int:
        """Get remaining requests for client."""
        current_count = len(self.request_history[client_id])
        return max(0, self.requests_per_minute - current_count)
    
    async def _cleanup_old_entries(self):
        """Periodic cleanup of old request history entries."""
        while True:
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                now = time.time()
                window_start = now - self.window_size * 2  # Keep extra buffer
                
                # Clean up old entries
                clients_to_remove = []
                for client_id, history in self.request_history.items():
                    while history and history[0] < window_start:
                        history.popleft()
                    
                    # Remove empty histories
                    if not history:
                        clients_to_remove.append(client_id)
                
                for client_id in clients_to_remove:
                    del self.request_history[client_id]
                
                logger.debug(f"Cleaned up rate limit history for {len(clients_to_remove)} clients")
            
            except Exception as e:
                logger.error(f"Rate limit cleanup error: {e}")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Request and response logging middleware.
    
    Logs all API requests with timing, status codes,
    and other relevant metadata.
    """
    
    def __init__(self, app, log_body: bool = False, max_body_size: int = 1024):
        super().__init__(app)
        self.log_body = log_body
        self.max_body_size = max_body_size
        self.config = get_config()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Extract request info
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        user_agent = request.headers.get("User-Agent", "unknown")
        
        # Log request
        request_info = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Optionally log request body (for debugging)
        if self.log_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if len(body) <= self.max_body_size:
                    request_info["body"] = body.decode("utf-8", errors="ignore")
                else:
                    request_info["body"] = f"<body too large: {len(body)} bytes>"
            except Exception as e:
                request_info["body"] = f"<error reading body: {e}>"
        
        logger.info(f"Request started: {json.dumps(request_info)}")
        
        # Add request ID to headers for tracking
        request.state.request_id = request_id
        
        # Process request
        try:
            response = await call_next(request)
            processing_time = time.time() - start_time
            
            # Log response
            response_info = {
                "request_id": request_id,
                "status_code": response.status_code,
                "processing_time": round(processing_time, 3),
                "response_size": response.headers.get("content-length", "unknown")
            }
            
            logger.info(f"Request completed: {json.dumps(response_info)}")
            
            # Add performance headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Processing-Time"] = str(round(processing_time, 3))
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Log error
            error_info = {
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "processing_time": round(processing_time, 3)
            }
            
            logger.error(f"Request failed: {json.dumps(error_info)}")
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Security headers middleware.
    
    Adds security headers to all responses to improve
    security posture of the API.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        for header, value in self.security_headers.items():
            response.headers[header] = value
        
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware.
    
    Catches unhandled exceptions and returns
    consistent error responses.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
            
        except HTTPException:
            # Re-raise HTTP exceptions (they're handled by FastAPI)
            raise
            
        except Exception as e:
            # Log the error
            request_id = getattr(request.state, 'request_id', 'unknown')
            logger.error(f"Unhandled exception in request {request_id}: {str(e)}", exc_info=True)
            
            # Return generic error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": "An unexpected error occurred",
                    "request_id": request_id
                }
            )


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Basic metrics collection middleware.
    
    Collects request metrics for monitoring
    and observability.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.metrics = {
            "total_requests": 0,
            "requests_by_method": defaultdict(int),
            "requests_by_status": defaultdict(int),
            "requests_by_endpoint": defaultdict(int),
            "total_processing_time": 0.0,
            "start_time": time.time()
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Update metrics
            processing_time = time.time() - start_time
            endpoint = f"{request.method} {request.url.path}"
            
            self.metrics["total_requests"] += 1
            self.metrics["requests_by_method"][request.method] += 1
            self.metrics["requests_by_status"][response.status_code] += 1
            self.metrics["requests_by_endpoint"][endpoint] += 1
            self.metrics["total_processing_time"] += processing_time
            
            return response
            
        except Exception as e:
            # Update error metrics
            processing_time = time.time() - start_time
            endpoint = f"{request.method} {request.url.path}"
            
            self.metrics["total_requests"] += 1
            self.metrics["requests_by_method"][request.method] += 1
            self.metrics["requests_by_status"][500] += 1  # Assume 500 for unhandled exceptions
            self.metrics["requests_by_endpoint"][endpoint] += 1
            self.metrics["total_processing_time"] += processing_time
            
            raise
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        uptime = time.time() - self.metrics["start_time"]
        avg_processing_time = (
            self.metrics["total_processing_time"] / self.metrics["total_requests"]
            if self.metrics["total_requests"] > 0 else 0
        )
        
        return {
            "uptime_seconds": round(uptime, 2),
            "total_requests": self.metrics["total_requests"],
            "requests_per_second": round(self.metrics["total_requests"] / uptime, 2) if uptime > 0 else 0,
            "average_processing_time": round(avg_processing_time, 3),
            "requests_by_method": dict(self.metrics["requests_by_method"]),
            "requests_by_status": dict(self.metrics["requests_by_status"]),
            "top_endpoints": dict(sorted(
                self.metrics["requests_by_endpoint"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])
        }
    
    def reset_metrics(self):
        """Reset all metrics."""
        self.metrics = {
            "total_requests": 0,
            "requests_by_method": defaultdict(int),
            "requests_by_status": defaultdict(int),
            "requests_by_endpoint": defaultdict(int),
            "total_processing_time": 0.0,
            "start_time": time.time()
        }


# Global metrics instance for access from routes
metrics_middleware = MetricsMiddleware(None)