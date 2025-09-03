"""
Plugin loading and discovery system.

This module handles automatic discovery, loading, and registration of plugins
for ingestors, database backends, and embedding providers.
"""

import importlib
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Dict, Any, List, Type, Optional
import sys

from ..core.base import (
    BasePlugin, BaseIngestor, BaseDatabaseBackend, BaseEmbeddingProvider,
    PluginRegistry
)
from ..core.exceptions import PluginError
from ..core.config import PluginConfig


class PluginLoader:
    """Handles plugin discovery and loading."""
    
    def __init__(self, config: PluginConfig, logger: Optional[logging.Logger] = None):
        """
        Initialize plugin loader.
        
        Args:
            config: Plugin configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._loaded_modules = {}
    
    async def load_plugins(self, registry: PluginRegistry) -> None:
        """
        Load and register all plugins.
        
        Args:
            registry: Plugin registry to populate
        """
        self.logger.info("Loading plugins...")
        
        # Load built-in plugins
        await self._load_builtin_plugins(registry)
        
        # Load external plugins from configured paths
        if self.config.auto_discover:
            await self._load_external_plugins(registry)
        
        self.logger.info("Plugin loading completed")
    
    async def _load_builtin_plugins(self, registry: PluginRegistry) -> None:
        """Load built-in plugins from the plugins package."""
        builtin_plugins_path = Path(__file__).parent
        
        # Load ingestors
        ingestors_path = builtin_plugins_path / "ingestors"
        if ingestors_path.exists():
            await self._load_plugins_from_directory(
                ingestors_path, BaseIngestor, registry.register_ingestor
            )
        
        # Load database backends
        databases_path = builtin_plugins_path / "databases"
        if databases_path.exists():
            await self._load_plugins_from_directory(
                databases_path, BaseDatabaseBackend, registry.register_database
            )
        
        # Load embedding providers
        embeddings_path = builtin_plugins_path / "embeddings"
        if embeddings_path.exists():
            await self._load_plugins_from_directory(
                embeddings_path, BaseEmbeddingProvider, registry.register_embedding_provider
            )
    
    async def _load_external_plugins(self, registry: PluginRegistry) -> None:
        """Load plugins from external paths."""
        for plugin_path in self.config.plugin_paths:
            try:
                path = Path(plugin_path)
                if path.is_file() and path.suffix == '.py':
                    await self._load_plugin_file(path, registry)
                elif path.is_dir():
                    await self._load_plugins_from_directory(
                        path, BasePlugin, self._register_any_plugin
                    )
                else:
                    self.logger.warning(f"Invalid plugin path: {plugin_path}")
            except Exception as e:
                self.logger.error(f"Failed to load plugins from {plugin_path}: {e}")
    
    async def _load_plugins_from_directory(
        self,
        directory: Path,
        base_class: Type[BasePlugin],
        register_func: callable
    ) -> None:
        """Load all plugins from a directory."""
        if not directory.exists():
            return
        
        for plugin_file in directory.glob("*.py"):
            if plugin_file.name.startswith("__"):
                continue
            
            try:
                await self._load_plugin_file(plugin_file, None, base_class, register_func)
            except Exception as e:
                self.logger.error(f"Failed to load plugin {plugin_file}: {e}")
    
    async def _load_plugin_file(
        self,
        plugin_file: Path,
        registry: Optional[PluginRegistry] = None,
        base_class: Type[BasePlugin] = BasePlugin,
        register_func: Optional[callable] = None
    ) -> None:
        """Load a single plugin file."""
        module_name = f"plugin_{plugin_file.stem}"
        
        try:
            # Load module
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if not spec or not spec.loader:
                raise PluginError(f"Cannot load plugin spec from {plugin_file}")
            
            module = importlib.util.module_from_spec(spec)
            self._loaded_modules[module_name] = module
            
            # Add to sys.modules for imports
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Find plugin classes
            plugin_classes = self._find_plugin_classes(module, base_class)
            
            # Register plugins
            for plugin_class in plugin_classes:
                if register_func:
                    await self._instantiate_and_register(plugin_class, register_func)
                elif registry:
                    await self._register_plugin_class(plugin_class, registry)
            
        except Exception as e:
            raise PluginError(f"Failed to load plugin from {plugin_file}: {e}")
    
    def _find_plugin_classes(
        self,
        module,
        base_class: Type[BasePlugin]
    ) -> List[Type[BasePlugin]]:
        """Find all plugin classes in a module."""
        plugin_classes = []
        
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and
                issubclass(obj, base_class) and
                obj is not base_class and
                not getattr(obj, '__abstract__', False)):
                plugin_classes.append(obj)
        
        return plugin_classes
    
    async def _instantiate_and_register(
        self,
        plugin_class: Type[BasePlugin],
        register_func: callable
    ) -> None:
        """Instantiate and register a plugin class."""
        try:
            # Get plugin configuration
            plugin_config = self._get_plugin_config(plugin_class)
            
            # Instantiate plugin
            plugin_instance = plugin_class(plugin_config, self.logger)
            
            # Register plugin
            register_func(plugin_instance.name, plugin_instance)
            
            self.logger.info(f"Loaded plugin: {plugin_class.__name__}")
            
        except Exception as e:
            self.logger.error(f"Failed to instantiate plugin {plugin_class.__name__}: {e}")
    
    async def _register_plugin_class(
        self,
        plugin_class: Type[BasePlugin],
        registry: PluginRegistry
    ) -> None:
        """Register a plugin class with the appropriate registry method."""
        if issubclass(plugin_class, BaseIngestor):
            await self._instantiate_and_register(plugin_class, registry.register_ingestor)
        elif issubclass(plugin_class, BaseDatabaseBackend):
            await self._instantiate_and_register(plugin_class, registry.register_database)
        elif issubclass(plugin_class, BaseEmbeddingProvider):
            await self._instantiate_and_register(plugin_class, registry.register_embedding_provider)
    
    def _register_any_plugin(self, name: str, plugin: BasePlugin) -> None:
        """Generic plugin registration function for external plugins."""
        # This would need the registry context, but serves as a placeholder
        self.logger.info(f"Would register plugin: {name}")
    
    def _get_plugin_config(self, plugin_class: Type[BasePlugin]) -> Dict[str, Any]:
        """Get configuration for a specific plugin."""
        plugin_name = plugin_class.__name__.lower()
        
        # Try to get plugin-specific config from environment or config files
        # For now, return empty config - this could be extended to read from
        # plugin-specific config sections
        return {}
    
    def get_loaded_modules(self) -> Dict[str, Any]:
        """Get information about loaded plugin modules."""
        return {
            name: {
                "file": getattr(module, "__file__", "unknown"),
                "classes": [
                    cls.__name__ for name, cls in inspect.getmembers(module)
                    if inspect.isclass(cls) and issubclass(cls, BasePlugin)
                ]
            }
            for name, module in self._loaded_modules.items()
        }