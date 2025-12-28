"""
Dependency Injection Container
SOLID: Dependency Inversion Principle - services depend on abstractions
"""
import logging
from typing import Dict, Any, Optional, Type, Callable, TypeVar
from functools import lru_cache

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ServiceContainer:
    """
    Simple dependency injection container
    Manages service lifecycle and dependencies
    """
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._initialized = False
    
    def register_singleton(self, name: str, instance: Any):
        """Register a singleton instance"""
        self._singletons[name] = instance
        logger.debug(f"Registered singleton: {name}")
    
    def register_factory(self, name: str, factory: Callable, singleton: bool = True):
        """Register a factory function"""
        self._factories[name] = (factory, singleton)
        logger.debug(f"Registered factory: {name} (singleton={singleton})")
    
    def get(self, name: str) -> Any:
        """Get service instance"""
        # Check singletons first
        if name in self._singletons:
            return self._singletons[name]
        
        # Check factories
        if name in self._factories:
            factory, is_singleton = self._factories[name]
            
            if is_singleton:
                # Create once and cache
                if name not in self._singletons:
                    self._singletons[name] = factory(self)
                return self._singletons[name]
            else:
                # Create new instance each time
                return factory(self)
        
        raise ValueError(f"Service '{name}' not registered")
    
    def has(self, name: str) -> bool:
        """Check if service is registered"""
        return name in self._singletons or name in self._factories


# Global container instance
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """Get global service container"""
    global _container
    if _container is None:
        _container = ServiceContainer()
        _initialize_container(_container)
    return _container


def _initialize_container(container: ServiceContainer):
    """Initialize container with default services"""
    from app.database import db
    from app.services.indicator_service import IndicatorService
    from app.services.strategy_service import StrategyService
    from app.services.portfolio_service import PortfolioService
    from app.services.report_generator import ReportGenerator
    from app.services.composite_score_service import CompositeScoreService
    from app.services.actionable_levels_service import ActionableLevelsService
    from app.llm.agent import LLMAgent
    from app.data_sources import get_data_source
    
    # Register database (singleton)
    container.register_singleton('database', db)
    
    # Register data source (singleton)
    container.register_singleton('data_source', get_data_source())
    
    # Register services (singletons with dependency injection)
    def create_indicator_service(c: ServiceContainer) -> IndicatorService:
        return IndicatorService()
    
    def create_strategy_service(c: ServiceContainer) -> StrategyService:
        return StrategyService()
    
    def create_portfolio_service(c: ServiceContainer) -> PortfolioService:
        indicator_service = c.get('indicator_service')
        strategy_service = c.get('strategy_service')
        return PortfolioService(indicator_service, strategy_service)
    
    def create_report_generator(c: ServiceContainer) -> ReportGenerator:
        indicator_service = c.get('indicator_service')
        strategy_service = c.get('strategy_service')
        llm_agent = LLMAgent()  # LLMAgent doesn't need DI yet
        return ReportGenerator(indicator_service, strategy_service, llm_agent)
    
    def create_composite_score_service(c: ServiceContainer) -> CompositeScoreService:
        return CompositeScoreService()
    
    def create_actionable_levels_service(c: ServiceContainer) -> ActionableLevelsService:
        return ActionableLevelsService()
    
    def create_multi_timeframe_service(c: ServiceContainer):
        from app.services.multi_timeframe_service import MultiTimeframeService
        return MultiTimeframeService(data_source=c.get('data_source'))
    
    def create_swing_risk_manager(c: ServiceContainer):
        from app.services.swing_risk_manager import SwingRiskManager
        return SwingRiskManager()
    
    container.register_factory('indicator_service', create_indicator_service)
    container.register_factory('strategy_service', create_strategy_service)
    container.register_factory('portfolio_service', create_portfolio_service)
    container.register_factory('report_generator', create_report_generator)
    container.register_factory('composite_score_service', create_composite_score_service)
    container.register_factory('actionable_levels_service', create_actionable_levels_service)
    container.register_factory('multi_timeframe_service', create_multi_timeframe_service)
    container.register_factory('swing_risk_manager', create_swing_risk_manager)
    
    logger.info("✅ Service container initialized")

