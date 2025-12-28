"""
Stock Insights Service
Aggregates strategy execution and stock analysis for comprehensive insights.
Used by both Streamlit and React UI via Go API proxy.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from app.services.base import BaseService
from app.repositories.market_data_daily_repository import MarketDataDailyRepository
from app.repositories.indicators_repository import IndicatorsRepository
from app.repositories.fundamentals_repository import FundamentalsRepository
from app.repositories.stock_insights_repository import StockInsightsRepository
from app.strategies.strategy_factory import StrategyFactory
from app.utils.indicator_keys import (
    normalize_indicator_keys, normalize_fundamental_keys,
    IndicatorKeys, get_missing_indicators, get_missing_fundamentals
)
from app.analysis.stock_analysis import StockAnalysis
from app.services.entry_exit_calculator import EntryExitCalculator
from app.observability.logging import get_logger
from app.utils.exception_handler import handle_database_errors

logger = get_logger(__name__)


class StockInsightsService(BaseService):
    """Service for generating comprehensive stock insights with strategy comparison"""
    
    def __init__(self):
        """Initialize stock insights service"""
        super().__init__()
        self.market_data_repo = MarketDataDailyRepository()
        self.indicators_repo = IndicatorsRepository()
        self.fundamentals_repo = FundamentalsRepository()
        self.insights_repo = StockInsightsRepository()
        self.strategy_factory = StrategyFactory()
        self.stock_analysis = StockAnalysis()
        self.entry_exit_calculator = EntryExitCalculator()

    @handle_database_errors
    def get_stock_insights(self, symbol: str, run_all_strategies: bool = True) -> Dict[str, Any]:
        """
        Generate comprehensive stock insights including strategy comparison and analysis
        
        Args:
            symbol: Stock symbol to analyze
            run_all_strategies: Whether to execute all strategies or just return analysis
            
        Returns:
            Comprehensive insights dictionary with:
            - analysis_sections: technical_momentum, financial_strength, valuation, trend_strength
            - overall_recommendation: buy/sell/hold signal with confidence
            - strategy_comparison: list of all strategies with their signals
            - metadata: timestamps, data sources, etc.
        """
        self.log_info(f"Generating stock insights for {symbol}", context={'symbol': symbol})
        
        try:
            # Fetch required data
            market_data = self._fetch_market_data(symbol)
            indicators = self._fetch_indicators(symbol, market_data)  # Pass market data for price injection
            fundamentals = self._fetch_fundamentals(symbol)
            
            # Generate analysis sections
            analysis = self.stock_analysis.analyze_stock(symbol, market_data, fundamentals)
            
            # Strategy comparison (optional)
            strategy_results = []
            if run_all_strategies:
                strategy_results = self._run_all_strategies(symbol, indicators, market_data)
            
            # Generate overall recommendation with entry/exit plans
            overall_recommendation = self._generate_overall_recommendation(
                symbol, market_data, indicators, fundamentals, strategy_results
            )
            
            # Create comprehensive insights
            insights = {
                "symbol": symbol,
                "generated_at": datetime.now().isoformat(),
                "overall_recommendation": overall_recommendation,
                "analysis_sections": analysis,
                "strategy_results": strategy_results,
                "data_status": self._check_data_availability(market_data, indicators, fundamentals)
            }
            
            # Save insights snapshot to database
            try:
                self.insights_repo.save_insights(symbol, insights)
            except Exception as e:
                self.log_warning(f"Failed to save insights snapshot for {symbol}: {e}")
            self.log_info(f"Generated insights for {symbol}: {overall_recommendation['signal']} signal", 
                         context={'symbol': symbol, 'signal': overall_recommendation['signal']})
            
            return insights
            
        except Exception as e:
            self.log_error(f"Error generating stock insights for {symbol}", e, context={'symbol': symbol})
            raise
    
    def _fetch_market_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch market data for symbol"""
        try:
            data = self.market_data_repo.fetch_by_symbol(symbol, order_by="trade_date DESC", limit=252)
            if data is None or len(data) == 0:
                self.log_warning(f"No market data found for {symbol}", context={'symbol': symbol})
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            if len(df) == 0:
                self.log_warning(f"Empty market data DataFrame for {symbol}", context={'symbol': symbol})
                return None
                
            return df
        except Exception as e:
            self.log_error(f"Error fetching market data for {symbol}", e, context={'symbol': symbol})
            return None
    
    def _fetch_indicators(self, symbol: str, market_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """Fetch technical indicators for symbol and normalize to canonical keys"""
        try:
            indicators_data = self.indicators_repo.fetch_latest_by_symbol(symbol)
            if not indicators_data:
                self.log_warning(f"No indicators found for {symbol}", context={'symbol': symbol})
                return {}
            
            # Normalize to canonical keys (handles aliased names, raw DB names, etc.)
            normalized_indicators = normalize_indicator_keys(indicators_data)
            
            # Inject price from market data if available (strategies require this)
            if market_data is not None and len(market_data) > 0:
                current_price = float(market_data.iloc[-1]['close'])
                normalized_indicators[IndicatorKeys.PRICE] = current_price
                self.log_debug(f"Injected price={current_price} for {symbol}", context={'symbol': symbol})
            
            # Log missing required indicators for debugging
            missing = get_missing_indicators(normalized_indicators)
            if missing:
                self.log_warning(f"Missing required indicators for {symbol}: {missing}", 
                               context={'symbol': symbol, 'missing': missing})
            
            return normalized_indicators
            
        except Exception as e:
            self.log_error(f"Error fetching indicators for {symbol}", e, context={'symbol': symbol})
            return {}
    
    def _generate_overall_recommendation(
        self, 
        symbol: str, 
        market_data: Optional[pd.DataFrame],
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        strategy_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate overall recommendation with entry/exit plans and reasoning"""
        try:
            # Get current price
            current_price = market_data.iloc[-1]['close'] if market_data is not None and len(market_data) > 0 else None
            
            # Aggregate signal from strategies
            overall_signal = self._aggregate_signals(strategy_results)
            overall_confidence = self._aggregate_confidence(strategy_results)
            
            # Generate entry/exit plans
            position_plan = None
            swing_plan = None
            
            if market_data is not None and current_price:
                position_plan = self.entry_exit_calculator.calculate_position_plan(
                    market_data, indicators, fundamentals, current_price
                )
                swing_plan = self.entry_exit_calculator.calculate_swing_plan(
                    market_data, indicators, current_price
                )
            
            # Generate reasoning
            reasoning = self._generate_recommendation_reasoning(
                overall_signal, indicators, fundamentals, strategy_results
            )
            
            # Key drivers
            key_drivers = self._identify_key_drivers(indicators, fundamentals, strategy_results)
            
            # What would change the call
            invalidation_triggers = self._identify_invalidation_triggers(indicators, fundamentals)
            
            recommendation = {
                "signal": overall_signal,
                "confidence": overall_confidence,
                "reason_summary": reasoning["summary"],
                "key_drivers": key_drivers,
                "position_plan": position_plan,
                "swing_plan": swing_plan,
                "invalidation_triggers": invalidation_triggers,
                "data_readiness": self._assess_data_readiness(market_data, indicators, fundamentals),
                "timeframe": "Medium-term (weeks to months)",
                "risk_level": self._assess_risk_level(overall_confidence, indicators)
            }
            
            return recommendation
            
        except Exception as e:
            self.log_error(f"Error generating overall recommendation for {symbol}", e, context={'symbol': symbol})
            return self._empty_recommendation()
    
    def _generate_recommendation_reasoning(
        self, 
        signal: str, 
        indicators: Dict[str, Any], 
        fundamentals: Dict[str, Any],
        strategy_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate reasoning for the recommendation"""
        summary_parts = []
        
        if signal == "BUY":
            summary_parts.append("Technical indicators suggest bullish momentum")
            
            # Check moving averages
            if indicators.get("sma50") and indicators.get("sma200"):
                if indicators["sma50"] > indicators["sma200"]:
                    summary_parts.append("Price is above key long-term moving averages")
            
            # Check fundamentals
            if fundamentals.get("pe_ratio") and 10 <= fundamentals["pe_ratio"] <= 25:
                summary_parts.append("Reasonable valuation supports upside potential")
            
            # Strategy alignment
            bullish_strategies = [s for s in strategy_results if s.get("signal") == "BUY"]
            if len(bullish_strategies) > len(strategy_results) / 2:
                summary_parts.append("Multiple strategies align on bullish outlook")
                
        elif signal == "SELL":
            summary_parts.append("Technical indicators suggest bearish momentum")
            
            # Check moving averages
            if indicators.get("sma50") and indicators.get("sma200"):
                if indicators["sma50"] < indicators["sma200"]:
                    summary_parts.append("Price is below key long-term moving averages")
            
            # Strategy alignment
            bearish_strategies = [s for s in strategy_results if s.get("signal") == "SELL"]
            if len(bearish_strategies) > len(strategy_results) / 2:
                summary_parts.append("Multiple strategies indicate sell signals")
                
        else:  # HOLD
            summary_parts.append("Mixed signals suggest waiting for clearer direction")
            
            # Check for conflicting signals
            if indicators.get("rsi") and 40 <= indicators.get("rsi", 0) <= 60:
                summary_parts.append("Momentum indicators are neutral")
            
            summary_parts.append("Monitor for confirmation before taking position")
        
        return {
            "summary": ". ".join(summary_parts) + ".",
            "length": len(summary_parts)
        }
    
    def _identify_key_drivers(
        self, 
        indicators: Dict[str, Any], 
        fundamentals: Dict[str, Any],
        strategy_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Identify the key drivers behind the recommendation"""
        drivers = []
        
        # Technical drivers
        if indicators.get("sma50") and indicators.get("sma200"):
            trend = "Bullish" if indicators["sma50"] > indicators["sma200"] else "Bearish"
            drivers.append({
                "category": "Technical",
                "factor": "Trend (50/200 MA)",
                "value": trend,
                "impact": "Positive" if trend == "Bullish" else "Negative"
            })
        
        if indicators.get("rsi"):
            rsi = indicators["rsi"]
            if rsi > 70:
                drivers.append({
                    "category": "Technical",
                    "factor": "RSI (Momentum)",
                    "value": f"Overbought ({rsi:.0f})",
                    "impact": "Negative"
                })
            elif rsi < 30:
                drivers.append({
                    "category": "Technical", 
                    "factor": "RSI (Momentum)",
                    "value": f"Oversold ({rsi:.0f})",
                    "impact": "Positive"
                })
            else:
                drivers.append({
                    "category": "Technical",
                    "factor": "RSI (Momentum)", 
                    "value": f"Neutral ({rsi:.0f})",
                    "impact": "Neutral"
                })
        
        # Fundamental drivers
        if fundamentals.get("pe_ratio"):
            pe = fundamentals["pe_ratio"]
            if pe <= 15:
                drivers.append({
                    "category": "Fundamental",
                    "factor": "Valuation (P/E)",
                    "value": f"Attractive ({pe:.1f})",
                    "impact": "Positive"
                })
            elif pe >= 35:
                drivers.append({
                    "category": "Fundamental",
                    "factor": "Valuation (P/E)",
                    "value": f"Expensive ({pe:.1f})",
                    "impact": "Negative"
                })
        
        if fundamentals.get("debt_to_equity"):
            debt = fundamentals["debt_to_equity"]
            if debt <= 0.5:
                drivers.append({
                    "category": "Fundamental",
                    "factor": "Financial Health",
                    "value": f"Low debt ({debt:.2f})",
                    "impact": "Positive"
                })
            elif debt >= 1.0:
                drivers.append({
                    "category": "Fundamental",
                    "factor": "Financial Health", 
                    "value": f"High debt ({debt:.2f})",
                    "impact": "Negative"
                })
        
        return drivers[:5]  # Return top 5 drivers
    
    def _identify_invalidation_triggers(self, indicators: Dict[str, Any], fundamentals: Dict[str, Any]) -> List[str]:
        """Identify what would change the current recommendation"""
        triggers = []
        
        # Technical triggers
        if indicators.get(IndicatorKeys.SMA_50) and indicators.get(IndicatorKeys.SMA_200):
            triggers.append("Close below 200-day moving average would invalidate bullish thesis")
        
        if indicators.get(IndicatorKeys.RSI_14):
            triggers.append("RSI breaking below 30 (oversold) or above 70 (overbought) extremes")
        
        # Fundamental triggers
        if fundamentals.get("pe_ratio"):
            triggers.append("P/E ratio expanding above 40 would reduce attractiveness")
        
        if fundamentals.get("debt_to_equity"):
            triggers.append("Debt-to-equity rising above 1.5 would signal financial stress")
        
        # General triggers
        triggers.append("Break of key support/resistance levels on increased volume")
        triggers.append("Deteriorating earnings or revenue growth trends")
        
        return triggers[:4]  # Return top 4 triggers
    
    def _assess_data_readiness(
        self, 
        market_data: Optional[pd.DataFrame], 
        indicators: Dict[str, Any], 
        fundamentals: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess data readiness for analysis"""
        readiness = {
            "market_data": False,
            "indicators": False,
            "fundamentals": False,
            "overall": False,
            "missing_items": []
        }
        
        # Check market data
        if market_data is not None and len(market_data) >= 50:
            readiness["market_data"] = True
        else:
            readiness["missing_items"].append("Insufficient market data (need 50+ days)")
        
        # Check indicators
        required_indicators = [
            IndicatorKeys.SMA_50,
            IndicatorKeys.SMA_200,
            IndicatorKeys.EMA_20,
            IndicatorKeys.RSI_14,
            IndicatorKeys.MACD_LINE,
            IndicatorKeys.MACD_SIGNAL,
        ]
        missing_indicators = [k for k in required_indicators if not indicators.get(k)]
        if len(missing_indicators) <= 2:
            readiness["indicators"] = True
        else:
            readiness["missing_items"].append(f"Missing indicators: {', '.join(missing_indicators)}")
        
        # Check fundamentals
        if fundamentals and len(fundamentals) >= 5:
            readiness["fundamentals"] = True
        else:
            readiness["missing_items"].append("Insufficient fundamental data")
        
        # Overall readiness
        readiness["overall"] = all([readiness["market_data"], readiness["indicators"]])
        
        return readiness
    
    def _assess_risk_level(self, confidence: float, indicators: Dict[str, Any]) -> str:
        """Assess overall risk level"""
        # Base risk on confidence
        if confidence >= 0.8:
            base_risk = "Low"
        elif confidence >= 0.6:
            base_risk = "Medium"
        else:
            base_risk = "High"
        
        # Adjust for volatility if available
        if indicators.get("atr"):
            # This is a simplified assessment - in practice you'd compare ATR to price
            base_risk = base_risk  # Keep as is for now
        
        return base_risk
    
    def _check_data_availability(
        self, 
        market_data: Optional[pd.DataFrame], 
        indicators: Dict[str, Any], 
        fundamentals: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check what data is available for analysis"""
        return {
            "market_data_available": market_data is not None and len(market_data) > 0,
            "indicators_available": len(indicators) > 0,
            "fundamentals_available": len(fundamentals) > 0,
            "can_generate_entry_exit": market_data is not None and len(market_data) >= 20
        }
    
    def _empty_recommendation(self) -> Dict[str, Any]:
        """Return empty recommendation structure"""
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "reason_summary": "Insufficient data to generate recommendation",
            "key_drivers": [],
            "position_plan": None,
            "swing_plan": None,
            "invalidation_triggers": ["Need more data to assess"],
            "data_readiness": {"overall": False, "missing_items": ["Insufficient data"]},
            "timeframe": "Unknown",
            "risk_level": "High"
        }
    
    def _generate_analysis(self, symbol: str, market_data: Optional[pd.DataFrame], 
                          fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        """Generate analysis sections"""
        try:
            return self.stock_analysis.analyze_stock(symbol, market_data, fundamentals)
        except Exception as e:
            self.log_error(f"Error generating analysis for {symbol}", e)
            return {}
    
    def _run_all_strategies(self, symbol: str, indicators: Dict[str, Any], 
                          market_data: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """Run all available strategies"""
        try:
            strategies = self.strategy_factory.get_available_strategies()
            results = []
            
            for strategy_name in strategies.keys():
                result = self.strategy_factory.execute_strategy(
                    strategy_name, indicators, {"symbol": symbol}
                )
                results.append(result)
            
            return results
        except Exception as e:
            self.log_error(f"Error running strategies for {symbol}", e)
            return []
    
    def _aggregate_signals(self, strategy_results: List[Dict[str, Any]]) -> str:
        """Aggregate signals from multiple strategies"""
        if not strategy_results:
            return "HOLD"
        
        signals = [r.get("signal", "HOLD") for r in strategy_results]
        buy_count = signals.count("BUY")
        sell_count = signals.count("SELL")
        
        if buy_count > sell_count:
            return "BUY"
        elif sell_count > buy_count:
            return "SELL"
        else:
            return "HOLD"
    
    def _aggregate_confidence(self, strategy_results: List[Dict[str, Any]]) -> float:
        """Aggregate confidence scores from multiple strategies"""
        if not strategy_results:
            return 0.0
        
        confidences = [r.get("confidence", 0.0) for r in strategy_results if isinstance(r.get("confidence"), (int, float))]
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    def _fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamentals for symbol and normalize to canonical keys"""
        try:
            fundamentals_data = self.fundamentals_repo.fetch_by_symbol(symbol)
            if not fundamentals_data:
                self.log_warning(f"No fundamentals found for {symbol}", context={'symbol': symbol})
                return {}
            
            # Normalize to canonical keys
            normalized_fundamentals = normalize_fundamental_keys(fundamentals_data)
            
            # Log missing required fundamentals for debugging
            missing = get_missing_fundamentals(normalized_fundamentals)
            if missing:
                self.log_info(f"Missing some fundamentals for {symbol}: {missing}", 
                            context={'symbol': symbol, 'missing': missing})
            
            return normalized_fundamentals
            
        except Exception as e:
            self.log_error(f"Error fetching fundamentals for {symbol}", e, context={'symbol': symbol})
            return {}
    
    def _generate_analysis(self, symbol: str, market_data: Optional[pd.DataFrame], 
                          fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        """Generate all analysis sections"""
        try:
            # Get industry key for valuation benchmarks (simplified)
            industry_key = self._get_industry_key(fundamentals)
            
            analysis = generate_stock_analysis(
                symbol=symbol,
                df=market_data,
                fundamentals=fundamentals,
                industry_key=industry_key
            )
            
            return analysis
            
        except Exception as e:
            self.log_error(f"Error generating analysis for {symbol}", e, context={'symbol': symbol})
            # Return empty analysis sections on error
            return {
                "symbol": symbol,
                "current_price": None,
                "last_updated": datetime.now().isoformat(),
                "technical_momentum": {"score": 0, "summary": "Analysis failed", "details": {}},
                "financial_strength": {"score": 0, "summary": "Analysis failed", "details": {}},
                "valuation": {"score": 5, "summary": "Analysis failed", "details": {}},
                "trend_strength": {"score": 0, "summary": "Analysis failed", "details": {}}
            }
    
    def _run_all_strategies(self, symbol: str, indicators: Dict[str, Any], 
                          market_data: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """Run all available strategies"""
        strategy_results = []
        
        try:
            available_strategies = self.strategy_factory.get_available_strategies()
            
            for strategy_name, description in available_strategies.items():
                try:
                    # Execute strategy
                    result = self.strategy_factory.execute_strategy(
                        strategy_name, indicators, {"symbol": symbol}
                    )
                    
                    # Convert result to dictionary for JSON serialization
                    strategy_dict = {
                        "name": strategy_name,
                        "description": description,
                        "signal": result.get("signal", "HOLD"),
                        "confidence": result.get("confidence", 0.0),
                        "reason": result.get("reason", "No reason provided"),
                        "metadata": result.get("metadata", {}),
                        "execution_time": datetime.now().isoformat()
                    }
                    
                    strategy_results.append(strategy_dict)
                    
                    self.log_info(f"Strategy {strategy_name} completed for {symbol}", 
                                 context={'symbol': symbol, 'strategy': strategy_name, 'signal': result.get("signal")})
                    
                except Exception as e:
                    self.log_error(f"Error executing strategy {strategy_name} for {symbol}", e,
                                 context={'symbol': symbol, 'strategy': strategy_name})
                    
                    # Add failed strategy result
                    strategy_results.append({
                        "name": strategy_name,
                        "description": description,
                        "signal": "HOLD",
                        "confidence": 0.0,
                        "reason": f"Strategy execution failed: {str(e)}",
                        "metadata": {"error": True},
                        "execution_time": datetime.now().isoformat()
                    })
            
            # Sort strategies by confidence (descending)
            strategy_results.sort(key=lambda x: x["confidence"], reverse=True)
            
        except Exception as e:
            self.log_error(f"Error running strategy comparison for {symbol}", e, context={'symbol': symbol})
        
        return strategy_results
    
    def _get_industry_key(self, fundamentals: Dict[str, Any]) -> Optional[str]:
        """Extract industry key from fundamentals for valuation benchmarks"""
        # Try different field names that might contain industry information
        industry_fields = ["sector", "industry", "industry_key", "gics_sector"]
        
        for field in industry_fields:
            if field in fundamentals and fundamentals[field]:
                industry = str(fundamentals[field]).lower().replace(" ", "-")
                # Map common variations to standard keys
                if "software" in industry or "technology" in industry:
                    return "software-infrastructure"
                elif "semiconductor" in industry:
                    return "semiconductors"
                elif "telecom" in industry:
                    return "telecom-services"
                elif "bank" in industry:
                    return "banks-diversified"
                elif "insurance" in industry:
                    return "insurance-diversified"
                elif "biotech" in industry or "pharmaceutical" in industry:
                    return "biotechnology"
                elif "cybersecurity" in industry:
                    return "cybersecurity"
                elif "renewable" in industry or "clean" in industry:
                    return "renewable-energy"
                elif "electric" in industry and "vehicle" in industry:
                    return "electric-vehicle"
                elif "capital" in industry or "financial" in industry:
                    return "capital-markets"
        
        return None
    
    def get_available_strategies(self) -> Dict[str, str]:
        """Get list of all available strategies with descriptions"""
        return self.strategy_factory.get_available_strategies()
    
    def run_single_strategy(self, symbol: str, strategy_name: str) -> Dict[str, Any]:
        """Run a single strategy for a symbol"""
        try:
            # Fetch data
            market_data = self._fetch_market_data(symbol)
            indicators = self._fetch_indicators(symbol, market_data)  # Pass market data for price injection
            
            # Execute strategy
            result = self.strategy_factory.execute_strategy(
                strategy_name, indicators, {"symbol": symbol}
            )
            
            return {
                "symbol": symbol,
                "strategy": {
                    "name": strategy_name,
                    "description": self.strategy_factory.get_available_strategies().get(strategy_name, ""),
                    "signal": result.get("signal", "HOLD"),
                    "confidence": round(result.get("confidence", 0.0), 3),
                    "reason": result.get("reason", "No reason provided"),
                    "metadata": result.get("metadata", {})
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.log_error(f"Error running strategy {strategy_name} for {symbol}", e,
                         context={'symbol': symbol, 'strategy': strategy_name})
            raise
