#!/usr/bin/env python3
"""
Example usage of the Knowledge Ingestor system.

This script demonstrates how to use the modular Knowledge Ingestor
to process documents from various sources.
"""

import os
import sys
from pathlib import Path

# Add the src directory to Python path for development
sys.path.insert(0, str(Path(__file__).parent / "src"))

from knowledge_ingestor.core.pipeline import ProcessingPipeline
from knowledge_ingestor.plugins.plugin_manager import initialize_plugin_system, get_plugin_manager
from knowledge_ingestor.core.config import get_config
from knowledge_ingestor.utils.logging import setup_logging, get_logger


def main():
    """Main example function."""
    # Setup logging
    setup_logging({
        'level': 'INFO',
        'console_enabled': True,
        'colored_output': True,
        'file_enabled': False
    })
    
    logger = get_logger(__name__)
    logger.info("Knowledge Ingestor Example Usage")
    
    # Check for required environment variables
    if not os.getenv('OPENAI_API_KEY'):
        logger.error("OPENAI_API_KEY environment variable is required")
        logger.error("Set it with: export OPENAI_API_KEY=your_api_key")
        return 1
    
    try:
        # Initialize the plugin system
        logger.info("Initializing plugin system...")
        plugin_count = initialize_plugin_system()
        logger.info(f"Loaded {plugin_count} plugins")
        
        # Get plugin manager and list plugins
        plugin_manager = get_plugin_manager()
        plugins = plugin_manager.list_available_plugins()
        
        logger.info("Available plugins:")
        for name, info in plugins.items():
            if 'error' not in info:
                plugin_type = info.get('type', 'unknown')
                logger.info(f"  - {name} ({plugin_type})")
        
        # Create processing pipeline
        logger.info("Creating processing pipeline...")
        pipeline = ProcessingPipeline()
        
        # Check system health
        health = pipeline.health_check()
        if not health.get('pipeline', False):
            logger.error("System health check failed")
            for error in health.get('errors', []):
                logger.error(f"  - {error}")
            return 1
        
        logger.info("System health check passed")
        
        # Example sources to process
        example_sources = [
            # ArXiv paper
            "https://arxiv.org/abs/2301.12345",  # Example ArXiv paper
            
            # Web articles (you can replace with actual URLs)
            "https://www.example.com",  # This will likely fail, but shows error handling
            
            # PDF URL (replace with actual PDF URL if available)
            # "https://example.com/document.pdf",
        ]
        
        # Filter to only sources that are likely to work
        working_sources = [
            "https://arxiv.org/abs/2301.12345",  # ArXiv paper should work
        ]
        
        if not working_sources:
            logger.warning("No valid sources to process in this example")
            logger.info("To test with real sources, modify the example_sources list")
            return 0
        
        logger.info(f"Processing {len(working_sources)} example sources...")
        
        # Process sources one by one to show individual results
        for i, source in enumerate(working_sources, 1):
            logger.info(f"Processing source {i}/{len(working_sources)}: {source}")
            
            try:
                result = pipeline.process_single(source)
                
                if result.success:
                    doc = result.document
                    logger.info(f"✅ Success: {source}")
                    logger.info(f"   Document ID: {doc.id}")
                    logger.info(f"   Title: {doc.metadata.title}")
                    logger.info(f"   Content Type: {doc.metadata.content_type.value}")
                    logger.info(f"   Word Count: {doc.metadata.word_count}")
                    logger.info(f"   Processing Time: {result.processing_time:.2f}s")
                    
                    if doc.metadata.summary:
                        summary_preview = doc.metadata.summary[:200] + "..." if len(doc.metadata.summary) > 200 else doc.metadata.summary
                        logger.info(f"   Summary: {summary_preview}")
                
                else:
                    logger.error(f"❌ Failed: {source}")
                    logger.error(f"   Error: {result.error}")
                    logger.error(f"   Processing Time: {result.processing_time:.2f}s")
            
            except Exception as e:
                logger.error(f"❌ Exception processing {source}: {e}")
        
        # Batch processing example
        logger.info("\nDemonstrating batch processing...")
        batch_results = pipeline.process_batch(working_sources, max_workers=2)
        
        successful = [r for r in batch_results if r.success]
        failed = [r for r in batch_results if not r.success]
        
        logger.info(f"Batch processing complete:")
        logger.info(f"  ✅ Successful: {len(successful)}")
        logger.info(f"  ❌ Failed: {len(failed)}")
        
        # Show pipeline statistics
        stats = pipeline.get_statistics()
        logger.info(f"\nPipeline Statistics:")
        logger.info(f"  Total sources processed: {stats.total_sources}")
        logger.info(f"  Successful ingestions: {stats.successful_ingestions}")
        logger.info(f"  Failed ingestions: {stats.failed_ingestions}")
        logger.info(f"  Successful storage: {stats.successful_storage}")
        logger.info(f"  Failed storage: {stats.failed_storage}")
        
        if stats.successful_ingestions > 0:
            logger.info(f"  Average processing time: {stats.average_processing_time:.2f}s")
        
        # Search example (if we have documents stored)
        if stats.successful_storage > 0:
            logger.info("\nTesting document search...")
            database = plugin_manager.get_database()
            
            if database:
                try:
                    search_results = database.search_similar("machine learning", k=3)
                    
                    logger.info(f"Found {len(search_results)} search results:")
                    for i, result in enumerate(search_results, 1):
                        metadata = result.get('metadata', {})
                        title = metadata.get('title', 'Untitled')
                        score = result.get('score', 0.0)
                        logger.info(f"  {i}. {title} (score: {score:.4f})")
                
                except Exception as e:
                    logger.error(f"Search failed: {e}")
            else:
                logger.warning("No database available for search")
        
        logger.info("\n🎉 Example completed successfully!")
        logger.info("Check the logs above for detailed processing information.")
        
        return 0
        
    except Exception as e:
        logger.error(f"Example failed with error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())