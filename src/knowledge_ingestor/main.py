"""
Main CLI entry point for the Knowledge Ingestor system.

This module provides command-line interface for the modular Knowledge Ingestor,
allowing users to process documents, manage the system, and interact with
the plugin-based architecture.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
import json

from .core.pipeline import ProcessingPipeline
from .core.config import get_config, load_config_from_file
from .plugins.plugin_manager import get_plugin_manager, initialize_plugin_system
from .utils.logging import setup_logging, get_logger


def setup_cli_logging(verbose: bool = False, quiet: bool = False):
    """Setup logging for CLI usage."""
    if quiet:
        level = "ERROR"
    elif verbose:
        level = "DEBUG"
    else:
        level = "INFO"
    
    # Setup logging with console output
    setup_logging({
        'level': level,
        'console_enabled': True,
        'file_enabled': False,
        'colored_output': True
    })


def cmd_ingest(args):
    """Handle the ingest command."""
    logger = get_logger(__name__)
    
    # Initialize the system
    logger.info("Initializing Knowledge Ingestor...")
    plugin_count = initialize_plugin_system()
    logger.info(f"Loaded {plugin_count} plugins")
    
    # Create pipeline
    pipeline = ProcessingPipeline()
    
    # Process sources
    sources = []
    if args.sources:
        sources.extend(args.sources)
    if args.file:
        with open(args.file, 'r') as f:
            file_sources = [line.strip() for line in f if line.strip()]
            sources.extend(file_sources)
    
    if not sources:
        logger.error("No sources provided. Use --sources or --file to specify sources.")
        return 1
    
    logger.info(f"Processing {len(sources)} sources...")
    
    # Process with options
    options = {}
    if args.max_workers:
        options['max_workers'] = args.max_workers
    
    results = pipeline.process_batch(sources, **options)
    
    # Report results
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    
    logger.info(f"Processing complete: {successful} successful, {failed} failed")
    
    # Output results if requested
    if args.output:
        output_data = {
            'summary': {
                'total_sources': len(sources),
                'successful': successful,
                'failed': failed,
                'stats': pipeline.get_statistics().__dict__
            },
            'results': []
        }
        
        for i, result in enumerate(results):
            result_data = {
                'source': sources[i],
                'success': result.success,
                'processing_time': result.processing_time,
                'error': result.error,
                'metadata': result.metadata
            }
            
            if result.document:
                result_data['document'] = {
                    'id': result.document.id,
                    'title': result.document.metadata.title,
                    'content_type': result.document.metadata.content_type.value,
                    'word_count': result.document.metadata.word_count
                }
            
            output_data['results'].append(result_data)
        
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        logger.info(f"Results written to {args.output}")
    
    return 0 if successful > 0 else 1


def cmd_search(args):
    """Handle the search command."""
    logger = get_logger(__name__)
    
    # Initialize the system
    initialize_plugin_system()
    
    # Get database
    plugin_manager = get_plugin_manager()
    database = plugin_manager.get_database()
    
    if not database:
        logger.error("No database configured")
        return 1
    
    try:
        database.connect()
        
        # Perform search
        logger.info(f"Searching for: {args.query}")
        results = database.search_similar(
            query=args.query,
            k=args.limit
        )
        
        # Display results
        if not results:
            logger.info("No results found")
        else:
            logger.info(f"Found {len(results)} results:")
            
            for i, result in enumerate(results, 1):
                metadata = result.get('metadata', {})
                title = metadata.get('title', 'Untitled')
                source_url = metadata.get('web_address', 'Unknown source')
                score = result.get('score', 0.0)
                
                print(f"\n{i}. {title}")
                print(f"   Score: {score:.4f}")
                print(f"   Source: {source_url}")
                
                if args.content:
                    content = result.get('text', '')
                    preview = content[:500] + "..." if len(content) > 500 else content
                    print(f"   Preview: {preview}")
        
        database.disconnect()
        return 0
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return 1


def cmd_list_plugins(args):
    """Handle the list-plugins command."""
    logger = get_logger(__name__)
    
    # Initialize plugin system
    plugin_count = initialize_plugin_system()
    
    # Get plugin manager
    plugin_manager = get_plugin_manager()
    plugins = plugin_manager.list_available_plugins()
    
    if not plugins:
        logger.info("No plugins loaded")
        return 0
    
    logger.info(f"Loaded {len(plugins)} plugins:")
    
    for name, info in plugins.items():
        if 'error' in info:
            print(f"  ❌ {name}: ERROR - {info['error']}")
        else:
            plugin_type = info.get('type', 'unknown')
            version = info.get('version', 'unknown')
            description = info.get('description', 'No description')
            
            print(f"  ✅ {name} ({plugin_type}) v{version}")
            print(f"     {description}")
            
            if args.verbose:
                author = info.get('author', 'Unknown')
                supported_types = info.get('supported_content_types', [])
                module = info.get('module_name', 'Unknown')
                
                print(f"     Author: {author}")
                print(f"     Module: {module}")
                if supported_types:
                    print(f"     Supports: {', '.join(supported_types)}")
    
    return 0


def cmd_status(args):
    """Handle the status command.""" 
    logger = get_logger(__name__)
    
    # Initialize system
    initialize_plugin_system()
    
    # Create pipeline and check health
    pipeline = ProcessingPipeline()
    health = pipeline.health_check()
    stats = pipeline.get_statistics()
    
    # Display status
    status = "HEALTHY" if health.get('pipeline', False) else "UNHEALTHY"
    print(f"System Status: {status}")
    
    print(f"\nPlugin Manager: {'✅ OK' if health.get('plugin_manager', False) else '❌ ERROR'}")
    print(f"Database: {'✅ OK' if health.get('database', False) else '❌ ERROR'}")
    
    # Show ingestor status
    ingestors = health.get('ingestors', {})
    print(f"\nIngestors ({len(ingestors)}):")
    for name, status in ingestors.items():
        print(f"  {'✅' if status else '❌'} {name}")
    
    # Show errors if any
    errors = health.get('errors', [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for error in errors:
            print(f"  ❌ {error}")
    
    # Show statistics
    print(f"\nStatistics:")
    print(f"  Total sources processed: {stats.total_sources}")
    print(f"  Successful ingestions: {stats.successful_ingestions}")
    print(f"  Failed ingestions: {stats.failed_ingestions}")
    print(f"  Successful storage: {stats.successful_storage}")
    print(f"  Failed storage: {stats.failed_storage}")
    
    if stats.successful_ingestions > 0:
        print(f"  Average processing time: {stats.average_processing_time:.2f}s")
    
    return 0 if status == "HEALTHY" else 1


def cmd_serve(args):
    """Handle the serve command."""
    logger = get_logger(__name__)
    
    try:
        import uvicorn
        from .api.routes import app
        
        logger.info("Starting Knowledge Ingestor API server...")
        
        # Get configuration
        config = get_config()
        host = args.host or config.api.host
        port = args.port or config.api.port
        
        logger.info(f"Server starting on {host}:{port}")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            reload=args.reload
        )
        
        return 0
        
    except ImportError:
        logger.error("FastAPI and uvicorn are required for the API server")
        logger.error("Install with: pip install 'knowledge-ingestor[api]'")
        return 1
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="knowledge-ingestor",
        description="Knowledge Ingestor - Modular document processing and ingestion system"
    )
    
    # Global options
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to configuration file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--quiet", "-q", 
        action="store_true",
        help="Enable quiet mode (errors only)"
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents from sources")
    ingest_parser.add_argument(
        "sources",
        nargs="*",
        help="Sources to ingest (URLs, file paths, etc.)"
    )
    ingest_parser.add_argument(
        "--file", "-f",
        type=str,
        help="File containing list of sources (one per line)"
    )
    ingest_parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file for results (JSON format)"
    )
    ingest_parser.add_argument(
        "--max-workers",
        type=int,
        help="Maximum number of worker processes"
    )
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search documents")
    search_parser.add_argument(
        "query",
        help="Search query"
    )
    search_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=5,
        help="Maximum number of results (default: 5)"
    )
    search_parser.add_argument(
        "--content",
        action="store_true",
        help="Show content previews"
    )
    
    # List plugins command
    plugins_parser = subparsers.add_parser("list-plugins", help="List available plugins")
    plugins_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed plugin information"
    )
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status")
    
    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument(
        "--host",
        type=str,
        help="Host to bind to"
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        help="Port to bind to"
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Setup logging
    setup_cli_logging(args.verbose, args.quiet)
    logger = get_logger(__name__)
    
    # Load configuration if specified
    if args.config:
        try:
            load_config_from_file(args.config)
            logger.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return 1
    
    # Handle commands
    if args.command == "ingest":
        return cmd_ingest(args)
    elif args.command == "search":
        return cmd_search(args)
    elif args.command == "list-plugins":
        return cmd_list_plugins(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "serve":
        return cmd_serve(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())