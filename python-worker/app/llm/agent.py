"""
LLM Agent for generating reports, explanations, and narratives
"""
import logging
from typing import Dict, Any, Optional, List
import json

try:
    from litellm import completion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logging.warning("LiteLLM not available, LLM features will be disabled")

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)


class LLMAgent:
    """LLM agent for generating trading reports and explanations"""
    
    def __init__(self):
        self.enabled = LITELLM_AVAILABLE and (
            settings.openai_api_key or
            settings.anthropic_api_key or
            settings.litellm_proxy_url
        )
        
        if not self.enabled:
            logger.warning("LLM agent disabled: no API keys configured")
    
    def generate_signal_explanation(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        signal: str
    ) -> str:
        """
        Generate human-readable explanation for a trading signal
        
        Returns:
            Explanation text
        """
        if not self.enabled:
            return self._generate_basic_explanation(symbol, indicators, signal)
        
        try:
            prompt = self._build_signal_explanation_prompt(symbol, indicators, signal)
            
            response = completion(
                model="gpt-4o-mini",  # or use settings to configure
                messages=[
                    {"role": "system", "content": "You are a financial analyst explaining trading signals in clear, professional language."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            explanation = response.choices[0].message.content
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating LLM explanation: {e}")
            return self._generate_basic_explanation(symbol, indicators, signal)
    
    def generate_stock_analysis(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate comprehensive stock analysis report
        
        Returns:
            Analysis text
        """
        if not self.enabled:
            return self._generate_basic_analysis(symbol, indicators)
        
        try:
            prompt = self._build_stock_analysis_prompt(symbol, indicators, market_data)
            
            response = completion(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a financial analyst providing comprehensive stock analysis."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            analysis = response.choices[0].message.content
            return analysis
            
        except Exception as e:
            logger.error(f"Error generating LLM analysis: {e}")
            return self._generate_basic_analysis(symbol, indicators)
    
    def generate_portfolio_report(
        self,
        portfolio_id: str,
        holdings: List[Dict[str, Any]],
        signals: List[Dict[str, Any]]
    ) -> str:
        """
        Generate portfolio-level analysis report
        
        Returns:
            Portfolio report text
        """
        if not self.enabled:
            return self._generate_basic_portfolio_report(holdings, signals)
        
        try:
            prompt = self._build_portfolio_report_prompt(portfolio_id, holdings, signals)
            
            response = completion(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a portfolio manager providing comprehensive portfolio analysis."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            report = response.choices[0].message.content
            return report
            
        except Exception as e:
            logger.error(f"Error generating LLM portfolio report: {e}")
            return self._generate_basic_portfolio_report(holdings, signals)
    
    def save_report(
        self,
        report_id: str,
        portfolio_id: Optional[str],
        stock_symbol: Optional[str],
        content: str,
        report_type: str
    ) -> bool:
        """Save generated report to database"""
        try:
            query = """
                INSERT OR REPLACE INTO llm_generated_reports
                (report_id, portfolio_id, stock_symbol, generated_content, report_type)
                VALUES (:report_id, :portfolio_id, :symbol, :content, :report_type)
            """
            
            params = {
                "report_id": report_id,
                "portfolio_id": portfolio_id,
                "symbol": stock_symbol,
                "content": content,
                "report_type": report_type
            }
            
            db.execute_update(query, params)
            return True
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            return False
    
    def _build_signal_explanation_prompt(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        signal: str
    ) -> str:
        """Build prompt for signal explanation"""
        return f"""
        Explain the {signal.upper()} signal for {symbol} based on the following technical indicators:
        
        - Long-term trend: {indicators.get('long_term_trend', 'N/A')}
        - Medium-term trend: {indicators.get('medium_term_trend', 'N/A')}
        - RSI: {indicators.get('rsi', 'N/A')}
        - MACD: {indicators.get('macd', 'N/A')}
        - Momentum Score: {indicators.get('momentum_score', 'N/A')}
        - Signal: {signal}
        
        Provide a clear, concise explanation (2-3 sentences) of why this signal was generated, 
        focusing on the key technical factors.
        """
    
    def _build_stock_analysis_prompt(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        market_data: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for stock analysis"""
        return f"""
        Provide a comprehensive technical analysis for {symbol}:
        
        Technical Indicators:
        - Moving Averages: MA7={indicators.get('ma7')}, EMA20={indicators.get('ema20')}, SMA200={indicators.get('sma200')}
        - RSI: {indicators.get('rsi')}
        - MACD: {indicators.get('macd')}
        - Trend: Long-term={indicators.get('long_term_trend')}, Medium-term={indicators.get('medium_term_trend')}
        - Signal: {indicators.get('signal')}
        - Momentum: {indicators.get('momentum_score')}
        
        Provide a 3-4 paragraph analysis covering:
        1. Current trend and momentum
        2. Key support/resistance levels
        3. Trading signal and rationale
        4. Risk considerations
        """
    
    def _build_portfolio_report_prompt(
        self,
        portfolio_id: str,
        holdings: List[Dict[str, Any]],
        signals: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for portfolio report"""
        holdings_summary = "\n".join([
            f"- {h['stock_symbol']}: {h.get('quantity', 0)} shares @ ${h.get('avg_entry_price', 0)}"
            for h in holdings
        ])
        
        signals_summary = "\n".join([
            f"- {s['stock_symbol']}: {s['signal_type']} (confidence: {s.get('confidence_score', 0):.2f})"
            for s in signals
        ])
        
        return f"""
        Provide a portfolio analysis report:
        
        Holdings:
        {holdings_summary}
        
        Current Signals:
        {signals_summary}
        
        Provide a comprehensive portfolio analysis covering:
        1. Overall portfolio health and diversification
        2. Key signals and recommended actions
        3. Risk assessment
        4. Strategic recommendations
        """
    
    def _generate_basic_explanation(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        signal: str
    ) -> str:
        """Generate basic explanation without LLM"""
        trend = indicators.get('long_term_trend', 'neutral')
        rsi = indicators.get('rsi', 50)
        
        if signal == 'buy':
            return f"{symbol} shows a {signal} signal. Long-term trend is {trend}, RSI is {rsi:.1f}. Consider entry on pullback to support levels."
        elif signal == 'sell':
            return f"{symbol} shows a {signal} signal. Momentum may be fading. Consider taking profits or tightening stop-loss."
        else:
            return f"{symbol} is in a {signal} position. Monitor for clearer signals."
    
    def _generate_basic_analysis(
        self,
        symbol: str,
        indicators: Dict[str, Any]
    ) -> str:
        """Generate basic analysis without LLM"""
        return f"""
        Technical Analysis for {symbol}:
        
        Trend: {indicators.get('long_term_trend', 'N/A')} (long-term), {indicators.get('medium_term_trend', 'N/A')} (medium-term)
        Signal: {indicators.get('signal', 'hold')}
        RSI: {indicators.get('rsi', 'N/A')}
        MACD: {indicators.get('macd', 'N/A')}
        Momentum: {indicators.get('momentum_score', 'N/A')}
        """
    
    def _generate_basic_portfolio_report(
        self,
        holdings: List[Dict[str, Any]],
        signals: List[Dict[str, Any]]
    ) -> str:
        """Generate basic portfolio report without LLM"""
        return f"""
        Portfolio Report:
        
        Holdings: {len(holdings)} positions
        Active Signals: {len(signals)} signals
        
        Review individual positions and signals for detailed recommendations.
        """

