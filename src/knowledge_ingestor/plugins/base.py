"""
Abstract base classes for the Knowledge Ingestor plugin system.

This module defines the interfaces that all plugins must implement,
providing a standardized way to extend the system's functionality.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Type, Iterator
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum

from ..core.document import Document, DocumentBatch, ContentType, ProcessingStatus


class PluginType(str, Enum):
    """Types of plugins supported by the system."""
    INGESTOR = "ingestor"
    DATABASE = "database" 
    PROCESSOR = "processor"
    EMBEDDER = "embedder"


@dataclass
class PluginMetadata:
    """Metadata for plugin registration and management."""
    name: str
    version: str
    description: str
    plugin_type: PluginType
    author: str
    supported_content_types: List[ContentType]
    dependencies: List[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class BasePlugin(ABC):
    """Base class for all plugins in the Knowledge Ingestor system."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the plugin with configuration.
        
        Args:
            config: Plugin-specific configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._is_initialized = False
    
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        pass
    
    def initialize(self) -> None:
        """Initialize the plugin. Override in subclasses for custom initialization."""
        self._is_initialized = True
        self.logger.info(f"Plugin {self.metadata.name} initialized")
    
    def shutdown(self) -> None:
        """Shutdown the plugin. Override in subclasses for cleanup."""
        self._is_initialized = False
        self.logger.info(f"Plugin {self.metadata.name} shutdown")
    
    def is_initialized(self) -> bool:
        """Check if plugin is initialized."""
        return self._is_initialized
    
    def validate_config(self) -> bool:
        """Validate plugin configuration. Override in subclasses."""
        return True


class BaseIngestor(BasePlugin):
    """
    Abstract base class for content ingestors.
    
    Ingestors are responsible for extracting content from various sources
    and converting them into standardized Document objects.
    """
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return ingestor metadata. Must be implemented by subclasses."""
        return PluginMetadata(
            name=self.__class__.__name__,
            version="1.0.0",
            description="Base ingestor class",
            plugin_type=PluginType.INGESTOR,
            author="Unknown",
            supported_content_types=[]
        )
    
    @abstractmethod
    def can_handle(self, source: Union[str, Path]) -> bool:
        """
        Check if this ingestor can handle the given source.
        
        Args:
            source: URL, file path, or other source identifier
            
        Returns:
            bool: True if this ingestor can process the source
        """
        pass
    
    @abstractmethod
    def extract_content(self, source: Union[str, Path], **kwargs) -> Document:
        """
        Extract content from the source and return a Document.
        
        Args:
            source: URL, file path, or other source identifier
            **kwargs: Additional parameters for extraction
            
        Returns:
            Document: Extracted document with metadata
            
        Raises:
            Exception: If extraction fails
        """
        pass
    
    def extract_batch(self, sources: List[Union[str, Path]], **kwargs) -> DocumentBatch:
        """
        Extract content from multiple sources.
        
        Args:
            sources: List of source identifiers
            **kwargs: Additional parameters for extraction
            
        Returns:
            DocumentBatch: Batch containing extracted documents
        """
        batch = DocumentBatch()
        
        for source in sources:
            try:
                if self.can_handle(source):
                    document = self.extract_content(source, **kwargs)
                    document.set_processing_status(ProcessingStatus.COMPLETED)
                    batch.add_document(document)
                else:
                    self.logger.warning(f"Cannot handle source: {source}")
            except Exception as e:
                self.logger.error(f"Failed to extract from {source}: {e}")
                # Create failed document
                failed_doc = Document()
                failed_doc.metadata.source_url = str(source)
                failed_doc.set_processing_status(ProcessingStatus.FAILED)
                batch.add_document(failed_doc)
        
        return batch
    
    def get_priority(self, source: Union[str, Path]) -> int:
        """
        Get priority for handling this source (higher = more preferred).
        
        Args:
            source: Source to evaluate
            
        Returns:
            int: Priority score (0-100)
        """
        return 50  # Default medium priority


class BaseDatabase(BasePlugin):
    """
    Abstract base class for database backends.
    
    Database plugins handle storage and retrieval of documents
    with vector embeddings for semantic search.
    """
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return database metadata. Must be implemented by subclasses."""
        return PluginMetadata(
            name=self.__class__.__name__,
            version="1.0.0",
            description="Base database class",
            plugin_type=PluginType.DATABASE,
            author="Unknown",
            supported_content_types=[]
        )
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection."""
        pass
    
    @abstractmethod
    def store_document(self, document: Document) -> str:
        """
        Store a document in the database.
        
        Args:
            document: Document to store
            
        Returns:
            str: Document ID in the database
        """
        pass
    
    @abstractmethod
    def store_documents(self, documents: List[Document]) -> List[str]:
        """
        Store multiple documents in the database.
        
        Args:
            documents: List of documents to store
            
        Returns:
            List[str]: List of document IDs in the database
        """
        pass
    
    @abstractmethod
    def retrieve_document(self, doc_id: str) -> Optional[Document]:
        """
        Retrieve a document by its ID.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Optional[Document]: Retrieved document or None if not found
        """
        pass
    
    @abstractmethod
    def search_similar(
        self, 
        query: Union[str, List[float]], 
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        
        Args:
            query: Query string or embedding vector
            k: Number of results to return
            filters: Optional metadata filters
            
        Returns:
            List[Dict[str, Any]]: Search results with scores
        """
        pass
    
    @abstractmethod
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from the database.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            bool: True if deletion was successful
        """
        pass
    
    @abstractmethod
    def list_documents(
        self, 
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        List documents in the database.
        
        Args:
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            filters: Optional metadata filters
            
        Returns:
            List[Dict[str, Any]]: Document metadata list
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dict[str, Any]: Statistics about the database
        """
        pass
    
    def health_check(self) -> bool:
        """
        Check if database is healthy.
        
        Returns:
            bool: True if database is accessible
        """
        try:
            stats = self.get_stats()
            return True
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False


