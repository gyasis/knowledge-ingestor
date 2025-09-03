"""
Configuration management for the Knowledge Ingestor system.

This module provides comprehensive configuration management using pydantic-settings,
supporting environment variables, config files, and runtime configuration.
"""

from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from pydantic import BaseSettings, Field, validator
from enum import Enum
import os


class LogLevel(str, Enum):
    """Logging level enumeration."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING" 
    INFO = "INFO"
    DEBUG = "DEBUG"


class DatabaseType(str, Enum):
    """Supported database types."""
    DEEPLAKE = "deeplake"
    PINECONE = "pinecone"
    CHROMADB = "chromadb"
    NEO4J = "neo4j"


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    COHERE = "cohere"


class DatabaseConfig(BaseSettings):
    """Database-specific configuration."""
    
    # General settings
    database_type: DatabaseType = Field(DatabaseType.DEEPLAKE, description="Database backend type")
    
    # DeepLake settings
    deeplake_path: str = Field("./deeplake_store", description="DeepLake storage path")
    deeplake_read_only: bool = Field(False, description="DeepLake read-only mode")
    deeplake_token: Optional[str] = Field(None, description="DeepLake authentication token")
    
    # Pinecone settings
    pinecone_api_key: Optional[str] = Field(None, description="Pinecone API key")
    pinecone_environment: Optional[str] = Field(None, description="Pinecone environment")
    pinecone_index_name: str = Field("knowledge-ingestor", description="Pinecone index name")
    
    # ChromaDB settings
    chromadb_path: str = Field("./chromadb_store", description="ChromaDB storage path")
    chromadb_host: str = Field("localhost", description="ChromaDB host")
    chromadb_port: int = Field(8000, description="ChromaDB port")
    
    # Neo4j settings
    neo4j_uri: str = Field("bolt://localhost:7687", description="Neo4j URI")
    neo4j_username: str = Field("neo4j", description="Neo4j username")
    neo4j_password: Optional[str] = Field(None, description="Neo4j password")
    
    class Config:
        env_prefix = "DB_"
        case_sensitive = False


class EmbeddingConfig(BaseSettings):
    """Embedding configuration."""
    
    provider: EmbeddingProvider = Field(EmbeddingProvider.OPENAI, description="Embedding provider")
    
    # OpenAI settings
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: str = Field("text-embedding-ada-002", description="OpenAI embedding model")
    openai_max_tokens: int = Field(8191, description="Maximum tokens for OpenAI")
    
    # HuggingFace settings
    hf_model: str = Field("sentence-transformers/all-MiniLM-L6-v2", description="HuggingFace model")
    hf_device: str = Field("cpu", description="Device for HuggingFace model")
    
    # Cohere settings
    cohere_api_key: Optional[str] = Field(None, description="Cohere API key")
    cohere_model: str = Field("embed-english-v2.0", description="Cohere embedding model")
    
    # General embedding settings
    embedding_dimension: int = Field(1536, description="Embedding vector dimension")
    batch_size: int = Field(100, description="Embedding batch size")
    
    class Config:
        env_prefix = "EMBEDDING_"
        case_sensitive = False


class ProcessingConfig(BaseSettings):
    """Document processing configuration."""
    
    # Text processing
    chunk_size: int = Field(1000, description="Text chunk size for processing")
    chunk_overlap: int = Field(200, description="Overlap between text chunks")
    max_document_size: int = Field(1_000_000, description="Maximum document size in characters")
    
    # Summarization
    enable_summarization: bool = Field(True, description="Enable AI summarization")
    summary_max_tokens: int = Field(500, description="Maximum tokens for summaries")
    summary_model: str = Field("gpt-3.5-turbo", description="Model for summarization")
    
    # Concurrent processing
    max_workers: int = Field(4, description="Maximum worker threads")
    processing_timeout: int = Field(300, description="Processing timeout in seconds")
    
    # Content extraction
    extract_keywords: bool = Field(True, description="Enable keyword extraction")
    extract_topics: bool = Field(True, description="Enable topic extraction")
    max_keywords: int = Field(10, description="Maximum keywords to extract")
    
    class Config:
        env_prefix = "PROCESSING_"
        case_sensitive = False


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    
    level: LogLevel = Field(LogLevel.INFO, description="Logging level")
    format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format"
    )
    file_enabled: bool = Field(True, description="Enable file logging")
    file_path: str = Field("./logs", description="Log file directory")
    file_max_size: int = Field(10_000_000, description="Maximum log file size in bytes")
    file_backup_count: int = Field(5, description="Number of backup log files")
    console_enabled: bool = Field(True, description="Enable console logging")
    colored_output: bool = Field(True, description="Enable colored console output")
    
    class Config:
        env_prefix = "LOG_"
        case_sensitive = False


class APIConfig(BaseSettings):
    """API configuration."""
    
    host: str = Field("0.0.0.0", description="API host")
    port: int = Field(8000, description="API port")
    debug: bool = Field(False, description="Debug mode")
    cors_enabled: bool = Field(True, description="Enable CORS")
    cors_origins: List[str] = Field(["*"], description="Allowed CORS origins")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(True, description="Enable rate limiting")
    rate_limit_requests: int = Field(100, description="Requests per minute")
    
    # Authentication
    auth_enabled: bool = Field(False, description="Enable authentication")
    auth_secret_key: Optional[str] = Field(None, description="JWT secret key")
    auth_algorithm: str = Field("HS256", description="JWT algorithm")
    auth_expire_minutes: int = Field(30, description="Token expiration time")
    
    class Config:
        env_prefix = "API_"
        case_sensitive = False


class PluginConfig(BaseSettings):
    """Plugin system configuration."""
    
    plugin_directories: List[str] = Field(
        ["./plugins", "./src/knowledge_ingestor/plugins"],
        description="Plugin search directories"
    )
    auto_discover: bool = Field(True, description="Enable automatic plugin discovery")
    enabled_ingestors: Optional[List[str]] = Field(None, description="Explicitly enabled ingestors")
    disabled_ingestors: List[str] = Field([], description="Disabled ingestors")
    plugin_timeout: int = Field(60, description="Plugin execution timeout")
    
    class Config:
        env_prefix = "PLUGIN_"
        case_sensitive = False


class Config(BaseSettings):
    """
    Main configuration class for the Knowledge Ingestor system.
    
    This class aggregates all configuration sections and provides
    centralized configuration management with environment variable support.
    """
    
    # Configuration sections
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    plugins: PluginConfig = Field(default_factory=PluginConfig)
    
    # General settings
    environment: str = Field("development", description="Environment name")
    debug: bool = Field(False, description="Global debug mode")
    test_mode: bool = Field(False, description="Test mode flag")
    
    # External service keys
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    medium_api_key: Optional[str] = Field(None, description="Medium API key")
    gemini_api_key: Optional[str] = Field(None, description="Gemini API key")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        validate_assignment = True
        
    @validator('environment')
    def validate_environment(cls, v):
        """Validate environment setting."""
        allowed_environments = ['development', 'testing', 'staging', 'production']
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of: {allowed_environments}")
        return v
    
    @classmethod
    def from_file(cls, config_path: Union[str, Path]) -> 'Config':
        """Load configuration from a file."""
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        if config_path.suffix.lower() == '.json':
            import json
            with open(config_path) as f:
                config_data = json.load(f)
        elif config_path.suffix.lower() in ['.yml', '.yaml']:
            import yaml
            with open(config_path) as f:
                config_data = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported config file format: {config_path.suffix}")
        
        return cls(**config_data)
    
    def save_to_file(self, config_path: Union[str, Path], format: str = 'yaml') -> None:
        """Save configuration to a file."""
        config_path = Path(config_path)
        config_data = self.dict()
        
        if format.lower() == 'json':
            import json
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)
        elif format.lower() in ['yml', 'yaml']:
            import yaml
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration as dictionary."""
        return self.database.dict()
    
    def get_embedding_config(self) -> Dict[str, Any]:
        """Get embedding configuration as dictionary."""
        return self.embedding.dict()
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.environment == "testing" or self.test_mode


# Global configuration instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config_instance
    _config_instance = config


def load_config_from_file(config_path: Union[str, Path]) -> Config:
    """Load configuration from file and set as global instance."""
    config = Config.from_file(config_path)
    set_config(config)
    return config