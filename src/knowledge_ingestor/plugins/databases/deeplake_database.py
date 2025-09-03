"""
DeepLake database plugin for the Knowledge Ingestor system.

This plugin provides integration with DeepLake vector database for storing
and retrieving documents with embeddings.
"""

import os
import uuid
from typing import List, Dict, Optional, Union, Any
from pathlib import Path
import deeplake
from openai import OpenAI

from ..base import BaseDatabase, PluginMetadata, PluginType
from ...core.document import Document
from ...core.config import get_config


class DeepLakeDatabase(BaseDatabase):
    """
    DeepLake database plugin for vector storage and retrieval.
    
    This plugin provides a full-featured interface to DeepLake vector database,
    including document storage, embedding generation, and similarity search.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the DeepLake database plugin."""
        super().__init__(config)
        
        # Configuration
        app_config = get_config()
        self.db_path = config.get('db_path') if config else app_config.database.deeplake_path
        self.read_only = config.get('read_only', False) if config else app_config.database.deeplake_read_only
        self.token = config.get('token') if config else app_config.database.deeplake_token
        
        # OpenAI client for embeddings
        openai_key = config.get('openai_api_key') if config else app_config.openai_api_key
        if not openai_key:
            openai_key = os.getenv('OPENAI_API_KEY')
        
        if openai_key:
            self.client = OpenAI(api_key=openai_key)
        else:
            self.logger.warning("No OpenAI API key provided - embeddings will not be available")
            self.client = None
        
        # Database connection
        self.ds = None
        self.embedding_model = config.get('embedding_model', 'text-embedding-ada-002') if config else 'text-embedding-ada-002'
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return DeepLake database metadata."""
        return PluginMetadata(
            name="DeepLakeDatabase",
            version="1.0.0",
            description="DeepLake vector database integration",
            plugin_type=PluginType.DATABASE,
            author="Knowledge Ingestor Team",
            supported_content_types=[],  # Supports all content types
            dependencies=["deeplake", "openai"]
        )
    
    def connect(self) -> None:
        """Establish connection to the DeepLake database."""
        try:
            self.logger.info(f"Connecting to DeepLake database at: {self.db_path}")
            
            # Open or create the dataset
            if Path(self.db_path).exists() or (self.token and self.db_path.startswith('hub://')):
                self.ds = deeplake.open(
                    self.db_path,
                    read_only=self.read_only,
                    token=self.token
                )
                self.logger.info("Connected to existing DeepLake database")
            else:
                # Create new dataset with standard schema
                self.ds = deeplake.empty(self.db_path, token=self.token)
                self._initialize_schema()
                self.logger.info("Created new DeepLake database with schema")
            
            self._validate_schema()
            
        except Exception as e:
            error_msg = f"Failed to connect to DeepLake database: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def disconnect(self) -> None:
        """Close database connection."""
        if self.ds:
            try:
                self.ds.flush()
                self.ds = None
                self.logger.info("Disconnected from DeepLake database")
            except Exception as e:
                self.logger.error(f"Error disconnecting from database: {e}")
    
    def _initialize_schema(self) -> None:
        """Initialize the DeepLake dataset schema."""
        try:
            # Create tensors for document storage
            self.ds.create_tensor('id', htype='text')
            self.ds.create_tensor('text', htype='text') 
            self.ds.create_tensor('embedding', htype='embedding')
            self.ds.create_tensor('metadata', htype='json')
            
            self.logger.info("Initialized DeepLake schema with tensors: id, text, embedding, metadata")
            
        except Exception as e:
            error_msg = f"Failed to initialize schema: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _validate_schema(self) -> None:
        """Validate that the database has the expected schema."""
        required_tensors = ['id', 'text', 'embedding', 'metadata']
        existing_tensors = list(self.ds.tensors.keys())
        
        missing_tensors = set(required_tensors) - set(existing_tensors)
        if missing_tensors:
            raise Exception(f"Database missing required tensors: {missing_tensors}")
        
        self.logger.debug(f"Schema validated - tensors: {existing_tensors}")
    
    def store_document(self, document: Document) -> str:
        """
        Store a single document in the database.
        
        Args:
            document: Document to store
            
        Returns:
            str: Document ID in the database
        """
        # Generate embedding if not present
        if not document.embedding and self.client:
            document.embedding = self._generate_embedding(document.content)
        
        try:
            # Convert document to storage format
            storage_doc = document.to_storage_format()
            
            # Append to dataset
            self.ds.append({
                'id': storage_doc['id'],
                'text': storage_doc['text'],
                'embedding': storage_doc['embedding'],
                'metadata': storage_doc['metadata']
            })
            
            # Commit the changes
            self.ds.flush()
            
            self.logger.info(f"Stored document: {storage_doc['id']}")
            return storage_doc['id']
            
        except Exception as e:
            error_msg = f"Failed to store document {document.id}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def store_documents(self, documents: List[Document]) -> List[str]:
        """
        Store multiple documents in the database.
        
        Args:
            documents: List of documents to store
            
        Returns:
            List[str]: List of document IDs in the database
        """
        if not documents:
            return []
        
        try:
            # Generate embeddings for documents that don't have them
            if self.client:
                texts_to_embed = []
                doc_indices = []
                
                for i, doc in enumerate(documents):
                    if not doc.embedding:
                        texts_to_embed.append(doc.content)
                        doc_indices.append(i)
                
                if texts_to_embed:
                    self.logger.info(f"Generating embeddings for {len(texts_to_embed)} documents")
                    embeddings = self._generate_embeddings(texts_to_embed)
                    
                    for i, embedding in enumerate(embeddings):
                        documents[doc_indices[i]].embedding = embedding
            
            # Convert all documents to storage format
            storage_docs = [doc.to_storage_format() for doc in documents]
            
            # Batch append to dataset
            batch_data = {
                'id': [doc['id'] for doc in storage_docs],
                'text': [doc['text'] for doc in storage_docs],
                'embedding': [doc['embedding'] for doc in storage_docs],
                'metadata': [doc['metadata'] for doc in storage_docs]
            }
            
            self.ds.extend(batch_data)
            self.ds.flush()
            
            doc_ids = [doc['id'] for doc in storage_docs]
            self.logger.info(f"Stored {len(documents)} documents")
            return doc_ids
            
        except Exception as e:
            error_msg = f"Failed to store documents: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def retrieve_document(self, doc_id: str) -> Optional[Document]:
        """
        Retrieve a document by its ID.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            Optional[Document]: Retrieved document or None if not found
        """
        try:
            # Search for document by ID
            results = self.ds.filter({'id': doc_id})
            
            if len(results) == 0:
                self.logger.debug(f"Document not found: {doc_id}")
                return None
            
            # Get the first (should be only) result
            result = results[0]
            
            # Convert back to Document object
            document = Document(
                id=result['id'].data()['value'],
                content=result['text'].data()['value'],
                embedding=result['embedding'].data()['value'],
                metadata=result['metadata'].data()['value']
            )
            
            self.logger.debug(f"Retrieved document: {doc_id}")
            return document
            
        except Exception as e:
            error_msg = f"Failed to retrieve document {doc_id}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
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
        try:
            # Generate embedding for query if it's a string
            if isinstance(query, str):
                if not self.client:
                    raise Exception("No OpenAI client available for query embedding")
                query_embedding = self._generate_embedding(query)
            else:
                query_embedding = query
            
            # Perform vector search
            if filters:
                # Apply filters first, then search
                filtered_ds = self.ds
                for key, value in filters.items():
                    filtered_ds = filtered_ds.filter({f'metadata.{key}': value})
                search_results = filtered_ds.search(embedding=query_embedding, k=k)
            else:
                search_results = self.ds.search(embedding=query_embedding, k=k)
            
            # Format results
            results = []
            for i, result in enumerate(search_results):
                results.append({
                    'id': result['id'].data()['value'],
                    'text': result['text'].data()['value'],
                    'metadata': result['metadata'].data()['value'],
                    'score': search_results.scores[i] if hasattr(search_results, 'scores') else 0.0,
                    'embedding': result['embedding'].data()['value']
                })
            
            self.logger.info(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            error_msg = f"Failed to search documents: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from the database.
        
        Args:
            doc_id: Document identifier
            
        Returns:
            bool: True if deletion was successful
        """
        try:
            # Find document indices to delete
            indices_to_delete = []
            for i in range(len(self.ds)):
                if self.ds['id'][i].data()['value'] == doc_id:
                    indices_to_delete.append(i)
            
            if not indices_to_delete:
                self.logger.warning(f"Document not found for deletion: {doc_id}")
                return False
            
            # Delete from dataset (note: DeepLake deletion can be complex)
            # For now, we'll mark as deleted in metadata
            for idx in indices_to_delete:
                metadata = self.ds['metadata'][idx].data()['value']
                metadata['deleted'] = True
                self.ds['metadata'][idx] = metadata
            
            self.ds.flush()
            
            self.logger.info(f"Marked document as deleted: {doc_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to delete document {doc_id}: {str(e)}"
            self.logger.error(error_msg)
            return False
    
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
        try:
            # Apply filters if specified
            ds = self.ds
            if filters:
                for key, value in filters.items():
                    ds = ds.filter({f'metadata.{key}': value})
            
            # Apply pagination
            start_idx = offset or 0
            end_idx = start_idx + (limit or len(ds))
            end_idx = min(end_idx, len(ds))
            
            documents = []
            for i in range(start_idx, end_idx):
                doc_data = {
                    'id': ds['id'][i].data()['value'],
                    'metadata': ds['metadata'][i].data()['value']
                }
                
                # Skip deleted documents
                if not doc_data['metadata'].get('deleted', False):
                    documents.append(doc_data)
            
            self.logger.info(f"Listed {len(documents)} documents")
            return documents
            
        except Exception as e:
            error_msg = f"Failed to list documents: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dict[str, Any]: Statistics about the database
        """
        try:
            stats = {
                'total_documents': len(self.ds),
                'database_path': self.db_path,
                'read_only': self.read_only,
                'tensors': list(self.ds.tensors.keys()),
                'embedding_model': self.embedding_model,
                'has_openai_client': self.client is not None
            }
            
            # Count non-deleted documents
            active_docs = 0
            deleted_docs = 0
            for i in range(len(self.ds)):
                metadata = self.ds['metadata'][i].data()['value']
                if metadata.get('deleted', False):
                    deleted_docs += 1
                else:
                    active_docs += 1
            
            stats.update({
                'active_documents': active_docs,
                'deleted_documents': deleted_docs
            })
            
            return stats
            
        except Exception as e:
            error_msg = f"Failed to get database stats: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not self.client:
            raise Exception("No OpenAI client available for embedding generation")
        
        try:
            # Clean text
            clean_text = text.replace("\n", " ").strip()
            
            response = self.client.embeddings.create(
                input=[clean_text],
                model=self.embedding_model
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            error_msg = f"Failed to generate embedding: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts with batching."""
        if not self.client:
            raise Exception("No OpenAI client available for embedding generation")
        
        try:
            # Clean texts
            clean_texts = [text.replace("\n", " ").strip() for text in texts]
            
            # Estimate tokens and batch if necessary
            total_chars = sum(len(text) for text in clean_texts)
            estimated_tokens = total_chars // 4  # Rough estimate
            
            MAX_TOKENS_PER_REQUEST = 300000
            TARGET_TOKENS_PER_BATCH = 290000
            
            if estimated_tokens <= TARGET_TOKENS_PER_BATCH:
                # Single batch
                response = self.client.embeddings.create(
                    input=clean_texts,
                    model=self.embedding_model
                )
                return [data.embedding for data in response.data]
            else:
                # Multiple batches
                all_embeddings = []
                batch_size = max(1, len(clean_texts) // (estimated_tokens // TARGET_TOKENS_PER_BATCH + 1))
                
                for i in range(0, len(clean_texts), batch_size):
                    batch_texts = clean_texts[i:i + batch_size]
                    response = self.client.embeddings.create(
                        input=batch_texts,
                        model=self.embedding_model
                    )
                    batch_embeddings = [data.embedding for data in response.data]
                    all_embeddings.extend(batch_embeddings)
                
                return all_embeddings
                
        except Exception as e:
            error_msg = f"Failed to generate embeddings: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def validate_config(self) -> bool:
        """Validate the database configuration."""
        try:
            import deeplake
            
            # Check if database path is accessible
            if not self.db_path:
                self.logger.error("Database path not specified")
                return False
            
            # Check OpenAI client if embedding generation is needed
            if self.client:
                try:
                    # Test embedding generation
                    self.client.embeddings.create(input=["test"], model=self.embedding_model)
                except Exception as e:
                    self.logger.error(f"OpenAI client validation failed: {e}")
                    return False
            
            return True
            
        except ImportError as e:
            self.logger.error(f"Required dependency not available: {e}")
            return False