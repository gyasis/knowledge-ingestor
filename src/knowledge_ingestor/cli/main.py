"""
Command-line interface for Knowledge Ingestor.

This module provides CLI commands for ingesting content, searching documents,
and managing the knowledge base.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich.panel import Panel
from rich import print as rprint

from ..core.config import Config
from ..core.manager import KnowledgeIngestorManager
from ..core.exceptions import KnowledgeIngestorError


console = Console()


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file"
)
@click.option(
    "--env-file",
    type=click.Path(exists=True),
    help="Path to environment file"
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="INFO",
    help="Logging level"
)
@click.pass_context
def cli(ctx, config: Optional[str], env_file: Optional[str], log_level: str):
    """Knowledge Ingestor - Document ingestion and storage system."""
    try:
        # Initialize configuration
        config_kwargs = {}
        if config:
            config_kwargs["config_file"] = config
        if env_file:
            config_kwargs["env_file"] = env_file
        
        # Override log level
        config_kwargs["logging"] = {"level": log_level}
        
        app_config = Config(**config_kwargs)
        
        # Initialize manager
        manager = KnowledgeIngestorManager(app_config)
        
        # Store in context for subcommands
        ctx.ensure_object(dict)
        ctx.obj["manager"] = manager
        ctx.obj["config"] = app_config
        
    except Exception as e:
        console.print(f"[red]Error initializing application: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("sources", nargs=-1, required=True)
@click.option(
    "--ingestor",
    "-i",
    help="Specific ingestor to use"
)
@click.option(
    "--no-store",
    is_flag=True,
    help="Process but don't store in database"
)
@click.option(
    "--batch-size",
    type=int,
    default=5,
    help="Number of sources to process concurrently"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for results (JSON format)"
)
@click.pass_context
def ingest(
    ctx,
    sources: List[str],
    ingestor: Optional[str],
    no_store: bool,
    batch_size: int,
    output: Optional[str]
):
    """Ingest content from URLs or files."""
    manager = ctx.obj["manager"]
    
    async def run_ingest():
        try:
            await manager.initialize()
            
            console.print(f"[blue]Ingesting {len(sources)} sources...[/blue]")
            
            # Process in batches
            results = []
            for i in range(0, len(sources), batch_size):
                batch = sources[i:i + batch_size]
                
                console.print(f"[yellow]Processing batch {i//batch_size + 1}...[/yellow]")
                
                batch_results = await manager.batch_ingest_content(
                    batch,
                    max_concurrent=batch_size,
                    store=not no_store
                )
                results.extend(batch_results)
                
                # Show progress
                for source, result in zip(batch, batch_results):
                    status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
                    console.print(f"  {status} {source}")
                    if not result.success:
                        console.print(f"    [red]Error: {result.error}[/red]")
            
            # Summary
            success_count = sum(1 for r in results if r.success)
            console.print(f"\n[bold]Results:[/bold] {success_count}/{len(results)} successful")
            
            # Save results if output specified
            if output:
                output_data = [
                    {
                        "source": sources[i],
                        "success": result.success,
                        "error": result.error,
                        "processing_time": result.processing_time,
                        "metadata": result.metadata
                    }
                    for i, result in enumerate(results)
                ]
                
                with open(output, 'w') as f:
                    json.dump(output_data, f, indent=2, default=str)
                
                console.print(f"[green]Results saved to {output}[/green]")
            
        except Exception as e:
            console.print(f"[red]Ingestion failed: {e}[/red]")
            sys.exit(1)
        finally:
            await manager.cleanup()
    
    asyncio.run(run_ingest())


@cli.command()
@click.argument("query")
@click.option(
    "--limit",
    "-l",
    type=int,
    default=10,
    help="Maximum number of results"
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "compact"]),
    default="table",
    help="Output format"
)
@click.option(
    "--filter",
    "filters",
    multiple=True,
    help="Metadata filters in key=value format"
)
@click.pass_context
def search(
    ctx,
    query: str,
    limit: int,
    output_format: str,
    filters: List[str]
):
    """Search documents in the knowledge base."""
    manager = ctx.obj["manager"]
    
    async def run_search():
        try:
            await manager.initialize()
            
            # Parse filters
            filter_dict = {}
            for filter_str in filters:
                if "=" in filter_str:
                    key, value = filter_str.split("=", 1)
                    filter_dict[key.strip()] = value.strip()
            
            console.print(f"[blue]Searching for: {query}[/blue]")
            
            results = await manager.search_documents(
                query=query,
                limit=limit,
                filters=filter_dict if filter_dict else None
            )
            
            if output_format == "json":
                output_data = {
                    "query": query,
                    "total_results": results.total_results,
                    "documents": [
                        {
                            "title": doc.title,
                            "url": doc.url,
                            "content_preview": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
                            "metadata": doc.metadata
                        }
                        for doc in results.documents
                    ]
                }
                console.print(json.dumps(output_data, indent=2, default=str))
                
            elif output_format == "compact":
                for i, doc in enumerate(results.documents, 1):
                    score = f" (score: {results.scores[i-1]:.3f})" if results.scores else ""
                    console.print(f"[bold]{i}.[/bold] {doc.title}{score}")
                    console.print(f"   [blue]{doc.url}[/blue]")
                    console.print(f"   {doc.content[:150]}...")
                    console.print()
                    
            else:  # table format
                table = Table(title=f"Search Results for '{query}'")
                table.add_column("Title", style="bold")
                table.add_column("URL", style="blue")
                table.add_column("Preview", max_width=50)
                table.add_column("Score", justify="right")
                
                for i, doc in enumerate(results.documents):
                    score = f"{results.scores[i]:.3f}" if results.scores else "N/A"
                    preview = doc.content[:100] + "..." if len(doc.content) > 100 else doc.content
                    
                    table.add_row(
                        doc.title or "Untitled",
                        doc.url or "N/A",
                        preview,
                        score
                    )
                
                console.print(table)
            
            console.print(f"\n[bold]Total results:[/bold] {results.total_results}")
            
        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            sys.exit(1)
        finally:
            await manager.cleanup()
    
    asyncio.run(run_search())


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status and configuration."""
    manager = ctx.obj["manager"]
    config = ctx.obj["config"]
    
    async def run_status():
        try:
            await manager.initialize()
            
            status_info = manager.get_status()
            
            # System status panel
            status_content = f"""
[bold]Initialization:[/bold] {'✓ Ready' if status_info['initialized'] else '✗ Not initialized'}
[bold]Default Database:[/bold] {status_info.get('default_database', 'None')}
[bold]Default Ingestor:[/bold] {status_info.get('default_ingestor', 'None')}
[bold]Embedding Provider:[/bold] {status_info.get('default_embedding_provider', 'None')}
            """.strip()
            
            console.print(Panel(status_content, title="System Status", border_style="green"))
            
            # Available plugins
            plugins_table = Table(title="Available Plugins")
            plugins_table.add_column("Type", style="bold")
            plugins_table.add_column("Name", style="blue")
            
            for ingestor in status_info.get('available_ingestors', []):
                plugins_table.add_row("Ingestor", ingestor)
            
            for database in status_info.get('available_databases', []):
                plugins_table.add_row("Database", database)
            
            for provider in status_info.get('available_embedding_providers', []):
                plugins_table.add_row("Embedding", provider)
            
            console.print(plugins_table)
            
            # Configuration summary
            config_content = f"""
[bold]Database Backend:[/bold] {config.database.backend}
[bold]OpenAI Model:[/bold] {config.openai.model}
[bold]Embedding Model:[/bold] {config.openai.embedding_model}
[bold]Chunk Size:[/bold] {config.processing.chunk_size}
[bold]Max Concurrent:[/bold] {config.processing.max_concurrent_requests}
[bold]Log Level:[/bold] {config.logging.level}
            """.strip()
            
            console.print(Panel(config_content, title="Configuration", border_style="blue"))
            
        except Exception as e:
            console.print(f"[red]Failed to get status: {e}[/red]")
            sys.exit(1)
        finally:
            await manager.cleanup()
    
    asyncio.run(run_status())


