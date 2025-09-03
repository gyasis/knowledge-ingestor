"""
Pydantic models for API request/response schemas.

This module provides comprehensive models for:
- Request validation
- Response serialization  
- Error handling
- API documentation
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, validator
from uuid import UUID


class APIVersion(str, Enum):
    """API version enumeration."""
    V1 = "v1"


class ContentTypeEnum(str, Enum):
    """Content type enumeration for documents."""
    ARTICLE = "article"
    PDF = "pdf"
    ARXIV = "arxiv"
    WEBPAGE = "webpage"
    VIDEO = "video"
    UNKNOWN = "unknown"


class ProcessingStatusEnum(str, Enum):
    """Processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorTypeEnum(str, Enum):
    """Error type enumeration."""
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND_ERROR = "not_found_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    PROCESSING_ERROR = "processing_error"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"


# Base Models
class BaseResponse(BaseModel):
    """Base response model with common fields."""
    success: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class ErrorDetail(BaseModel):
    """Detailed error information."""
    type: ErrorTypeEnum
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    field: Optional[str] = None


class APIError(BaseResponse):
    """Standard API error response."""
    success: bool = False
    error: ErrorDetail
    help_url: Optional[str] = None


class ValidationError(APIError):
    """Validation error response."""
    error: ErrorDetail = Field(..., example={
        "type": "validation_error",
        "code": "INVALID_INPUT",
        "message": "Request validation failed",
        "details": {"field": "sources", "issue": "URL format invalid"}
    })


# Authentication Models
class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    scope: List[str] = []


class APIKeyRequest(BaseModel):
    """API key creation request."""
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable key name")
    scopes: List[str] = Field(..., description="List of permissions for the API key")
    expires_days: Optional[int] = Field(None, ge=1, le=365, description="Expiration in days")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")


class APIKeyResponse(BaseModel):
    """API key creation response."""
    key_id: str
    name: str
    api_key: str
    scopes: List[str]
    expires_at: Optional[datetime]
    created_at: datetime


