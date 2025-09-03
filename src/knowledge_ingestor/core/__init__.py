"""Core components for the Knowledge Ingestor system."""

from .document import Document, DocumentMetadata
from .pipeline import ProcessingPipeline
from .config import Config

__all__ = ["Document", "DocumentMetadata", "ProcessingPipeline", "Config"]