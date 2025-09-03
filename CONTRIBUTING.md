# Contributing to Knowledge Ingestor

Thank you for your interest in contributing to the Knowledge Ingestor project! This document provides guidelines and instructions for contributors.

## Table of Contents

- [Development Setup](#development-setup)
- [Git Workflow](#git-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Submitting Changes](#submitting-changes)
- [Version Management](#version-management)

## Development Setup

### Prerequisites

- Python 3.9+ (recommended: Python 3.11)
- [UV](https://github.com/astral-sh/uv) for dependency management
- Docker and Docker Compose (for containerized development)
- Git

### Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/gyasis/knowledge-ingestor.git
   cd knowledge-ingestor
   ```

2. **Install UV** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Create and activate virtual environment**:
   ```bash
   uv sync --dev
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env.development
   # Edit .env.development with your configuration
   ```

5. **Install pre-commit hooks**:
   ```bash
   uv run pre-commit install
   ```

### Docker Development

For containerized development:

```bash
# Development environment
docker compose -f docker-compose.dev.yml up --build

# Production-like environment
docker compose up --build
```

## Git Workflow

### Branch Strategy

We use a **feature branch workflow** with semantic versioning:

- **`main`**: Production-ready code, protected branch
- **`develop`**: Integration branch (optional, for complex features)
- **`feature/<description>`**: New features
- **`fix/<description>`**: Bug fixes
- **`hotfix/<description>`**: Urgent production fixes

### Branch Naming Conventions

- Use descriptive names with hyphens: `feature/user-authentication`
- Keep branch names concise but meaningful
- Include issue numbers when applicable: `fix/issue-123-auth-bug`

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or modifying tests
- `chore`: Build process or auxiliary tool changes

**Examples**:
```
feat(api): add document similarity search endpoint
fix(parser): resolve PDF parsing timeout issue
docs(readme): update installation instructions
chore: bump version to 1.2.3.a
```

### Version Management

We use **semantic versioning** with **alpha character increments**:

- **Standard versions**: `1.0.7` (major.minor.patch)
- **Alpha increments**: `1.0.7.a`, `1.0.7.b`, ..., `1.0.7.z`
- **Completion**: `1.0.8` (when feature/fix is complete)

#### Using the Version Manager

```bash
# Check current version
python scripts/version_manager.py current

# Increment version
python scripts/version_manager.py increment alpha    # 1.0.7 -> 1.0.7.a
python scripts/version_manager.py increment patch   # 1.0.7.a -> 1.0.8
python scripts/version_manager.py increment minor   # 1.0.8 -> 1.1.0
python scripts/version_manager.py increment major   # 1.1.0 -> 2.0.0

# Set specific version
python scripts/version_manager.py set 1.2.3.b

# Create git tag
python scripts/version_manager.py increment patch --tag
```

## Coding Standards

### Code Quality Tools

We use the following tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **Ruff**: Modern linting (replaces flake8)
- **mypy**: Type checking
- **Bandit**: Security analysis

### Pre-commit Hooks

All code must pass pre-commit checks:

```bash
# Run all hooks manually
uv run pre-commit run --all-files

# Run specific hook
uv run pre-commit run black
```

### Code Style Guidelines

1. **Follow PEP 8** with Black formatting (88 character line length)
2. **Use type hints** for function parameters and return values
3. **Write docstrings** for all public functions and classes (Google style)
4. **Keep functions focused** and maintain single responsibility
5. **Use meaningful variable names** and avoid abbreviations
6. **Add comments** for complex logic, not obvious code

### Example Code Style

```python
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def process_documents(
    documents: List[str], 
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, int]:
    """Process a list of documents and return processing statistics.
    
    Args:
        documents: List of document paths or content to process
        options: Optional processing configuration
        
    Returns:
        Dictionary containing processing statistics
        
    Raises:
        DocumentProcessingError: If document processing fails
    """
    if options is None:
        options = {}
    
    stats = {"processed": 0, "failed": 0}
    
    for doc in documents:
        try:
            # Process document logic here
            logger.debug(f"Processing document: {doc}")
            stats["processed"] += 1
        except Exception as e:
            logger.error(f"Failed to process {doc}: {e}")
            stats["failed"] += 1
    
    return stats
```

## Testing

### Test Structure

- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test component interactions
- **End-to-end tests**: Test complete workflows

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=knowledge_ingestor --cov-report=html

# Run specific test file
uv run pytest tests/test_parser.py

# Run tests matching pattern
uv run pytest -k "test_pdf"

# Run tests with verbose output
uv run pytest -v
```

### Writing Tests

1. **Test file naming**: `test_<module_name>.py`
2. **Test function naming**: `test_<functionality>`
3. **Use fixtures** for common test data
4. **Mock external dependencies** (APIs, file system, etc.)
5. **Test edge cases** and error conditions

### Example Test

```python
import pytest
from unittest.mock import Mock, patch
from knowledge_ingestor.parsers import PDFParser

@pytest.fixture
def sample_pdf_path():
    return "tests/fixtures/sample.pdf"

def test_pdf_parser_success(sample_pdf_path):
    """Test successful PDF parsing."""
    parser = PDFParser()
    result = parser.parse(sample_pdf_path)
    
    assert result is not None
    assert len(result.content) > 0
    assert result.metadata["type"] == "pdf"

@patch('knowledge_ingestor.parsers.external_api_call')
def test_pdf_parser_with_api_error(mock_api, sample_pdf_path):
    """Test PDF parsing with API error."""
    mock_api.side_effect = ConnectionError("API unavailable")
    
    parser = PDFParser()
    with pytest.raises(ParsingError):
        parser.parse(sample_pdf_path)
```

## Documentation

### Types of Documentation

1. **Code documentation**: Docstrings and inline comments
2. **API documentation**: Auto-generated from docstrings
3. **User guides**: Setup, configuration, and usage
4. **Developer guides**: Architecture and contribution guidelines

### Documentation Standards

- **Use Google-style docstrings** for Python code
- **Keep README.md updated** with current installation and usage
- **Document configuration options** and environment variables
- **Provide examples** for complex features
- **Update CHANGELOG.md** with all changes

## Submitting Changes

### Pull Request Process

1. **Create a feature branch** from main:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following coding standards

3. **Update tests** and ensure all tests pass:
   ```bash
   uv run pytest
   ```

4. **Update documentation** as needed

5. **Run pre-commit checks**:
   ```bash
   uv run pre-commit run --all-files
   ```

6. **Update version** (for significant changes):
   ```bash
   python scripts/version_manager.py increment alpha
   ```

7. **Commit changes** with conventional commit messages:
   ```bash
   git add .
   git commit -m "feat(parser): add support for DOCX files"
   ```

8. **Push to your fork** and create a Pull Request

### Pull Request Template

When creating a PR, please include:

- **Clear description** of changes made
- **Link to related issues** (if applicable)
- **Testing instructions** for reviewers
- **Screenshots/examples** (if UI changes)
- **Breaking changes** documentation (if any)

### Code Review Guidelines

**For Authors**:
- Keep PRs focused and reasonably sized
- Provide clear commit messages and PR descriptions
- Respond to feedback promptly
- Update documentation as needed

**For Reviewers**:
- Focus on code quality, maintainability, and standards
- Check for security issues and potential bugs
- Verify tests cover new functionality
- Be constructive and specific in feedback

## Security Guidelines

### Sensitive Files

**NEVER commit these files**:
- `.specstory/` directories
- `claude.md` or `cursor.md` files
- API keys or credentials
- Local configuration files (`.env.local`, etc.)

### Security Best Practices

1. **Use environment variables** for sensitive configuration
2. **Validate all inputs** from external sources
3. **Use secure dependencies** and keep them updated
4. **Run security scans** with bandit and safety
5. **Follow OWASP guidelines** for web security

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions or propose ideas
- **Documentation**: Check existing docs first
- **Code Comments**: Look for inline documentation

## Recognition

Contributors will be recognized in:
- **CHANGELOG.md**: For significant contributions
- **GitHub Contributors**: Automatic recognition
- **Release notes**: For major features

Thank you for contributing to Knowledge Ingestor! 🚀

---
*For questions about contributing, please open an issue or discussion on GitHub.*