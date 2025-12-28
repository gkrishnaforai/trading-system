"""
Hybrid LLM Strategy
Combines technical analysis with LLM-based geopolitical/news analysis
"""
import logging
from typing import Dict, Any, Optional
import pandas as pd

from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.technical_strategy import TechnicalStrategy
from app.llm.agent import LLMAgent

logger = logging.getLogger(__name__)


class HybridLLMStrategy(BaseStrategy):
    """
    Hybrid strategy combining technical analysis with LLM-based news/geopolitical analysis
    
    This strategy:
    1. Gets technical signal from TechnicalStrategy
    2. Gets LLM opinion based on current news/geopolitical events
    3. Combines both signals with weighted confidence
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.technical_strategy = TechnicalStrategy()
        self.llm_agent = LLMAgent()
        
        # Configuration
        self.technical_weight = self.config.get('technical_weight', 0.7)  # 70% technical
        self.llm_weight = self.config.get('llm_weight', 0.3)  # 30% LLM
        self.require_llm_confirmation = self.config.get('require_llm_confirmation', False)
    
    def get_name(self) -> str:
        return "hybrid_llm"
    
    def get_description(self) -> str:
        return "Hybrid strategy combining technical analysis (70%) with LLM-based geopolitical/news analysis (30%)"
    
    def get_required_indicators(self) -> list:
        """
        Return list of required indicator names (same as TechnicalStrategy)
        
        Returns:
            List of required indicator names
        """
        return self.technical_strategy.get_required_indicators()
    
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        """
        Generate signal by combining technical and LLM analysis
        """
        # Get technical signal
        technical_result = self.technical_strategy.generate_signal(indicators, market_data, context)
        
        # Get LLM opinion
        llm_signal = self._get_llm_signal(indicators, context)
        
        # Combine signals
        combined_signal, combined_confidence, combined_reason = self._combine_signals(
            technical_result, llm_signal
        )
        
        metadata = {
            'technical_signal': technical_result.signal,
            'technical_confidence': technical_result.confidence,
            'llm_signal': llm_signal.get('signal', 'hold'),
            'llm_confidence': llm_signal.get('confidence', 0.5),
            'llm_reason': llm_signal.get('reason', ''),
            'technical_weight': self.technical_weight,
            'llm_weight': self.llm_weight,
        }
        
        return StrategyResult(
            signal=combined_signal,
            confidence=combined_confidence,
            reason=combined_reason,
            metadata=metadata,
            strategy_name=self.name
        )
    
    def _get_llm_signal(
        self,
        indicators: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get LLM-based signal considering geopolitical/news context
        
        Returns:
            Dictionary with 'signal', 'confidence', 'reason'
        """
        symbol = context.get('symbol', 'UNKNOWN') if context else 'UNKNOWN'
        
        # Build prompt for LLM
        prompt = f"""
        Analyze the current geopolitical and news context for {symbol} stock.
        Consider:
        - Recent news events
        - Geopolitical tensions
        - Economic indicators
        - Market sentiment
        
        Based on this analysis, provide a trading signal (buy/sell/hold) with confidence (0-1).
        
        Current technical indicators show:
        - Trend: {indicators.get('long_term_trend', 'unknown')}
        - RSI: {indicators.get('rsi', 'unknown')}
        - MACD: {indicators.get('macd_line', 'unknown')}
        
        Provide your analysis and recommendation.
        """
        
        try:
            # Use LLM to analyze
            if self.llm_agent.enabled:
                # In a real implementation, you'd call the LLM here
                # For now, return a neutral signal
                llm_response = {
                    'signal': 'hold',
                    'confidence': 0.5,
                    'reason': 'LLM analysis pending (requires API key)'
                }
            else:
                llm_response = {
                    'signal': 'hold',
                    'confidence': 0.5,
                    'reason': 'LLM not enabled'
                }
        except Exception as e:
            logger.error(f"Error getting LLM signal: {e}")
            llm_response = {
                'signal': 'hold',
                'confidence': 0.5,
                'reason': f'LLM analysis error: {str(e)}'
            }
        
        return llm_response
    
    def _combine_signals(
        self,
        technical_result: StrategyResult,
        llm_signal: Dict[str, Any]
    ) -> tuple:
        """
        Combine technical and LLM signals
        
        Returns:
            Tuple of (signal, confidence, reason)
        """
        tech_signal = technical_result.signal
        tech_conf = technical_result.confidence
        llm_sig = llm_signal.get('signal', 'hold')
        llm_conf = llm_signal.get('confidence', 0.5)
        
        # Weighted confidence
        combined_confidence = (
            tech_conf * self.technical_weight +
            llm_conf * self.llm_weight
        )
        
        # Signal combination logic
        if tech_signal == 'buy' and llm_sig in ['buy', 'hold']:
            combined_signal = 'buy'
        elif tech_signal == 'sell' and llm_sig in ['sell', 'hold']:
            combined_signal = 'sell'
        elif tech_signal == 'hold' and llm_sig == 'buy':
            # LLM bullish but technical neutral - slight buy bias
            combined_signal = 'buy'
            combined_confidence *= 0.8  # Reduce confidence
        elif tech_signal == 'hold' and llm_sig == 'sell':
            # LLM bearish but technical neutral - slight sell bias
            combined_signal = 'sell'
            combined_confidence *= 0.8  # Reduce confidence
        else:
            # Conflicting signals - default to hold
            combined_signal = 'hold'
            combined_confidence *= 0.6  # Lower confidence on conflicts
        
        # Build combined reason
        reason = f"Technical: {technical_result.reason}. LLM: {llm_signal.get('reason', 'No analysis')}"
        
        return combined_signal, combined_confidence, reason

