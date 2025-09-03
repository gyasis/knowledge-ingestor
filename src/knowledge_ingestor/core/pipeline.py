"""
Processing pipeline for the Knowledge Ingestor system.

This module provides the main processing pipeline that coordinates document
ingestion, processing, and storage using the plugin system.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Union, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading
from dataclasses import dataclass

from .document import Document, DocumentBatch, ProcessingStatus
from .config import get_config
from ..plugins.plugin_manager import get_plugin_manager
from ..plugins.base import BaseIngestor, BaseDatabase


@dataclass 
class ProcessingResult:
    """Result of a processing operation."""
    success: bool
    document: Optional[Document] = None
    error: Optional[str] = None
    processing_time: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class PipelineStats:
    """Statistics for pipeline execution."""
    total_sources: int = 0
    successful_ingestions: int = 0
    failed_ingestions: int = 0
    successful_storage: int = 0
    failed_storage: int = 0
    total_processing_time: float = 0.0
    average_processing_time: float = 0.0
    
    def update_averages(self):
        """Update calculated fields."""
        if self.successful_ingestions > 0:
            self.average_processing_time = self.total_processing_time / self.successful_ingestions


class ProcessingPipeline:
    """
    Main processing pipeline for document ingestion and storage.
    
    This class coordinates the entire document processing workflow:
    1. Source routing to appropriate ingestors
    2. Content extraction and document creation
    3. Document processing and enhancement
    4. Storage in configured database
    5. Error handling and reporting
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the processing pipeline."""
        self.config = config or get_config().processing.dict()
        self.plugin_manager = get_plugin_manager()
        self.logger = self._setup_logging()
        
        # Processing configuration
        self.max_workers = self.config.get('max_workers', 4)
        self.processing_timeout = self.config.get('processing_timeout', 300)
        self.chunk_size = self.config.get('chunk_size', 1000)
        self.chunk_overlap = self.config.get('chunk_overlap', 200)
        
        # Statistics
        self.stats = PipelineStats()
        self.stats_lock = threading.Lock()
        
        # Processing hooks
        self.pre_ingestion_hooks: List[Callable] = []
        self.post_ingestion_hooks: List[Callable] = []
        self.pre_storage_hooks: List[Callable] = []
        self.post_storage_hooks: List[Callable] = []
    
    def _setup_logging(self):
        """Setup logging for the pipeline."""
        import logging
        logger = logging.getLogger(self.__class__.__name__)
        return logger
    
    def add_pre_ingestion_hook(self, hook: Callable[[Union[str, Path]], Union[str, Path]]) -> None:
        """Add a pre-ingestion hook that can modify sources before processing."""
        self.pre_ingestion_hooks.append(hook)
    
    def add_post_ingestion_hook(self, hook: Callable[[Document], Document]) -> None:
        """Add a post-ingestion hook that can modify documents after extraction."""
        self.post_ingestion_hooks.append(hook)
    
    def add_pre_storage_hook(self, hook: Callable[[Document], Document]) -> None:
        """Add a pre-storage hook that can modify documents before storage.""" 
        self.pre_storage_hooks.append(hook)
    
    def add_post_storage_hook(self, hook: Callable[[Document, str], None]) -> None:
        """Add a post-storage hook that runs after successful storage."""
        self.post_storage_hooks.append(hook)
    
    def process_single(self, source: Union[str, Path], **kwargs) -> ProcessingResult:
        """
        Process a single source through the complete pipeline.
        
        Args:
            source: Source to process (URL, file path, etc.)
            **kwargs: Additional parameters for processing
            
        Returns:
            ProcessingResult: Result of the processing operation
        """
        start_time = time.time()
        
        try:
            # Apply pre-ingestion hooks
            processed_source = source
            for hook in self.pre_ingestion_hooks:
                processed_source = hook(processed_source)
            
            # Find appropriate ingestor
            ingestor = self.plugin_manager.get_ingestor_for_source(processed_source)
            if not ingestor:
                error = f"No suitable ingestor found for source: {source}"
                self.logger.error(error)
                return ProcessingResult(
                    success=False,
                    error=error,
                    processing_time=time.time() - start_time
                )
            
            # Extract content
            self.logger.info(f"Processing {source} with {ingestor.metadata.name}")
            document = ingestor.extract_content(processed_source, **kwargs)
            
            # Apply post-ingestion hooks
            for hook in self.post_ingestion_hooks:
                document = hook(document)
            
            # Process document chunks if needed
            if not document.chunks:
                document.chunks = self._chunk_content(document.content)
            
            # Apply pre-storage hooks
            for hook in self.pre_storage_hooks:
                document = hook(document)
            
            # Store in database
            database = self.plugin_manager.get_database()
            if database:
                try:
                    doc_id = database.store_document(document)
                    document.id = doc_id
                    
                    # Apply post-storage hooks
                    for hook in self.post_storage_hooks:
                        hook(document, doc_id)
                    
                    self.logger.info(f"Successfully stored document: {doc_id}")
                    
                    # Update stats
                    with self.stats_lock:
                        self.stats.successful_storage += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to store document: {e}")
                    with self.stats_lock:
                        self.stats.failed_storage += 1
            else:
                self.logger.warning("No database configured - document not stored")
            
            # Update stats
            processing_time = time.time() - start_time
            with self.stats_lock:
                self.stats.successful_ingestions += 1
                self.stats.total_processing_time += processing_time
                self.stats.update_averages()
            
            return ProcessingResult(
                success=True,
                document=document,
                processing_time=processing_time,
                metadata={
                    'ingestor_used': ingestor.metadata.name,
                    'content_type': document.metadata.content_type.value,
                    'word_count': document.metadata.word_count,
                    'has_embedding': document.embedding is not None
                }
            )
            
        except Exception as e:
            error = f"Pipeline processing failed for {source}: {str(e)}"
            self.logger.error(error)
            
            # Update stats
            with self.stats_lock:
                self.stats.failed_ingestions += 1
            
            return ProcessingResult(
                success=False,
                error=error,
                processing_time=time.time() - start_time
            )
    
    def process_batch(
        self, 
        sources: List[Union[str, Path]], 
        max_workers: Optional[int] = None,
        **kwargs
    ) -> List[ProcessingResult]:
        """
        Process multiple sources concurrently.
        
        Args:
            sources: List of sources to process
            max_workers: Maximum number of concurrent workers (defaults to config)
            **kwargs: Additional parameters for processing
            
        Returns:
            List[ProcessingResult]: Results for each source
        """
        if not sources:
            return []
        
        workers = max_workers or self.max_workers
        self.logger.info(f"Processing {len(sources)} sources with {workers} workers")
        
        # Update stats
        with self.stats_lock:
            self.stats.total_sources += len(sources)
        
        # Process with thread pool
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self.process_single, source, **kwargs) 
                for source in sources
            ]
            
            results = []
            for i, future in enumerate(futures):
                try:
                    result = future.result(timeout=self.processing_timeout)
                    results.append(result)
                    
                    if result.success:
                        self.logger.debug(f"Completed {i+1}/{len(sources)}: {sources[i]}")
                    else:
                        self.logger.warning(f"Failed {i+1}/{len(sources)}: {sources[i]} - {result.error}")
                        
                except Exception as e:
                    error = f"Processing timeout or error for {sources[i]}: {str(e)}"
                    self.logger.error(error)
                    results.append(ProcessingResult(
                        success=False,
                        error=error,
                        processing_time=self.processing_timeout
                    ))
        
        return results
    
    def process_document_batch(self, documents: DocumentBatch) -> List[ProcessingResult]:
        """
        Process a batch of pre-created documents.
        
        Args:
            documents: DocumentBatch to process
            
        Returns:
            List[ProcessingResult]: Processing results
        """
        results = []
        database = self.plugin_manager.get_database()
        
        if not database:
            error = "No database configured for document storage"
            self.logger.error(error)
            return [ProcessingResult(success=False, error=error) for _ in documents.documents]
        
        try:
            # Store all documents at once for efficiency
            doc_ids = database.store_documents(documents.documents)
            
            for i, (doc, doc_id) in enumerate(zip(documents.documents, doc_ids)):
                doc.id = doc_id
                
                # Apply post-storage hooks
                for hook in self.post_storage_hooks:
                    hook(doc, doc_id)
                
                results.append(ProcessingResult(
                    success=True,
                    document=doc,
                    metadata={'batch_processed': True, 'doc_id': doc_id}
                ))
            
            # Update stats
            with self.stats_lock:
                self.stats.successful_storage += len(documents.documents)
            
            self.logger.info(f"Successfully processed document batch: {len(documents.documents)} documents")
            
        except Exception as e:
            error = f"Failed to process document batch: {str(e)}"
            self.logger.error(error)
            
            # Return failed results for all documents
            with self.stats_lock:
                self.stats.failed_storage += len(documents.documents)
            
            results = [
                ProcessingResult(success=False, error=error, document=doc)
                for doc in documents.documents
            ]
        
        return results
    
    def _chunk_content(self, content: str) -> List[str]:
        """
        Split content into chunks for processing.
        
        Args:
            content: Content to chunk
            
        Returns:
            List[str]: Content chunks
        """
        if not content:
            return []
        
        # Simple chunking implementation
        chunks = []
        words = content.split()
        
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + 1  # +1 for space
            
            if current_length + word_length > self.chunk_size and current_chunk:
                # Create chunk from current words
                chunk = ' '.join(current_chunk)
                chunks.append(chunk)
                
                # Start new chunk with overlap
                overlap_words = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else current_chunk
                current_chunk = overlap_words + [word]
                current_length = sum(len(w) + 1 for w in current_chunk)
            else:
                current_chunk.append(word)
                current_length += word_length
        
        # Add final chunk
        if current_chunk:
            chunk = ' '.join(current_chunk)
            chunks.append(chunk)
        
        return chunks
    
    def get_statistics(self) -> PipelineStats:
        """Get processing statistics."""
        with self.stats_lock:
            return self.stats
    
    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        with self.stats_lock:
            self.stats = PipelineStats()
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check of the pipeline components.
        
        Returns:
            Dict[str, Any]: Health status of components
        """
        health = {
            'pipeline': True,
            'plugin_manager': True,
            'ingestors': {},
            'database': None,
            'errors': []
        }
        
        try:
            # Check plugin manager
            if not self.plugin_manager:
                health['plugin_manager'] = False
                health['errors'].append("Plugin manager not initialized")
            
            # Check available ingestors
            plugin_info = self.plugin_manager.list_available_plugins()
            for name, info in plugin_info.items():
                if 'error' in info:
                    health['ingestors'][name] = False
                    health['errors'].append(f"Ingestor {name}: {info['error']}")
                else:
                    health['ingestors'][name] = True
            
            # Check database
            database = self.plugin_manager.get_database()
            if database:
                health['database'] = database.health_check()
                if not health['database']:
                    health['errors'].append("Database health check failed")
            else:
                health['database'] = False
                health['errors'].append("No database configured")
            
            # Overall health status
            health['pipeline'] = (
                health['plugin_manager'] and 
                health['database'] and 
                any(health['ingestors'].values())
            )
            
        except Exception as e:
            health['pipeline'] = False
            health['errors'].append(f"Health check error: {str(e)}")
        
        return health