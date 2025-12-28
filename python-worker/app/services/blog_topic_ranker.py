"""
Blog Topic Ranker Service
Deterministic topic scoring - system decides what's important, not LLM
Industry Standard: Content scoring and ranking
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
import uuid

from app.database import db
from app.services.base import BaseService
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_exceptions


class BlogTopicRanker(BaseService):
    """
    Ranks blog topics deterministically based on signals, trends, volume, etc.
    
    SOLID: Single Responsibility - only handles topic ranking
    """
    
    def __init__(
        self,
        indicator_service: Optional[IndicatorService] = None,
        strategy_service: Optional[StrategyService] = None
    ):
        """
        Initialize blog topic ranker
        
        Args:
            indicator_service: Indicator service (optional, will get from DI if not provided)
            strategy_service: Strategy service (optional, will get from DI if not provided)
        """
        super().__init__()
        from app.di import get_container
        container = get_container()
        
        self.indicator_service = indicator_service or container.get('indicator_service')
        self.strategy_service = strategy_service or container.get('strategy_service')
    
    def rank_topics_for_user(
        self,
        user_id: str,
        limit: int = 5,
        min_score: float = 50.0
    ) -> List[Dict[str, Any]]:
        """
        Rank topics for a specific user based on their watchlists and portfolios
        
        Args:
            user_id: User ID
            limit: Maximum number of topics to return
            min_score: Minimum score threshold
        
        Returns:
            List of ranked topics with scores
        """
        try:
            # Get user's symbols from watchlists and portfolios
            symbols = self._get_user_symbols(user_id)
            
            if not symbols:
                return []
            
            # Score each symbol
            topics = []
            for symbol in symbols:
                topic_scores = self._score_symbol_topics(symbol, user_id)
                topics.extend(topic_scores)
            
            # Sort by score descending
            topics.sort(key=lambda x: x['score'], reverse=True)
            
            # Filter by min_score and limit
            filtered_topics = [t for t in topics if t['score'] >= min_score][:limit]
            
            # Save topics to database
            for topic in filtered_topics:
                self._save_topic(topic)
            
            return filtered_topics
            
        except Exception as e:
            logger.error(f"Error ranking topics for user {user_id}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to rank topics: {str(e)}") from e
    
    def get_top_topics(
        self,
        user_id: Optional[str] = None,
        limit: int = 5,
        urgency: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get top ranked topics from database
        
        Args:
            user_id: Optional user ID filter
            limit: Maximum number of topics
            urgency: Optional urgency filter (low, medium, high, critical)
        
        Returns:
            List of topics
        """
        try:
            query = """
                SELECT topic_id, user_id, symbol, topic_type, reason, urgency,
                       audience, confidence, score, context_data, created_at
                FROM blog_topics
                WHERE (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """
            params = {}
            
            if user_id:
                query += " AND user_id = :user_id"
                params["user_id"] = user_id
            
            if urgency:
                query += " AND urgency = :urgency"
                params["urgency"] = urgency
            
            query += " ORDER BY score DESC, created_at DESC LIMIT :limit"
            params["limit"] = limit
            
            result = db.execute_query(query, params)
            
            return [
                {
                    "topic_id": r['topic_id'],
                    "user_id": r.get('user_id'),
                    "symbol": r['symbol'],
                    "topic_type": r['topic_type'],
                    "reason": r['reason'],
                    "urgency": r['urgency'],
                    "audience": r['audience'],
                    "confidence": r['confidence'],
                    "score": r['score'],
                    "context_data": r.get('context_data'),
                    "created_at": r['created_at']
                }
                for r in result
            ]
            
        except Exception as e:
            logger.error(f"Error getting top topics: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get topics: {str(e)}") from e
    
    def _get_user_symbols(self, user_id: str) -> List[str]:
        """Get all symbols from user's watchlists and portfolios"""
        try:
            # Get from watchlists
            watchlist_query = """
                SELECT DISTINCT stock_symbol
                FROM watchlist_items
                WHERE watchlist_id IN (
                    SELECT watchlist_id FROM watchlists WHERE user_id = :user_id
                )
                AND stock_symbol IS NOT NULL
            """
            watchlist_symbols = db.execute_query(watchlist_query, {"user_id": user_id})
            
            # Get from portfolios
            portfolio_query = """
                SELECT DISTINCT stock_symbol
                FROM holdings
                WHERE portfolio_id IN (
                    SELECT portfolio_id FROM portfolios WHERE user_id = :user_id
                )
                AND stock_symbol IS NOT NULL
            """
            portfolio_symbols = db.execute_query(portfolio_query, {"user_id": user_id})
            
            # Combine and deduplicate
            symbols = set()
            for row in watchlist_symbols:
                symbols.add(row['stock_symbol'])
            for row in portfolio_symbols:
                symbols.add(row['stock_symbol'])
            
            return list(symbols)
            
        except Exception as e:
            logger.error(f"Error getting user symbols: {e}", exc_info=True)
            return []
    
    def _score_symbol_topics(self, symbol: str, user_id: str) -> List[Dict[str, Any]]:
        """Score all possible topics for a symbol"""
        topics = []
        
        try:
            # Get latest indicators
            indicators = self.indicator_service.get_latest_indicators(symbol)
            if not indicators:
                return []
            
            # Get latest signal
            strategy_indicators = {
                'price': indicators.get('sma50') or 100,
                'ema20': indicators.get('ema20'),
                'ema50': indicators.get('ema50'),
                'sma200': indicators.get('sma200'),
                'macd_line': indicators.get('macd'),
                'macd_signal': indicators.get('macd_signal'),
                'rsi': indicators.get('rsi'),
                'long_term_trend': indicators.get('long_term_trend'),
                'medium_term_trend': indicators.get('medium_term_trend'),
            }
            
            strategy_result = self.strategy_service.execute_strategy(
                "technical",
                strategy_indicators,
                context={'symbol': symbol}
            )
            
            current_signal = strategy_result.get('signal', 'HOLD')
            
            # Score different topic types
            topics.append(self._score_signal_change_topic(symbol, user_id, indicators, current_signal))
            topics.append(self._score_golden_cross_topic(symbol, user_id, indicators))
            topics.append(self._score_rsi_extreme_topic(symbol, user_id, indicators))
            topics.append(self._score_earnings_proximity_topic(symbol, user_id))
            topics.append(self._score_volume_spike_topic(symbol, user_id, indicators))
            topics.append(self._score_portfolio_heavy_topic(symbol, user_id))
            
            # Filter out None topics (not applicable)
            return [t for t in topics if t is not None]
            
        except Exception as e:
            logger.warning(f"Error scoring topics for {symbol}: {e}")
            return []
    
    def _score_signal_change_topic(
        self,
        symbol: str,
        user_id: str,
        indicators: Dict[str, Any],
        current_signal: str
    ) -> Optional[Dict[str, Any]]:
        """Score signal change topic"""
        try:
            # Get previous signal from database
            query = """
                SELECT signal FROM portfolio_signals
                WHERE stock_symbol = :symbol
                ORDER BY date DESC LIMIT 1
            """
            prev_result = db.execute_query(query, {"symbol": symbol})
            
            if not prev_result:
                return None
            
            prev_signal = prev_result[0].get('signal', 'HOLD')
            
            # Only score if signal changed significantly
            if current_signal == prev_signal:
                return None
            
            # Calculate score
            signal_change_weight = 0.25
            trend_strength = self._calculate_trend_strength(indicators)
            volume_spike = self._calculate_volume_spike(indicators)
            
            score = (
                trend_strength * 0.35 +
                signal_change_weight * 100 * 0.25 +  # Signal change is important
                volume_spike * 0.20 +
                50 * 0.10 +  # Base score
                50 * 0.10  # User exposure (default)
            )
            
            if score < 50:
                return None
            
            # Determine urgency
            if current_signal in ['BUY', 'SELL'] and prev_signal == 'HOLD':
                urgency = 'high'
            elif current_signal == 'SELL' and prev_signal == 'BUY':
                urgency = 'critical'
            else:
                urgency = 'medium'
            
            return {
                "topic_id": f"{symbol}_SIGNAL_CHANGE_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "symbol": symbol,
                "topic_type": "signal_change",
                "reason": [f"signal_changed_{prev_signal}_to_{current_signal}"],
                "urgency": urgency,
                "audience": "basic_to_pro",
                "confidence": 0.85,
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Error scoring signal change topic for {symbol}: {e}")
            return None
    
    def _score_golden_cross_topic(
        self,
        symbol: str,
        user_id: str,
        indicators: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Score golden cross topic (price above 200 MA)"""
        try:
            price = indicators.get('sma50') or indicators.get('close')
            sma200 = indicators.get('sma200')
            
            if not price or not sma200:
                return None
            
            # Check if price just crossed above 200 MA
            if price <= sma200:
                return None
            
            # Calculate score
            trend_strength = self._calculate_trend_strength(indicators)
            volume_spike = self._calculate_volume_spike(indicators)
            
            score = (
                trend_strength * 0.35 +
                80 * 0.25 +  # Golden cross is significant
                volume_spike * 0.20 +
                50 * 0.10 +
                50 * 0.10
            )
            
            if score < 50:
                return None
            
            return {
                "topic_id": f"{symbol}_GOLDEN_CROSS_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "symbol": symbol,
                "topic_type": "golden_cross",
                "reason": ["price_above_200MA", "bullish_trend"],
                "urgency": "high",
                "audience": "basic_to_pro",
                "confidence": 0.90,
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Error scoring golden cross topic for {symbol}: {e}")
            return None
    
    def _score_rsi_extreme_topic(
        self,
        symbol: str,
        user_id: str,
        indicators: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Score RSI extreme topic (overbought/oversold)"""
        try:
            rsi = indicators.get('rsi')
            if not rsi:
                return None
            
            # Check for extreme RSI
            if rsi > 70:  # Overbought
                urgency = 'high'
                reason = ["rsi_overbought", "potential_reversal"]
            elif rsi < 30:  # Oversold
                urgency = 'medium'
                reason = ["rsi_oversold", "potential_bounce"]
            else:
                return None
            
            trend_strength = self._calculate_trend_strength(indicators)
            
            score = (
                trend_strength * 0.35 +
                60 * 0.25 +  # RSI extreme is notable
                50 * 0.20 +
                50 * 0.10 +
                50 * 0.10
            )
            
            if score < 50:
                return None
            
            return {
                "topic_id": f"{symbol}_RSI_EXTREME_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "symbol": symbol,
                "topic_type": "rsi_extreme",
                "reason": reason,
                "urgency": urgency,
                "audience": "pro",
                "confidence": 0.75,
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Error scoring RSI extreme topic for {symbol}: {e}")
            return None
    
    def _score_earnings_proximity_topic(
        self,
        symbol: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Score earnings proximity topic"""
        try:
            # Get next earnings date
            query = """
                SELECT earnings_date FROM earnings_data
                WHERE stock_symbol = :symbol
                AND earnings_date >= date('now')
                ORDER BY earnings_date ASC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol})
            
            if not result:
                return None
            
            earnings_date = result[0].get('earnings_date')
            if not earnings_date:
                return None
            
            # Parse date
            if isinstance(earnings_date, str):
                earnings_date = datetime.fromisoformat(earnings_date).date()
            
            days_away = (earnings_date - date.today()).days
            
            # Only score if within 14 days
            if days_away > 14:
                return None
            
            # Score based on proximity
            proximity_score = max(0, 100 - (days_away * 5))
            
            score = (
                50 * 0.35 +  # Base trend
                50 * 0.25 +
                50 * 0.20 +
                proximity_score * 0.10 +  # Earnings proximity
                50 * 0.10
            )
            
            if score < 50:
                return None
            
            urgency = 'high' if days_away <= 7 else 'medium'
            
            return {
                "topic_id": f"{symbol}_EARNINGS_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "symbol": symbol,
                "topic_type": "earnings_proximity",
                "reason": [f"earnings_in_{days_away}_days"],
                "urgency": urgency,
                "audience": "basic_to_pro",
                "confidence": 0.80,
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Error scoring earnings proximity topic for {symbol}: {e}")
            return None
    
    def _score_volume_spike_topic(
        self,
        symbol: str,
        user_id: str,
        indicators: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Score volume spike topic"""
        try:
            volume_spike = self._calculate_volume_spike(indicators)
            
            # Only score if significant volume spike (>50%)
            if volume_spike < 50:
                return None
            
            trend_strength = self._calculate_trend_strength(indicators)
            
            score = (
                trend_strength * 0.35 +
                50 * 0.25 +
                volume_spike * 0.20 +  # Volume spike is important
                50 * 0.10 +
                50 * 0.10
            )
            
            if score < 50:
                return None
            
            return {
                "topic_id": f"{symbol}_VOLUME_SPIKE_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "symbol": symbol,
                "topic_type": "volume_spike",
                "reason": ["volume_spike", "unusual_activity"],
                "urgency": "medium",
                "audience": "pro",
                "confidence": 0.70,
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Error scoring volume spike topic for {symbol}: {e}")
            return None
    
    def _score_portfolio_heavy_topic(
        self,
        symbol: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Score portfolio heavy topic (high exposure)"""
        try:
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
            
            if total_value == 0:
                return None
            
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
            
            exposure_pct = (symbol_value / total_value * 100) if total_value > 0 else 0
            
            # Only score if exposure > 20%
            if exposure_pct < 20:
                return None
            
            # Score based on exposure
            exposure_score = min(100, exposure_pct * 2)  # 50% exposure = 100 score
            
            score = (
                50 * 0.35 +
                50 * 0.25 +
                50 * 0.20 +
                50 * 0.10 +
                exposure_score * 0.10  # High exposure is important
            )
            
            if score < 50:
                return None
            
            return {
                "topic_id": f"{symbol}_PORTFOLIO_HEAVY_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "symbol": symbol,
                "topic_type": "portfolio_heavy",
                "reason": [f"portfolio_exposure_{exposure_pct:.1f}%"],
                "urgency": "medium",
                "audience": "elite",
                "confidence": 0.85,
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Error scoring portfolio heavy topic for {symbol}: {e}")
            return None
    
    def _calculate_trend_strength(self, indicators: Dict[str, Any]) -> float:
        """Calculate trend strength score (0-100)"""
        try:
            long_term_trend = indicators.get('long_term_trend')
            medium_term_trend = indicators.get('medium_term_trend')
            
            score = 50  # Neutral
            
            if long_term_trend == 'bullish':
                score += 20
            elif long_term_trend == 'bearish':
                score -= 20
            
            if medium_term_trend == 'bullish':
                score += 15
            elif medium_term_trend == 'bearish':
                score -= 15
            
            return max(0, min(100, score))
            
        except Exception:
            return 50
    
    def _calculate_volume_spike(self, indicators: Dict[str, Any]) -> float:
        """Calculate volume spike score (0-100)"""
        try:
            # This would need actual volume data
            # For now, return a default
            return 50
        except Exception:
            return 50
    
    def _save_topic(self, topic: Dict[str, Any]):
        """Save topic to database"""
        try:
            import json
            
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency,
                 audience, confidence, score, context_data, expires_at)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency,
                        :audience, :confidence, :score, :context_data, :expires_at)
            """
            
            # Set expiration (topics expire after 7 days)
            expires_at = (datetime.now() + timedelta(days=7)).isoformat()
            
            db.execute_update(query, {
                "topic_id": topic['topic_id'],
                "user_id": topic.get('user_id'),
                "symbol": topic['symbol'],
                "topic_type": topic['topic_type'],
                "reason": json.dumps(topic['reason']),
                "urgency": topic['urgency'],
                "audience": topic['audience'],
                "confidence": topic['confidence'],
                "score": topic['score'],
                "context_data": json.dumps(topic.get('context_data', {})),
                "expires_at": expires_at
            })
            
        except Exception as e:
            logger.error(f"Error saving topic: {e}", exc_info=True)
            # Don't raise - this is non-critical

