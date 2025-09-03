"""
Unit tests for configuration management.
"""

import os
import tempfile
import pytest
from pathlib import Path

from knowledge_ingestor.core.config import Config, ConfigError


class TestConfig:
    """Test configuration management."""
    
    def test_default_config(self):
        """Test default configuration initialization."""
        # Set required environment variable
        os.environ["OPENAI_API_KEY"] = "test-key"
        
        config = Config()
        
        assert config.database.backend == "deeplake"
        assert config.openai.api_key == "test-key"
        assert config.processing.chunk_size == 1000
        assert config.logging.level == "INFO"
        
        # Clean up
        del os.environ["OPENAI_API_KEY"]
    
    def test_env_override(self):
        """Test environment variable overrides."""
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["DATABASE_BACKEND"] = "chroma"
        os.environ["CHUNK_SIZE"] = "2000"
        os.environ["LOG_LEVEL"] = "DEBUG"
        
        config = Config()
        
        assert config.database.backend == "chroma"
        assert config.processing.chunk_size == 2000
        assert config.logging.level == "DEBUG"
        
        # Clean up
        del os.environ["OPENAI_API_KEY"]
        del os.environ["DATABASE_BACKEND"]
        del os.environ["CHUNK_SIZE"]
        del os.environ["LOG_LEVEL"]
    
    def test_config_file_json(self):
        """Test JSON configuration file loading."""
        config_data = {
            "database": {"backend": "pinecone"},
            "openai": {"api_key": "file-key", "model": "gpt-4"},
            "processing": {"chunk_size": 1500}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            import json
            json.dump(config_data, f)
            config_file = f.name
        
        try:
            config = Config(config_file=config_file)
            
            assert config.database.backend == "pinecone"
            assert config.openai.api_key == "file-key"
            assert config.openai.model == "gpt-4"
            assert config.processing.chunk_size == 1500
            
        finally:
            os.unlink(config_file)
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Missing OpenAI API key should raise error
        with pytest.raises(ConfigError, match="OpenAI API key"):
            config = Config()
            config.validate()
    
    def test_config_validation_chunk_size(self):
        """Test chunk size validation."""
        os.environ["OPENAI_API_KEY"] = "test-key"
        
        config = Config()
        config.processing.chunk_size = -1
        
        with pytest.raises(ConfigError, match="Chunk size must be positive"):
            config.validate()
        
        # Clean up
        del os.environ["OPENAI_API_KEY"]
    
    def test_config_validation_chunk_overlap(self):
        """Test chunk overlap validation."""
        os.environ["OPENAI_API_KEY"] = "test-key"
        
        config = Config()
        config.processing.chunk_overlap = 2000  # Greater than chunk_size (1000)
        
        with pytest.raises(ConfigError, match="Chunk overlap must be less than chunk size"):
            config.validate()
        
        # Clean up
        del os.environ["OPENAI_API_KEY"]
    
    def test_config_to_dict(self):
        """Test configuration serialization to dictionary."""
        os.environ["OPENAI_API_KEY"] = "test-key"
        
        config = Config()
        config_dict = config.to_dict()
        
        assert "database" in config_dict
        assert "openai" in config_dict
        assert "processing" in config_dict
        assert "logging" in config_dict
        assert "plugins" in config_dict
        
        assert config_dict["database"]["backend"] == "deeplake"
        assert config_dict["openai"]["api_key"] == "test-key"
        
        # Clean up
        del os.environ["OPENAI_API_KEY"]