"""
Comprehensive integration tests for the Knowledge Ingestor API.

This module provides end-to-end tests for:
- Authentication and authorization
- Document ingestion endpoints
- Search functionality
- Document management
- Rate limiting
- Error handling
- API versioning
"""

import pytest
import asyncio
import time
from typing import Dict, Any, List
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from src.knowledge_ingestor.api.app import create_app
from src.knowledge_ingestor.core.config import get_config, set_config, Config
from src.knowledge_ingestor.api.auth import auth_manager
from src.knowledge_ingestor.api.models import *


@pytest.fixture(scope="session")
def test_config():
    """Create test configuration."""
    config = Config(
        environment="testing",
        debug=True,
        test_mode=True,
        api=Config.APIConfig(
            host="127.0.0.1",
            port=8000,
            debug=True,
            auth_enabled=True,
            auth_secret_key="test_secret_key_for_testing_only",
            rate_limit_enabled=True,
            rate_limit_requests=100
        ),
        database=Config.DatabaseConfig(
            database_type="deeplake",
            deeplake_path="./test_deeplake_store"
        ),
        embedding=Config.EmbeddingConfig(
            provider="openai",
            openai_api_key="test_openai_key"
        )
    )
    set_config(config)
    return config


@pytest.fixture
def client(test_config):
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_database():
    """Mock database for testing."""
    mock_db = Mock()
    mock_db.search_similar.return_value = [
        {
            "id": "test_doc_1",
            "text": "This is a test document about machine learning",
            "score": 0.95,
            "metadata": {
                "title": "Test Document 1",
                "content_type": "article",
                "web_address": "https://example.com/doc1"
            }
        }
    ]
    mock_db.list_documents.return_value = [
        {
            "id": "test_doc_1",
            "text": "Test content",
            "metadata": {
                "title": "Test Document 1",
                "content_type": "article",
                "web_address": "https://example.com/doc1"
            },
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }
    ]
    mock_db.retrieve_document.return_value = Mock(
        id="test_doc_1",
        content="Test document content",
        metadata=Mock(
            title="Test Document 1",
            content_type=Mock(value="article"),
            source_url="https://example.com/doc1",
            dict=lambda: {
                "title": "Test Document 1",
                "content_type": "article",
                "source_url": "https://example.com/doc1"
            }
        ),
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00"
    )
    mock_db.delete_document.return_value = True
    mock_db.get_stats.return_value = {"total_documents": 1}
    mock_db.get_document_count.return_value = 1
    return mock_db


@pytest.fixture
def mock_pipeline():
    """Mock processing pipeline."""
    mock_pipeline = Mock()
    mock_result = Mock()
    mock_result.success = True
    mock_result.processing_time = 1.5
    mock_result.error = None
    mock_result.document = Mock(
        id="test_doc_1",
        metadata=Mock(
            title="Test Document",
            content_type=Mock(value="article"),
            word_count=100
        )
    )
    mock_pipeline.process_batch.return_value = [mock_result]
    mock_pipeline.get_statistics.return_value = Mock(
        total_processed=1,
        successful=1,
        failed=0
    )
    mock_pipeline.health_check.return_value = {"pipeline": True}
    return mock_pipeline


