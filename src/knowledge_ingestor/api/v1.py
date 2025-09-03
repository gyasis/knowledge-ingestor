"""
API v1 router for the Knowledge Ingestor API.

This module provides the complete v1 API implementation with:
- All core endpoints
- Authentication integration
- Enhanced error handling
- Comprehensive request/response models
- Async job processing
"""

import time
import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, Path
from fastapi.responses import JSONResponse

from ..core.config import get_config
from ..core.pipeline import ProcessingPipeline
from ..plugins.plugin_manager import get_plugin_manager
from ..utils.logging import get_logger
from .models import *
from .auth import (
    auth_manager, get_current_user, require_auth, require_api_key,
    require_ingest_scope, require_search_scope, require_admin_scope,
    APIKeyScope, UserRole, LoginRequest, TokenResponse, APIKeyRequest, APIKeyResponse
)
from .monitoring import prometheus_metrics

logger = get_logger(__name__)

# Create v1 router
api_v1_router = APIRouter(tags=["v1"])

# Global instances
config = get_config()
pipeline = ProcessingPipeline()

# Job storage (in production, use Redis or database)
job_store: Dict[str, JobStatus] = {}


# Authentication endpoints
@api_v1_router.post("/auth/login", response_model=TokenResponse, tags=["authentication"])
async def login(credentials: LoginRequest):
    """Authenticate user and return JWT token."""
    if not config.api.auth_enabled:
        raise HTTPException(
            status_code=501,
            detail="Authentication is not enabled"
        )
    
    user = auth_manager.authenticate_user(credentials.username, credentials.password)
    if not user:
        prometheus_metrics.record_error("authentication_failed", "auth")
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=auth_manager.access_token_expire_minutes)
    access_token = auth_manager.create_access_token(
        data={"sub": user.username, "scopes": [role.value for role in user.roles]},
        expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=auth_manager.access_token_expire_minutes * 60,
        scope=[role.value for role in user.roles]
    )


@api_v1_router.post("/auth/api-keys", response_model=APIKeyResponse, tags=["authentication"])
async def create_api_key(
    request: APIKeyRequest,
    current_user: Dict[str, Any] = Depends(require_auth(["admin", "user"]))
):
    """Create a new API key."""
    if not config.api.auth_enabled:
        raise HTTPException(
            status_code=501,
            detail="Authentication is not enabled"
        )
    
    # Validate scopes
    valid_scopes = [scope.value for scope in APIKeyScope]
    invalid_scopes = [s for s in request.scopes if s not in valid_scopes]
    if invalid_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scopes: {invalid_scopes}. Valid scopes: {valid_scopes}"
        )
    
    # Convert string scopes to enum
    scopes = [APIKeyScope(scope) for scope in request.scopes]
    
    # Generate API key
    key_id, api_key = auth_manager.generate_api_key(
        name=request.name,
        scopes=scopes,
        expires_days=request.expires_days
    )
    
    # Get key info for response
    key_info = auth_manager.api_keys_db[auth_manager._hash_key(api_key)]
    
    return APIKeyResponse(
        key_id=key_id,
        name=request.name,
        api_key=api_key,
        scopes=request.scopes,
        expires_at=key_info.get("expires_at"),
        created_at=key_info["created_at"]
    )


@api_v1_router.get("/auth/api-keys", response_model=List[APIKeyInfo], tags=["authentication"])
async def list_api_keys(current_user: Dict[str, Any] = Depends(require_auth(["admin"]))):
    """List all API keys (admin only)."""
    if not config.api.auth_enabled:
        raise HTTPException(
            status_code=501,
            detail="Authentication is not enabled"
        )
    
    return auth_manager.list_api_keys()


@api_v1_router.delete("/auth/api-keys/{key_id}", tags=["authentication"])
async def revoke_api_key(
    key_id: str = Path(..., description="API key ID to revoke"),
    current_user: Dict[str, Any] = Depends(require_auth(["admin"]))
):
    """Revoke an API key."""
    if not config.api.auth_enabled:
        raise HTTPException(
            status_code=501,
            detail="Authentication is not enabled"
        )
    
    success = auth_manager.revoke_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    
    return {"message": f"API key {key_id} revoked successfully"}


