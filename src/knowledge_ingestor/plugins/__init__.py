"""Plugin system for the Knowledge Ingestor."""

from .base import BaseIngestor, BaseDatabase, PluginRegistry
from .plugin_manager import PluginManager

__all__ = ["BaseIngestor", "BaseDatabase", "PluginRegistry", "PluginManager"]