class BaseProcessor(BasePlugin):
    """
    Abstract base class for document processors.
    
    Processors handle document transformation, analysis, and enhancement.
    """
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return processor metadata. Must be implemented by subclasses."""
        return PluginMetadata(
            name=self.__class__.__name__,
            version="1.0.0",
            description="Base processor class",
            plugin_type=PluginType.PROCESSOR,
            author="Unknown",
            supported_content_types=[]
        )
    
    @abstractmethod
    def process_document(self, document: Document) -> Document:
        """
        Process a document and return the processed version.
        
        Args:
            document: Document to process
            
        Returns:
            Document: Processed document
        """
        pass
    
    def process_batch(self, documents: List[Document]) -> List[Document]:
        """
        Process multiple documents.
        
        Args:
            documents: List of documents to process
            
        Returns:
            List[Document]: List of processed documents
        """
        processed = []
        for doc in documents:
            try:
                processed_doc = self.process_document(doc)
                processed.append(processed_doc)
            except Exception as e:
                self.logger.error(f"Failed to process document {doc.id}: {e}")
                doc.set_processing_status(ProcessingStatus.FAILED)
                processed.append(doc)
        
        return processed


class BaseEmbedder(BasePlugin):
    """
    Abstract base class for embedding providers.
    
    Embedders generate vector embeddings from text content.
    """
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return embedder metadata. Must be implemented by subclasses."""
        return PluginMetadata(
            name=self.__class__.__name__,
            version="1.0.0",
            description="Base embedder class",
            plugin_type=PluginType.EMBEDDER,
            author="Unknown",
            supported_content_types=[]
        )
    
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List[float]: Embedding vector
        """
        pass
    
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        pass
    
    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Return the dimension of embeddings produced by this embedder."""
        pass