class APIKeyInfo(BaseModel):
    """API key information (without sensitive data)."""
    key_id: str
    name: str
    scopes: List[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used: Optional[datetime]
    usage_count: int


# Ingestion Models
class SourceInput(BaseModel):
    """Individual source input for ingestion."""
    url: Union[HttpUrl, str] = Field(..., description="URL or source identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    priority: Optional[int] = Field(1, ge=1, le=10, description="Processing priority (1-10)")


class IngestRequest(BaseModel):
    """Document ingestion request."""
    sources: List[Union[HttpUrl, str]] = Field(
        ..., 
        min_items=1, 
        max_items=100,
        description="List of URLs or sources to ingest"
    )
    options: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Processing options and configuration"
    )
    callback_url: Optional[HttpUrl] = Field(
        None, 
        description="Webhook URL for processing notifications"
    )
    async_processing: bool = Field(
        False, 
        description="Process asynchronously and return job ID"
    )
    
    @validator('sources')
    def validate_sources(cls, v):
        """Validate source URLs."""
        if not v:
            raise ValueError("At least one source is required")
        return v


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    title: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[datetime] = None
    source_url: Optional[str] = None
    content_type: ContentTypeEnum = ContentTypeEnum.UNKNOWN
    language: Optional[str] = None
    word_count: Optional[int] = None
    summary: Optional[str] = None
    keywords: List[str] = []
    topics: List[str] = []
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    """Individual processing result."""
    source: str
    success: bool
    document_id: Optional[str] = None
    processing_time: float
    error_message: Optional[str] = None
    error_type: Optional[ErrorTypeEnum] = None
    metadata: Optional[DocumentMetadata] = None
    warnings: List[str] = []


class IngestResponse(BaseResponse):
    """Document ingestion response."""
    job_id: Optional[str] = None  # For async processing
    results: List[ProcessingResult]
    total_processed: int
    successful_count: int
    failed_count: int
    processing_time: float
    stats: Dict[str, Any] = Field(default_factory=dict)


class JobStatus(BaseModel):
    """Async job status."""
    job_id: str
    status: ProcessingStatusEnum
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    progress: float = Field(0.0, ge=0.0, le=1.0)  # 0.0 to 1.0
    total_items: int
    completed_items: int
    failed_items: int
    results: List[ProcessingResult] = []
    error_message: Optional[str] = None


class JobStatusResponse(BaseResponse):
    """Job status response."""
    job: JobStatus


# Search Models
class SearchRequest(BaseModel):
    """Document search request."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")
    include_content: bool = Field(False, description="Include document content in results")
    similarity_threshold: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0, 
        description="Minimum similarity score (0.0-1.0)"
    )
    
    @validator('query')
    def validate_query(cls, v):
        """Validate search query."""
        if not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()


class SearchResultItem(BaseModel):
    """Individual search result item."""
    id: str
    title: str
    content_preview: str
    content: Optional[str] = None  # Full content if requested
    score: float = Field(..., ge=0.0, le=1.0)
    metadata: DocumentMetadata
    source_url: Optional[str] = None
    highlighted_snippets: List[str] = []


class SearchResponse(BaseResponse):
    """Document search response."""
    query: str
    results: List[SearchResultItem]
    total_results: int
    returned_count: int
    offset: int
    processing_time: float
    suggestions: List[str] = []  # Query suggestions


# Document Models
class DocumentSummary(BaseModel):
    """Document summary information."""
    id: str
    title: Optional[str]
    content_type: ContentTypeEnum
    source_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: DocumentMetadata
    content_length: int


class DocumentDetail(DocumentSummary):
    """Detailed document information."""
    content: str
    embedding_info: Optional[Dict[str, Any]] = None
    processing_info: Dict[str, Any] = Field(default_factory=dict)


class DocumentListRequest(BaseModel):
    """Document listing request."""
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    content_type: Optional[ContentTypeEnum] = None
    sort_by: str = Field("created_at", description="Sort field")
    sort_order: str = Field("desc", regex="^(asc|desc)$")
    search: Optional[str] = Field(None, max_length=200, description="Search in titles/metadata")


class DocumentListResponse(BaseResponse):
    """Document listing response."""
    documents: List[DocumentSummary]
    total_count: int
    returned_count: int
    offset: int
    has_more: bool


class DocumentResponse(BaseResponse):
    """Single document response."""
    document: DocumentDetail


class DeleteResponse(BaseResponse):
    """Delete operation response."""
    deleted_id: str
    message: str = "Document deleted successfully"


# Plugin Models
class PluginInfo(BaseModel):
    """Plugin information."""
    name: str
    type: str
    version: str
    description: Optional[str]
    enabled: bool
    configuration: Dict[str, Any] = Field(default_factory=dict)


class PluginListResponse(BaseResponse):
    """Plugin listing response."""
    plugins: List[PluginInfo]
    total_count: int


# System Models
class SystemInfo(BaseModel):
    """System information."""
    version: str
    environment: str
    debug_mode: bool
    uptime_seconds: float
    start_time: datetime


class SystemStats(BaseModel):
    """System statistics."""
    total_documents: int
    total_searches: int
    avg_processing_time: float
    storage_usage: Dict[str, Any]
    performance_metrics: Dict[str, Any]


class SystemStatusResponse(BaseResponse):
    """System status response."""
    status: str  # healthy, degraded, unhealthy
    system_info: SystemInfo
    stats: SystemStats
    components: Dict[str, Dict[str, Any]]


# Batch Operations
class BatchOperationRequest(BaseModel):
    """Batch operation request."""
    operation: str = Field(..., description="Operation type")
    target_ids: List[str] = Field(..., min_items=1, max_items=1000)
    options: Dict[str, Any] = Field(default_factory=dict)


class BatchOperationResponse(BaseResponse):
    """Batch operation response."""
    operation: str
    total_items: int
    successful_items: int
    failed_items: int
    results: List[Dict[str, Any]]


# Configuration Models
class ConfigurationUpdate(BaseModel):
    """Configuration update request."""
    section: str
    settings: Dict[str, Any]
    validate_only: bool = False


class ConfigurationResponse(BaseResponse):
    """Configuration response."""
    current_config: Dict[str, Any]
    updated_fields: List[str] = []


# Export/Import Models
class ExportRequest(BaseModel):
    """Data export request."""
    format: str = Field("json", regex="^(json|csv|jsonl)$")
    filter_criteria: Optional[Dict[str, Any]] = None
    include_content: bool = True
    include_embeddings: bool = False


class ExportResponse(BaseResponse):
    """Data export response."""
    export_id: str
    format: str
    total_documents: int
    download_url: str
    expires_at: datetime


class ImportRequest(BaseModel):
    """Data import request."""
    source_url: HttpUrl
    format: str = Field("json", regex="^(json|csv|jsonl)$")
    options: Dict[str, Any] = Field(default_factory=dict)


class ImportResponse(BaseResponse):
    """Data import response."""
    import_id: str
    status: ProcessingStatusEnum
    total_items: int
    processed_items: int
    failed_items: int