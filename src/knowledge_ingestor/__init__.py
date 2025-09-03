"""
Knowledge Ingestor: A modular document processing and ingestion system.

This package provides a plugin-based architecture for processing various document types
and storing them in vector databases for semantic search and retrieval.

Core Features:
- Plugin-based ingestor system for different content types
- Database abstraction layer supporting multiple vector databases
- Standardized document processing pipeline
- Configuration management with environment-based settings
- Comprehensive logging and error handling
"""

__version__ = "1.0.0"
__author__ = "Knowledge Ingestor Team"

from .core.document import Document, DocumentMetadata
from .core.pipeline import ProcessingPipeline
from .core.config import Config

__all__ = [
    "Document", 
    "DocumentMetadata", 
    "ProcessingPipeline", 
    "Config"
]