# Document ingestion endpoints
@api_v1_router.post("/ingest", response_model=IngestResponse, tags=["ingestion"])
async def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """
    Ingest documents from provided sources.
    
    Supports both synchronous and asynchronous processing.
    For large batches, use async_processing=True to get a job ID.
    """
    
    # Check authentication if enabled
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check API key scopes if using API key auth
    if current_user and current_user.get("auth_method") == "api_key":
        scopes = current_user.get("scopes", [])
        if "ingest" not in scopes and "admin" not in scopes:
            raise HTTPException(status_code=403, detail="Ingest scope required")
    
    start_time = time.time()
    sources = [str(source) for source in request.sources]
    
    logger.info(f"Received ingestion request for {len(sources)} sources (async: {request.async_processing})")
    
    # Record metrics
    prometheus_metrics.record_api_key_request(
        key_name=current_user.get("api_key", {}).get("name", "unknown") if current_user else "anonymous",
        status_code=200
    )
    
    if request.async_processing and len(sources) > 5:
        # Async processing for large batches
        job_id = str(uuid.uuid4())
        job_status = JobStatus(
            job_id=job_id,
            status=ProcessingStatusEnum.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_items=len(sources),
            completed_items=0,
            failed_items=0,
            results=[]
        )
        job_store[job_id] = job_status
        
        # Start background processing
        background_tasks.add_task(
            process_documents_async, 
            job_id, 
            sources, 
            request.options
        )
        
        return IngestResponse(
            job_id=job_id,
            results=[],
            total_processed=0,
            successful_count=0,
            failed_count=0,
            processing_time=0.0,
            stats={"message": "Processing started in background"}
        )
    
    else:
        # Synchronous processing
        try:
            results = pipeline.process_batch(sources, **request.options)
            
            # Format response
            formatted_results = []
            successful_count = 0
            
            for i, result in enumerate(results):
                processing_result = ProcessingResult(
                    source=sources[i],
                    success=result.success,
                    processing_time=result.processing_time,
                    error_message=result.error if not result.success else None,
                    error_type=ErrorTypeEnum.PROCESSING_ERROR if not result.success else None
                )
                
                if result.success and result.document:
                    processing_result.document_id = result.document.id
                    processing_result.metadata = DocumentMetadata(
                        title=result.document.metadata.title,
                        content_type=ContentTypeEnum(result.document.metadata.content_type.value),
                        word_count=result.document.metadata.word_count,
                        source_url=sources[i]
                    )
                    successful_count += 1
                    
                    # Record metrics
                    prometheus_metrics.record_document_ingestion(
                        status="success",
                        content_type=result.document.metadata.content_type.value,
                        duration=result.processing_time
                    )
                else:
                    prometheus_metrics.record_document_ingestion(
                        status="failed",
                        content_type="unknown",
                        duration=result.processing_time
                    )
                
                formatted_results.append(processing_result)
            
            processing_time = time.time() - start_time
            stats = pipeline.get_statistics()
            
            return IngestResponse(
                results=formatted_results,
                total_processed=len(sources),
                successful_count=successful_count,
                failed_count=len(sources) - successful_count,
                processing_time=processing_time,
                stats=vars(stats)
            )
            
        except Exception as e:
            prometheus_metrics.record_error("ingestion_error", "pipeline")
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@api_v1_router.get("/ingest/{job_id}/status", response_model=JobStatusResponse, tags=["ingestion"])
async def get_job_status(
    job_id: str = Path(..., description="Job ID to check"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """Get the status of an async ingestion job."""
    
    # Check authentication if enabled
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(job=job)


# Search endpoints
@api_v1_router.post("/search", response_model=SearchResponse, tags=["search"])
async def search_documents(
    request: SearchRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """
    Search documents using semantic similarity.
    
    Supports filtering, pagination, and configurable similarity thresholds.
    """
    
    # Check authentication if enabled
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check API key scopes if using API key auth
    if current_user and current_user.get("auth_method") == "api_key":
        scopes = current_user.get("scopes", [])
        if "search" not in scopes and "readonly" not in scopes and "admin" not in scopes:
            raise HTTPException(status_code=403, detail="Search scope required")
    
    start_time = time.time()
    
    try:
        # Get database instance
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Perform search
        search_results = database.search_similar(
            query=request.query,
            k=request.limit,
            filters=request.filters,
            similarity_threshold=request.similarity_threshold
        )
        
        # Format results
        formatted_results = []
        for result in search_results[:request.limit]:  # Ensure limit is respected
            search_item = SearchResultItem(
                id=result.get("id", ""),
                title=result.get("metadata", {}).get("title", "Untitled"),
                content_preview=result.get("text", "")[:500] + "..." if len(result.get("text", "")) > 500 else result.get("text", ""),
                score=float(result.get("score", 0.0)),
                metadata=DocumentMetadata(
                    title=result.get("metadata", {}).get("title"),
                    source_url=result.get("metadata", {}).get("web_address"),
                    content_type=ContentTypeEnum(result.get("metadata", {}).get("content_type", "unknown"))
                ),
                source_url=result.get("metadata", {}).get("web_address")
            )
            
            # Include full content if requested
            if request.include_content:
                search_item.content = result.get("text", "")
            
            formatted_results.append(search_item)
        
        processing_time = time.time() - start_time
        
        # Record metrics
        prometheus_metrics.record_search_request(processing_time)
        if current_user and current_user.get("auth_method") == "api_key":
            prometheus_metrics.record_api_key_request(
                key_name=current_user.get("api_key", {}).get("name", "unknown"),
                status_code=200
            )
        
        return SearchResponse(
            query=request.query,
            results=formatted_results,
            total_results=len(search_results),
            returned_count=len(formatted_results),
            offset=request.offset,
            processing_time=processing_time
        )
        
    except Exception as e:
        prometheus_metrics.record_error("search_error", "database")
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# Document management endpoints
@api_v1_router.get("/documents", response_model=DocumentListResponse, tags=["documents"])
async def list_documents(
    request: DocumentListRequest = Depends(),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """List documents with pagination and filtering."""
    
    # Check authentication if enabled
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Get documents (implement filtering in database layer)
        documents = database.list_documents(
            limit=request.limit,
            offset=request.offset,
            content_type=request.content_type.value if request.content_type else None,
            sort_by=request.sort_by,
            sort_order=request.sort_order,
            search=request.search
        )
        
        # Format response
        formatted_docs = []
        for doc in documents:
            doc_summary = DocumentSummary(
                id=doc.get("id", ""),
                title=doc.get("metadata", {}).get("title"),
                content_type=ContentTypeEnum(doc.get("metadata", {}).get("content_type", "unknown")),
                source_url=doc.get("metadata", {}).get("web_address"),
                created_at=datetime.fromisoformat(doc.get("created_at", datetime.utcnow().isoformat())),
                updated_at=datetime.fromisoformat(doc.get("updated_at", datetime.utcnow().isoformat())),
                metadata=DocumentMetadata(**doc.get("metadata", {})),
                content_length=len(doc.get("text", ""))
            )
            formatted_docs.append(doc_summary)
        
        total_count = database.get_document_count() if hasattr(database, 'get_document_count') else len(documents)
        
        return DocumentListResponse(
            documents=formatted_docs,
            total_count=total_count,
            returned_count=len(formatted_docs),
            offset=request.offset,
            has_more=len(formatted_docs) == request.limit
        )
        
    except Exception as e:
        logger.error(f"Document listing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document listing failed: {str(e)}")


@api_v1_router.get("/documents/{doc_id}", response_model=DocumentResponse, tags=["documents"])
async def get_document(
    doc_id: str = Path(..., description="Document ID"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """Get a specific document by ID."""
    
    # Check authentication if enabled
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Retrieve document
        document = database.retrieve_document(doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc_detail = DocumentDetail(
            id=document.id,
            title=document.metadata.title,
            content_type=ContentTypeEnum(document.metadata.content_type.value),
            source_url=document.metadata.source_url,
            created_at=document.created_at,
            updated_at=document.updated_at,
            metadata=DocumentMetadata(**document.metadata.dict()),
            content_length=len(document.content),
            content=document.content
        )
        
        return DocumentResponse(document=doc_detail)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document retrieval failed: {str(e)}")


@api_v1_router.delete("/documents/{doc_id}", response_model=DeleteResponse, tags=["documents"])
async def delete_document(
    doc_id: str = Path(..., description="Document ID"),
    current_user: Dict[str, Any] = Depends(require_auth(["admin", "user"]))
):
    """Delete a document by ID."""
    
    try:
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Delete document
        success = database.delete_document(doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found or could not be deleted")
        
        return DeleteResponse(deleted_id=doc_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document deletion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document deletion failed: {str(e)}")


# System endpoints
@api_v1_router.get("/plugins", response_model=PluginListResponse, tags=["admin"])
async def list_plugins(current_user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    """List available plugins."""
    
    # Check authentication if enabled
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        plugin_manager = get_plugin_manager()
        plugins_info = plugin_manager.list_available_plugins()
        
        formatted_plugins = []
        for plugin_info in plugins_info:
            plugin = PluginInfo(
                name=plugin_info.get("name", "Unknown"),
                type=plugin_info.get("type", "Unknown"),
                version=plugin_info.get("version", "Unknown"),
                description=plugin_info.get("description"),
                enabled=plugin_info.get("enabled", False),
                configuration=plugin_info.get("config", {})
            )
            formatted_plugins.append(plugin)
        
        return PluginListResponse(
            plugins=formatted_plugins,
            total_count=len(formatted_plugins)
        )
        
    except Exception as e:
        logger.error(f"Plugin listing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Plugin listing failed: {str(e)}")


@api_v1_router.get("/stats", response_model=Dict[str, Any], tags=["admin"])
async def get_statistics(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """Get system statistics."""
    
    # Check authentication if enabled  
    if config.api.auth_enabled and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Get pipeline statistics
        pipeline_stats = pipeline.get_statistics()
        
        # Get database statistics
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        db_stats = database.get_stats() if database and hasattr(database, 'get_stats') else {}
        
        return {
            "pipeline": vars(pipeline_stats),
            "database": db_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Statistics retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Statistics retrieval failed: {str(e)}")


# Async job processing function
async def process_documents_async(job_id: str, sources: List[str], options: Dict[str, Any]):
    """Process documents asynchronously and update job status."""
    
    job = job_store[job_id]
    job.status = ProcessingStatusEnum.PROCESSING
    job.updated_at = datetime.utcnow()
    
    try:
        results = pipeline.process_batch(sources, **options)
        
        # Update job with results
        formatted_results = []
        successful_count = 0
        
        for i, result in enumerate(results):
            processing_result = ProcessingResult(
                source=sources[i],
                success=result.success,
                processing_time=result.processing_time,
                error_message=result.error if not result.success else None
            )
            
            if result.success and result.document:
                processing_result.document_id = result.document.id
                processing_result.metadata = DocumentMetadata(
                    title=result.document.metadata.title,
                    content_type=ContentTypeEnum(result.document.metadata.content_type.value),
                    word_count=result.document.metadata.word_count
                )
                successful_count += 1
            
            formatted_results.append(processing_result)
            
            # Update progress
            job.completed_items = i + 1
            job.progress = (i + 1) / len(sources)
            job.updated_at = datetime.utcnow()
        
        # Final update
        job.results = formatted_results
        job.completed_items = len(sources)
        job.failed_items = len(sources) - successful_count
        job.status = ProcessingStatusEnum.COMPLETED
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        
    except Exception as e:
        # Handle processing error
        job.status = ProcessingStatusEnum.FAILED
        job.error_message = str(e)
        job.updated_at = datetime.utcnow()
        logger.error(f"Async processing failed for job {job_id}: {e}", exc_info=True)