"""
Document data structures and metadata management for the Knowledge Ingestor system.

This module defines the core data structures used throughout the system for
representing documents and their metadata.
"""

from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, validator
from enum import Enum
import uuid


class ContentType(str, Enum):
    """Enumeration of supported content types."""
    ARXIV_PAPER = "arxiv_paper"
    WEB_ARTICLE = "web_article"
    PDF_DOCUMENT = "pdf_document"
    YOUTUBE_VIDEO = "youtube_video"
    MEDIUM_ARTICLE = "medium_article"
    TEXT_FILE = "text_file"
    MARKTECHPOST_ARTICLE = "marktechpost_article"
    GENERAL_WEB_PAGE = "general_web_page"


class ProcessingStatus(str, Enum):
    """Document processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DocumentMetadata(BaseModel):
    """
    Metadata structure for documents in the Knowledge Ingestor system.
    
    This class represents all metadata associated with a document,
    including source information, processing details, and content characteristics.
    """
    
    # Source Information
    title: Optional[str] = Field(None, description="Document title")
    authors: Optional[List[str]] = Field(default_factory=list, description="Document authors")
    source_url: Optional[Union[HttpUrl, str]] = Field(None, description="Original source URL")
    content_type: ContentType = Field(ContentType.TEXT_FILE, description="Type of content")
    
    # Processing Information
    processed_at: datetime = Field(default_factory=datetime.utcnow, description="Processing timestamp")
    processing_status: ProcessingStatus = Field(ProcessingStatus.PENDING, description="Current processing status")
    processor_version: Optional[str] = Field(None, description="Version of processor used")
    
    # Content Characteristics
    language: Optional[str] = Field("en", description="Document language")
    word_count: Optional[int] = Field(None, description="Approximate word count")
    char_count: Optional[int] = Field(None, description="Character count")
    
    # Summarization and Analysis
    summary: Optional[str] = Field(None, description="AI-generated summary")
    keywords: Optional[List[str]] = Field(default_factory=list, description="Extracted keywords")
    topics: Optional[List[str]] = Field(default_factory=list, description="Identified topics")
    
    # Technical Metadata
    file_size: Optional[int] = Field(None, description="File size in bytes")
    mime_type: Optional[str] = Field(None, description="MIME type")
    encoding: Optional[str] = Field("utf-8", description="Text encoding")
    
    # Custom fields for extensibility
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata fields")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str,
        }
    
    @validator('source_url', pre=True)
    def validate_url(cls, v):
        """Validate and normalize URLs."""
        if v is None:
            return v
        if isinstance(v, str):
            if not v.startswith(('http://', 'https://')):
                return f"https://{v}"
        return v


class Document(BaseModel):
    """
    Core document structure for the Knowledge Ingestor system.
    
    This class represents a document with its content, metadata, and processing information.
    All documents in the system use this standardized structure.
    """
    
    # Core Identifiers
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique document identifier")
    hash_id: Optional[str] = Field(None, description="Content-based hash identifier")
    
    # Content
    content: str = Field("", description="Raw document content")
    processed_content: Optional[str] = Field(None, description="Processed/cleaned content")
    chunks: Optional[List[str]] = Field(default_factory=list, description="Content chunks for embedding")
    
    # Embeddings
    embedding: Optional[List[float]] = Field(None, description="Document embedding vector")
    chunk_embeddings: Optional[List[List[float]]] = Field(None, description="Embeddings for content chunks")
    
    # Metadata
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata, description="Document metadata")
    
    # Processing Information
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Document creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    version: int = Field(1, description="Document version number")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
    
    def update_content(self, new_content: str) -> None:
        """Update document content and refresh metadata."""
        self.content = new_content
        self.updated_at = datetime.utcnow()
        self.version += 1
        
        # Update content characteristics
        self.metadata.word_count = len(new_content.split())
        self.metadata.char_count = len(new_content)
    
    def add_chunk_embeddings(self, embeddings: List[List[float]]) -> None:
        """Add chunk embeddings to the document."""
        self.chunk_embeddings = embeddings
        self.updated_at = datetime.utcnow()
    
    def set_processing_status(self, status: ProcessingStatus) -> None:
        """Update the processing status."""
        self.metadata.processing_status = status
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary format."""
        return self.dict()
    
    def to_storage_format(self) -> Dict[str, Any]:
        """
        Convert document to storage-optimized format.
        
        This method prepares the document for storage in vector databases,
        ensuring compatibility with different storage backends.
        """
        return {
            "id": self.id,
            "text": self.content,
            "embedding": self.embedding,
            "metadata": {
                "title": self.metadata.title,
                "summary": self.metadata.summary,
                "web_address": str(self.metadata.source_url) if self.metadata.source_url else None,
                "content_type": self.metadata.content_type,
                "processed_at": self.metadata.processed_at.isoformat(),
                "authors": self.metadata.authors,
                "language": self.metadata.language,
                "word_count": self.metadata.word_count,
                **self.metadata.custom_fields
            }
        }


class DocumentBatch(BaseModel):
    """Container for batch processing of documents."""
    
    documents: List[Document] = Field(default_factory=list, description="List of documents")
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Batch identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Batch creation time")
    
    def add_document(self, document: Document) -> None:
        """Add a document to the batch."""
        self.documents.append(document)
    
    def get_pending_documents(self) -> List[Document]:
        """Get all documents with pending status."""
        return [
            doc for doc in self.documents 
            if doc.metadata.processing_status == ProcessingStatus.PENDING
        ]
    
    def get_completed_documents(self) -> List[Document]:
        """Get all documents with completed status."""
        return [
            doc for doc in self.documents 
            if doc.metadata.processing_status == ProcessingStatus.COMPLETED
        ]
    
    def get_failed_documents(self) -> List[Document]:
        """Get all documents with failed status."""
        return [
            doc for doc in self.documents 
            if doc.metadata.processing_status == ProcessingStatus.FAILED
        ]