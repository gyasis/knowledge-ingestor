"""
FastAPI routes for the Knowledge Ingestor system.

This module provides REST API endpoints for document ingestion,
search, and system management.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Any, Optional, Union
import asyncio
from pathlib import Path
import time

from ..core.pipeline import ProcessingPipeline, ProcessingResult
from ..core.document import Document, ContentType, ProcessingStatus
from ..core.config import get_config
from ..plugins.plugin_manager import get_plugin_manager, initialize_plugin_system
from ..utils.logging import setup_logging, get_logger

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Initialize plugin system
logger.info("Initializing plugin system...")
plugin_count = initialize_plugin_system()
logger.info(f"Loaded {plugin_count} plugins")

# Create FastAPI app
config = get_config()
app = FastAPI(
    title="Knowledge Ingestor API",
    description="REST API for the Knowledge Ingestor document processing system",
    version="1.0.0",
    debug=config.api.debug
)

# Configure CORS
if config.api.cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Global pipeline instance
pipeline = ProcessingPipeline()


# Request/Response Models
class IngestRequest(BaseModel):
    """Request model for document ingestion."""
    sources: List[Union[HttpUrl, str]] = Field(..., description="List of URLs or sources to ingest")
    options: Dict[str, Any] = Field(default_factory=dict, description="Additional processing options")


class IngestResponse(BaseModel):
    """Response model for document ingestion."""
    success: bool
    message: str
    results: List[Dict[str, Any]]
    stats: Dict[str, Any]


class SearchRequest(BaseModel):
    """Request model for document search."""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=5, ge=1, le=100, description="Number of results to return")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")


class SearchResponse(BaseModel):
    """Response model for document search."""
    query: str
    results: List[Dict[str, Any]]
    total_results: int
    processing_time: float


class SystemStatusResponse(BaseModel):
    """Response model for system status."""
    status: str
    version: str
    uptime: float
    health: Dict[str, Any]
    stats: Dict[str, Any]


# Dependency functions
def get_pipeline() -> ProcessingPipeline:
    """Dependency to get the processing pipeline."""
    return pipeline


def get_plugin_manager_instance():
    """Dependency to get the plugin manager."""
    return get_plugin_manager()


# API Routes

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with basic API information."""
    return {
        "name": "Knowledge Ingestor API",
        "version": "1.0.0",
        "description": "Document processing and ingestion system",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=SystemStatusResponse)
