"""Ingestor plugins for the Knowledge Ingestor system."""

from .arxiv_ingestor import ArxivIngestor
from .web_ingestor import WebIngestor
from .pdf_ingestor import PDFIngestor

__all__ = ["ArxivIngestor", "WebIngestor", "PDFIngestor"]