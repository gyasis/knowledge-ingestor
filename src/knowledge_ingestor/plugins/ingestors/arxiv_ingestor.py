"""
ArXiv paper ingestor plugin for the Knowledge Ingestor system.

This plugin handles extraction of content from ArXiv papers by downloading
the PDF version and converting it to structured text using pymupdf4llm.
"""

import re
import tempfile
from pathlib import Path
from typing import Union, Optional, List
import arxiv
import pymupdf4llm

from ..base import BaseIngestor, PluginMetadata, PluginType
from ...core.document import Document, DocumentMetadata, ContentType, ProcessingStatus


class ArxivIngestor(BaseIngestor):
    """
    ArXiv paper ingestor plugin.
    
    This plugin can process ArXiv URLs and identifiers, downloading the PDF
    and extracting structured content including metadata like title, authors,
    and abstract.
    """
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return ArXiv ingestor metadata."""
        return PluginMetadata(
            name="ArxivIngestor",
            version="1.0.0", 
            description="Ingestor for ArXiv scientific papers",
            plugin_type=PluginType.INGESTOR,
            author="Knowledge Ingestor Team",
            supported_content_types=[ContentType.ARXIV_PAPER],
            dependencies=["arxiv", "pymupdf4llm"]
        )
    
    def can_handle(self, source: Union[str, Path]) -> bool:
        """
        Check if this ingestor can handle the given source.
        
        Args:
            source: URL or identifier to check
            
        Returns:
            bool: True if source is an ArXiv URL or identifier
        """
        source_str = str(source)
        
        # Check for ArXiv URL patterns
        arxiv_url_patterns = [
            r'arxiv\.org/abs/\d+\.\d+',
            r'arxiv\.org/pdf/\d+\.\d+',
            r'export\.arxiv\.org/abs/\d+\.\d+'
        ]
        
        for pattern in arxiv_url_patterns:
            if re.search(pattern, source_str):
                return True
        
        # Check for bare ArXiv identifiers (like 2301.12345)
        if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', source_str):
            return True
        
        return False
    
    def get_priority(self, source: Union[str, Path]) -> int:
        """
        Get priority for handling ArXiv sources.
        
        Args:
            source: Source to evaluate
            
        Returns:
            int: High priority (90) for ArXiv sources
        """
        return 90 if self.can_handle(source) else 0
    
    def extract_identifier(self, url_or_id: str) -> str:
        """
        Extract the ArXiv identifier from a URL or return the identifier if already provided.
        
        Args:
            url_or_id: The ArXiv URL or identifier
            
        Returns:
            str: The clean ArXiv identifier
        """
        # Try to extract from URL
        match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+(?:v\d+)?)', url_or_id)
        if match:
            return match.group(1)
        
        # If it's already just an identifier, return as-is
        if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', url_or_id):
            return url_or_id
        
        # Fallback: return the original string
        return url_or_id
    
    def extract_content(self, source: Union[str, Path], **kwargs) -> Document:
        """
        Extract content from an ArXiv paper.
        
        Args:
            source: ArXiv URL or identifier
            **kwargs: Additional parameters (currently unused)
            
        Returns:
            Document: Extracted document with content and metadata
            
        Raises:
            Exception: If extraction fails
        """
        source_str = str(source)
        identifier = self.extract_identifier(source_str)
        
        self.logger.info(f"Extracting ArXiv paper: {identifier}")
        
        try:
            # Create a client and search for the paper
            client = arxiv.Client()
            search = arxiv.Search(id_list=[identifier])
            paper = next(client.results(search))
            
            # Extract paper metadata first
            metadata = DocumentMetadata(
                title=paper.title,
                authors=[str(author) for author in paper.authors],
                source_url=f"https://arxiv.org/abs/{identifier}",
                content_type=ContentType.ARXIV_PAPER,
                summary=paper.summary,
                custom_fields={
                    "arxiv_id": identifier,
                    "published": paper.published.isoformat() if paper.published else None,
                    "updated": paper.updated.isoformat() if paper.updated else None,
                    "categories": paper.categories,
                    "primary_category": paper.primary_category,
                    "pdf_url": paper.pdf_url,
                    "entry_id": paper.entry_id,
                    "doi": paper.doi,
                    "journal_ref": paper.journal_ref,
                    "comment": paper.comment
                }
            )
            
            # Download and process the PDF
            content = self._download_and_convert_pdf(paper, identifier)
            
            # Create the document
            document = Document(
                content=content,
                metadata=metadata
            )
            
            # Update content characteristics
            document.metadata.word_count = len(content.split())
            document.metadata.char_count = len(content)
            document.set_processing_status(ProcessingStatus.COMPLETED)
            
            self.logger.info(f"Successfully extracted ArXiv paper: {identifier}")
            return document
            
        except StopIteration:
            error_msg = f"No paper found with identifier: {identifier}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Failed to extract ArXiv paper {identifier}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _download_and_convert_pdf(self, paper: arxiv.Result, identifier: str) -> str:
        """
        Download the ArXiv PDF and convert it to markdown.
        
        Args:
            paper: ArXiv paper result object
            identifier: ArXiv identifier
            
        Returns:
            str: Converted markdown content
            
        Raises:
            Exception: If download or conversion fails
        """
        try:
            # Create a temporary directory
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Define the PDF path
                pdf_path = Path(tmp_dir) / f"{identifier}.pdf"
                
                self.logger.debug(f"Downloading PDF to: {pdf_path}")
                
                # Download the PDF to the temporary directory
                paper.download_pdf(dirpath=tmp_dir, filename=f"{identifier}.pdf")
                
                # Convert PDF to Markdown using pymupdf4llm
                self.logger.debug(f"Converting PDF to markdown: {pdf_path}")
                md_content = pymupdf4llm.to_markdown(str(pdf_path))
                
                if not md_content:
                    raise Exception("PDF conversion resulted in empty content")
                
                return md_content
                
        except Exception as e:
            error_msg = f"Failed to download/convert PDF for {identifier}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_arxiv_abstract(self, identifier: str) -> Optional[str]:
        """
        Retrieve just the abstract of an ArXiv paper.
        
        Args:
            identifier: The ArXiv identifier
            
        Returns:
            Optional[str]: The abstract or None if not found
        """
        try:
            identifier = self.extract_identifier(identifier)
            
            # Search for the paper
            client = arxiv.Client()
            results = client.results(arxiv.Search(id_list=[identifier]))
            paper = next(results)
            
            return paper.summary
            
        except StopIteration:
            self.logger.warning(f"No paper found with identifier: {identifier}")
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving abstract for {identifier}: {e}")
            return None
    
    def validate_config(self) -> bool:
        """
        Validate the ingestor configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        # ArXiv ingestor doesn't require specific configuration
        # Just check if required dependencies are available
        try:
            import arxiv
            import pymupdf4llm
            return True
        except ImportError as e:
            self.logger.error(f"Required dependency not available: {e}")
            return False