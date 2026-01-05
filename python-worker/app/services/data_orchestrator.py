"""
Data Source Orchestrator
Intelligent multi-source data management with configurable routing
Implements industry best practices: Idempotent, Self-healing, Medallion Architecture
"""
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import pandas as pd
from pathlib import Path
import json

from app.data_sources.adapters.factory import AdapterFactory
from app.data_sources.adapters.base_adapter import BaseDataSourceAdapter
from app.providers.alphavantage.client import AlphaVantageClient
from app.observability.tracing import trace_function
from app.observability.logging import get_logger
from app.config import settings

logger = get_logger("data_orchestrator")

class DataType(Enum):
    """Data types for routing"""
    PRICE_DATA = "price_data"
    TECHNICAL_INDICATORS = "technical_indicators"
    FUNDAMENTALS = "fundamentals"
    MARKET_NEWS = "market_news"
    SYMBOL_DETAILS = "symbol_details"
    SENTIMENT_DATA = "sentiment_data"
    EARNINGS_DATA = "earnings_data"

class LoadFrequency(Enum):
    """Load frequency patterns"""
    REAL_TIME = "real_time"      # Every minute
    INTRADAY = "intraday"        # Every 15 minutes
    DAILY = "daily"              # Once per day
    WEEKLY = "weekly"            # Once per week
    MONTHLY = "monthly"          # Once per month
    QUARTERLY = "quarterly"      # Once per quarter
    ONE_TIME = "one_time"        # Historical load only
    ON_DEMAND = "on_demand"      # Manual trigger

class ExtractionPattern(Enum):
    """Extraction patterns from industry best practices"""
    TIME_RANGED = "time_ranged"   # Specific timeframe
    FULL_SNAPSHOT = "full_snapshot"  # Entire dataset
    LOOKBACK = "lookback"         # Last n periods
    STREAMING = "streaming"       # Real-time streaming

class BehavioralPattern(Enum):
    """Behavioral patterns for reliability"""
    IDEMPOTENT = "idempotent"    # Same result on rerun
    SELF_HEALING = "self_healing"  # Auto-catchup on failures
    APPEND_ONLY = "append_only"   # Never overwrite, only add

@dataclass
class DataSourceConfig:
    """Configuration for a data source"""
    name: str
    priority: int = 100  # Lower number = higher priority
    enabled: bool = True
    cost_per_call: float = 0.0
    rate_limit_per_minute: int = 60
    reliability_score: float = 1.0  # 0.0 to 1.0
    data_quality_score: float = 1.0  # 0.0 to 1.0
    supported_data_types: List[DataType] = field(default_factory=list)
    historical_coverage_days: int = 365
    real_time_support: bool = False
    api_key_required: bool = True

@dataclass
class DataLoadConfig:
    """Configuration for data loading"""
    data_type: DataType
    primary_source: str
    fallback_sources: List[str] = field(default_factory=list)
    load_frequency: LoadFrequency = LoadFrequency.DAILY
    extraction_pattern: ExtractionPattern = ExtractionPattern.TIME_RANGED
    behavioral_pattern: BehavioralPattern = BehavioralPattern.IDEMPOTENT
    retention_days: int = 3650  # 10 years default
    quality_threshold: float = 0.8  # Minimum data quality score
    cost_threshold: float = 1.0  # Maximum cost per load
    retry_attempts: int = 3
    retry_delay_seconds: int = 60

