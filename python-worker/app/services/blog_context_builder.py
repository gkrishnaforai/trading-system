"""
Blog Context Builder Service
Builds structured, unambiguous context for LLM blog generation
Industry Standard: Context engineering for LLM applications
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, date, timedelta

from app.database import db
from app.services.base import BaseService
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.services.composite_score_service import CompositeScoreService
from app.services.actionable_levels_service import ActionableLevelsService
from app.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class BlogContextBuilder(BaseService):
    """
    Builds structured context for blog generation
    
    SOLID: Single Responsibility - only handles context building
    Industry Standard: Context engineering - no raw indicators, no opinions, no guessing
    """
    
    def __init__(
        self,
        indicator_service: Optional[IndicatorService] = None,
        strategy_service: Optional[StrategyService] = None,
        composite_score_service: Optional[CompositeScoreService] = None,
        actionable_levels_service: Optional[ActionableLevelsService] = None
    ):
        """
        Initialize blog context builder
        
        Args:
            indicator_service: Indicator service (optional, will get from DI if not provided)
            strategy_service: Strategy service (optional, will get from DI if not provided)
            composite_score_service: Composite score service (optional)
            actionable_levels_service: Actionable levels service (optional)
        """
        super().__init__()
        from app.di import get_container
        container = get_container()
        
        self.indicator_service = indicator_service or container.get('indicator_service')
        self.strategy_service = strategy_service or container.get('strategy_service')
        self.composite_score_service = composite_score_service or container.get('composite_score_service')
        self.actionable_levels_service = actionable_levels_service or container.get('actionable_levels_service')
    
    def build_context(
        self,
        topic_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build structured context for blog generation
        
        Args:
            topic_id: Topic ID from blog_topics table
            user_id: Optional user ID for user-specific context
        
        Returns:
            Structured context dictionary ready for LLM
        """
        try:
            # Get topic data
            topic = self._get_topic(topic_id)
            if not topic:
                raise ValidationError(f"Topic {topic_id} not found")
            
            symbol = topic['symbol']
            
            # Get latest indicators
            indicators = self.indicator_service.get_latest_indicators(symbol)
            if not indicators:
                raise ValidationError(f"No indicators available for {symbol}")
            
            # Get signal using strategy
            strategy_indicators = self._prepare_strategy_indicators(indicators)
            strategy_result = self.strategy_service.execute_strategy(
                "technical",
                strategy_indicators,
                context={'symbol': symbol}
            )
            
            # Build context sections
            context = {
                "system_role": "financial_content_explainer",
                "domain": "stocks",
                "topic": self._build_topic_context(topic),
                "signal_summary": self._build_signal_summary(strategy_result, indicators),
                "technical_context": self._build_technical_context(indicators, strategy_result),
                "risk_context": self._build_risk_context(symbol, indicators),
                "user_relevance": self._build_user_relevance(symbol, user_id) if user_id else {},
                "allowed_assumptions": [
                    "Explain in simple terms",
                    "Avoid technical jargon",
                    "Do not give financial advice",
                    "Focus on 'why it matters' for investors",
                    "Highlight risks clearly",
                    "Keep tone neutral and educational"
                ]
            }
            
            logger.info(f"✅ Built context for topic {topic_id} (symbol: {symbol})")
            return context
            
        except Exception as e:
            logger.error(f"Error building context for topic {topic_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to build context: {str(e)}") from e
    
    def _get_topic(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """Get topic data from database"""
        try:
            import json
            
            query = """
                SELECT topic_id, user_id, symbol, topic_type, reason, urgency,
                       audience, confidence, score
                FROM blog_topics
                WHERE topic_id = :topic_id
            """
            result = db.execute_query(query, {"topic_id": topic_id})
            
            if result:
                topic = result[0]
                return {
                    "topic_id": topic['topic_id'],
                    "user_id": topic.get('user_id'),
                    "symbol": topic['symbol'],
                    "topic_type": topic['topic_type'],
                    "reason": json.loads(topic['reason']) if topic.get('reason') else [],
                    "urgency": topic['urgency'],
                    "audience": topic['audience'],
                    "confidence": topic['confidence'],
                    "score": topic['score']
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting topic: {e}", exc_info=True)
            return None
    
    def _prepare_strategy_indicators(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare indicators for strategy execution"""
        return {
            'price': indicators.get('sma50') or indicators.get('close') or 100,
            'ema20': indicators.get('ema20'),
            'ema50': indicators.get('ema50'),
            'sma200': indicators.get('sma200'),
            'macd_line': indicators.get('macd'),
            'macd_signal': indicators.get('macd_signal'),
            'macd_histogram': indicators.get('macd_histogram'),
            'rsi': indicators.get('rsi'),
            'long_term_trend': indicators.get('long_term_trend'),
            'medium_term_trend': indicators.get('medium_term_trend'),
        }
    
    def _build_topic_context(self, topic: Dict[str, Any]) -> Dict[str, Any]:
        """Build topic-specific context"""
        # Map topic types to title hints
        title_hints = {
            'signal_change': f"{topic['symbol']} Signal Change",
            'golden_cross': f"{topic['symbol']} Golden Cross Buy Signal",
            'rsi_extreme': f"{topic['symbol']} RSI Extreme - Overbought or Oversold?",
            'earnings_proximity': f"{topic['symbol']} Earnings Preview",
            'volume_spike': f"{topic['symbol']} Unusual Volume Activity",
            'portfolio_heavy': f"{topic['symbol']} Portfolio Risk Analysis"
        }
        
        return {
            "symbol": topic['symbol'],
            "title_hint": title_hints.get(topic['topic_type'], f"{topic['symbol']} Market Analysis"),
            "urgency": topic['urgency'],
            "topic_type": topic['topic_type'],
            "reasons": topic['reason'],
            "confidence": topic['confidence']
        }
    
    def _build_signal_summary(
        self,
        strategy_result,
        indicators: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build signal summary (pre-processed, no raw indicators)"""
        # StrategyResult is a dataclass, access attributes directly
        signal = strategy_result.signal if hasattr(strategy_result, 'signal') else 'HOLD'
        confidence = strategy_result.confidence if hasattr(strategy_result, 'confidence') else 0.5
        
        # Determine trend
        long_term_trend = indicators.get('long_term_trend', 'neutral')
        medium_term_trend = indicators.get('medium_term_trend', 'neutral')
        
        if long_term_trend == 'bullish' and medium_term_trend == 'bullish':
            trend = "BULLISH"
        elif long_term_trend == 'bearish' and medium_term_trend == 'bearish':
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"
        
        return {
            "trend": trend,
            "signal": signal,
            "confidence": round(confidence, 2),
            "long_term_trend": long_term_trend,
            "medium_term_trend": medium_term_trend
        }
    
    def _build_technical_context(
        self,
        indicators: Dict[str, Any],
        strategy_result  # StrategyResult object (not used but kept for consistency)
    ) -> Dict[str, Any]:
        """Build technical context (pre-processed, human-readable)"""
        price = indicators.get('sma50') or indicators.get('close') or 0
        sma200 = indicators.get('sma200') or 0
        ema20 = indicators.get('ema20') or 0
        ema50 = indicators.get('ema50') or 0
        rsi = indicators.get('rsi')
        macd = indicators.get('macd') or 0
        macd_signal = indicators.get('macd_signal') or 0
        
        # Calculate price vs 200 MA
        price_vs_200ma = None
        if price and sma200 and sma200 > 0:
            percent_diff = ((price - sma200) / sma200) * 100
            price_vs_200ma = f"{'+' if percent_diff > 0 else ''}{percent_diff:.1f}%"
        
        # EMA cross status
        ema_cross = None
        if ema20 and ema50:
            if ema20 > ema50:
                ema_cross = "EMA20 above EMA50 (bullish)"
            elif ema20 < ema50:
                ema_cross = "EMA20 below EMA50 (bearish)"
            else:
                ema_cross = "EMA20 aligned with EMA50"
        
        # MACD status
        macd_status = None
        if macd and macd_signal:
            if macd > macd_signal:
                macd_status = "positive and rising"
            elif macd < macd_signal:
                macd_status = "negative and declining"
            else:
                macd_status = "neutral"
        
        # RSI status
        rsi_status = None
        if rsi:
            if rsi > 70:
                rsi_status = f"{rsi:.0f} (overbought)"
            elif rsi < 30:
                rsi_status = f"{rsi:.0f} (oversold)"
            else:
                rsi_status = f"{rsi:.0f} (healthy)"
        
        # Volume status (simplified)
        volume_status = "above average"  # Would need actual volume data
        
        return {
            "price_vs_200ma": price_vs_200ma,
            "ema_cross": ema_cross,
            "macd": macd_status,
            "rsi": rsi_status,
            "volume": volume_status,
            "current_price": round(price, 2) if price else None,
            "sma200": round(sma200, 2) if sma200 else None
        }
    
    def _build_risk_context(
        self,
        symbol: str,
        indicators: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build risk context"""
        rsi = indicators.get('rsi')
        
        # Determine overextension
        overextension = "moderate"
        if rsi:
            if rsi > 75:
                overextension = "high"
            elif rsi < 25:
                overextension = "low"
        
        # Get earnings date
        earnings_days_away = None
        try:
            query = """
                SELECT earnings_date FROM earnings_data
                WHERE stock_symbol = :symbol
                AND earnings_date >= date('now')
                ORDER BY earnings_date ASC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol})
            if result and result[0].get('earnings_date'):
                earnings_date = result[0]['earnings_date']
                if isinstance(earnings_date, str):
                    earnings_date = datetime.fromisoformat(earnings_date).date()
                days_away = (earnings_date - date.today()).days
                earnings_days_away = days_away if days_away >= 0 else None
        except Exception:
            pass
        
        # Market risk (simplified - would need market data)
        market_risk = "neutral"
        
        return {
            "overextension": overextension,
            "earnings_days_away": earnings_days_away,
            "market_risk": market_risk
        }
    
    def _build_user_relevance(
        self,
        symbol: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Build user relevance context"""
        watchlisted = False
        portfolio_exposure_pct = 0.0
        
        try:
            # Check if in watchlist
            query = """
                SELECT COUNT(*) as count
                FROM watchlist_items
                WHERE stock_symbol = :symbol
                AND watchlist_id IN (
                    SELECT watchlist_id FROM watchlists WHERE user_id = :user_id
                )
            """
            result = db.execute_query(query, {"symbol": symbol, "user_id": user_id})
            if result and result[0].get('count', 0) > 0:
                watchlisted = True
            
            # Calculate portfolio exposure
            query = """
                SELECT SUM(current_value) as total_value
                FROM holdings
                WHERE portfolio_id IN (
                    SELECT portfolio_id FROM portfolios WHERE user_id = :user_id
                )
            """
            total_result = db.execute_query(query, {"user_id": user_id})
            total_value = total_result[0].get('total_value', 0) if total_result else 0
            
            if total_value > 0:
                query = """
                    SELECT SUM(current_value) as symbol_value
                    FROM holdings
                    WHERE stock_symbol = :symbol
                    AND portfolio_id IN (
                        SELECT portfolio_id FROM portfolios WHERE user_id = :user_id
                    )
                """
                symbol_result = db.execute_query(query, {"symbol": symbol, "user_id": user_id})
                symbol_value = symbol_result[0].get('symbol_value', 0) if symbol_result else 0
                portfolio_exposure_pct = (symbol_value / total_value * 100) if total_value > 0 else 0
        
        except Exception as e:
            logger.warning(f"Error building user relevance: {e}")
        
        return {
            "watchlisted": watchlisted,
            "portfolio_exposure_pct": round(portfolio_exposure_pct, 1)
        }

