"""
TipRanks-style Stock Report Generator
Creates comprehensive, layman-friendly stock reports
"""
from datetime import datetime, date
from typing import Dict, Any, Optional
import uuid
import json

from app.database import db
from app.services.base import BaseService
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.llm.agent import LLMAgent
from app.exceptions import IndicatorCalculationError, ValidationError
from app.utils.validation_patterns import validate_symbol_param
from app.utils.exception_handler import handle_exceptions


class ReportGenerator(BaseService):
    """
    Generates TipRanks-style stock reports
    
    SOLID: Single Responsibility - only handles report generation
    Dependency Injection: Receives dependencies via constructor
    """
    
    def __init__(
        self,
        indicator_service: IndicatorService,
        strategy_service: StrategyService,
        llm_agent: LLMAgent
    ):
        """
        Initialize report generator with dependencies
        
        Args:
            indicator_service: Indicator service instance
            strategy_service: Strategy service instance
            llm_agent: LLM agent instance
        """
        super().__init__()
        self.indicator_service = indicator_service
        self.strategy_service = strategy_service
        self.llm_agent = llm_agent
    
    def generate_stock_report(
        self,
        symbol: str,
        strategy_name: Optional[str] = None,
        include_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Generate comprehensive TipRanks-style stock report
        
        Returns:
            Dictionary with report data
        """
        try:
            # Get indicators
            indicators = self.indicator_service.get_latest_indicators(symbol)
            if not indicators:
                return {
                    "error": f"No data available for {symbol}",
                    "symbol": symbol
                }
            
            # Get signal using strategy
            if not strategy_name:
                strategy_name = "technical"
            
            # Prepare indicators for strategy
            strategy_indicators = {
                'price': indicators.get('sma50') or 100,
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
            
            strategy_result = self.strategy_service.execute_strategy(
                strategy_name,
                strategy_indicators,
                context={'symbol': symbol}
            )
            
            # Generate report sections
            report = {
                "symbol": symbol,
                "generated_at": datetime.now().isoformat(),
                "summary": self._generate_summary(indicators, strategy_result),
                "trend_status": self._generate_trend_status(indicators),
                "signal_clarity": self._generate_signal_clarity(strategy_result, indicators),
                "technical_analysis": self._generate_technical_analysis(indicators),
                "risk_assessment": self._generate_risk_assessment(indicators, strategy_result),
                "recommendation": self._generate_recommendation(strategy_result, indicators),
                "strategy_used": strategy_name,
                "confidence": strategy_result.confidence,
            }
            
            # Add LLM narrative if enabled
            if include_llm and self.llm_agent.enabled:
                llm_narrative = self.llm_agent.generate_stock_analysis(
                    symbol,
                    indicators,
                    market_data=None
                )
                report["llm_narrative"] = llm_narrative
            
            return report
            
        except Exception as e:
            self.log_error(f"Error generating report for {symbol}", e, context={'symbol': symbol})
            return {
                "error": str(e),
                "symbol": symbol
            }
    
    def _generate_summary(self, indicators: Dict, strategy_result) -> str:
        """Generate simple, layman-friendly summary"""
        signal = strategy_result.signal.upper()
        trend = indicators.get('long_term_trend', 'neutral')
        
        summary = f"{signal} signal for this stock. "
        
        if signal == 'BUY':
            summary += "The technical indicators suggest this could be a good time to consider buying. "
            if trend == 'bullish':
                summary += "The long-term trend is positive, and momentum indicators are aligned."
        elif signal == 'SELL':
            summary += "Technical indicators suggest caution. Consider taking profits or reducing position. "
            summary += "Momentum may be fading."
        else:
            summary += "Current indicators are mixed. It may be best to wait for clearer signals before making a decision."
        
        return summary
    
    def _generate_trend_status(self, indicators: Dict) -> Dict[str, str]:
        """Generate trend status for short/medium/long term"""
        return {
            "short_term": self._interpret_trend(indicators.get('ema20'), indicators.get('ema50'), "EMA20 vs EMA50"),
            "medium_term": self._interpret_trend(indicators.get('medium_term_trend'), None, "Medium-term trend"),
            "long_term": self._interpret_trend(indicators.get('long_term_trend'), None, "Long-term trend (Price vs SMA200)")
        }
    
    def _interpret_trend(self, value1, value2, description) -> str:
        """Interpret trend value"""
        if isinstance(value1, str):
            if value1 == 'bullish':
                return f"✅ Bullish - {description}"
            elif value1 == 'bearish':
                return f"❌ Bearish - {description}"
            else:
                return f"⚪ Neutral - {description}"
        elif value1 and value2:
            if value1 > value2:
                return f"✅ Bullish - {description}"
            elif value1 < value2:
                return f"❌ Bearish - {description}"
            else:
                return f"⚪ Neutral - {description}"
        return "N/A"
    
    def _generate_signal_clarity(self, strategy_result, indicators: Dict) -> Dict[str, Any]:
        """Generate clear explanation of why buy/why wait"""
        signal = strategy_result.signal.upper()
        
        clarity = {
            "signal": signal,
            "why": strategy_result.reason,
            "confidence": f"{strategy_result.confidence * 100:.0f}%",
            "key_factors": []
        }
        
        # Add key factors
        if indicators.get('long_term_trend') == 'bullish':
            clarity["key_factors"].append("✅ Long-term trend is bullish")
        if indicators.get('medium_term_trend') == 'bullish':
            clarity["key_factors"].append("✅ Medium-term trend is bullish")
        if indicators.get('rsi') and indicators['rsi'] < 70:
            clarity["key_factors"].append("✅ RSI not overbought")
        if indicators.get('macd') and indicators.get('macd_signal'):
            if indicators['macd'] > indicators['macd_signal']:
                clarity["key_factors"].append("✅ MACD positive")
        
        if signal == 'BUY':
            clarity["action"] = "Consider buying on pullback to support levels"
        elif signal == 'SELL':
            clarity["action"] = "Consider taking profits or tightening stop-loss"
        else:
            clarity["action"] = "Wait for clearer signals before making a decision"
        
        return clarity
    
    def _generate_technical_analysis(self, indicators: Dict) -> Dict[str, Any]:
        """Generate technical analysis section"""
        return {
            "moving_averages": {
                "ema20": indicators.get('ema20'),
                "sma50": indicators.get('sma50'),
                "sma200": indicators.get('sma200'),
                "analysis": self._analyze_moving_averages(indicators)
            },
            "momentum": {
                "rsi": indicators.get('rsi'),
                "macd": indicators.get('macd'),
                "macd_signal": indicators.get('macd_signal'),
                "analysis": self._analyze_momentum(indicators)
            },
            "volatility": {
                "atr": indicators.get('atr'),
                "bb_upper": indicators.get('bb_upper'),
                "bb_lower": indicators.get('bb_lower'),
                "analysis": self._analyze_volatility(indicators)
            }
        }
    
    def _analyze_moving_averages(self, indicators: Dict) -> str:
        """Analyze moving averages"""
        ema20 = indicators.get('ema20')
        sma50 = indicators.get('sma50')
        sma200 = indicators.get('sma200')
        
        if all([ema20, sma50, sma200]):
            if ema20 > sma50 > sma200:
                return "Strong bullish alignment - all MAs trending up"
            elif ema20 < sma50 < sma200:
                return "Bearish alignment - all MAs trending down"
            else:
                return "Mixed signals - MAs not aligned"
        return "Insufficient data"
    
    def _analyze_momentum(self, indicators: Dict) -> str:
        """Analyze momentum indicators"""
        rsi = indicators.get('rsi')
        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        
        analysis = []
        if rsi:
            if rsi > 70:
                analysis.append("RSI overbought")
            elif rsi < 30:
                analysis.append("RSI oversold")
            else:
                analysis.append("RSI neutral")
        
        if macd and macd_signal:
            if macd > macd_signal:
                analysis.append("MACD bullish")
            else:
                analysis.append("MACD bearish")
        
        return ". ".join(analysis) if analysis else "Insufficient data"
    
    def _analyze_volatility(self, indicators: Dict) -> str:
        """Analyze volatility"""
        atr = indicators.get('atr')
        if atr:
            return f"ATR: {atr:.2f} - {'High' if atr > 5 else 'Moderate' if atr > 2 else 'Low'} volatility"
        return "Insufficient data"
    
    def _generate_risk_assessment(self, indicators: Dict, strategy_result) -> Dict[str, Any]:
        """Generate risk assessment"""
        confidence = strategy_result.confidence
        
        risk_level = "Low" if confidence > 0.7 else "Moderate" if confidence > 0.5 else "High"
        
        return {
            "risk_level": risk_level,
            "confidence": f"{confidence * 100:.0f}%",
            "stop_loss": indicators.get('pullback_zone_lower'),
            "support_level": indicators.get('pullback_zone_lower'),
            "resistance_level": indicators.get('pullback_zone_upper'),
            "recommendation": f"Use stop-loss at {risk_level.lower()} risk tolerance"
        }
    
    def _generate_recommendation(self, strategy_result, indicators: Dict) -> Dict[str, Any]:
        """Generate final recommendation"""
        signal = strategy_result.signal.upper()
        
        recommendation = {
            "action": signal,
            "confidence": f"{strategy_result.confidence * 100:.0f}%",
            "reasoning": strategy_result.reason,
            "target_price": None,  # Can be calculated based on indicators
            "stop_loss": indicators.get('pullback_zone_lower'),
            "time_horizon": "Short-term" if signal == 'BUY' else "Monitor closely"
        }
        
        return recommendation
    
    def save_report(self, report: Dict[str, Any], portfolio_id: Optional[str] = None) -> str:
        """
        Save report to database
        
        Returns:
            Report ID
        """
        report_id = str(uuid.uuid4())
        
        query = """
            INSERT OR REPLACE INTO llm_generated_reports
            (report_id, portfolio_id, stock_symbol, generated_content, report_type, timestamp)
            VALUES (:report_id, :portfolio_id, :symbol, :content, :report_type, CURRENT_TIMESTAMP)
        """
        
        params = {
            "report_id": report_id,
            "portfolio_id": portfolio_id,
            "symbol": report.get("symbol"),
            "content": json.dumps(report),
            "report_type": "stock_analysis"
        }
        
        try:
            db.execute_update(query, params)
            self.log_info(f"✅ Saved report {report_id} for {report.get('symbol')}", 
                         context={'report_id': report_id, 'symbol': report.get('symbol')})
            return report_id
        except Exception as e:
            self.log_error("Error saving report", e, context={'report_id': report_id, 'symbol': report.get('symbol')})
            raise
    
    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve report from database"""
        query = """
            SELECT generated_content, stock_symbol, timestamp
            FROM llm_generated_reports
            WHERE report_id = :report_id
        """
        
        result = db.execute_query(query, {"report_id": report_id})
        if result:
            return json.loads(result[0]['generated_content'])
        return None