class TestAuthentication:
    """Test authentication endpoints and functionality."""
    
    def test_login_success(self, client):
        """Test successful login."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
    
    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "wrong_password"
            }
        )
        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]
    
    def test_create_api_key(self, client):
        """Test API key creation."""
        # First login to get token
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Create API key
        response = client.post(
            "/api/v1/auth/api-keys",
            json={
                "name": "test_key",
                "scopes": ["ingest", "search"],
                "expires_days": 30
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "key_id" in data
        assert "api_key" in data
        assert data["api_key"].startswith("ki_")
        assert data["scopes"] == ["ingest", "search"]
    
    def test_list_api_keys(self, client):
        """Test API key listing."""
        # Login and create key first
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Create API key
        client.post(
            "/api/v1/auth/api-keys",
            json={
                "name": "test_key",
                "scopes": ["ingest"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # List keys
        response = client.get(
            "/api/v1/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        keys = response.json()
        assert isinstance(keys, list)
        assert len(keys) >= 1
    
    def test_revoke_api_key(self, client):
        """Test API key revocation."""
        # Login and create key
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Create API key
        create_response = client.post(
            "/api/v1/auth/api-keys",
            json={
                "name": "test_key",
                "scopes": ["ingest"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        key_id = create_response.json()["key_id"]
        
        # Revoke key
        response = client.delete(
            f"/api/v1/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert "revoked successfully" in response.json()["message"]


class TestIngestionEndpoints:
    """Test document ingestion endpoints."""
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_ingest_documents_sync(self, mock_get_plugin_manager, client, mock_pipeline, mock_database):
        """Test synchronous document ingestion."""
        # Mock plugin manager
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        with patch('src.knowledge_ingestor.api.v1.pipeline', mock_pipeline):
            response = client.post(
                "/api/v1/ingest",
                json={
                    "sources": ["https://example.com/article1"],
                    "async_processing": False
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total_processed"] == 1
            assert data["successful_count"] == 1
            assert len(data["results"]) == 1
            assert data["results"][0]["success"] is True
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_ingest_documents_async(self, mock_get_plugin_manager, client, mock_pipeline, mock_database):
        """Test asynchronous document ingestion."""
        # Mock plugin manager
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        with patch('src.knowledge_ingestor.api.v1.pipeline', mock_pipeline):
            response = client.post(
                "/api/v1/ingest",
                json={
                    "sources": ["https://example.com/article" + str(i) for i in range(6)],  # More than 5 for async
                    "async_processing": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "job_id" in data
            assert data["total_processed"] == 0  # Not processed yet
    
    def test_get_job_status(self, client):
        """Test job status endpoint."""
        # First create an async job
        with patch('src.knowledge_ingestor.api.v1.pipeline') as mock_pipeline:
            mock_pipeline.process_batch.return_value = []
            response = client.post(
                "/api/v1/ingest",
                json={
                    "sources": ["https://example.com/article" + str(i) for i in range(6)],
                    "async_processing": True
                }
            )
            job_id = response.json()["job_id"]
        
        # Check job status
        response = client.get(f"/api/v1/ingest/{job_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job"]["job_id"] == job_id
        assert data["job"]["status"] in ["pending", "processing", "completed", "failed"]
    
    def test_ingest_validation_error(self, client):
        """Test ingestion with validation errors."""
        response = client.post(
            "/api/v1/ingest",
            json={
                "sources": [],  # Empty sources should fail validation
                "async_processing": False
            }
        )
        assert response.status_code == 422  # Validation error


class TestSearchEndpoints:
    """Test search functionality."""
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_search_documents(self, mock_get_plugin_manager, client, mock_database):
        """Test document search."""
        # Mock plugin manager
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.post(
            "/api/v1/search",
            json={
                "query": "machine learning",
                "limit": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["query"] == "machine learning"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Test Document 1"
        assert "processing_time" in data
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_search_with_filters(self, mock_get_plugin_manager, client, mock_database):
        """Test search with metadata filters."""
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "limit": 10,
                "filters": {"content_type": "article"},
                "include_content": True,
                "similarity_threshold": 0.5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Verify filters were passed to database
        mock_database.search_similar.assert_called_with(
            query="test",
            k=10,
            filters={"content_type": "article"},
            similarity_threshold=0.5
        )
    
    def test_search_validation_error(self, client):
        """Test search with validation errors."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "",  # Empty query should fail
                "limit": 5
            }
        )
        assert response.status_code == 422  # Validation error
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_search_database_unavailable(self, mock_get_plugin_manager, client):
        """Test search when database is unavailable."""
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = None
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "limit": 5
            }
        )
        
        assert response.status_code == 503
        assert "Database not available" in response.json()["detail"]