class DataOrchestrator:
    """
    Intelligent data source orchestration
    Implements industry best practices for multi-source data management
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.adapter_factory = AdapterFactory()
        self.data_sources: Dict[str, BaseDataSourceAdapter] = {}
        self.source_configs: Dict[str, DataSourceConfig] = {}
        self.load_configs: Dict[DataType, DataLoadConfig] = {}
        
        # Load configurations
        self._load_default_configs()
        if config_file:
            self._load_config_file(config_file)
        
        # Initialize adapters
        self._initialize_adapters()
        
        logger.info("🚀 Data Orchestrator initialized with multi-source routing")
    
    def _load_default_configs(self):
        """Load default data source configurations"""
        
        # Yahoo Finance Configuration
        self.source_configs["yahoo"] = DataSourceConfig(
            name="yahoo",
            priority=200,  # Lower priority (higher number) than paid sources
            enabled=True,
            cost_per_call=0.0,
            rate_limit_per_minute=2000,
            reliability_score=0.85,
            data_quality_score=0.80,
            supported_data_types=[
                DataType.PRICE_DATA,
                DataType.TECHNICAL_INDICATORS,
                DataType.FUNDAMENTALS,
                DataType.SYMBOL_DETAILS
            ],
            historical_coverage_days=365 * 20,  # 20 years
            real_time_support=False,
            api_key_required=False
        )
        
        # Massive Configuration
        self.source_configs["massive"] = DataSourceConfig(
            name="massive",
            priority=100,  # Higher priority (lower number)
            enabled=True,
            cost_per_call=0.01,
            rate_limit_per_minute=5,
            reliability_score=0.95,
            data_quality_score=0.95,
            supported_data_types=[
                DataType.PRICE_DATA,
                DataType.TECHNICAL_INDICATORS,
                DataType.FUNDAMENTALS,
                DataType.MARKET_NEWS,
                DataType.SENTIMENT_DATA,
                DataType.SYMBOL_DETAILS
            ],
            historical_coverage_days=365 * 5,  # 5 years
            real_time_support=True,
            api_key_required=True
        )
        
        # Alpha Vantage Configuration (only if API key is available)
        if settings.alphavantage_api_key and settings.alphavantage_api_key.strip():
            self.source_configs["alphavantage"] = DataSourceConfig(
                name="alphavantage",
                priority=150,
                enabled=True,
                cost_per_call=0.0,
                rate_limit_per_minute=5,
                reliability_score=0.90,
                data_quality_score=0.85,
                supported_data_types=[
                    DataType.PRICE_DATA,
                    DataType.TECHNICAL_INDICATORS,
                    DataType.FUNDAMENTALS,
                    DataType.MARKET_NEWS
                ],
                real_time_support=True,
                api_key_required=True
            )
            logger.info("✅ Alpha Vantage data source configured (API key available)")
        else:
            logger.info("⚠️ Alpha Vantage data source skipped (no API key configured)")
        
        # Default load configurations
        price_fallback_sources = ["massive"]
        if settings.alphavantage_api_key and settings.alphavantage_api_key.strip():
            price_fallback_sources.insert(0, "alphavantage")  # Add Alpha Vantage as first fallback if available
        
        self.load_configs[DataType.PRICE_DATA] = DataLoadConfig(
            data_type=DataType.PRICE_DATA,
            primary_source="yahoo",  # Use Yahoo for historical depth
            fallback_sources=price_fallback_sources,
            load_frequency=LoadFrequency.DAILY,
            extraction_pattern=ExtractionPattern.TIME_RANGED,
            behavioral_pattern=BehavioralPattern.IDEMPOTENT,
            retention_days=365 * 10  # 10 years
        )
        
        # Technical indicators fallback sources
        technical_fallback_sources = ["yahoo"]
        if settings.alphavantage_api_key and settings.alphavantage_api_key.strip():
            technical_fallback_sources.insert(0, "alphavantage")  # Add Alpha Vantage as first fallback if available
        
        self.load_configs[DataType.TECHNICAL_INDICATORS] = DataLoadConfig(
            data_type=DataType.TECHNICAL_INDICATORS,
            primary_source="massive",  # Use Massive for premium indicators
            fallback_sources=technical_fallback_sources,
            load_frequency=LoadFrequency.DAILY,
            extraction_pattern=ExtractionPattern.LOOKBACK,
            behavioral_pattern=BehavioralPattern.IDEMPOTENT,
            retention_days=365 * 2  # 2 years
        )
        
        # Fundamentals fallback sources
        fundamentals_fallback_sources = ["yahoo"]
        if settings.alphavantage_api_key and settings.alphavantage_api_key.strip():
            fundamentals_fallback_sources.insert(0, "alphavantage")  # Add Alpha Vantage as first fallback if available
        
        self.load_configs[DataType.FUNDAMENTALS] = DataLoadConfig(
            data_type=DataType.FUNDAMENTALS,
            primary_source="massive",  # Use Massive for comprehensive fundamentals
            fallback_sources=fundamentals_fallback_sources,
            load_frequency=LoadFrequency.WEEKLY,
            extraction_pattern=ExtractionPattern.FULL_SNAPSHOT,
            behavioral_pattern=BehavioralPattern.IDEMPOTENT,
            retention_days=365 * 5  # 5 years
        )
        
        # Market news fallback sources
        news_fallback_sources = []
        if settings.alphavantage_api_key and settings.alphavantage_api_key.strip():
            news_fallback_sources.append("alphavantage")  # Only add Alpha Vantage if available
        
        self.load_configs[DataType.MARKET_NEWS] = DataLoadConfig(
            data_type=DataType.MARKET_NEWS,
            primary_source="massive",
            fallback_sources=news_fallback_sources,
            load_frequency=LoadFrequency.INTRADAY,
            extraction_pattern=ExtractionPattern.LOOKBACK,
            behavioral_pattern=BehavioralPattern.APPEND_ONLY,
            retention_days=30  # 30 days
        )
    
    def _load_config_file(self, config_file: str):
        """Load configuration from JSON file"""
        try:
            config_path = Path(config_file)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                # Override source configs
                if "data_sources" in config:
                    for name, source_config in config["data_sources"].items():
                        if name in self.source_configs:
                            # Update existing config
                            for key, value in source_config.items():
                                if hasattr(self.source_configs[name], key):
                                    setattr(self.source_configs[name], key, value)
                
                # Override load configs
                if "load_configs" in config:
                    for data_type_str, load_config in config["load_configs"].items():
                        data_type = DataType(data_type_str)
                        if data_type in self.load_configs:
                            # Update existing config
                            for key, value in load_config.items():
                                if hasattr(self.load_configs[data_type], key):
                                    if key == "data_type":
                                        setattr(self.load_configs[data_type], key, DataType(value))
                                    elif key == "load_frequency":
                                        setattr(self.load_configs[data_type], key, LoadFrequency(value))
                                    elif key == "extraction_pattern":
                                        setattr(self.load_configs[data_type], key, ExtractionPattern(value))
                                    elif key == "behavioral_pattern":
                                        setattr(self.load_configs[data_type], key, BehavioralPattern(value))
                                    else:
                                        setattr(self.load_configs[data_type], key, value)
                
                logger.info(f"✅ Loaded configuration from {config_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load config file {config_file}: {e}")
    
    def _initialize_adapters(self):
        """Initialize all enabled adapters"""
        for name, config in self.source_configs.items():
            if config.enabled:
                try:
                    adapter = self.adapter_factory.create_adapter(name)
                    if adapter and adapter.is_available:
                        self.data_sources[name] = adapter
                        logger.info(f"✅ Initialized {name} adapter")
                    else:
                        logger.warning(f"⚠️ {name} adapter not available")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize {name} adapter: {e}")
    
    @trace_function("get_optimal_source")
    def get_optimal_source(
        self,
        data_type: DataType,
        symbol: str = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        force_source: Optional[str] = None
    ) -> Optional[str]:
        """
        Get optimal data source based on configuration and availability
        
        Args:
            data_type: Type of data to fetch
            symbol: Stock symbol
            start_date: Start date for historical data
            end_date: End date for historical data
            force_source: Force specific source
        
        Returns:
            Optimal source name
        """
        try:
            # If specific source requested, check if available and supports data type
            if force_source:
                if force_source in self.data_sources:
                    source_config = self.source_configs[force_source]
                    if data_type in source_config.supported_data_types:
                        return force_source
                    else:
                        logger.warning(f"Source {force_source} doesn't support {data_type.value}")
                else:
                    logger.warning(f"Source {force_source} not available")
            
            # Get load configuration
            if data_type not in self.load_configs:
                logger.error(f"No load configuration for {data_type.value}")
                return None
            
            load_config = self.load_configs[data_type]
            
            # Try primary source first
            if load_config.primary_source in self.data_sources:
                primary_config = self.source_configs[load_config.primary_source]
                
                # Check if primary source supports this data type
                if data_type in primary_config.supported_data_types:
                    # Check historical coverage requirements
                    if start_date and primary_config.historical_coverage_days:
                        days_needed = (datetime.now() - start_date).days
                        if days_needed > primary_config.historical_coverage_days:
                            logger.info(f"Primary source {load_config.primary_source} lacks historical coverage, trying fallbacks")
                        else:
                            return load_config.primary_source
                    else:
                        return load_config.primary_source
            
            # Try fallback sources
            for fallback_name in load_config.fallback_sources:
                if fallback_name in self.data_sources:
                    fallback_config = self.source_configs[fallback_name]
                    
                    if data_type in fallback_config.supported_data_types:
                        # Check historical coverage
                        if start_date and fallback_config.historical_coverage_days:
                            days_needed = (datetime.now() - start_date).days
                            if days_needed <= fallback_config.historical_coverage_days:
                                return fallback_name
                        else:
                            return fallback_name
            
            logger.error(f"No suitable source found for {data_type.value}")
            return None
            
        except Exception as e:
            logger.error(f"Error determining optimal source: {e}")
            return None
    
    @trace_function("fetch_data")
    def fetch_data(
        self,
        data_type: DataType,
        symbol: str,
        **kwargs
    ) -> Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]], None]:
        """
        Fetch data using optimal source with fallbacks
        
        Args:
            data_type: Type of data to fetch
            symbol: Stock symbol
            **kwargs: Additional parameters for data fetching
        
        Returns:
            Data in appropriate format
        """
        try:
            # Get optimal source
            source_name = self.get_optimal_source(data_type, symbol, **kwargs)
            
            if not source_name:
                logger.error(f"No source available for {data_type.value}")
                return None
            
            adapter = self.data_sources[source_name]
            load_config = self.load_configs[data_type]
            
            logger.info(f"Fetching {data_type.value} for {symbol} from {source_name}")
            
            # Fetch data based on type
            if data_type == DataType.PRICE_DATA:
                return adapter.fetch_price_data(symbol, **kwargs)
            elif data_type == DataType.TECHNICAL_INDICATORS:
                return adapter.fetch_technical_indicators(symbol, **kwargs)
            elif data_type == DataType.FUNDAMENTALS:
                return adapter.fetch_fundamentals(symbol, **kwargs)
            elif data_type == DataType.MARKET_NEWS:
                return adapter.fetch_news(symbol, **kwargs)
            elif data_type == DataType.SYMBOL_DETAILS:
                return adapter.fetch_symbol_details(symbol, **kwargs)
            else:
                logger.error(f"Unsupported data type: {data_type.value}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching {data_type.value} for {symbol}: {e}")
            return None
    
    def get_source_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all data sources"""
        status = {}
        
        for name, config in self.source_configs.items():
            adapter = self.data_sources.get(name)
            
            status[name] = {
                "enabled": config.enabled,
                "available": adapter is not None and adapter.is_available if adapter else False,
                "priority": config.priority,
                "cost_per_call": config.cost_per_call,
                "reliability_score": config.reliability_score,
                "data_quality_score": config.data_quality_score,
                "supported_data_types": [dt.value for dt in config.supported_data_types],
                "historical_coverage_days": config.historical_coverage_days,
                "real_time_support": config.real_time_support
            }
        
        return status
    
    def get_load_recommendations(self, symbol: str) -> Dict[str, Any]:
        """Get data loading recommendations for a symbol"""
        recommendations = {}
        
        for data_type, load_config in self.load_configs.items():
            source = self.get_optimal_source(data_type, symbol)
            
            recommendations[data_type.value] = {
                "recommended_source": source,
                "primary_source": load_config.primary_source,
                "fallback_sources": load_config.fallback_sources,
                "load_frequency": load_config.load_frequency.value,
                "retention_days": load_config.retention_days,
                "cost_estimate": self._estimate_cost(data_type, symbol),
                "quality_score": self._get_source_quality_score(source) if source else 0.0
            }
        
        return recommendations
    
    def _estimate_cost(self, data_type: DataType, symbol: str) -> float:
        """Estimate cost for data loading"""
        try:
            source_name = self.get_optimal_source(data_type, symbol)
            if not source_name:
                return 0.0
            
            config = self.source_configs[source_name]
            return config.cost_per_call
            
        except:
            return 0.0
    
    def _get_source_quality_score(self, source_name: str) -> float:
        """Get data quality score for a source"""
        try:
            if source_name in self.source_configs:
                config = self.source_configs[source_name]
                return config.data_quality_score
            return 0.0
        except:
            return 0.0
    
    @trace_function("fetch_alphavantage_simple")
    def fetch_alphavantage_simple(
        self,
        data_type: str,
        symbol: str,
    ) -> Optional[Any]:
        """
        Simple Alpha Vantage fetch - bypasses complex adapter system
        Uses direct API calls like Alpha Vantage examples
        """
        try:
            if not settings.alphavantage_api_key or not settings.alphavantage_api_key.strip():
                logger.warning("Alpha Vantage API key not configured - skipping fetch")
                return None

            client = AlphaVantageClient.from_settings(api_key=settings.alphavantage_api_key)
            logger.info(f"Fetching {data_type} for {symbol} via AlphaVantageClient")

            dt = (data_type or "").lower()
            if dt in {"symbol_details", "overview", "company_overview"}:
                return client.fetch_symbol_details(symbol)
            if dt in {"price_data", "price_historical", "time_series_daily"}:
                return client.fetch_price_data(symbol, outputsize="compact")
            if dt in {"fundamentals"}:
                return client.fetch_fundamentals(symbol)
            if dt in {"earnings"}:
                return client.fetch_earnings(symbol)
            if dt in {"technical_indicators", "indicators"}:
                # caller must specify indicator_type elsewhere; default to SMA
                return client.fetch_technical_indicators(symbol, indicator_type="SMA")

            logger.warning(f"Unknown Alpha Vantage simple data_type '{data_type}', defaulting to symbol_details")
            return client.fetch_symbol_details(symbol)
            
        except Exception as e:
            logger.error(f"Error fetching {data_type} for {symbol} via simple Alpha Vantage: {e}")
            return None


# Global orchestrator instance
data_orchestrator = DataOrchestrator()
