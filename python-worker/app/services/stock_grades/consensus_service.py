"""
Consensus Service
Follows SOLID: Single Responsibility Principle
Handles consensus change detection and alert triggering
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta

from app.services.stock_grades.service import get_stock_grades_service
from app.services.stock_grades.repository import StockGradesRepository
from app.services.universal_alert_service_enhanced import UniversalEvent, EntityType, universal_alert_service
from app.observability.logging import get_logger

logger = get_logger(__name__)


class ConsensusService:
    """Service for consensus change detection and alerting
    
    Single Responsibility: Only handles consensus change logic
    Observer Pattern - monitors consensus changes and triggers alerts
    """
    
    def __init__(self):
        self.grades_service = get_stock_grades_service()
        self.repository = StockGradesRepository()
    
    async def update_consensus_for_symbol(
        self, 
        symbol: str, 
        data_source: str = "fmp",
        force_update: bool = False
    ) -> Dict[str, Any]:
        """Update consensus for a symbol and detect changes"""
        try:
            logger.info(f"📊 Updating consensus for {symbol}")
            
            # Get current consensus
            current_consensus = await self.repository.get_consensus(symbol)
            
            # Load latest consensus from data source
            from app.services.data_sources.base import DataSourceType
            new_consensus = await self.grades_service.load_consensus_for_symbol(
                symbol, 
                DataSourceType.FMP
            )
            
            if not new_consensus:
                logger.warning(f"No consensus data available for {symbol}")
                return {'symbol': symbol, 'status': 'no_data'}
            
            # Analyze changes
            change_analysis = self._analyze_consensus_change(current_consensus, new_consensus)
            
            if change_analysis['has_change']:
                logger.info(f"🔄 Consensus change detected for {symbol}: {change_analysis}")
                
                # Store consensus history (handled by database trigger)
                # Trigger alerts if significant
                if change_analysis['significance_level'] >= 3:
                    await self._trigger_consensus_alert(symbol, new_consensus, change_analysis)
                
                # Log market event
                await self._log_market_event(symbol, change_analysis)
            
            return {
                'symbol': symbol,
                'status': 'updated',
                'change_detected': change_analysis['has_change'],
                'change_analysis': change_analysis,
                'new_consensus': {
                    'rating': new_consensus.consensus_rating,
                    'score': new_consensus.consensus_score,
                    'total_analysts': new_consensus.total_analysts
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error updating consensus for {symbol}: {e}")
            return {'symbol': symbol, 'status': 'error', 'error': str(e)}
    
    def _analyze_consensus_change(
        self, 
        previous: Optional[Dict[str, Any]], 
        new: Any
    ) -> Dict[str, Any]:
        """Analyze consensus change for significance"""
        
        if not previous:
            return {
                'has_change': True,
                'change_type': 'initiate',
                'previous_consensus': None,
                'new_consensus': new.consensus_rating,
                'consensus_score_change': new.consensus_score,
                'total_analysts': new.total_analysts,
                'significance_level': self._calculate_significance_level(new.consensus_score, 0, new.total_analysts),
                'market_impact': self._assess_market_impact(new.consensus_score, 0, new.total_analysts)
            }
        
        prev_rating = previous.get('consensus_rating')
        new_rating = new.consensus_rating
        
        if prev_rating == new_rating:
            return {'has_change': False}
        
        # Determine change type
        change_type = self._determine_change_type(prev_rating, new_rating)
        
        # Calculate score change
        score_change = new.consensus_score - previous.get('consensus_score', 0)
        
        # Calculate significance
        significance_level = self._calculate_significance_level(
            new.consensus_score, 
            previous.get('consensus_score', 0), 
            new.total_analysts
        )
        
        # Assess market impact
        market_impact = self._assess_market_impact(
            new.consensus_score, 
            previous.get('consensus_score', 0), 
            new.total_analysts
        )
        
        return {
            'has_change': True,
            'change_type': change_type,
            'previous_consensus': prev_rating,
            'new_consensus': new_rating,
            'consensus_score_change': score_change,
            'total_analysts': new.total_analysts,
            'significance_level': significance_level,
            'market_impact': market_impact,
            'distribution': {
                'strong_buy': new.strong_buy,
                'buy': new.buy,
                'hold': new.hold,
                'sell': new.sell,
                'strong_sell': new.strong_sell
            }
        }
    
    def _determine_change_type(self, previous: str, new: str) -> str:
        """Determine consensus change type"""
        if not previous:
            return 'initiate'
        
        # Define rating hierarchy
        rating_hierarchy = {
            'Strong Sell': 1,
            'Sell': 2,
            'Hold': 3,
            'Buy': 4,
            'Strong Buy': 5
        }
        
        prev_score = rating_hierarchy.get(previous, 3)
        new_score = rating_hierarchy.get(new, 3)
        
        if new_score > prev_score:
            return 'upgrade'
        elif new_score < prev_score:
            return 'downgrade'
        else:
            return 'maintain'
    
    def _calculate_significance_level(
        self, 
        new_score: float, 
        old_score: float, 
        analyst_count: int
    ) -> int:
        """Calculate significance level (1-5)"""
        score_change = abs(new_score - old_score)
        
        # Base significance from score change
        if score_change >= 1.0:
            base_significance = 5
        elif score_change >= 0.7:
            base_significance = 4
        elif score_change >= 0.5:
            base_significance = 3
        elif score_change >= 0.3:
            base_significance = 2
        else:
            base_significance = 1
        
        # Adjust based on analyst count
        if analyst_count >= 20:
            return min(5, base_significance + 1)
        elif analyst_count >= 10:
            return min(5, base_significance)
        elif analyst_count >= 5:
            return max(1, base_significance - 1)
        else:
            return max(1, base_significance - 2)
    
    def _assess_market_impact(
        self, 
        new_score: float, 
        old_score: float, 
        analyst_count: int
    ) -> str:
        """Assess market impact level"""
        significance = self._calculate_significance_level(new_score, old_score, analyst_count)
        
        if significance >= 4 and analyst_count >= 10:
            return 'VERY_HIGH'
        elif significance >= 3 and analyst_count >= 5:
            return 'HIGH'
        elif significance >= 2 and analyst_count >= 3:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    async def _trigger_consensus_alert(
        self, 
        symbol: str, 
        consensus_data: Any, 
        change_analysis: Dict[str, Any]
    ):
        """Emit a universal consensus_update event for downstream alert evaluation/notification"""
        try:
            source_id = (
                f"consensus_update:{symbol.upper()}:"
                f"{change_analysis.get('previous_consensus')}->{change_analysis.get('new_consensus')}:"
                f"{change_analysis.get('total_analysts')}"
            )
            event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"consensus_service:{source_id}"))

            event = UniversalEvent(
                event_id=event_id,
                event_type='consensus_update',
                entity_type=EntityType.STOCK,
                entity_id=symbol.upper(),
                event_data={
                    'symbol': symbol.upper(),
                    'previous_consensus': change_analysis.get('previous_consensus'),
                    'new_consensus': change_analysis.get('new_consensus'),
                    'total_analysts': change_analysis.get('total_analysts'),
                    'consensus_score': getattr(consensus_data, 'consensus_score', None),
                    'change_type': change_analysis.get('change_type'),
                    'significance_level': change_analysis.get('significance_level'),
                    'market_impact': change_analysis.get('market_impact'),
                    'distribution': change_analysis.get('distribution'),
                },
                previous_data={
                    'consensus': change_analysis.get('previous_consensus'),
                },
                event_timestamp=datetime.utcnow(),
                data_source='consensus_service',
                source_id=source_id,
                confidence_score=0.9,
            )

            await universal_alert_service.event_repo.save_event(event)
            logger.info(f"📢 Emitted universal consensus_update event for {symbol}: {event_id}")
            
        except Exception as e:
            logger.error(f"❌ Error triggering consensus alerts for {symbol}: {e}")
    
    async def _log_market_event(self, symbol: str, change_analysis: Dict[str, Any]):
        """Log significant consensus change as market event"""
        try:
            event_data = {
                'event_type': 'consensus_change',
                'symbol': symbol,
                'change_type': change_analysis['change_type'],
                'previous_consensus': change_analysis['previous_consensus'],
                'new_consensus': change_analysis['new_consensus'],
                'significance_level': change_analysis['significance_level'],
                'total_analysts': change_analysis['total_analysts'],
                'market_impact': change_analysis['market_impact'],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Store in market events log (would need to create this table)
            logger.info(f"📈 Market event logged: {event_data}")
            
        except Exception as e:
            logger.error(f"❌ Error logging market event for {symbol}: {e}")
    
    async def batch_update_consensus(
        self, 
        symbols: List[str], 
        max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """Batch update consensus for multiple symbols"""
        try:
            logger.info(f"🔄 Batch updating consensus for {len(symbols)} symbols")
            
            import asyncio
            from asyncio import Semaphore
            
            semaphore = Semaphore(max_concurrent)
            
            async def update_with_semaphore(symbol: str):
                async with semaphore:
                    return await self.update_consensus_for_symbol(symbol)
            
            # Execute concurrently
            tasks = [update_with_semaphore(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            summary = {
                'total_symbols': len(symbols),
                'successful': 0,
                'failed': 0,
                'changes_detected': 0,
                'alerts_triggered': 0,
                'errors': []
            }
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    summary['failed'] += 1
                    summary['errors'].append(f"{symbols[i]}: {result}")
                else:
                    summary['successful'] += 1
                    if result.get('change_detected'):
                        summary['changes_detected'] += 1
            
            logger.info(f"✅ Batch consensus update completed: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error in batch consensus update: {e}")
            raise
    
    async def get_consensus_change_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get summary of recent consensus changes"""
        try:
            # Query recent consensus changes
            query = """
                SELECT 
                    COUNT(*) as total_changes,
                    COUNT(CASE WHEN consensus_change = 'upgrade' THEN 1 END) as upgrades,
                    COUNT(CASE WHEN consensus_change = 'downgrade' THEN 1 END) as downgrades,
                    COUNT(CASE WHEN significance_level >= 4 THEN 1 END) as very_significant,
                    COUNT(CASE WHEN significance_level >= 3 THEN 1 END) as significant,
                    AVG(total_analysts) as avg_analyst_count,
                    recorded_at::date as change_date
                FROM stock_consensus_history
                WHERE recorded_at >= CURRENT_DATE - INTERVAL ':days days'
                GROUP BY recorded_at::date
                ORDER BY change_date DESC
            """
            
            params = {'days': days}
            results = self.repository.db.execute_query(query, params)
            
            return {
                'summary': results[0] if results else {},
                'daily_breakdown': results or []
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting consensus change summary: {e}")
            return {}


# Singleton instance
consensus_service = ConsensusService()


def get_consensus_service() -> ConsensusService:
    """Get the consensus service instance"""
    return consensus_service