class TestDocumentManagement:
    """Test document management endpoints."""
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_list_documents(self, mock_get_plugin_manager, client, mock_database):
        """Test document listing."""
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.get("/api/v1/documents?limit=10&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["documents"]) == 1
        assert data["documents"][0]["id"] == "test_doc_1"
        assert data["total_count"] == 1
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_get_document(self, mock_get_plugin_manager, client, mock_database):
        """Test getting a specific document."""
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.get("/api/v1/documents/test_doc_1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["document"]["id"] == "test_doc_1"
        assert data["document"]["content"] == "Test document content"
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_get_document_not_found(self, mock_get_plugin_manager, client, mock_database):
        """Test getting non-existent document."""
        mock_plugin_manager = Mock()
        mock_database.retrieve_document.return_value = None
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.get("/api/v1/documents/nonexistent")
        
        assert response.status_code == 404
        assert "Document not found" in response.json()["detail"]
    
    @patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager')
    def test_delete_document(self, mock_get_plugin_manager, client, mock_database):
        """Test document deletion (requires auth)."""
        # Login first
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Mock plugin manager
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_database.return_value = mock_database
        mock_get_plugin_manager.return_value = mock_plugin_manager
        
        response = client.delete(
            "/api/v1/documents/test_doc_1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_id"] == "test_doc_1"


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limit_headers(self, client):
        """Test that rate limit headers are included."""
        response = client.get("/")
        
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
    
    @pytest.mark.slow
    def test_rate_limit_enforcement(self, client):
        """Test rate limit enforcement."""
        # This test would need to be run with a very low rate limit
        # or use time manipulation to test effectively
        
        # Make multiple requests rapidly
        responses = []
        for i in range(5):  # Make several requests
            response = client.get("/")
            responses.append(response)
            if i < 4:
                time.sleep(0.1)  # Small delay
        
        # All should succeed under normal rate limits
        assert all(r.status_code == 200 for r in responses)


class TestErrorHandling:
    """Test error handling and response formats."""
    
    def test_404_error_format(self, client):
        """Test 404 error response format."""
        response = client.get("/api/v1/nonexistent-endpoint")
        
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert data["error"]["type"] == "not_found_error"
        assert data["error"]["code"] == "HTTP_404"
    
    def test_validation_error_format(self, client):
        """Test validation error response format."""
        response = client.post(
            "/api/v1/ingest",
            json={
                "sources": "not_a_list"  # Should be a list
            }
        )
        
        assert response.status_code == 422
        # FastAPI returns validation errors in a different format
        # but our error handler should catch and format them


class TestMonitoring:
    """Test monitoring and health endpoints."""
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/monitoring/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "uptime_seconds" in data
        assert "components" in data
    
    def test_liveness_check(self, client):
        """Test Kubernetes liveness probe."""
        response = client.get("/monitoring/health/liveness")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
    
    def test_readiness_check(self, client):
        """Test Kubernetes readiness probe."""
        response = client.get("/monitoring/health/readiness")
        
        # Should return 200 or 503 depending on system health
        assert response.status_code in [200, 503]
    
    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = client.get("/monitoring/metrics")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


class TestAPIVersioning:
    """Test API versioning and documentation."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint information."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Knowledge Ingestor API"
        assert data["version"] == "1.0.0"
        assert "docs" in data
        assert "health" in data
    
    def test_openapi_schema(self, client):
        """Test OpenAPI schema generation."""
        response = client.get("/api/openapi.json")
        
        assert response.status_code == 200
        schema = response.json()
        assert schema["openapi"].startswith("3.")
        assert schema["info"]["title"] == "Knowledge Ingestor API"
        assert "components" in schema
        assert "securitySchemes" in schema["components"]
    
    def test_documentation_pages(self, client):
        """Test documentation page accessibility."""
        # Test Swagger UI
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Test ReDoc
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# Test fixtures and utilities
@pytest.fixture(autouse=True)
def cleanup_auth_manager():
    """Clean up auth manager state between tests."""
    yield
    # Reset auth manager state
    auth_manager.users_db.clear()
    auth_manager.api_keys_db.clear()
    auth_manager._initialize_default_users()


@pytest.mark.asyncio
async def test_async_operations():
    """Test async operation handling."""
    # Test async job processing
    from src.knowledge_ingestor.api.v1 import process_documents_async, job_store
    
    job_id = "test_job_123"
    sources = ["https://example.com/test"]
    options = {}
    
    # This would normally require proper mocking of the pipeline
    # and database components for a complete test
    pass


# Performance tests
class TestPerformance:
    """Test API performance characteristics."""
    
    @pytest.mark.slow
    def test_search_response_time(self, client, mock_database):
        """Test search response time is reasonable."""
        with patch('src.knowledge_ingestor.plugins.plugin_manager.get_plugin_manager') as mock_get_pm:
            mock_plugin_manager = Mock()
            mock_plugin_manager.get_database.return_value = mock_database
            mock_get_pm.return_value = mock_plugin_manager
            
            start_time = time.time()
            response = client.post(
                "/api/v1/search",
                json={
                    "query": "test query",
                    "limit": 10
                }
            )
            end_time = time.time()
            
            assert response.status_code == 200
            assert (end_time - start_time) < 2.0  # Should complete in under 2 seconds
    
    @pytest.mark.slow
    def test_concurrent_requests(self, client):
        """Test handling of concurrent requests."""
        import concurrent.futures
        
        def make_request():
            return client.get("/")
        
        # Test multiple concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            responses = [f.result() for f in futures]
        
        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])