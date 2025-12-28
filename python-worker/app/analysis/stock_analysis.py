"""
Stock analysis sections: Technical momentum, Financial strength, Valuation, Trend strength.
Similar to TipRanks style.
"""

import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime


class StockAnalysis:
    """Stock analysis wrapper class"""
    
    def analyze_stock(self, symbol: str, market_data: pd.DataFrame, fundamentals: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze stock across multiple dimensions
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data with indicators
            fundamentals: Fundamental data
            
        Returns:
            Analysis results by section
        """
        try:
            # Get current price from market data
            current_price = None
            if market_data is not None and len(market_data) > 0:
                latest = market_data.iloc[-1]
                current_price = latest.get("close") or latest.get("price")
            
            # Get industry key from fundamentals
            industry_key = self._get_industry_key(fundamentals)
            
            return {
                "technical_momentum": calculate_technical_momentum(market_data),
                "financial_strength": calculate_financial_strength(fundamentals),
                "valuation": calculate_valuation(fundamentals, current_price, industry_key),
                "trend_strength": calculate_trend_strength(market_data)
            }
        except Exception as e:
            return {
                "technical_momentum": {"score": 0, "summary": f"Error: {e}", "details": {}},
                "financial_strength": {"score": 0, "summary": f"Error: {e}", "details": {}},
                "valuation": {"score": 0, "summary": f"Error: {e}", "details": {}},
                "trend_strength": {"score": 0, "summary": f"Error: {e}", "details": {}}
            }
    
    def _get_industry_key(self, fundamentals: Dict[str, Any]) -> Optional[str]:
        """Extract industry key from fundamentals"""
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
                elif "renewable" in industry or "clean" in industry:
                    return "renewable-energy"
                elif "electric" in industry and "vehicle" in industry:
                    return "electric-vehicle"
                elif "capital" in industry or "financial" in industry:
                    return "capital-markets"
        
        return None

def calculate_technical_momentum(df: pd.DataFrame) -> Dict[str, Any]:
    """Technical momentum based on RSI, MACD, EMAs, volume."""
    if df is None or df.empty:
        return {"score": 0, "summary": "No data available", "details": {}}
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    
    # RSI momentum
    rsi = latest.get("rsi")
    rsi_signal = "Neutral"
    if rsi:
        if rsi > 70:
            rsi_signal = "Overbought (bearish)"
        elif rsi < 30:
            rsi_signal = "Oversold (bullish)"
        elif rsi > 50:
            rsi_signal = "Bullish"
        else:
            rsi_signal = "Bearish"
    
    # MACD momentum
    macd = latest.get("macd")
    macd_signal = latest.get("macd_signal")
    macd_trend = "Neutral"
    if macd and macd_signal:
        if macd > macd_signal:
            macd_trend = "Bullish (above signal)"
        else:
            macd_trend = "Bearish (below signal)"
    
    # EMA trend
    ema20 = latest.get("ema20")
    ema50 = latest.get("ema50")
    sma200 = latest.get("sma200")
    ema_trend = "Neutral"
    if ema20 and ema50 and sma200:
        if ema20 > ema50 > sma200:
            ema_trend = "Strong bullish"
        elif ema20 > ema50 and ema50 < sma200:
            ema_trend = "Bullish (short-term)"
        elif ema20 < ema50 and ema50 > sma200:
            ema_trend = "Pullback in uptrend"
        else:
            ema_trend = "Bearish"
    
    # Volume confirmation
    volume = latest.get("volume", 0)
    volume_ma = latest.get("volume_ma", 1)
    volume_signal = "Neutral"
    if volume_ma > 0:
        vol_ratio = volume / volume_ma
        if vol_ratio > 1.5:
            volume_signal = "High volume (confirmation)"
        elif vol_ratio < 0.5:
            volume_signal = "Low volume (weak)"
        else:
            volume_signal = "Average"
    
    # Scoring
    score = 0
    reasons = []
    if rsi and 30 < rsi < 70:
        score += 1
        reasons.append("RSI in normal range")
    if macd and macd_signal and macd > macd_signal:
        score += 1
        reasons.append("MACD above signal")
    if ema20 and ema50 and ema20 > ema50:
        score += 1
        reasons.append("Short EMA above long EMA")
    if volume_ma > 0 and volume > volume_ma * 1.2:
        score += 1
        reasons.append("Volume spike confirms")
    
    max_score = 4
    normalized_score = (score / max_score) * 10
    
    summary = f"Technical momentum is {'strong' if normalized_score >= 7 else 'moderate' if normalized_score >= 4 else 'weak'} ({normalized_score:.1f}/10)."
    if reasons:
        summary += " " + "; ".join(reasons) + "."
    
    return {
        "score": round(normalized_score, 1),
        "summary": summary,
        "details": {
            "RSI": f"{rsi:.1f} ({rsi_signal})" if rsi else "N/A",
            "MACD": macd_trend,
            "EMA trend": ema_trend,
            "Volume": volume_signal
        }
    }

def calculate_financial_strength(fundamentals: Dict[str, Any]) -> Dict[str, Any]:
    """Financial strength based on debt, profitability, liquidity."""
    if not fundamentals:
        return {"score": 0, "summary": "No fundamentals available", "details": {}}
    
    # Key metrics
    debt_to_equity = fundamentals.get("debt_to_equity")
    roe = fundamentals.get("roe")
    roa = fundamentals.get("roa")
    profit_margin = fundamentals.get("profit_margin")
    operating_margin = fundamentals.get("operating_margin")
    current_ratio = fundamentals.get("current_ratio")
    
    score = 0
    reasons = []
    details = {}
    
    # Debt evaluation
    if debt_to_equity is not None:
        if debt_to_equity < 0.5:
            score += 2
            reasons.append("Low debt")
            details["Debt/Equity"] = f"{debt_to_equity:.2f} (Low)"
        elif debt_to_equity < 1.0:
            score += 1
            reasons.append("Moderate debt")
            details["Debt/Equity"] = f"{debt_to_equity:.2f} (Moderate)"
        else:
            details["Debt/Equity"] = f"{debt_to_equity:.2f} (High)"
    
    # Profitability
    if roe is not None:
        if roe > 0.15:
            score += 2
            reasons.append("Strong ROE")
            details["ROE"] = f"{roe:.2%} (Strong)"
        elif roe > 0.10:
            score += 1
            reasons.append("Good ROE")
            details["ROE"] = f"{roe:.2%} (Good)"
        else:
            details["ROE"] = f"{roe:.2%} (Weak)"
    
    if roa is not None:
        if roa > 0.05:
            score += 1
            details["ROA"] = f"{roa:.2%} (Good)"
        else:
            details["ROA"] = f"{roa:.2%} (Weak)"
    
    # Margins
    if profit_margin is not None:
        if profit_margin > 0.10:
            score += 1
            details["Profit Margin"] = f"{profit_margin:.2%} (Strong)"
        else:
            details["Profit Margin"] = f"{profit_margin:.2%} (Weak)"
    
    # Liquidity
    if current_ratio is not None:
        if current_ratio > 1.5:
            score += 1
            details["Current Ratio"] = f"{current_ratio:.2f} (Strong)"
        elif current_ratio > 1.0:
            details["Current Ratio"] = f"{current_ratio:.2f} (Adequate)"
        else:
            details["Current Ratio"] = f"{current_ratio:.2f} (Weak)"
    
    max_score = 7
    normalized_score = (score / max_score) * 10 if max_score > 0 else 0
    
    summary = f"Financial strength is {'strong' if normalized_score >= 7 else 'moderate' if normalized_score >= 4 else 'weak'} ({normalized_score:.1f}/10)."
    if reasons:
        summary += " " + "; ".join(reasons) + "."
    
    return {
        "score": round(normalized_score, 1),
        "summary": summary,
        "details": details
    }

def calculate_valuation(fundamentals: Dict[str, Any], price: float, industry_key: str = None) -> Dict[str, Any]:
    """Valuation based on PE, PB, PS, EV/EBITDA with industry benchmarks."""
    if not fundamentals or price is None:
        return {"score": 5, "summary": "Insufficient data for valuation", "details": {}}
    
    pe = fundamentals.get("pe_ratio")
    pb = fundamentals.get("pb_ratio")
    ps = fundamentals.get("price_to_sales")
    ev_ebitda = fundamentals.get("ev_ebitda")
    forward_pe = fundamentals.get("forward_pe")
    
    # Derive EV/EBITDA if not directly available
    if not ev_ebitda:
        enterprise_value = fundamentals.get("enterprise_value")
        operating_income = fundamentals.get("operating_income")
        if enterprise_value and operating_income and operating_income != 0:
            # EBITDA ≈ Operating Income + D&A (use operating income as proxy)
            ev_ebitda = enterprise_value / operating_income
    
    # Industry EV/EBITDA benchmarks (median values)
    industry_ev_ebitda_benchmarks = {
        "software-infrastructure": {"median": 14, "undervalued": 10, "expensive": 20},
        "capital-markets": {"median": 10, "undervalued": 7, "expensive": 14},
        "semiconductors": {"median": 14, "undervalued": 10, "expensive": 20},
        "telecom-services": {"median": 8, "undervalued": 6, "expensive": 12},
        "renewable-energy": {"median": 12, "undervalued": 8, "expensive": 18},
        "electric-vehicle": {"median": 15, "undervalued": 10, "expensive": 22},
        "banks-diversified": {"median": 8, "undervalued": 6, "expensive": 12},
        "insurance-diversified": {"median": 10, "undervalued": 7, "expensive": 14},
        "biotechnology": {"median": 18, "undervalued": 12, "expensive": 25},
        "cybersecurity": {"median": 16, "undervalued": 11, "expensive": 22}
    }
    
    score = 5  # Neutral baseline
    reasons = []
    details = {}
    
    # EV/EBITDA analysis (primary metric)
    ev_analysis = {}
    if ev_ebitda:
        ev_analysis["current"] = round(ev_ebitda, 1)
        
        # Industry comparison
        if industry_key and industry_key in industry_ev_ebitda_benchmarks:
            benchmark = industry_ev_ebitda_benchmarks[industry_key]
            median = benchmark["median"]
            premium = ((ev_ebitda - median) / median) * 100
            ev_analysis["industry_median"] = median
            ev_analysis["premium_pct"] = round(premium, 1)
            
            if ev_ebitda < benchmark["undervalued"]:
                ev_analysis["signal"] = "Undervalued"
                score += 2
                reasons.append("EV/EBITDA below industry")
            elif ev_ebitda > benchmark["expensive"]:
                ev_analysis["signal"] = "Expensive"
                score -= 2
                reasons.append("EV/EBITDA above industry")
            else:
                ev_analysis["signal"] = "Fair"
        else:
            # Generic EV/EBITDA interpretation
            if ev_ebitda < 8:
                ev_analysis["signal"] = "Undervalued"
                score += 1
                reasons.append("Low EV/EBITDA")
            elif ev_ebitda > 18:
                ev_analysis["signal"] = "Expensive"
                score -= 1
                reasons.append("High EV/EBITDA")
            else:
                ev_analysis["signal"] = "Fair"
        
        details["EV/EBITDA"] = ev_analysis
    
    # PE ratio
    if pe:
        if pe < 15:
            score += 1
            reasons.append("Low PE")
            details["PE"] = f"{pe:.1f} (Attractive)"
        elif pe > 30:
            score -= 1
            reasons.append("High PE")
            details["PE"] = f"{pe:.1f} (Expensive)"
        else:
            details["PE"] = f"{pe:.1f} (Fair)"
    
    # PB ratio
    if pb:
        if pb < 1.0:
            score += 1
            reasons.append("Low PB")
            details["PB"] = f"{pb:.2f} (Attractive)"
        elif pb > 5:
            score -= 1
            reasons.append("High PB")
            details["PB"] = f"{pb:.2f} (Expensive)"
        else:
            details["PB"] = f"{pb:.2f} (Fair)"
    
    # PS ratio
    if ps:
        if ps < 2:
            score += 1
            reasons.append("Low PS")
            details["PS"] = f"{ps:.2f} (Attractive)"
        elif ps > 8:
            score -= 1
            reasons.append("High PS")
            details["PS"] = f"{ps:.2f} (Expensive)"
        else:
            details["PS"] = f"{ps:.2f} (Fair)"
    
    # Forward PE (growth adjustment)
    if forward_pe and pe:
        if forward_pe < pe * 0.8:
            score += 1
            reasons.append("Forward PE suggests growth")
        elif forward_pe > pe * 1.2:
            score -= 1
            reasons.append("Forward PE suggests slowdown")
    
    max_score = 9
    min_score = 1
    normalized_score = max(min_score, min(max_score, score))
    normalized_score = ((normalized_score - 1) / (max_score - 1)) * 10
    
    if normalized_score >= 7:
        valuation_level = "Undervalued"
    elif normalized_score <= 3:
        valuation_level = "Overvalued"
    else:
        valuation_level = "Fairly valued"
    
    # Build summary with EV/EBITDA context
    summary_parts = [f"Valuation is {valuation_level.lower()} ({normalized_score:.1f}/10)"]
    if ev_ebitda:
        ev_signal = ev_analysis.get("signal", "Fair")
        summary_parts.append(f"EV/EBITDA {ev_signal.lower()}")
        if "premium_pct" in ev_analysis:
            premium = ev_analysis["premium_pct"]
            if premium > 0:
                summary_parts.append(f"+{premium}% vs industry")
            else:
                summary_parts.append(f"{premium}% vs industry")
    if reasons:
        summary_parts.append("; ".join(reasons[:3]))  # Limit to top 3 reasons
    summary = ". ".join(summary_parts) + "."
    
    return {
        "score": round(normalized_score, 1),
        "summary": summary,
        "details": details
    }

def calculate_trend_strength(df: pd.DataFrame) -> Dict[str, Any]:
    """Trend strength based on moving averages and price momentum."""
    if df is None or df.empty:
        return {"score": 0, "summary": "No data available", "details": {}}
    
    latest = df.iloc[-1]
    price = latest.get("close", 0)
    
    # Moving average positioning
    sma20 = latest.get("sma20")
    sma50 = latest.get("sma50")
    sma200 = latest.get("sma200")
    
    score = 0
    reasons = []
    details = {}
    
    if price and sma20:
        if price > sma20:
            score += 1
            reasons.append("Price above SMA20")
            details["vs SMA20"] = "Above"
        else:
            details["vs SMA20"] = "Below"
    
    if sma20 and sma50:
        if sma20 > sma50:
            score += 1
            reasons.append("SMA20 above SMA50")
            details["SMA20/50"] = "Bullish crossover"
        else:
            details["SMA20/50"] = "Bearish crossover"
    
    if sma50 and sma200:
        if sma50 > sma200:
            score += 2
            reasons.append("SMA50 above SMA200 (golden cross)")
            details["SMA50/200"] = "Golden cross"
        else:
            details["SMA50/200"] = "Death cross"
    
    # Price momentum (1-month, 3-month)
    if len(df) >= 20:
        price_1m_ago = df.iloc[-20]["close"]
        momentum_1m = (price - price_1m_ago) / price_1m_ago
        if momentum_1m > 0.05:
            score += 1
            reasons.append("Strong 1-month momentum")
            details["1M momentum"] = f"+{momentum_1m:.1%}"
        elif momentum_1m < -0.05:
            details["1M momentum"] = f"{momentum_1m:.1%}"
        else:
            details["1M momentum"] = "Flat"
    
    if len(df) >= 60:
        price_3m_ago = df.iloc[-60]["close"]
        momentum_3m = (price - price_3m_ago) / price_3m_ago
        if momentum_3m > 0.10:
            score += 1
            reasons.append("Strong 3-month momentum")
            details["3M momentum"] = f"+{momentum_3m:.1%}"
        elif momentum_3m < -0.10:
            details["3M momentum"] = f"{momentum_3m:.1%}"
        else:
            details["3M momentum"] = "Flat"
    
    max_score = 6
    normalized_score = (score / max_score) * 10 if max_score > 0 else 0
    
    trend_desc = "strong" if normalized_score >= 7 else "moderate" if normalized_score >= 4 else "weak"
    summary = f"Trend strength is {trend_desc} ({normalized_score:.1f}/10)."
    if reasons:
        summary += " " + "; ".join(reasons) + "."
    
    return {
        "score": round(normalized_score, 1),
        "summary": summary,
        "details": details
    }

def generate_stock_analysis(symbol: str, df: pd.DataFrame, fundamentals: Dict[str, Any], industry_key: str = None) -> Dict[str, Any]:
    """Generate complete stock analysis with all sections."""
    current_price = df.iloc[-1]["close"] if df is not None and not df.empty else None
    
    return {
        "symbol": symbol,
        "current_price": current_price,
        "last_updated": datetime.now().isoformat(),
        "technical_momentum": calculate_technical_momentum(df),
        "financial_strength": calculate_financial_strength(fundamentals),
        "valuation": calculate_valuation(fundamentals, current_price, industry_key),
        "trend_strength": calculate_trend_strength(df)
    }
