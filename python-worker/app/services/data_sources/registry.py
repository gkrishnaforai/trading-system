"""
Data Source Registry
Follows SOLID: Single Responsibility Principle
Manages registration and retrieval of data sources
"""
import logging
from typing import Dict, Type, Optional, List
from enum import Enum

from app.services.data_sources.base import BaseDataSource, DataSourceType
from app.services.data_sources.fmp import FMPDataSource

logger = logging.getLogger(__name__)


class DataSourceRegistry:
    """Registry for managing data sources
    
    Single Responsibility: Only manages data source registration and retrieval
    Follows Registry Pattern for centralized management
    """
    
    def __init__(self):
        self._sources: Dict[DataSourceType, BaseDataSource] = {}
        self._source_classes: Dict[DataSourceType, Type[BaseDataSource]] = {}
        self._register_default_sources()
    
    def _register_default_sources(self):
        """Register default data sources"""
        self.register_source_class(DataSourceType.FMP, FMPDataSource)
    
    def register_source_class(self, source_type: DataSourceType, source_class: Type[BaseDataSource]):
        """Register a data source class
        
        Factory Method Pattern - allows registration of new data source types
        """
        if not issubclass(source_class, BaseDataSource):
            raise ValueError(f"Source class must inherit from BaseDataSource")
        
        self._source_classes[source_type] = source_class
        logger.info(f"📝 Registered data source class: {source_type.value}")
    
    def get_source(self, source_type: DataSourceType) -> BaseDataSource:
        """Get or create data source instance
        
        Lazy Loading Pattern - creates instances only when needed
        """
        if source_type not in self._sources:
            if source_type not in self._source_classes:
                raise ValueError(f"Data source {source_type.value} not registered")
            
            # Create new instance
            source_class = self._source_classes[source_type]
            self._sources[source_type] = source_class()
            logger.info(f"🔧 Created data source instance: {source_type.value}")
        
        return self._sources[source_type]
    
    def get_available_sources(self) -> List[DataSourceType]:
        """Get list of available data source types"""
        return list(self._source_classes.keys())
    
    def is_source_available(self, source_type: DataSourceType) -> bool:
        """Check if data source type is available"""
        return source_type in self._source_classes
    
    async def test_source(self, source_type: DataSourceType) -> bool:
        """Test data source connection"""
        try:
            source = self.get_source(source_type)
            if hasattr(source, 'test_connection'):
                return await source.test_connection()
            else:
                # Fallback validation
                return await source.validate_symbol('AAPL')
        except Exception as e:
            logger.error(f"❌ Failed to test {source_type.value}: {e}")
            return False
    
    async def test_all_sources(self) -> Dict[DataSourceType, bool]:
        """Test all registered data sources"""
        results = {}
        for source_type in self.get_available_sources():
            results[source_type] = await self.test_source(source_type)
        return results
    
    def get_source_info(self, source_type: DataSourceType) -> Dict[str, str]:
        """Get information about a data source"""
        try:
            source = self.get_source(source_type)
            info = {
                'name': source_type.value,
                'class': source.__class__.__name__,
                'description': source.__doc__ or 'No description available'
            }
            
            # Add rate limit info if available
            if hasattr(source, 'get_rate_limit_info'):
                info.update(source.get_rate_limit_info())
            
            return info
        except Exception as e:
            return {
                'name': source_type.value,
                'error': str(e)
            }
    
    def get_all_source_info(self) -> Dict[DataSourceType, Dict[str, str]]:
        """Get information about all data sources"""
        info = {}
        for source_type in self.get_available_sources():
            info[source_type] = self.get_source_info(source_type)
        return info


# Global registry instance (Singleton Pattern)
data_source_registry = DataSourceRegistry()


def get_data_source_registry() -> DataSourceRegistry:
    """Get the global data source registry instance"""
    return data_source_registry


# Convenience functions
def get_data_source(source_type: DataSourceType) -> BaseDataSource:
    """Get data source by type"""
    return data_source_registry.get_source(source_type)


def get_fmp_source() -> FMPDataSource:
    """Get FMP data source (convenience function)"""
    return data_source_registry.get_source(DataSourceType.FMP)


async def validate_all_sources() -> Dict[str, bool]:
    """Validate all data sources"""
    results = {}
    for source_type in data_source_registry.get_available_sources():
        results[source_type.value] = await data_source_registry.test_source(source_type)
    return results
