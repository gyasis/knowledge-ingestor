"""
PDF document ingestor plugin for the Knowledge Ingestor system.

This plugin handles extraction of content from PDF files using pymupdf4llm
for structured markdown conversion.
"""

import re
from pathlib import Path
from typing import Union, Optional, List, Dict, Any
import tempfile
import pymupdf4llm
import requests

from ..base import BaseIngestor, PluginMetadata, PluginType
from ...core.document import Document, DocumentMetadata, ContentType, ProcessingStatus


class PDFIngestor(BaseIngestor):
    """
    PDF document ingestor plugin.
    
    This plugin can extract content from PDF files, both local files
    and PDF URLs, converting them to structured markdown format.
    """
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return PDF ingestor metadata."""
        return PluginMetadata(
            name="PDFIngestor",
            version="1.0.0",
            description="Ingestor for PDF documents",
            plugin_type=PluginType.INGESTOR,
            author="Knowledge Ingestor Team",
            supported_content_types=[ContentType.PDF_DOCUMENT],
            dependencies=["pymupdf4llm", "requests"]
        )
    
    def can_handle(self, source: Union[str, Path]) -> bool:
        """
        Check if this ingestor can handle the given source.
        
        Args:
            source: File path or URL to check
            
        Returns:
            bool: True if source is a PDF file or PDF URL
        """
        source_str = str(source)
        
        # Check for PDF file extension
        if source_str.lower().endswith('.pdf'):
            return True
        
        # Check for PDF URLs
        if re.search(r'\.pdf(\?|$)', source_str, re.IGNORECASE):
            return True
        
        # Check for local file paths
        if Path(source_str).exists() and Path(source_str).suffix.lower() == '.pdf':
            return True
        
        return False
    
    def get_priority(self, source: Union[str, Path]) -> int:
        """
        Get priority for handling PDF sources.
        
        Args:
            source: Source to evaluate
            
        Returns:
            int: High priority (95) for PDF files
        """
        return 95 if self.can_handle(source) else 0
    
    def extract_content(self, source: Union[str, Path], **kwargs) -> Document:
        """
        Extract content from a PDF file.
        
        Args:
            source: PDF file path or URL
            **kwargs: Additional parameters
            
        Returns:
            Document: Extracted document with content and metadata
            
        Raises:
            Exception: If extraction fails
        """
        source_str = str(source)
        self.logger.info(f"Extracting PDF content from: {source_str}")
        
        try:
            # Determine if source is URL or local file
            is_url = source_str.startswith(('http://', 'https://'))
            
            if is_url:
                # Download PDF from URL
                pdf_path = self._download_pdf(source_str)
                filename = Path(source_str).name or "downloaded.pdf"
            else:
                # Local file
                pdf_path = Path(source_str)
                if not pdf_path.exists():
                    raise Exception(f"PDF file not found: {pdf_path}")
                filename = pdf_path.name
            
            # Extract content using pymupdf4llm
            content = self._extract_pdf_content(pdf_path)
            
            # Create metadata
            metadata = DocumentMetadata(
                title=self._extract_title_from_filename(filename),
                source_url=source_str if is_url else f"file://{pdf_path.absolute()}",
                content_type=ContentType.PDF_DOCUMENT,
                file_size=pdf_path.stat().st_size if pdf_path.exists() else None,
                mime_type="application/pdf",
                custom_fields={
                    "extraction_method": "pymupdf4llm",
                    "original_filename": filename,
                    "is_url_source": is_url
                }
            )
            
            # Create the document
            document = Document(
                content=content,
                metadata=metadata
            )
            
            # Update content characteristics
            document.metadata.word_count = len(content.split())
            document.metadata.char_count = len(content)
            document.set_processing_status(ProcessingStatus.COMPLETED)
            
            self.logger.info(f"Successfully extracted PDF content from: {source_str}")
            return document
            
        except Exception as e:
            error_msg = f"Failed to extract PDF content from {source_str}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        finally:
            # Clean up downloaded temporary file if needed
            if is_url and 'pdf_path' in locals() and pdf_path.exists():
                try:
                    pdf_path.unlink()
                    self.logger.debug(f"Cleaned up temporary file: {pdf_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to clean up temporary file {pdf_path}: {e}")
    
    def _download_pdf(self, url: str) -> Path:
        """
        Download PDF from URL to a temporary file.
        
        Args:
            url: PDF URL
            
        Returns:
            Path: Path to downloaded PDF file
            
        Raises:
            Exception: If download fails
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            
            # Check if response is actually a PDF
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
                # Try to detect PDF by magic number
                chunk = response.iter_content(chunk_size=8192).__next__()
                if not chunk.startswith(b'%PDF'):
                    raise Exception(f"URL does not appear to contain a PDF file: {content_type}")
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            temp_path = Path(temp_file.name)
            
            # Download the file
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.logger.debug(f"Downloaded PDF from {url} to {temp_path}")
            return temp_path
            
        except Exception as e:
            error_msg = f"Failed to download PDF from {url}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _extract_pdf_content(self, pdf_path: Path) -> str:
        """
        Extract content from PDF using pymupdf4llm.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            str: Extracted markdown content
            
        Raises:
            Exception: If extraction fails
        """
        try:
            self.logger.debug(f"Extracting content from PDF: {pdf_path}")
            
            # Use pymupdf4llm to convert PDF to markdown
            markdown_content = pymupdf4llm.to_markdown(str(pdf_path))
            
            if not markdown_content or not markdown_content.strip():
                raise Exception("PDF extraction resulted in empty content")
            
            # Basic cleanup
            cleaned_content = self._clean_pdf_content(markdown_content)
            
            return cleaned_content
            
        except Exception as e:
            error_msg = f"Failed to extract content from PDF {pdf_path}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _clean_pdf_content(self, content: str) -> str:
        """
        Clean extracted PDF content.
        
        Args:
            content: Raw extracted content
            
        Returns:
            str: Cleaned content
        """
        # Remove excessive whitespace
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # Remove page markers/headers that might be artifacts
        cleaned = re.sub(r'^Page \d+.*$', '', cleaned, flags=re.MULTILINE)
        
        # Remove very short lines that are likely artifacts
        lines = cleaned.split('\n')
        filtered_lines = []
        
        for line in lines:
            stripped = line.strip()
            # Keep non-empty lines and lines that are likely content
            if not stripped:
                filtered_lines.append('')  # Preserve empty lines for formatting
            elif len(stripped) > 2 or stripped.isalpha():  # Keep reasonable content
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    def _extract_title_from_filename(self, filename: str) -> str:
        """
        Extract a title from the PDF filename.
        
        Args:
            filename: PDF filename
            
        Returns:
            str: Extracted title
        """
        # Remove extension
        name = Path(filename).stem
        
        # Replace common separators with spaces
        name = re.sub(r'[_-]+', ' ', name)
        
        # Capitalize words
        title = ' '.join(word.capitalize() for word in name.split())
        
        return title if title else "PDF Document"
    
    def validate_config(self) -> bool:
        """
        Validate the ingestor configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        try:
            import pymupdf4llm
            import requests
            return True
        except ImportError as e:
            self.logger.error(f"Required dependency not available: {e}")
            return False