@cli.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Configuration format"
)
def init_config(output_format: str):
    """Generate a sample configuration file."""
    
    if output_format == "json":
        config_template = {
            "database": {
                "backend": "deeplake",
                "dataset_path": "./deeplake_dataset",
                "read_only": False
            },
            "openai": {
                "model": "gpt-3.5-turbo",
                "embedding_model": "text-embedding-ada-002",
                "max_tokens": 1500,
                "temperature": 0.3
            },
            "processing": {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "max_concurrent_requests": 5,
                "retry_attempts": 3
            },
            "logging": {
                "level": "INFO",
                "file": "knowledge_ingestor.log"
            },
            "plugins": {
                "enabled_ingestors": ["web", "pdf", "arxiv", "youtube"],
                "enabled_databases": ["deeplake"],
                "auto_discover": True
            }
        }
        
        console.print(json.dumps(config_template, indent=2))
    
    else:  # YAML
        config_template = """# Knowledge Ingestor Configuration

database:
  backend: deeplake
  dataset_path: ./deeplake_dataset
  read_only: false

openai:
  model: gpt-3.5-turbo
  embedding_model: text-embedding-ada-002
  max_tokens: 1500
  temperature: 0.3

processing:
  chunk_size: 1000
  chunk_overlap: 200
  max_concurrent_requests: 5
  retry_attempts: 3

logging:
  level: INFO
  file: knowledge_ingestor.log

plugins:
  enabled_ingestors:
    - web
    - pdf
    - arxiv
    - youtube
  enabled_databases:
    - deeplake
  auto_discover: true
"""
        
        console.print(config_template)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()