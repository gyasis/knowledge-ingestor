"""
Main manager class that orchestrates the knowledge ingestion pipeline.

This module provides the KnowledgeIngestorManager class that coordinates
plugin initialization, content processing, and storage operations.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from .config import Config
from .base import (
    PluginRegistry, BaseIngestor, BaseDatabaseBackend, BaseEmbeddingProvider,
    Document, ProcessingResult, SearchResult
)
from .exceptions import (
    KnowledgeIngestorError, PluginError, IngestionError, DatabaseError
)
from ..plugins.loader import PluginLoader


class KnowledgeIngestorManager:
    """Main manager class for the knowledge ingestion system."""
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the Knowledge Ingestor Manager.
        
        Args:
            config: Configuration object. If None, loads default configuration.
        """
        self.config = config or Config()
        self.config.validate()
        
        # Setup logging
        self._setup_logging()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize components
        self.registry = PluginRegistry()
        self.plugin_loader = PluginLoader(self.config.plugins, self.logger)
        
        # Plugin instances
        self.default_ingestor: Optional[BaseIngestor] = None
        self.default_database: Optional[BaseDatabaseBackend] = None
        self.default_embedding_provider: Optional[BaseEmbeddingProvider] = None
        
        self._initialized = False
        self.logger.info("KnowledgeIngestorManager initialized")
    
    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        log_config = self.config.logging
        
        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, log_config.level.upper()),
            format=log_config.format
        )
        
        # Setup file logging if specified
        if log_config.file:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_config.file,
                maxBytes=log_config.max_bytes,
                backupCount=log_config.backup_count
            )
            file_handler.setFormatter(logging.Formatter(log_config.format))
            logging.getLogger().addHandler(file_handler)
        
        # Setup colored logging if enabled
        if log_config.enable_colors:
            try:
                import colorlog
                handler = colorlog.StreamHandler()
                handler.setFormatter(colorlog.ColoredFormatter(
                    '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
                logging.getLogger().handlers = [handler]
            except ImportError:
                pass  # colorlog not available, use default formatting
    
    async def initialize(self) -> None:
        """Initialize all plugins and components."""
        if self._initialized:
            return
        
        self.logger.info("Initializing Knowledge Ingestor Manager...")
        
        try:
            # Load plugins
            await self.plugin_loader.load_plugins(self.registry)
            
            # Initialize default plugins
            await self._initialize_default_plugins()
            
            self._initialized = True
            self.logger.info("Knowledge Ingestor Manager initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            raise KnowledgeIngestorError(f"Initialization failed: {e}")
    
    async def _initialize_default_plugins(self) -> None:
        """Initialize default plugin instances."""
        # Initialize default database
        if self.config.database.backend in self.registry.list_databases():
            self.default_database = self.registry.get_database(self.config.database.backend)
            if self.default_database and not self.default_database.initialized:
                await self.default_database.initialize()
                self.logger.info(f"Initialized default database: {self.config.database.backend}")
        else:
            raise PluginError(f"Database backend '{self.config.database.backend}' not found")
        
        # Initialize default embedding provider (typically OpenAI)
        openai_provider = self.registry.get_embedding_provider("openai")
        if openai_provider:
            self.default_embedding_provider = openai_provider
            if not openai_provider.initialized:
                await openai_provider.initialize()
                self.logger.info("Initialized default embedding provider: openai")
        
        # Initialize enabled ingestors
        for ingestor_name in self.config.plugins.enabled_ingestors:
            ingestor = self.registry.get_ingestor(ingestor_name)
            if ingestor and not ingestor.initialized:
                await ingestor.initialize()
                self.logger.info(f"Initialized ingestor: {ingestor_name}")
                
                # Set first ingestor as default if none set
                if self.default_ingestor is None:
                    self.default_ingestor = ingestor
    
    async def ingest_content(
        self,
        source: Union[str, Dict[str, Any]],
        ingestor_name: Optional[str] = None,
        store: bool = True
    ) -> ProcessingResult:
        """
        Ingest content from a source.
        
        Args:
            source: URL or source specification
            ingestor_name: Specific ingestor to use, auto-detected if None
            store: Whether to store the result in database
            
        Returns:
            ProcessingResult with the processed document
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        
        try:
            # Find appropriate ingestor
            if ingestor_name:
                ingestor = self.registry.get_ingestor(ingestor_name)
                if not ingestor:
                    raise PluginError(f"Ingestor '{ingestor_name}' not found")
            else:
                ingestor = self.registry.find_ingestor_for_source(source)
                if not ingestor:
                    ingestor = self.default_ingestor
            
            if not ingestor:
                raise IngestionError("No suitable ingestor found for source")
            
            self.logger.info(f"Processing {source} with {ingestor.name} ingestor")
            
            # Process content
            result = await ingestor.ingest(source)
            
            if result.success and result.document and store:
                # Generate embeddings if provider available
                if self.default_embedding_provider and result.document.content:
                    try:
                        embeddings = await self.default_embedding_provider.generate_embedding(
                            result.document.content
                        )
                        result.document.metadata["embeddings"] = embeddings
                    except Exception as e:
                        self.logger.warning(f"Failed to generate embeddings: {e}")
                
                # Store in database
                stored = await self.default_database.store_document(result.document)
                if stored:
                    self.logger.info(f"Successfully stored document from {source}")
                else:
                    self.logger.error(f"Failed to store document from {source}")
                    result.success = False
                    result.error = "Storage failed"
            
            result.processing_time = time.time() - start_time
            return result
            
        except Exception as e:
            self.logger.error(f"Content ingestion failed: {e}")
            return ProcessingResult(
                success=False,
                error=str(e),
                processing_time=time.time() - start_time,
                metadata={"source": str(source)}
            )
    
    async def batch_ingest_content(
        self,
        sources: List[Union[str, Dict[str, Any]]],
        max_concurrent: Optional[int] = None,
        store: bool = True
    ) -> List[ProcessingResult]:
        """
        Ingest multiple sources concurrently.
        
        Args:
            sources: List of sources to process
            max_concurrent: Maximum concurrent operations (uses config default if None)
            store: Whether to store results in database
            
        Returns:
            List of ProcessingResults
        """
        if not self._initialized:
            await self.initialize()
        
        if max_concurrent is None:
            max_concurrent = self.config.processing.max_concurrent_requests
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(source):
            async with semaphore:
                return await self.ingest_content(source, store=store)
        
        self.logger.info(f"Starting batch ingestion of {len(sources)} sources")
        
        tasks = [process_with_semaphore(source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ProcessingResult(
                    success=False,
                    error=str(result),
                    metadata={"source": str(sources[i])}
                ))
            else:
                processed_results.append(result)
        
        success_count = sum(1 for r in processed_results if r.success)
        self.logger.info(f"Batch ingestion completed: {success_count}/{len(sources)} successful")
        
        return processed_results
    
    async def search_documents(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        database_name: Optional[str] = None
    ) -> SearchResult:
        """
        Search for documents in the database.
        
        Args:
            query: Search query
            limit: Maximum number of results
            filters: Optional filters to apply
            database_name: Specific database to search (uses default if None)
            
        Returns:
            SearchResult with matching documents
        """
        if not self._initialized:
            await self.initialize()
        
        database = self.default_database
        if database_name:
            database = self.registry.get_database(database_name)
            if not database:
                raise DatabaseError(f"Database '{database_name}' not found")
        
        if not database:
            raise DatabaseError("No database available for search")
        
        try:
            result = await database.search_documents(query, limit, filters)
            self.logger.info(f"Search completed: {len(result.documents)} results for '{query}'")
            return result
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            raise DatabaseError(f"Search operation failed: {e}")
    
    async def get_document(
        self,
        doc_id: str,
        database_name: Optional[str] = None
    ) -> Optional[Document]:
        """
        Retrieve a document by ID.
        
        Args:
            doc_id: Document identifier
            database_name: Specific database to query (uses default if None)
            
        Returns:
            Document if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        database = self.default_database
        if database_name:
            database = self.registry.get_database(database_name)
            if not database:
                raise DatabaseError(f"Database '{database_name}' not found")
        
        if not database:
            raise DatabaseError("No database available")
        
        try:
            return await database.get_document_by_id(doc_id)
        except Exception as e:
            self.logger.error(f"Failed to retrieve document {doc_id}: {e}")
            raise DatabaseError(f"Document retrieval failed: {e}")
    
    async def delete_document(
        self,
        doc_id: str,
        database_name: Optional[str] = None
    ) -> bool:
        """
        Delete a document by ID.
        
        Args:
            doc_id: Document identifier
            database_name: Specific database to use (uses default if None)
            
        Returns:
            True if deletion was successful
        """
        if not self._initialized:
            await self.initialize()
        
        database = self.default_database
        if database_name:
            database = self.registry.get_database(database_name)
            if not database:
                raise DatabaseError(f"Database '{database_name}' not found")
        
        if not database:
            raise DatabaseError("No database available")
        
        try:
            success = await database.delete_document(doc_id)
            if success:
                self.logger.info(f"Deleted document: {doc_id}")
            else:
                self.logger.warning(f"Failed to delete document: {doc_id}")
            return success
        except Exception as e:
            self.logger.error(f"Failed to delete document {doc_id}: {e}")
            raise DatabaseError(f"Document deletion failed: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get system status information.
        
        Returns:
            Status dictionary with system information
        """
        return {
            "initialized": self._initialized,
            "available_ingestors": self.registry.list_ingestors(),
            "available_databases": self.registry.list_databases(),
            "available_embedding_providers": self.registry.list_embedding_providers(),
            "default_ingestor": self.default_ingestor.name if self.default_ingestor else None,
            "default_database": self.default_database.name if self.default_database else None,
            "default_embedding_provider": self.default_embedding_provider.name if self.default_embedding_provider else None,
            "config": self.config.to_dict()
        }
    
    async def cleanup(self) -> None:
        """Cleanup all resources and shutdown plugins."""
        if not self._initialized:
            return
        
        self.logger.info("Shutting down Knowledge Ingestor Manager...")
        
        # Cleanup all plugins
        all_plugins = []
        all_plugins.extend(self.registry._ingestors.values())
        all_plugins.extend(self.registry._databases.values())
        all_plugins.extend(self.registry._embeddings.values())
        
        for plugin in all_plugins:
            try:
                await plugin.cleanup()
            except Exception as e:
                self.logger.error(f"Error cleaning up plugin {plugin.name}: {e}")
        
        self._initialized = False
        self.logger.info("Knowledge Ingestor Manager shutdown complete")