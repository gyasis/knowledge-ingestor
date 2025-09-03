"""
Integration tests for the complete system.
"""

import asyncio
import os
import tempfile
import pytest
from pathlib import Path

from knowledge_ingestor.core.config import Config
from knowledge_ingestor.core.manager import KnowledgeIngestorManager


@pytest.mark.integration
@pytest.mark.asyncio
class TestSystemIntegration:
    """Test complete system integration."""
    
    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary directory for test data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def test_config(self, temp_data_dir):
        """Create test configuration."""
        # Only run integration tests if we have a real API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "test-key":
            pytest.skip("Integration tests require real OPENAI_API_KEY")
        
        config = Config()
        config.database.dataset_path = f"{temp_data_dir}/deeplake_dataset"
        return config
    
    async def test_manager_initialization(self, test_config):
        """Test manager initialization with all components."""
        manager = KnowledgeIngestorManager(test_config)
        
        try:
            await manager.initialize()
            
            assert manager._initialized
            assert manager.default_database is not None
            assert manager.default_embedding_provider is not None
            
            # Test status
            status = manager.get_status()
            assert status["initialized"]
            assert len(status["available_databases"]) > 0
            assert len(status["available_embedding_providers"]) > 0
            
        finally:
            await manager.cleanup()
    
    async def test_web_ingestion_flow(self, test_config):
        """Test complete web ingestion flow."""
        manager = KnowledgeIngestorManager(test_config)
        
        try:
            await manager.initialize()
            
            # Test ingesting a simple web page
            # Using a reliable test URL
            test_url = "https://httpbin.org/html"
            
            result = await manager.ingest_content(test_url, store=False)  # Don't store for test
            
            assert result.success
            assert result.document is not None
            assert len(result.document.content) > 0
            assert result.document.url == test_url
            assert "embeddings" in result.document.metadata
            
        finally:
            await manager.cleanup()
    
    async def test_batch_ingestion(self, test_config):
        """Test batch ingestion functionality."""
        manager = KnowledgeIngestorManager(test_config)
        
        try:
            await manager.initialize()
            
            # Test URLs
            test_urls = [
                "https://httpbin.org/html",
                "https://httpbin.org/json"
            ]
            
            results = await manager.batch_ingest_content(
                test_urls, 
                max_concurrent=2,
                store=False
            )
            
            assert len(results) == 2
            # At least one should succeed (html should work)
            success_count = sum(1 for r in results if r.success)
            assert success_count >= 1
            
        finally:
            await manager.cleanup()
    
    async def test_store_and_search_flow(self, test_config):
        """Test storing documents and searching."""
        manager = KnowledgeIngestorManager(test_config)
        
        try:
            await manager.initialize()
            
            # Create a test document manually
            from knowledge_ingestor.core.base import Document
            test_doc = Document(
                content="This is a test document about machine learning and artificial intelligence.",
                title="Test ML Document",
                url="https://test.example.com/ml",
                document_type="test"
            )
            
            # Store the document
            stored = await manager.default_database.store_document(test_doc)
            assert stored
            
            # Search for it
            search_results = await manager.search_documents("machine learning", limit=5)
            
            assert len(search_results.documents) > 0
            # The test document should be in the results
            found = any("machine learning" in doc.content.lower() for doc in search_results.documents)
            assert found
            
        finally:
            await manager.cleanup()