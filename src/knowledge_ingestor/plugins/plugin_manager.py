"""
Plugin discovery and management system for the Knowledge Ingestor.

This module provides functionality to automatically discover, load, and manage
plugins from various sources including directories, packages, and entry points.
"""

import importlib
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Type, Union
import logging
from dataclasses import dataclass

from .base import BasePlugin, BaseIngestor, BaseDatabase, PluginType, get_plugin_registry
from ..core.config import get_config


@dataclass
class PluginSource:
    """Information about a plugin source."""
    name: str
    path: Path
    module_name: str
    plugin_class: Type[BasePlugin]


class PluginLoader:
    """Handles loading plugins from various sources."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def load_from_file(self, plugin_file: Path) -> List[PluginSource]:
        """
        Load plugins from a Python file.
        
        Args:
            plugin_file: Path to Python file containing plugins
            
        Returns:
            List[PluginSource]: List of discovered plugin sources
        """
        plugins = []
        
        try:
            # Generate module name from file path
            module_name = f"dynamic_plugin_{plugin_file.stem}"
            
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                self.logger.error(f"Cannot load module from {plugin_file}")
                return plugins
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Find plugin classes in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, BasePlugin) and 
                    obj != BasePlugin and 
                    not inspect.isabstract(obj)):
                    
                    plugins.append(PluginSource(
                        name=name,
                        path=plugin_file,
                        module_name=module_name,
                        plugin_class=obj
                    ))
                    self.logger.info(f"Discovered plugin: {name} from {plugin_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to load plugin from {plugin_file}: {e}")
        
        return plugins
    
    def load_from_directory(self, plugin_dir: Path) -> List[PluginSource]:
        """
        Load all plugins from a directory.
        
        Args:
            plugin_dir: Directory containing plugin files
            
        Returns:
            List[PluginSource]: List of discovered plugin sources
        """
        plugins = []
        
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            self.logger.warning(f"Plugin directory does not exist: {plugin_dir}")
            return plugins
        
        # Search for Python files
        for python_file in plugin_dir.rglob("*.py"):
            # Skip __init__.py and __pycache__ directories
            if python_file.name == "__init__.py" or "__pycache__" in str(python_file):
                continue
            
            file_plugins = self.load_from_file(python_file)
            plugins.extend(file_plugins)
        
        return plugins
    
    def load_from_package(self, package_name: str) -> List[PluginSource]:
        """
        Load plugins from an installed package.
        
        Args:
            package_name: Name of the package to load plugins from
            
        Returns:
            List[PluginSource]: List of discovered plugin sources
        """
        plugins = []
        
        try:
            package = importlib.import_module(package_name)
            package_path = Path(package.__file__).parent
            
            # Search for plugin modules in the package
            for python_file in package_path.rglob("*.py"):
                if python_file.name == "__init__.py":
                    continue
                
                # Convert file path to module name
                relative_path = python_file.relative_to(package_path.parent)
                module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
                full_module_name = ".".join(module_parts)
                
                try:
                    module = importlib.import_module(full_module_name)
                    
                    # Find plugin classes
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (issubclass(obj, BasePlugin) and 
                            obj != BasePlugin and 
                            not inspect.isabstract(obj)):
                            
                            plugins.append(PluginSource(
                                name=name,
                                path=python_file,
                                module_name=full_module_name,
                                plugin_class=obj
                            ))
                            self.logger.info(f"Discovered plugin: {name} from package {package_name}")
                
                except ImportError as e:
                    self.logger.debug(f"Could not import {full_module_name}: {e}")
                    continue
        
        except ImportError as e:
            self.logger.error(f"Could not import package {package_name}: {e}")
        
        return plugins


class PluginDiscovery:
    """Plugin discovery system using various strategies."""
    
    def __init__(self, loader: PluginLoader = None):
        self.loader = loader or PluginLoader()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def discover_from_directories(self, directories: List[Union[str, Path]]) -> List[PluginSource]:
        """
        Discover plugins from multiple directories.
        
        Args:
            directories: List of directories to search
            
        Returns:
            List[PluginSource]: All discovered plugin sources
        """
        all_plugins = []
        
        for directory in directories:
            dir_path = Path(directory).expanduser().resolve()
            plugins = self.loader.load_from_directory(dir_path)
            all_plugins.extend(plugins)
        
        return all_plugins
    
    def discover_builtin_plugins(self) -> List[PluginSource]:
        """
        Discover built-in plugins from the package structure.
        
        Returns:
            List[PluginSource]: Built-in plugin sources
        """
        plugins = []
        
        # Get the current package directory
        current_dir = Path(__file__).parent
        
        # Search in ingestors directory
        ingestors_dir = current_dir / "ingestors"
        if ingestors_dir.exists():
            plugins.extend(self.loader.load_from_directory(ingestors_dir))
        
        # Search in databases directory
        databases_dir = current_dir / "databases"
        if databases_dir.exists():
            plugins.extend(self.loader.load_from_directory(databases_dir))
        
        return plugins
    
    def discover_entry_point_plugins(self) -> List[PluginSource]:
        """
        Discover plugins through setuptools entry points.
        
        Returns:
            List[PluginSource]: Entry point plugin sources
        """
        plugins = []
        
        try:
            import pkg_resources
            
            # Look for plugins in standard entry points
            entry_point_groups = [
                'knowledge_ingestor.ingestors',
                'knowledge_ingestor.databases',
                'knowledge_ingestor.processors',
                'knowledge_ingestor.embedders'
            ]
            
            for group in entry_point_groups:
                for entry_point in pkg_resources.iter_entry_points(group):
                    try:
                        plugin_class = entry_point.load()
                        if issubclass(plugin_class, BasePlugin):
                            plugins.append(PluginSource(
                                name=entry_point.name,
                                path=Path(entry_point.module_name),
                                module_name=entry_point.module_name,
                                plugin_class=plugin_class
                            ))
                            self.logger.info(f"Discovered entry point plugin: {entry_point.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to load entry point {entry_point.name}: {e}")
        
        except ImportError:
            self.logger.debug("pkg_resources not available, skipping entry point discovery")
        
        return plugins


class PluginManager:
    """
    Main plugin management system for the Knowledge Ingestor.
    
    Coordinates plugin discovery, loading, registration, and lifecycle management.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or get_config().plugins.dict()
        self.registry = get_plugin_registry()
        self.discovery = PluginDiscovery()
        self.loader = PluginLoader()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Track loaded plugins
        self.loaded_plugins: Dict[str, PluginSource] = {}
    
    def discover_all_plugins(self) -> List[PluginSource]:
        """
        Discover all available plugins from all sources.
        
        Returns:
            List[PluginSource]: All discovered plugin sources
        """
        all_plugins = []
        
        # Discover built-in plugins
        if self.config.get('auto_discover', True):
            builtin_plugins = self.discovery.discover_builtin_plugins()
            all_plugins.extend(builtin_plugins)
            self.logger.info(f"Discovered {len(builtin_plugins)} built-in plugins")
        
        # Discover from configured directories
        plugin_directories = self.config.get('plugin_directories', [])
        if plugin_directories:
            dir_plugins = self.discovery.discover_from_directories(plugin_directories)
            all_plugins.extend(dir_plugins)
            self.logger.info(f"Discovered {len(dir_plugins)} plugins from directories")
        
        # Discover entry point plugins
        entry_plugins = self.discovery.discover_entry_point_plugins()
        all_plugins.extend(entry_plugins)
        self.logger.info(f"Discovered {len(entry_plugins)} entry point plugins")
        
        return all_plugins
    
    def load_plugin(self, plugin_source: PluginSource, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Load and register a single plugin.
        
        Args:
            plugin_source: Plugin source to load
            config: Optional plugin-specific configuration
            
        Returns:
            bool: True if plugin was loaded successfully
        """
        try:
            # Check if plugin is disabled
            disabled_plugins = self.config.get('disabled_ingestors', [])
            if plugin_source.name in disabled_plugins:
                self.logger.info(f"Plugin {plugin_source.name} is disabled, skipping")
                return False
            
            # Check if specific plugins are enabled
            enabled_plugins = self.config.get('enabled_ingestors')
            if enabled_plugins and plugin_source.name not in enabled_plugins:
                self.logger.info(f"Plugin {plugin_source.name} not in enabled list, skipping")
                return False
            
            # Register the plugin class
            self.registry.register_plugin(plugin_source.plugin_class)
            
            # Store the plugin source
            self.loaded_plugins[plugin_source.name] = plugin_source
            
            self.logger.info(f"Successfully loaded plugin: {plugin_source.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load plugin {plugin_source.name}: {e}")
            return False
    
    def load_all_plugins(self) -> int:
        """
        Discover and load all available plugins.
        
        Returns:
            int: Number of plugins successfully loaded
        """
        plugins = self.discover_all_plugins()
        loaded_count = 0
        
        for plugin_source in plugins:
            if self.load_plugin(plugin_source):
                loaded_count += 1
        
        self.logger.info(f"Loaded {loaded_count} out of {len(plugins)} discovered plugins")
        return loaded_count
    
    def get_ingestor_for_source(self, source: Union[str, Path]) -> Optional[BaseIngestor]:
        """
        Get the best ingestor for a given source.
        
        Args:
            source: Source to find ingestor for
            
        Returns:
            Optional[BaseIngestor]: Best ingestor or None if none found
        """
        ingestors = self.registry.get_ingestors_for_source(source)
        return ingestors[0] if ingestors else None
    
    def get_database(self, database_name: Optional[str] = None) -> Optional[BaseDatabase]:
        """
        Get database instance by name.
        
        Args:
            database_name: Name of database plugin (defaults to configured database)
            
        Returns:
            Optional[BaseDatabase]: Database instance or None if not found
        """
        if database_name is None:
            # Get default database from config
            from ..core.config import get_config
            database_name = get_config().database.database_type.value
        
        return self.registry.get_plugin_instance(PluginType.DATABASE, database_name)
    
    def list_available_plugins(self) -> Dict[str, Dict[str, Any]]:
        """
        List all available plugins with their metadata.
        
        Returns:
            Dict[str, Dict[str, Any]]: Plugin information by name
        """
        plugin_info = {}
        
        for plugin_name, plugin_source in self.loaded_plugins.items():
            try:
                # Get plugin metadata
                temp_instance = plugin_source.plugin_class()
                metadata = temp_instance.metadata
                
                plugin_info[plugin_name] = {
                    'name': metadata.name,
                    'version': metadata.version,
                    'description': metadata.description,
                    'type': metadata.plugin_type.value,
                    'author': metadata.author,
                    'supported_content_types': [ct.value for ct in metadata.supported_content_types],
                    'source_path': str(plugin_source.path),
                    'module_name': plugin_source.module_name
                }
            except Exception as e:
                self.logger.error(f"Error getting info for plugin {plugin_name}: {e}")
                plugin_info[plugin_name] = {
                    'name': plugin_name,
                    'error': str(e)
                }
        
        return plugin_info
    
    def shutdown(self) -> None:
        """Shutdown the plugin manager and all loaded plugins."""
        self.registry.shutdown_all()
        self.loaded_plugins.clear()
        self.logger.info("Plugin manager shutdown complete")


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def initialize_plugin_system() -> int:
    """
    Initialize the plugin system by discovering and loading all plugins.
    
    Returns:
        int: Number of plugins loaded
    """
    manager = get_plugin_manager()
    return manager.load_all_plugins()