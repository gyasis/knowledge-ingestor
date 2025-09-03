"""
DeepLake database backend plugin.

This plugin provides integration with DeepLake vector database,
adapted from the legacy CustomDeepLake implementation.
"""

import os
import logging
from typing import List, Dict, Any, Optional
import deeplake
from openai import OpenAI
import uuid
from datetime import datetime

from ...core.base import BaseDatabaseBackend, Document, SearchResult
from ...core.exceptions import DatabaseError, ConfigError


class DeepLakeBackend(BaseDatabaseBackend):
    """DeepLake vector database backend implementation."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize DeepLake backend.
        
        Args:
            config: Backend configuration including connection details
            logger: Logger instance
        """
        super().__init__(config, logger)
        self.name = "deeplake"
        
        # Configuration
        self.dataset_path = config.get("dataset_path", "./deeplake_dataset")
        self.read_only = config.get("read_only", False)
        self.token = config.get("token", os.getenv("ACTIVELOOP_TOKEN"))
        
        # OpenAI client for embeddings
        openai_key = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ConfigError("OpenAI API key is required for DeepLake backend")
        
        self.openai_client = OpenAI(api_key=openai_key)
        self.embedding_model = config.get("embedding_model", "text-embedding-ada-002")
        
        # DeepLake dataset
        self.dataset = None
        
    @property
    def supported_types(self) -> List[str]:
        """Return supported content types."""
        return ["text", "document", "web", "pdf", "article"]
    
    async def initialize(self) -> None:
        """Initialize the DeepLake dataset."""
        try:
            if os.path.exists(self.dataset_path) and not self.read_only:
                # Load existing dataset
                self.dataset = deeplake.load(
                    self.dataset_path,
                    read_only=self.read_only,
                    token=self.token
                )
                self.logger.info(f"Loaded existing DeepLake dataset from {self.dataset_path}")
            else:
                # Create new dataset
                self.dataset = deeplake.empty(
                    self.dataset_path,
                    token=self.token,
                    overwrite=False
                )
                
                # Create tensors if dataset is empty
                if len(self.dataset) == 0:
                    self._create_tensors()
                
                self.logger.info(f"Created new DeepLake dataset at {self.dataset_path}")
            
            self.initialized = True
            
        except Exception as e:
            raise DatabaseError(f"Failed to initialize DeepLake dataset: {e}")
    
    def _create_tensors(self) -> None:
        """Create the required tensors in the dataset."""
        try:
            # Create tensors with appropriate dtypes and shapes
            self.dataset.create_tensor("id", htype="text", dtype=str)
            self.dataset.create_tensor("text", htype="text", dtype=str)
            self.dataset.create_tensor("embedding", htype="embedding", dtype="float32")
            self.dataset.create_tensor("metadata", htype="json", dtype=str)
            
            self.logger.info("Created DeepLake tensors: id, text, embedding, metadata")
            
        except Exception as e:
            raise DatabaseError(f"Failed to create dataset tensors: {e}")
    
    async def store_document(self, document: Document) -> bool:
        """
        Store a document in the DeepLake dataset.
        
        Args:
            document: Document to store
            
        Returns:
            True if storage was successful
        """
        if not self.initialized:
            await self.initialize()
        
        try:
            # Generate embeddings if not provided
            embeddings = document.metadata.get("embeddings")
            if not embeddings:
                embeddings = await self._generate_embeddings(document.content)
            
            # Generate document ID if not provided
            doc_id = document.metadata.get("id") or str(uuid.uuid4())
            
            # Prepare metadata
            metadata = {
                "title": document.title,
                "url": document.url,
                "document_type": document.document_type,
                "timestamp": document.timestamp.isoformat() if document.timestamp else datetime.utcnow().isoformat(),
                **document.metadata
            }
            
            # Remove embeddings from metadata to avoid duplication
            metadata.pop("embeddings", None)
            
            # Store in dataset
            self.dataset.append({
                "id": doc_id,
                "text": document.content,
                "embedding": embeddings,
                "metadata": metadata
            })
            
            self.logger.info(f"Stored document with ID: {doc_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store document: {e}")
            raise DatabaseError(f"Document storage failed: {e}")
    
    async def search_documents(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """
        Search for documents using semantic similarity.
        
        Args:
            query: Search query
            limit: Maximum number of results
            filters: Optional metadata filters
            
        Returns:
            SearchResult with matching documents
        """
        if not self.initialized:
            await self.initialize()
        
        try:
            # Generate query embedding
            query_embedding = await self._generate_embeddings(query)
            
            # Perform similarity search
            search_results = self.dataset.search(
                embedding=query_embedding,
                k=limit,
                return_tensors=["id", "text", "metadata"],
                return_view=False
            )
            
            # Convert results to documents
            documents = []
            scores = []
            
            for result in search_results["text"]:
                # Extract data from result
                doc_id = result.get("id", [""])[0] if "id" in result else ""
                text = result.get("text", [""])[0] if "text" in result else ""
                metadata = result.get("metadata", [{}])[0] if "metadata" in result else {}
                score = result.get("score", [0.0])[0] if "score" in result else 0.0
                
                # Create document
                doc = Document(
                    content=text,
                    title=metadata.get("title"),
                    url=metadata.get("url"),
                    document_type=metadata.get("document_type"),
                    metadata={"id": doc_id, **metadata}
                )
                
                documents.append(doc)
                scores.append(float(score))
            
            return SearchResult(
                documents=documents,
                scores=scores,
                total_results=len(documents),
                query=query
            )
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            raise DatabaseError(f"Search operation failed: {e}")
    
    async def get_document_by_id(self, doc_id: str) -> Optional[Document]:
        """
        Retrieve a document by ID.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Document if found, None otherwise
        """
        if not self.initialized:
            await self.initialize()
        
        try:
            # Search for document with matching ID
            # Note: DeepLake doesn't have direct ID lookup, so we filter
            results = self.dataset.filter(lambda x: x["id"].data()["value"] == doc_id)
            
            if len(results) == 0:
                return None
            
            # Get first matching result
            result = results[0]
            metadata = result["metadata"].data()["value"]
            
            return Document(
                content=result["text"].data()["value"],
                title=metadata.get("title"),
                url=metadata.get("url"),
                document_type=metadata.get("document_type"),
                metadata={"id": doc_id, **metadata}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve document {doc_id}: {e}")
            return None
    
    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document by ID.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            True if deletion was successful
        """
        if not self.initialized:
            await self.initialize()
        
        if self.read_only:
            raise DatabaseError("Cannot delete from read-only dataset")
        
        try:
            # Find and delete document with matching ID
            # Note: This is a simplified implementation
            # In practice, you might need to rebuild the dataset
            indices_to_delete = []
            
            for i in range(len(self.dataset)):
                if self.dataset[i]["id"].data()["value"] == doc_id:
                    indices_to_delete.append(i)
            
            if not indices_to_delete:
                return False
            
            # Delete indices (reverse order to maintain indices)
            for idx in reversed(indices_to_delete):
                del self.dataset[idx]
            
            self.logger.info(f"Deleted document: {doc_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete document {doc_id}: {e}")
            return False
    
    async def _generate_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for text using OpenAI."""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            raise DatabaseError(f"Failed to generate embeddings: {e}")
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self.dataset:
            # DeepLake datasets are automatically saved
            pass
        self.initialized = False
        self.logger.info("DeepLake backend cleanup completed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get dataset statistics."""
        if not self.dataset:
            return {}
        
        return {
            "total_documents": len(self.dataset),
            "dataset_path": self.dataset_path,
            "read_only": self.read_only,
            "tensors": list(self.dataset.tensors.keys()) if hasattr(self.dataset, "tensors") else []
        }