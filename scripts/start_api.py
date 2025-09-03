#!/usr/bin/env python3
"""
Startup script for the Knowledge Ingestor API.

This script provides a comprehensive way to start the API server with
proper configuration, health checks, and logging.
"""

import os
import sys
import time
import signal
import argparse
from pathlib import Path
from typing import Optional

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from knowledge_ingestor.core.config import get_config, set_config, Config
from knowledge_ingestor.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Knowledge Ingestor API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start_api.py                          # Start with default settings
  python start_api.py --host 0.0.0.0 --port 8080  # Custom host/port
  python start_api.py --env production         # Production mode
  python start_api.py --config config.yaml    # Custom config file
  python start_api.py --workers 4             # Multiple workers
        """
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="API host (default: from config)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="API port (default: from config)"
    )
    
    parser.add_argument(
        "--env",
        choices=["development", "testing", "staging", "production"],
        default=None,
        help="Environment (default: from config)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Config file path"
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes (production only)"
    )
    
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Log level"
    )
    
    parser.add_argument(
        "--access-log",
        action="store_true",
        default=None,
        help="Enable access logs"
    )
    
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication"
    )
    
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Check dependencies and exit"
    )
    
    return parser.parse_args()


def check_dependencies():
    """Check if all required dependencies are installed."""
    logger.info("Checking dependencies...")
    
    required_packages = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pydantic", "Pydantic"),
        ("jose", "Python-JOSE"),
        ("passlib", "Passlib"),
        ("prometheus_client", "Prometheus Client"),
        ("psutil", "Psutil")
    ]
    
    missing_packages = []
    
    for package, name in required_packages:
        try:
            __import__(package)
            logger.info(f"✓ {name}")
        except ImportError:
            missing_packages.append(name)
            logger.error(f"✗ {name} (missing)")
    
    if missing_packages:
        logger.error(f"Missing packages: {', '.join(missing_packages)}")
        logger.error("Install with: pip install -r requirements.txt")
        return False
    
    logger.info("All dependencies satisfied")
    return True


def setup_configuration(args):
    """Setup configuration from arguments and files."""
    
    # Load config from file if specified
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
        
        logger.info(f"Loading config from: {config_path}")
        config = Config.from_file(config_path)
        set_config(config)
    
    # Get current config
    config = get_config()
    
    # Override with command line arguments
    if args.host:
        config.api.host = args.host
    
    if args.port:
        config.api.port = args.port
    
    if args.env:
        config.environment = args.env
    
    if args.debug:
        config.debug = True
        config.api.debug = True
    
    if args.no_auth:
        config.api.auth_enabled = False
    
    if args.log_level:
        config.logging.level = args.log_level
    
    return config


def validate_configuration(config: Config):
    """Validate configuration before starting."""
    logger.info("Validating configuration...")
    
    errors = []
    
    # Check required API keys
    if config.embedding.provider == "openai" and not config.openai_api_key:
        errors.append("OpenAI API key not configured (required for OpenAI embedding provider)")
    
    # Check database configuration
    if config.database.database_type == "deeplake":
        deeplake_path = Path(config.database.deeplake_path)
        if not deeplake_path.parent.exists():
            logger.warning(f"DeepLake parent directory doesn't exist: {deeplake_path.parent}")
            logger.info("Creating DeepLake directory...")
            deeplake_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check authentication configuration
    if config.api.auth_enabled and not config.api.auth_secret_key:
        logger.warning("Authentication enabled but no secret key configured")
        logger.info("Generating random secret key for this session")
    
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        return False
    
    logger.info("Configuration validation passed")
    return True


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def start_server(config: Config, args):
    """Start the API server."""
    import uvicorn
    
    # Server configuration
    server_config = {
        "app": "knowledge_ingestor.api.app:app",
        "host": config.api.host,
        "port": config.api.port,
        "log_level": args.log_level.lower() if args.log_level else "info",
        "access_log": args.access_log if args.access_log is not None else True,
        "server_header": False,
        "date_header": False,
    }
    
    # Environment-specific settings
    if config.is_development() or args.reload:
        server_config.update({
            "reload": True,
            "reload_dirs": ["src/knowledge_ingestor"],
            "reload_excludes": ["*.log", "*.tmp", "__pycache__"]
        })
    
    if config.is_production() and args.workers:
        server_config.update({
            "workers": args.workers,
            "loop": "uvloop" if sys.platform != "win32" else "asyncio",
            "http": "httptools",
            "lifespan": "on"
        })
    
    logger.info("=" * 60)
    logger.info(f"Starting Knowledge Ingestor API")
    logger.info("=" * 60)
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Host: {server_config['host']}")
    logger.info(f"Port: {server_config['port']}")
    logger.info(f"Debug mode: {config.api.debug}")
    logger.info(f"Authentication: {'enabled' if config.api.auth_enabled else 'disabled'}")
    logger.info(f"Rate limiting: {'enabled' if config.api.rate_limit_enabled else 'disabled'}")
    logger.info(f"Database: {config.database.database_type}")
    logger.info(f"Embedding provider: {config.embedding.provider}")
    
    if "workers" in server_config:
        logger.info(f"Workers: {server_config['workers']}")
    
    logger.info("=" * 60)
    logger.info(f"API Documentation: http://{server_config['host']}:{server_config['port']}/docs")
    logger.info(f"Health Check: http://{server_config['host']}:{server_config['port']}/monitoring/health")
    logger.info(f"Metrics: http://{server_config['host']}:{server_config['port']}/monitoring/metrics")
    logger.info("=" * 60)
    
    try:
        uvicorn.run(**server_config)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Setup logging early
    setup_logging()
    
    logger.info("Knowledge Ingestor API Startup")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Check dependencies if requested
    if args.check_deps:
        success = check_dependencies()
        sys.exit(0 if success else 1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Setup configuration
    try:
        config = setup_configuration(args)
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Validate configuration
    if not validate_configuration(config):
        sys.exit(1)
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Start server
    start_server(config, args)


if __name__ == "__main__":
    main()