"""
Base classes and interfaces for the Knowledge Ingestor plugin system.

This module defines the core abstractions that all plugins must implement,
including base classes for ingestors and database backends.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
import logging


@dataclass
class Document:
    """Represents a document with content and metadata."""
    content: str
    title: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = None
    timestamp: datetime = None
    document_type: Optional[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class ProcessingResult:
    """Result of document processing operation."""
    success: bool
    document: Optional[Document] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass 
class SearchResult:
    """Result of a search operation."""
    documents: List[Document]
    scores: List[float] = None
    total_results: int = 0
    query: Optional[str] = None
    search_time: Optional[float] = None
    
    def __post_init__(self):
        if self.scores is None:
            self.scores = []
        if not self.total_results:
            self.total_results = len(self.documents)


class BasePlugin(ABC):
    """Base class for all plugins."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize plugin.
        
        Args:
            config: Plugin-specific configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.name = self.__class__.__name__.lower().replace('plugin', '').replace('ingestor', '')
        self.initialized = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the plugin. Called once during setup."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources. Called during shutdown."""
        pass
    
    @property
    @abstractmethod
    def supported_types(self) -> List[str]:
        """Return list of supported content types/formats."""
        pass
    
    def can_handle(self, source: Union[str, Dict[str, Any]]) -> bool:
        """
        Check if this plugin can handle the given source.
        
        Args:
            source: URL string or source metadata dict
            
        Returns:
            True if plugin can handle this source
        """
        return False


class BaseIngestor(BasePlugin):
    """Base class for content ingestors."""
    
    @abstractmethod
    async def ingest(self, source: Union[str, Dict[str, Any]]) -> ProcessingResult:
        """
        Ingest content from source.
        
        Args:
            source: URL string or source specification dict
            
        Returns:
            ProcessingResult containing the processed document or error
        """
        pass
    
    async def batch_ingest(self, sources: List[Union[str, Dict[str, Any]]]) -> List[ProcessingResult]:
        """
        Ingest multiple sources. Default implementation processes sequentially.
        
        Args:
            sources: List of sources to ingest
            
        Returns:
            List of ProcessingResults
        """
        results = []
        for source in sources:
            try:
                result = await self.ingest(source)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to ingest {source}: {e}")
                results.append(ProcessingResult(
                    success=False,
                    error=str(e),
                    metadata={"source": str(source)}
                ))
        return results
    
    def extract_metadata(self, content: str, source: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract metadata from content and source.
        
        Args:
            content: Extracted content
            source: Original source
            
        Returns:
            Metadata dictionary
        """
        metadata = {
            "ingestor": self.name,
            "processing_timestamp": datetime.utcnow().isoformat(),
            "content_length": len(content) if content else 0,
        }
        
        if isinstance(source, str):
            metadata["source_url"] = source
        elif isinstance(source, dict):
            metadata.update(source)
        
        return metadata


class BaseDatabaseBackend(BasePlugin):
    """Base class for database backends."""
    
    @abstractmethod
    async def store_document(self, document: Document) -> bool:
        """
        Store a document in the database.
        
        Args:
            document: Document to store
            
        Returns:
            True if storage was successful
        """
        pass
    
    @abstractmethod
    async def search_documents(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """
        Search for documents.
        
        Args:
            query: Search query
            limit: Maximum number of results
            filters: Optional filters to apply
            
        Returns:
            SearchResult containing matching documents
        """
        pass
    
    @abstractmethod
    async def get_document_by_id(self, doc_id: str) -> Optional[Document]:
        """
        Retrieve a document by ID.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document by ID.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            True if deletion was successful
        """
        pass
    
    async def store_documents(self, documents: List[Document]) -> List[bool]:
        """
        Store multiple documents. Default implementation stores sequentially.
        
        Args:
            documents: List of documents to store
            
        Returns:
            List of boolean results indicating success/failure for each document
        """
        results = []
        for document in documents:
            try:
                success = await self.store_document(document)
                results.append(success)
            except Exception as e:
                self.logger.error(f"Failed to store document: {e}")
                results.append(False)
        return results
    
    async def batch_search(self, queries: List[str], **kwargs) -> List[SearchResult]:
        """
        Perform multiple searches. Default implementation searches sequentially.
        
        Args:
            queries: List of search queries
            **kwargs: Additional search parameters
            
        Returns:
            List of SearchResults
        """
        results = []
        for query in queries:
            try:
                result = await self.search_documents(query, **kwargs)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Search failed for query '{query}': {e}")
                results.append(SearchResult(
                    documents=[],
                    query=query,
                    total_results=0
                ))
        return results


class BaseEmbeddingProvider(BasePlugin):
    """Base class for embedding providers."""
    
    @abstractmethod
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        pass
    
    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Return the dimension of embeddings produced by this provider."""
        pass
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string
            
        Returns:
            Embedding vector
        """
        embeddings = await self.generate_embeddings([text])
        return embeddings[0] if embeddings else []


class PluginRegistry:
    """Registry for managing plugins."""
    
    def __init__(self):
        self._ingestors: Dict[str, BaseIngestor] = {}
        self._databases: Dict[str, BaseDatabaseBackend] = {}
        self._embeddings: Dict[str, BaseEmbeddingProvider] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_ingestor(self, name: str, ingestor: BaseIngestor) -> None:
        """Register an ingestor plugin."""
        self._ingestors[name] = ingestor
        self.logger.info(f"Registered ingestor plugin: {name}")
    
    def register_database(self, name: str, database: BaseDatabaseBackend) -> None:
        """Register a database backend plugin."""
        self._databases[name] = database
        self.logger.info(f"Registered database plugin: {name}")
    
    def register_embedding_provider(self, name: str, provider: BaseEmbeddingProvider) -> None:
        """Register an embedding provider plugin."""
        self._embeddings[name] = provider
        self.logger.info(f"Registered embedding provider: {name}")
    
    def get_ingestor(self, name: str) -> Optional[BaseIngestor]:
        """Get ingestor plugin by name."""
        return self._ingestors.get(name)
    
    def get_database(self, name: str) -> Optional[BaseDatabaseBackend]:
        """Get database backend by name."""
        return self._databases.get(name)
    
    def get_embedding_provider(self, name: str) -> Optional[BaseEmbeddingProvider]:
        """Get embedding provider by name."""
        return self._embeddings.get(name)
    
    def list_ingestors(self) -> List[str]:
        """List available ingestor plugins."""
        return list(self._ingestors.keys())
    
    def list_databases(self) -> List[str]:
        """List available database plugins."""
        return list(self._databases.keys())
    
    def list_embedding_providers(self) -> List[str]:
        """List available embedding providers."""
        return list(self._embeddings.keys())
    
    def find_ingestor_for_source(self, source: Union[str, Dict[str, Any]]) -> Optional[BaseIngestor]:
        """
        Find the best ingestor for a given source.
        
        Args:
            source: Source to process
            
        Returns:
            Best matching ingestor or None
        """
        for ingestor in self._ingestors.values():
            if ingestor.can_handle(source):
                return ingestor
        return None