async def health_check(pipeline_instance: ProcessingPipeline = Depends(get_pipeline)):
    """Health check endpoint."""
    start_time = time.time()
    
    try:
        # Perform health checks
        health = pipeline_instance.health_check()
        stats = pipeline_instance.get_statistics()
        
        status = "healthy" if health.get('pipeline', False) else "unhealthy"
        
        return SystemStatusResponse(
            status=status,
            version="1.0.0",
            uptime=time.time() - start_time,
            health=health,
            stats=stats.dict() if hasattr(stats, 'dict') else vars(stats)
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    pipeline_instance: ProcessingPipeline = Depends(get_pipeline)
):
    """Ingest documents from provided sources."""
    try:
        sources = [str(source) for source in request.sources]
        logger.info(f"Received ingestion request for {len(sources)} sources")
        
        # Process sources
        results = pipeline_instance.process_batch(sources, **request.options)
        
        # Format response
        formatted_results = []
        successful_count = 0
        
        for i, result in enumerate(results):
            formatted_result = {
                "source": sources[i],
                "success": result.success,
                "processing_time": result.processing_time,
                "error": result.error if not result.success else None,
                "metadata": result.metadata or {}
            }
            
            if result.success and result.document:
                formatted_result.update({
                    "document_id": result.document.id,
                    "title": result.document.metadata.title,
                    "content_type": result.document.metadata.content_type.value,
                    "word_count": result.document.metadata.word_count
                })
                successful_count += 1
            
            formatted_results.append(formatted_result)
        
        # Get updated stats
        stats = pipeline_instance.get_statistics()
        
        return IngestResponse(
            success=successful_count > 0,
            message=f"Processed {len(sources)} sources, {successful_count} successful",
            results=formatted_results,
            stats=vars(stats)
        )
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    plugin_manager_instance = Depends(get_plugin_manager_instance)
):
    """Search documents by similarity."""
    start_time = time.time()
    
    try:
        # Get database instance
        database = plugin_manager_instance.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Perform search
        search_results = database.search_similar(
            query=request.query,
            k=request.limit,
            filters=request.filters
        )
        
        # Format results
        formatted_results = []
        for result in search_results:
            formatted_results.append({
                "id": result.get("id"),
                "title": result.get("metadata", {}).get("title", "Untitled"),
                "content_preview": result.get("text", "")[:500] + "..." if len(result.get("text", "")) > 500 else result.get("text", ""),
                "score": result.get("score", 0.0),
                "metadata": result.get("metadata", {}),
                "source_url": result.get("metadata", {}).get("web_address")
            })
        
        processing_time = time.time() - start_time
        
        return SearchResponse(
            query=request.query,
            results=formatted_results,
            total_results=len(formatted_results),
            processing_time=processing_time
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/documents", response_model=Dict[str, Any])
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100, description="Number of documents to return"),
    offset: int = Query(default=0, ge=0, description="Number of documents to skip"),
    plugin_manager_instance = Depends(get_plugin_manager_instance)
):
    """List documents in the database."""
    try:
        # Get database instance
        database = plugin_manager_instance.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # List documents
        documents = database.list_documents(limit=limit, offset=offset)
        
        # Format response
        formatted_docs = []
        for doc in documents:
            formatted_docs.append({
                "id": doc.get("id"),
                "metadata": doc.get("metadata", {})
            })
        
        return {
            "documents": formatted_docs,
            "count": len(formatted_docs),
            "offset": offset,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Document listing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Document listing failed: {str(e)}")


@app.get("/documents/{doc_id}", response_model=Dict[str, Any])
async def get_document(
    doc_id: str,
    plugin_manager_instance = Depends(get_plugin_manager_instance)
):
    """Get a specific document by ID."""
    try:
        # Get database instance
        database = plugin_manager_instance.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Retrieve document
        document = database.retrieve_document(doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {
            "id": document.id,
            "content": document.content,
            "metadata": document.metadata.dict(),
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Document retrieval failed: {str(e)}")


@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    plugin_manager_instance = Depends(get_plugin_manager_instance)
):
    """Delete a document by ID."""
    try:
        # Get database instance
        database = plugin_manager_instance.get_database()
        if not database:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Delete document
        success = database.delete_document(doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found or could not be deleted")
        
        return {"message": f"Document {doc_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document deletion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Document deletion failed: {str(e)}")


@app.get("/plugins", response_model=Dict[str, Any])
async def list_plugins(plugin_manager_instance = Depends(get_plugin_manager_instance)):
    """List available plugins."""
    try:
        plugins = plugin_manager_instance.list_available_plugins()
        
        return {
            "plugins": plugins,
            "count": len(plugins)
        }
        
    except Exception as e:
        logger.error(f"Plugin listing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Plugin listing failed: {str(e)}")


@app.get("/stats", response_model=Dict[str, Any])
async def get_statistics(
    pipeline_instance: ProcessingPipeline = Depends(get_pipeline),
    plugin_manager_instance = Depends(get_plugin_manager_instance)
):
    """Get system statistics."""
    try:
        # Get pipeline statistics
        pipeline_stats = pipeline_instance.get_statistics()
        
        # Get database statistics
        database = plugin_manager_instance.get_database()
        db_stats = database.get_stats() if database else {}
        
        return {
            "pipeline": vars(pipeline_stats),
            "database": db_stats,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Statistics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics retrieval failed: {str(e)}")


@app.post("/reset-stats")
async def reset_statistics(pipeline_instance: ProcessingPipeline = Depends(get_pipeline)):
    """Reset pipeline statistics."""
    try:
        pipeline_instance.reset_statistics()
        return {"message": "Statistics reset successfully"}
        
    except Exception as e:
        logger.error(f"Statistics reset failed: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics reset failed: {str(e)}")


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception in {request.method} {request.url}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    logger.info("Knowledge Ingestor API starting up...")
    
    # Initialize database connection
    try:
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        if database:
            database.connect()
            logger.info("Database connection established")
        else:
            logger.warning("No database plugin configured")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
    
    logger.info("Knowledge Ingestor API ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    logger.info("Knowledge Ingestor API shutting down...")
    
    # Cleanup database connection
    try:
        plugin_manager = get_plugin_manager()
        database = plugin_manager.get_database()
        if database:
            database.disconnect()
            logger.info("Database connection closed")
        
        # Shutdown plugin manager
        plugin_manager.shutdown()
        logger.info("Plugin manager shutdown complete")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    
    logger.info("Knowledge Ingestor API shutdown complete")


if __name__ == "__main__":
    import uvicorn
    
    # Configuration
    host = config.api.host
    port = config.api.port
    debug = config.api.debug
    
    logger.info(f"Starting Knowledge Ingestor API on {host}:{port}")
    
    uvicorn.run(
        "knowledge_ingestor.api.routes:app",
        host=host,
        port=port,
        debug=debug,
        reload=debug,
        log_level="info" if not debug else "debug"
    )