"""
OpenAI embedding provider plugin.

This plugin provides OpenAI embedding generation capabilities
for the knowledge ingestion system.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI, AsyncOpenAI
import asyncio

from ...core.base import BaseEmbeddingProvider
from ...core.exceptions import ConfigError, PluginError


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider implementation."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize OpenAI embedding provider.
        
        Args:
            config: Provider configuration
            logger: Logger instance
        """
        super().__init__(config, logger)
        self.name = "openai"
        
        # Configuration
        api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigError("OpenAI API key is required")
        
        self.model = config.get("model", "text-embedding-ada-002")
        self.batch_size = config.get("batch_size", 100)
        self.max_retries = config.get("max_retries", 3)
        self.timeout = config.get("timeout", 60)
        
        # Initialize clients
        self.client = OpenAI(
            api_key=api_key,
            timeout=self.timeout,
            max_retries=self.max_retries
        )
        
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            timeout=self.timeout,
            max_retries=self.max_retries
        )
        
        self._embedding_dimension = None
    
    @property
    def supported_types(self) -> List[str]:
        """Return supported content types."""
        return ["text", "document"]
    
    @property
    def embedding_dimension(self) -> int:
        """Return the dimension of embeddings produced by this provider."""
        if self._embedding_dimension is None:
            # Get dimension from model (most common values)
            if "ada-002" in self.model:
                self._embedding_dimension = 1536
            elif "ada-001" in self.model:
                self._embedding_dimension = 1024
            else:
                # Try to get it dynamically by making a test call
                try:
                    test_embedding = self.client.embeddings.create(
                        model=self.model,
                        input="test"
                    ).data[0].embedding
                    self._embedding_dimension = len(test_embedding)
                except Exception as e:
                    self.logger.warning(f"Could not determine embedding dimension: {e}")
                    self._embedding_dimension = 1536  # Default fallback
        
        return self._embedding_dimension
    
    async def initialize(self) -> None:
        """Initialize the provider."""
        try:
            # Test the connection with a simple embedding request
            await self.generate_embedding("test connection")
            self.initialized = True
            self.logger.info(f"OpenAI embedding provider initialized with model: {self.model}")
        except Exception as e:
            raise PluginError(f"Failed to initialize OpenAI embedding provider: {e}")
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        if hasattr(self.async_client, 'close'):
            await self.async_client.close()
        self.initialized = False
        self.logger.info("OpenAI embedding provider cleanup completed")
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        try:
            # Process texts in batches
            all_embeddings = []
            
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                
                # Make API call
                response = await self.async_client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                
                # Extract embeddings
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
                self.logger.debug(f"Generated embeddings for batch {i//self.batch_size + 1}: {len(batch)} texts")
            
            return all_embeddings
            
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {e}")
            raise PluginError(f"Embedding generation failed: {e}")
    
    def generate_embeddings_sync(self, texts: List[str]) -> List[List[float]]:
        """
        Synchronous version of generate_embeddings.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        try:
            # Process texts in batches
            all_embeddings = []
            
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                
                # Make API call
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                
                # Extract embeddings
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
                self.logger.debug(f"Generated embeddings for batch {i//self.batch_size + 1}: {len(batch)} texts")
            
            return all_embeddings
            
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {e}")
            raise PluginError(f"Embedding generation failed: {e}")
    
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "model": self.model,
            "embedding_dimension": self.embedding_dimension,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "timeout": self.timeout
        }