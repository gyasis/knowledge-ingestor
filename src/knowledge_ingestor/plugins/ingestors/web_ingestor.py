"""
Web content ingestor plugin for the Knowledge Ingestor system.

This plugin handles extraction of content from web pages using multiple strategies
including crawl4ai for modern web scraping and newspaper3k for article extraction.
"""

import asyncio
import re
from pathlib import Path
from typing import Union, Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import html2text
import html2markdown
from newspaper import Article

# Optional dependencies with graceful fallback
try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from ..base import BaseIngestor, PluginMetadata, PluginType
from ...core.document import Document, DocumentMetadata, ContentType, ProcessingStatus


class WebIngestor(BaseIngestor):
    """
    Web content ingestor plugin.
    
    This plugin can extract content from various web sources including:
    - General web pages and articles
    - MarkTechPost articles
    - Medium articles
    - News articles
    - Blog posts
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the web ingestor with configuration."""
        super().__init__(config)
        self.include_images = config.get('include_images', False) if config else False
        self.use_crawl4ai = config.get('use_crawl4ai', True) if config else True
        self.crawler = None
        self.crawler_initialized = False
    
    @property
    def metadata(self) -> PluginMetadata:
        """Return web ingestor metadata."""
        return PluginMetadata(
            name="WebIngestor",
            version="1.0.0",
            description="Ingestor for web pages and articles",
            plugin_type=PluginType.INGESTOR,
            author="Knowledge Ingestor Team",
            supported_content_types=[
                ContentType.WEB_ARTICLE,
                ContentType.MEDIUM_ARTICLE,
                ContentType.MARKTECHPOST_ARTICLE,
                ContentType.GENERAL_WEB_PAGE
            ],
            dependencies=["requests", "beautifulsoup4", "newspaper3k", "html2text"]
        )
    
    def can_handle(self, source: Union[str, Path]) -> bool:
        """
        Check if this ingestor can handle the given source.
        
        Args:
            source: URL to check
            
        Returns:
            bool: True if source is a web URL
        """
        source_str = str(source)
        
        # Basic URL pattern matching
        url_patterns = [
            r'^https?://',
            r'^www\.',
        ]
        
        for pattern in url_patterns:
            if re.search(pattern, source_str, re.IGNORECASE):
                return True
        
        # Check for common domain patterns
        if any(domain in source_str.lower() for domain in ['.com', '.org', '.net', '.edu', '.gov']):
            return True
        
        return False
    
    def get_priority(self, source: Union[str, Path]) -> int:
        """
        Get priority for handling web sources.
        
        Args:
            source: Source to evaluate
            
        Returns:
            int: Priority score based on URL characteristics
        """
        source_str = str(source).lower()
        
        # High priority for known article sites
        if any(domain in source_str for domain in ['marktechpost.com', 'medium.com', 'towardsdatascience.com']):
            return 80
        
        # Medium priority for news sites
        if any(domain in source_str for domain in ['.news', 'blog', 'article']):
            return 70
        
        # Base priority for general web pages
        return 60 if self.can_handle(source) else 0
    
    def extract_content(self, source: Union[str, Path], **kwargs) -> Document:
        """
        Extract content from a web page.
        
        Args:
            source: URL to extract from
            **kwargs: Additional parameters
            
        Returns:
            Document: Extracted document with content and metadata
            
        Raises:
            Exception: If extraction fails
        """
        url = str(source)
        self.logger.info(f"Extracting web content from: {url}")
        
        try:
            # Determine content type based on URL
            content_type = self._determine_content_type(url)
            
            # Try multiple extraction strategies
            content, metadata = self._extract_with_fallback(url, content_type)
            
            # Create the document
            document = Document(
                content=content,
                metadata=metadata
            )
            
            # Update content characteristics
            document.metadata.word_count = len(content.split())
            document.metadata.char_count = len(content)
            document.set_processing_status(ProcessingStatus.COMPLETED)
            
            self.logger.info(f"Successfully extracted web content from: {url}")
            return document
            
        except Exception as e:
            error_msg = f"Failed to extract web content from {url}: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    def _determine_content_type(self, url: str) -> ContentType:
        """Determine content type based on URL."""
        url_lower = url.lower()
        
        if 'marktechpost.com' in url_lower:
            return ContentType.MARKTECHPOST_ARTICLE
        elif 'medium.com' in url_lower or 'towardsdatascience.com' in url_lower:
            return ContentType.MEDIUM_ARTICLE
        elif any(keyword in url_lower for keyword in ['article', 'post', 'blog', 'news']):
            return ContentType.WEB_ARTICLE
        else:
            return ContentType.GENERAL_WEB_PAGE
    
    def _extract_with_fallback(self, url: str, content_type: ContentType) -> tuple[str, DocumentMetadata]:
        """Extract content using multiple strategies with fallback."""
        
        # Strategy 1: Use crawl4ai for modern web scraping (if available and enabled)
        if CRAWL4AI_AVAILABLE and self.use_crawl4ai:
            try:
                return asyncio.run(self._extract_with_crawl4ai(url, content_type))
            except Exception as e:
                self.logger.warning(f"crawl4ai extraction failed, falling back: {e}")
        
        # Strategy 2: Use newspaper3k for article extraction
        try:
            return self._extract_with_newspaper(url, content_type)
        except Exception as e:
            self.logger.warning(f"newspaper3k extraction failed, falling back: {e}")
        
        # Strategy 3: Use BeautifulSoup for basic HTML parsing
        try:
            return self._extract_with_beautifulsoup(url, content_type)
        except Exception as e:
            self.logger.warning(f"BeautifulSoup extraction failed, falling back: {e}")
        
        # Strategy 4: Basic requests fallback
        return self._extract_with_requests(url, content_type)
    
    async def _extract_with_crawl4ai(self, url: str, content_type: ContentType) -> tuple[str, DocumentMetadata]:
        """Extract content using crawl4ai."""
        if not self.crawler_initialized:
            self.crawler = AsyncWebCrawler()
            await self.crawler.start()
            self.crawler_initialized = True
        
        result = await self.crawler.crawl(url, extract_text=True)
        
        if not result.success:
            raise Exception(f"crawl4ai failed: {result.error_message}")
        
        # Extract metadata
        metadata = DocumentMetadata(
            title=result.title or "Untitled",
            source_url=url,
            content_type=content_type,
            custom_fields={
                "extraction_method": "crawl4ai",
                "response_headers": dict(result.response_headers) if result.response_headers else {},
                "status_code": result.status_code,
                "links_extracted": len(result.links) if result.links else 0
            }
        )
        
        content = result.cleaned_html or result.html or ""
        
        # Convert HTML to markdown if needed
        if result.cleaned_html:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = not self.include_images
            content = h.handle(result.cleaned_html)
        
        return content, metadata
    
    def _extract_with_newspaper(self, url: str, content_type: ContentType) -> tuple[str, DocumentMetadata]:
        """Extract content using newspaper3k."""
        article = Article(url)
        article.download()
        article.parse()
        
        # Try to get additional info
        try:
            article.nlp()
        except:
            pass  # NLP processing is optional
        
        metadata = DocumentMetadata(
            title=article.title or "Untitled",
            authors=article.authors or [],
            source_url=url,
            content_type=content_type,
            summary=article.summary or None,
            custom_fields={
                "extraction_method": "newspaper3k",
                "publish_date": article.publish_date.isoformat() if article.publish_date else None,
                "top_image": article.top_image,
                "keywords": article.keywords or [],
                "meta_keywords": article.meta_keywords or [],
                "meta_description": article.meta_description,
                "canonical_link": article.canonical_link,
                "movies": article.movies or []
            }
        )
        
        return article.text, metadata
    
    def _extract_with_beautifulsoup(self, url: str, content_type: ContentType) -> tuple[str, DocumentMetadata]:
        """Extract content using BeautifulSoup."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract title
        title = "Untitled"
        title_tag = (soup.find('h1') or 
                    soup.find('title') or 
                    soup.find('meta', property='og:title') or
                    soup.find('meta', attrs={'name': 'title'}))
        
        if title_tag:
            if title_tag.name == 'meta':
                title = title_tag.get('content', 'Untitled')
            else:
                title = title_tag.get_text().strip()
        
        # Extract main content based on content type
        content = ""
        if content_type == ContentType.MARKTECHPOST_ARTICLE:
            content = self._extract_marktechpost_content(soup)
        else:
            content = self._extract_general_content(soup)
        
        # Convert to markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = not self.include_images
        content = h.handle(str(content))
        
        metadata = DocumentMetadata(
            title=title,
            source_url=url,
            content_type=content_type,
            custom_fields={
                "extraction_method": "beautifulsoup",
                "content_length": len(content),
                "status_code": response.status_code
            }
        )
        
        return content, metadata
    
    def _extract_marktechpost_content(self, soup: BeautifulSoup) -> str:
        """Extract content specifically from MarkTechPost articles."""
        # Look for article content
        article = soup.find('article') or soup.find('div', class_='entry-content')
        
        if article:
            # Remove unwanted elements
            for element in article.find_all(['script', 'style', 'nav', 'footer', 'aside']):
                element.decompose()
            return str(article)
        
        return self._extract_general_content(soup)
    
    def _extract_general_content(self, soup: BeautifulSoup) -> str:
        """Extract general content from any webpage."""
        # Try various content selectors
        content_selectors = [
            'article',
            '.content',
            '.post-content', 
            '.entry-content',
            '#content',
            'main',
            '.main-content',
            'body'
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                # Clean up the content
                for element in content.find_all(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                    element.decompose()
                return str(content)
        
        # Fallback: return body content
        body = soup.find('body')
        if body:
            for element in body.find_all(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                element.decompose()
            return str(body)
        
        return str(soup)
    
    def _extract_with_requests(self, url: str, content_type: ContentType) -> tuple[str, DocumentMetadata]:
        """Basic extraction using requests as final fallback."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Convert HTML to text
        h = html2text.HTML2Text()
        h.ignore_links = False  
        h.ignore_images = not self.include_images
        content = h.handle(response.text)
        
        metadata = DocumentMetadata(
            title="Extracted Content",
            source_url=url,
            content_type=content_type,
            custom_fields={
                "extraction_method": "requests_fallback",
                "status_code": response.status_code,
                "content_type_header": response.headers.get('content-type', '')
            }
        )
        
        return content, metadata
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text (if tiktoken is available)."""
        if not TIKTOKEN_AVAILABLE:
            # Fallback: rough estimate
            return len(text.split())
        
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            tokens = encoding.encode(text)
            return len(tokens)
        except Exception:
            return len(text.split())
    
    def validate_config(self) -> bool:
        """Validate the ingestor configuration."""
        try:
            import requests
            import bs4
            import html2text
            import newspaper
            return True
        except ImportError as e:
            self.logger.error(f"Required dependency not available: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown the ingestor and cleanup resources."""
        if self.crawler and self.crawler_initialized:
            try:
                await self.crawler.close()
                self.crawler_initialized = False
                self.logger.info("Crawl4AI crawler closed successfully")
            except Exception as e:
                self.logger.error(f"Error closing crawler: {e}")
        
        super().shutdown()