class PluginRegistry:
    """
    Registry for managing plugins in the Knowledge Ingestor system.
    
    The registry maintains a catalog of available plugins and provides
    methods for registration, discovery, and retrieval.
    """
    
    def __init__(self):
        self._plugins: Dict[PluginType, Dict[str, Type[BasePlugin]]] = {
            plugin_type: {} for plugin_type in PluginType
        }
        self._instances: Dict[str, BasePlugin] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_plugin(self, plugin_class: Type[BasePlugin]) -> None:
        """
        Register a plugin class with the registry.
        
        Args:
            plugin_class: Plugin class to register
        """
        # Create temporary instance to get metadata
        temp_instance = plugin_class()
        metadata = temp_instance.metadata
        
        plugin_type = metadata.plugin_type
        plugin_name = metadata.name
        
        if plugin_name in self._plugins[plugin_type]:
            self.logger.warning(f"Plugin {plugin_name} already registered, overriding")
        
        self._plugins[plugin_type][plugin_name] = plugin_class
        self.logger.info(f"Registered {plugin_type.value} plugin: {plugin_name}")
    
    def unregister_plugin(self, plugin_type: PluginType, plugin_name: str) -> None:
        """
        Unregister a plugin.
        
        Args:
            plugin_type: Type of plugin
            plugin_name: Name of plugin to unregister
        """
        if plugin_name in self._plugins[plugin_type]:
            del self._plugins[plugin_type][plugin_name]
            self.logger.info(f"Unregistered {plugin_type.value} plugin: {plugin_name}")
        
        # Remove instance if exists
        if plugin_name in self._instances:
            del self._instances[plugin_name]
    
    def get_plugin_class(self, plugin_type: PluginType, plugin_name: str) -> Optional[Type[BasePlugin]]:
        """
        Get a plugin class by type and name.
        
        Args:
            plugin_type: Type of plugin
            plugin_name: Name of plugin
            
        Returns:
            Optional[Type[BasePlugin]]: Plugin class or None if not found
        """
        return self._plugins[plugin_type].get(plugin_name)
    
    def get_plugin_instance(
        self, 
        plugin_type: PluginType, 
        plugin_name: str, 
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[BasePlugin]:
        """
        Get or create a plugin instance.
        
        Args:
            plugin_type: Type of plugin
            plugin_name: Name of plugin
            config: Plugin configuration
            
        Returns:
            Optional[BasePlugin]: Plugin instance or None if not found
        """
        instance_key = f"{plugin_type.value}:{plugin_name}"
        
        if instance_key in self._instances:
            return self._instances[instance_key]
        
        plugin_class = self.get_plugin_class(plugin_type, plugin_name)
        if plugin_class is None:
            return None
        
        try:
            instance = plugin_class(config or {})
            instance.initialize()
            self._instances[instance_key] = instance
            return instance
        except Exception as e:
            self.logger.error(f"Failed to create instance of {plugin_name}: {e}")
            return None
    
    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> Dict[str, List[str]]:
        """
        List all registered plugins.
        
        Args:
            plugin_type: Optional filter by plugin type
            
        Returns:
            Dict[str, List[str]]: Dictionary of plugin types and their plugin names
        """
        if plugin_type:
            return {plugin_type.value: list(self._plugins[plugin_type].keys())}
        
        return {
            ptype.value: list(plugins.keys()) 
            for ptype, plugins in self._plugins.items()
        }
    
    def get_ingestors_for_source(self, source: Union[str, Path]) -> List[BaseIngestor]:
        """
        Get all ingestors that can handle a given source.
        
        Args:
            source: Source to check
            
        Returns:
            List[BaseIngestor]: List of compatible ingestors, sorted by priority
        """
        compatible_ingestors = []
        
        for name, plugin_class in self._plugins[PluginType.INGESTOR].items():
            instance = self.get_plugin_instance(PluginType.INGESTOR, name)
            if instance and isinstance(instance, BaseIngestor) and instance.can_handle(source):
                compatible_ingestors.append(instance)
        
        # Sort by priority (highest first)
        compatible_ingestors.sort(key=lambda x: x.get_priority(source), reverse=True)
        return compatible_ingestors
    
    def shutdown_all(self) -> None:
        """Shutdown all plugin instances."""
        for instance in self._instances.values():
            try:
                instance.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down plugin {instance.metadata.name}: {e}")
        
        self._instances.clear()


# Global plugin registry
_plugin_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry."""
    return _plugin_registry