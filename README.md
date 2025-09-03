# Knowledge Ingestor

A modular, plugin-based document processing and ingestion system designed to extract, process, and store content from various sources with vector embeddings for semantic search.

## Features

- **Plugin Architecture**: Extensible system with pluggable ingestors and database backends
- **Multiple Content Sources**: Support for ArXiv papers, web articles, PDFs, and more
- **Vector Database Integration**: Store documents with embeddings for semantic search
- **Modern Web Scraping**: Advanced content extraction using crawl4ai and newspaper3k
- **Configuration Management**: Environment-based configuration with pydantic-settings
- **REST API**: FastAPI-based web interface for document operations
- **CLI Interface**: Command-line tools for batch processing and system management
- **Comprehensive Logging**: Structured logging with colored output

## Architecture Overview

The system is built around a modular plugin architecture:

```
src/knowledge_ingestor/
├── core/                 # Core system components
│   ├── document.py       # Document data structures
│   ├── pipeline.py       # Processing pipeline
│   └── config.py         # Configuration management
├── plugins/              # Plugin system
│   ├── base.py          # Abstract base classes
│   ├── ingestors/       # Content extraction plugins
│   ├── databases/       # Database storage plugins
│   └── plugin_manager.py # Plugin discovery and management
├── api/                 # REST API interface
├── utils/               # Utility modules
└── main.py              # CLI entry point
```

## Quick Start

### Installation

```bash
# Clone and install
git clone <repository-url>
cd knowledge-ingestor
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Configuration

Create a `.env` file with your configuration:

```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Database Configuration  
DB_DEEPLAKE_PATH=./deeplake_store
DB_DEEPLAKE_READ_ONLY=false

# Processing Configuration
PROCESSING_MAX_WORKERS=4
PROCESSING_CHUNK_SIZE=1000

# Logging Configuration
LOG_LEVEL=INFO
LOG_COLORED_OUTPUT=true
```

### Basic Usage

#### CLI Interface

```bash
# Process documents from URLs
python -m knowledge_ingestor.main ingest \
  "https://arxiv.org/abs/2301.12345" \
  "https://example.com/article" \
  --output results.json

# Search documents
python -m knowledge_ingestor.main search "machine learning" --limit 5

# Check system status
python -m knowledge_ingestor.main status

# List available plugins
python -m knowledge_ingestor.main list-plugins

# Start API server
python -m knowledge_ingestor.main serve --host 0.0.0.0 --port 8000
```

#### Programmatic Usage

```python
from knowledge_ingestor import ProcessingPipeline, initialize_plugin_system

# Initialize the system
initialize_plugin_system()

# Create pipeline
pipeline = ProcessingPipeline()

# Process a single document
result = pipeline.process_single("https://arxiv.org/abs/2301.12345")

if result.success:
    print(f"Document processed: {result.document.id}")
    print(f"Title: {result.document.metadata.title}")
    print(f"Content type: {result.document.metadata.content_type}")
else:
    print(f"Processing failed: {result.error}")

# Process multiple documents
sources = [
    "https://arxiv.org/abs/2301.12345",
    "https://example.com/article.pdf",
    "https://blog.example.com/post"
]

results = pipeline.process_batch(sources)
successful = [r for r in results if r.success]
print(f"Processed {len(successful)}/{len(sources)} documents successfully")
```

#### API Usage

```bash
# Start the API server
python -m knowledge_ingestor.main serve

# Ingest documents
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["https://arxiv.org/abs/2301.12345"],
    "options": {}
  }'

# Search documents
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "limit": 5
  }'

# Get system health
curl "http://localhost:8000/health"
```

## Plugin System

### Built-in Plugins

#### Ingestors
- **ArxivIngestor**: Process ArXiv scientific papers
- **WebIngestor**: Extract content from web pages and articles
- **PDFIngestor**: Process PDF documents

#### Databases
- **DeepLakeDatabase**: Vector storage with DeepLake

### Creating Custom Plugins

#### Custom Ingestor

```python
from knowledge_ingestor.plugins.base import BaseIngestor, PluginMetadata, PluginType
from knowledge_ingestor.core.document import Document, DocumentMetadata, ContentType

class CustomIngestor(BaseIngestor):
    @property
    def metadata(self):
        return PluginMetadata(
            name="CustomIngestor",
            version="1.0.0",
            description="Custom content ingestor",
            plugin_type=PluginType.INGESTOR,
            author="Your Name",
            supported_content_types=[ContentType.TEXT_FILE],
            dependencies=["requests"]
        )
    
    def can_handle(self, source):
        return str(source).startswith("custom://")
    
    def extract_content(self, source, **kwargs):
        # Your extraction logic here
        content = "Extracted content from " + str(source)
        
        metadata = DocumentMetadata(
            title="Custom Document",
            source_url=str(source),
            content_type=ContentType.TEXT_FILE
        )
        
        return Document(content=content, metadata=metadata)
```

## Configuration

The system uses environment-based configuration with pydantic-settings. Configuration sections include:

- **Database**: DeepLake, Pinecone, ChromaDB, Neo4j settings
- **Embedding**: OpenAI, HuggingFace, Cohere embedding providers
- **Processing**: Chunking, concurrency, timeout settings
- **Logging**: Level, format, file output settings
- **API**: Server host, port, CORS, authentication
- **Plugins**: Plugin directories, enabled/disabled plugins

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=knowledge_ingestor --cov-report=html
```

### Code Quality

```bash
# Format code
black src/
isort src/

# Lint code  
flake8 src/
mypy src/
```

## API Documentation

Once the server is running, visit `http://localhost:8000/docs` for interactive API documentation.

### Key Endpoints

- `POST /ingest` - Ingest documents from sources
- `POST /search` - Search documents by similarity  
- `GET /documents` - List documents
- `GET /documents/{id}` - Get specific document
- `DELETE /documents/{id}` - Delete document
- `GET /plugins` - List available plugins
- `GET /health` - System health check
- `GET /stats` - System statistics

## Troubleshooting

### Common Issues

1. **Plugin Loading Errors**
   - Check plugin dependencies are installed
   - Verify plugin configuration
   - Use `list-plugins` command to check status

2. **Database Connection Issues**
   - Verify database path/credentials
   - Check database plugin configuration
   - Use `status` command for health check

3. **Content Extraction Failures**
   - Check source accessibility
   - Verify API keys for external services
   - Review ingestor-specific requirements

### Debug Mode

```bash
# Enable verbose logging
python -m knowledge_ingestor.main --verbose ingest <sources>

# Check detailed system status
python -m knowledge_ingestor.main status
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run code quality checks
5. Submit a pull request

## License

This project is licensed under the MIT License.