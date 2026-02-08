"""
Stock Grades Service
Follows SOLID: Single Responsibility & Dependency Inversion Principles
Main service for stock grades operations - orchestrates data sources and repository
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from app.services.data_sources.base import DataSourceType, StockGrade, ConsensusData
from app.services.data_sources.registry import get_data_source_registry
from app.services.stock_grades.repository import StockGradesRepository
from app.observability.logging import get_logger

logger = get_logger(__name__)


class StockGradesService:
    """Main service for stock grades operations
    
    Single Responsibility: Orchestrates stock grades operations
    Dependency Inversion: Depends on abstractions, not concrete implementations
    """
    
    def __init__(self):
        self.repository = StockGradesRepository()
        self.data_source_registry = get_data_source_registry()
    
    async def load_grades_for_symbol(
        self, 
        symbol: str, 
        data_source: DataSourceType = DataSourceType.FMP,
        force_refresh: bool = False
    ) -> List[StockGrade]:
        """Load grades for a symbol from specified data source
        
        Facade Pattern - provides simple interface for complex operations
        """
        try:
            logger.info(f"📊 Loading grades for {symbol} from {data_source.value}")
            
            # Get data source
            source = self.data_source_registry.get_source(data_source)
            
            # Validate symbol
            if not await source.validate_symbol(symbol):
                raise ValueError(f"Symbol {symbol} not found in {data_source.value}")
            
            # Fetch grades from data source
            external_grades = await source.get_stock_grades(symbol)
            
            if not external_grades:
                logger.warning(f"No grades found for {symbol} in {data_source.value}")
                return []
            
            # Convert to standardized format
            grades = [source.to_stock_grade(grade) for grade in external_grades]
            
            # Store in database
            success = await self.repository.store_grades(symbol, grades)
            
            if success:
                logger.info(f"✅ Loaded and stored {len(grades)} grades for {symbol}")
            else:
                logger.warning(f"⚠️ Failed to store grades for {symbol}")
            
            return grades
            
        except Exception as e:
            logger.error(f"❌ Error loading grades for {symbol}: {e}")
            raise
    
    async def load_consensus_for_symbol(
        self, 
        symbol: str, 
        data_source: DataSourceType = DataSourceType.FMP
    ) -> Optional[ConsensusData]:
        """Load consensus data for a symbol"""
        try:
            logger.info(f"📊 Loading consensus for {symbol} from {data_source.value}")
            
            # Get data source
            source = self.data_source_registry.get_source(data_source)
            
            # Fetch consensus data
            external_consensus = await source.get_consensus_data(symbol)
            
            if not external_consensus:
                logger.warning(f"No consensus data found for {symbol} in {data_source.value}")
                return None
            
            # Convert to standardized format
            consensus = source.to_consensus_data(external_consensus)
            
            # Store in database
            success = await self.repository.store_consensus(consensus)
            
            if success:
                logger.info(f"✅ Loaded and stored consensus for {symbol}")
            else:
                logger.warning(f"⚠️ Failed to store consensus for {symbol}")
            
            return consensus
            
        except Exception as e:
            logger.error(f"❌ Error loading consensus for {symbol}: {e}")
            raise
    
    async def get_grades_for_symbol(
        self, 
        symbol: str, 
        limit: Optional[int] = None,
        tier1_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Get grades for a symbol with optional filtering"""
        try:
            if tier1_only:
                return await self.repository.get_tier1_firm_grades(symbol, days=365)
            else:
                return await self.repository.get_grades_by_symbol(symbol, limit)
                
        except Exception as e:
            logger.error(f"❌ Error getting grades for {symbol}: {e}")
            return []
    
    async def get_consensus_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus data for a symbol"""
        try:
            return await self.repository.get_consensus(symbol)
        except Exception as e:
            logger.error(f"❌ Error getting consensus for {symbol}: {e}")
            return None
    
    async def get_recent_changes(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent grade changes for a symbol"""
        try:
            return await self.repository.get_recent_changes(symbol, days)
        except Exception as e:
            logger.error(f"❌ Error getting recent changes for {symbol}: {e}")
            return []

    async def get_recent_price_target_changes(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        try:
            return await self.repository.get_recent_price_target_changes(symbol, days)
        except Exception as e:
            logger.error(f"❌ Error getting recent price target changes for {symbol}: {e}")
            return []
    
    async def get_consensus_history(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get consensus history for a symbol"""
        try:
            return await self.repository.get_consensus_history(symbol, days)
        except Exception as e:
            logger.error(f"❌ Error getting consensus history for {symbol}: {e}")
            return []
    
    async def get_symbols_with_recent_changes(self, days: int = 7) -> List[str]:
        """Get symbols with recent grade changes"""
        try:
            return await self.repository.get_symbols_with_recent_changes(days)
        except Exception as e:
            logger.error(f"❌ Error getting symbols with recent changes: {e}")
            return []
    
    async def refresh_symbol_data(
        self, 
        symbol: str, 
        data_source: DataSourceType = DataSourceType.FMP,
        include_consensus: bool = True
    ) -> Dict[str, Any]:
        """Refresh all data for a symbol"""
        try:
            logger.info(f"🔄 Refreshing data for {symbol}")
            
            results = {
                'symbol': symbol,
                'data_source': data_source.value,
                'timestamp': datetime.utcnow().isoformat(),
                'grades_loaded': 0,
                'consensus_loaded': False,
                'grades': [],
                'consensus': None,
                'errors': []
            }
            
            # Load grades
            try:
                grades = await self.load_grades_for_symbol(symbol, data_source)
                results['grades_loaded'] = len(grades)
                results['grades'] = grades
            except Exception as e:
                error_msg = f"Failed to load grades: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
            
            # Load consensus
            if include_consensus:
                try:
                    consensus = await self.load_consensus_for_symbol(symbol, data_source)
                    results['consensus_loaded'] = consensus is not None
                    results['consensus'] = consensus
                except Exception as e:
                    error_msg = f"Failed to load consensus: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            logger.info(f"✅ Refresh completed for {symbol}: {results}")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error refreshing data for {symbol}: {e}")
            raise
    
    async def batch_refresh_symbols(
        self, 
        symbols: List[str], 
        data_source: DataSourceType = DataSourceType.FMP,
        max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """Refresh data for multiple symbols concurrently"""
        try:
            logger.info(f"🔄 Batch refreshing {len(symbols)} symbols")
            
            import asyncio
            from asyncio import Semaphore
            
            semaphore = Semaphore(max_concurrent)
            
            async def refresh_with_semaphore(symbol: str):
                async with semaphore:
                    return await self.refresh_symbol_data(symbol, data_source)
            
            # Execute concurrently
            tasks = [refresh_with_semaphore(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            summary = {
                'total_symbols': len(symbols),
                'successful': 0,
                'failed': 0,
                'total_grades_loaded': 0,
                'total_consensus_loaded': 0,
                'errors': []
            }
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    summary['failed'] += 1
                    summary['errors'].append(f"{symbols[i]}: {result}")
                else:
                    summary['successful'] += 1
                    summary['total_grades_loaded'] += result.get('grades_loaded', 0)
                    if result.get('consensus_loaded'):
                        summary['total_consensus_loaded'] += 1
                    summary['errors'].extend(result.get('errors', []))
            
            logger.info(f"✅ Batch refresh completed: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error in batch refresh: {e}")
            raise
    
    async def get_coverage_stats(self) -> Dict[str, Any]:
        """Get overall coverage statistics"""
        try:
            return await self.repository.get_coverage_stats()
        except Exception as e:
            logger.error(f"❌ Error getting coverage stats: {e}")
            return {}
    
    async def validate_data_sources(self) -> Dict[str, bool]:
        """Validate all registered data sources"""
        try:
            return await self.data_source_registry.test_all_sources()
        except Exception as e:
            logger.error(f"❌ Error validating data sources: {e}")
            return {}
    
    async def get_latest_grades(self, symbol: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        """Get latest grades across all symbols or for a specific symbol"""
        try:
            if symbol:
                # Get grades for specific symbol
                return await self.repository.get_recent_changes(symbol, days)
            else:
                # Get latest grades across all symbols
                symbols = await self.repository.get_symbols_with_recent_changes(days)
                all_grades = []
                for sym in symbols[:20]:  # Limit to 20 symbols to avoid too much data
                    grades = await self.repository.get_recent_changes(sym, days)
                    all_grades.extend(grades)
                
                # Sort by date and return latest
                all_grades.sort(key=lambda x: x.get('grade_date', ''), reverse=True)
                return all_grades[:100]  # Return top 100 latest grades
                
        except Exception as e:
            logger.error(f"❌ Error getting latest grades: {e}")
            return []
    
    async def get_today_changes(self) -> List[Dict[str, Any]]:
        """Get today's grade changes across all symbols"""
        try:
            from datetime import date
            today = date.today().isoformat()
            
            symbols = await self.repository.get_symbols_with_recent_changes(1)
            today_changes = []
            
            for sym in symbols:
                changes = await self.repository.get_recent_changes(sym, 1)
                # Filter only today's changes
                for change in changes:
                    if change.get('grade_date', '').startswith(today):
                        today_changes.append(change)
            
            return today_changes
            
        except Exception as e:
            logger.error(f"❌ Error getting today's changes: {e}")
            return []
    
    async def get_data_source_info(self) -> Dict[str, Any]:
        """Get information about available data sources"""
        try:
            return self.data_source_registry.get_all_source_info()
        except Exception as e:
            logger.error(f"❌ Error getting data source info: {e}")
            return {}


# Singleton instance for dependency injection
stock_grades_service = StockGradesService()


def get_stock_grades_service() -> StockGradesService:
    """Get the stock grades service instance"""
    return stock_grades_service
