"""
Exception classes for the Knowledge Ingestor system.

This module defines custom exceptions for different components and error scenarios
in the knowledge ingestion pipeline.
"""

from typing import Optional, Any


class KnowledgeIngestorError(Exception):
    """Base exception class for all Knowledge Ingestor errors."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigError(KnowledgeIngestorError):
    """Raised when there are configuration-related errors."""
    pass


class PluginError(KnowledgeIngestorError):
    """Raised when there are plugin-related errors."""
    
    def __init__(self, message: str, plugin_name: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.plugin_name = plugin_name


class IngestionError(KnowledgeIngestorError):
    """Raised when there are errors during the ingestion process."""
    
    def __init__(self, message: str, source_url: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.source_url = source_url


class DatabaseError(KnowledgeIngestorError):
    """Raised when there are database-related errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.operation = operation


class ValidationError(KnowledgeIngestorError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None):
        super().__init__(message)
        self.field = field
        self.value = value


class ProcessingError(IngestionError):
    """Raised when content processing fails."""
    
    def __init__(self, message: str, processor: Optional[str] = None, source_url: Optional[str] = None):
        super().__init__(message, source_url)
        self.processor = processor


class NetworkError(KnowledgeIngestorError):
    """Raised when network-related errors occur."""
    
    def __init__(self, message: str, url: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class AuthenticationError(KnowledgeIngestorError):
    """Raised when authentication fails."""
    pass


class RateLimitError(KnowledgeIngestorError):
    """Raised when rate limits are exceeded."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after