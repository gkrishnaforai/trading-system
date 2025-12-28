"""
Investment recommendation system combining technical, financial, valuation, and trend analysis.
Provides portfolio advice and optional LLM sentiment analysis.
"""

import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime
import math

def calculate_overall_signal(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate overall buy/sell/hold signal based on four analysis sections."""
    tech = analysis["technical_momentum"]
    fin = analysis["financial_strength"]
    val = analysis["valuation"]
    trend = analysis["trend_strength"]
    
    # Convert scores to numeric
    scores = {
        "technical": tech.get("score", 0),
        "financial": fin.get("score", 0),
        "valuation": 10 - val.get("score", 5),  # Invert: low valuation = good
        "trend": trend.get("score", 0)
    }
    
    # Weight factors (adjustable based on strategy)
    weights = {
        "technical": 0.25,
        "financial": 0.20,
        "valuation": 0.30,  # Valuation is most important
        "trend": 0.25
    }
    
    # Calculate weighted score
    weighted_score = sum(scores[k] * weights[k] for k in scores)
    
    # Determine signal
    if weighted_score >= 7.5:
        signal = "Strong Buy"
        confidence = "High"
    elif weighted_score >= 6.0:
        signal = "Buy"
        confidence = "Medium"
    elif weighted_score >= 4.0:
        signal = "Hold"
        confidence = "Medium"
    elif weighted_score >= 2.5:
        signal = "Sell"
        confidence = "Medium"
    else:
        signal = "Strong Sell"
        confidence = "High"
    
    # Build rationale
    strengths = []
    weaknesses = []
    
    if scores["technical"] >= 7:
        strengths.append("Strong technical momentum")
    elif scores["technical"] <= 3:
        weaknesses.append("Weak technical momentum")
    
    if scores["financial"] >= 7:
        strengths.append("Solid financial foundation")
    elif scores["financial"] <= 3:
        weaknesses.append("Financial concerns")
    
    if scores["valuation"] >= 7:  # Remember: high score = undervalued
        strengths.append("Attractive valuation")
    elif scores["valuation"] <= 3:
        weaknesses.append("Expensive valuation")
    
    if scores["trend"] >= 7:
        strengths.append("Positive trend")
    elif scores["trend"] <= 3:
        weaknesses.append("Negative trend")
    
    rationale = []
    if strengths:
        rationale.append("Strengths: " + "; ".join(strengths))
    if weaknesses:
        rationale.append("Concerns: " + "; ".join(weaknesses))
    
    return {
        "signal": signal,
        "confidence": confidence,
        "weighted_score": round(weighted_score, 1),
        "component_scores": scores,
        "rationale": ". ".join(rationale) + "."
    }

def generate_portfolio_advice(analysis: Dict[str, Any], recommendation: Dict[str, Any]) -> Dict[str, Any]:
    """Generate portfolio management advice."""
    signal = recommendation["signal"]
    current_price = analysis.get("current_price", 0)
    
    advice = {
        "action": "",
        "position_sizing": "",
        "profit_strategy": "",
        "risk_management": ""
    }
    
    if "Strong Buy" in signal or "Buy" in signal:
        advice["action"] = "Consider initiating or adding to position"
        advice["position_sizing"] = "Allocate 2-5% of portfolio per position"
        advice["profit_strategy"] = "Set target 20-30% above entry; trail stop at 10% below highs"
        advice["risk_management"] = "Stop loss at 8-12% below entry"
    
    elif "Hold" in signal:
        advice["action"] = "Maintain current position"
        advice["position_sizing"] = "No new capital recommended"
        advice["profit_strategy"] = "Take partial profits at 15% if overvalued"
        advice["risk_management"] = "Raise stop loss to breakeven after 10% gain"
    
    elif "Sell" in signal or "Strong Sell" in signal:
        advice["action"] = "Consider reducing or exiting position"
        advice["position_sizing"] = "Reduce exposure to <1% or exit completely"
        advice["profit_strategy"] = "Preserve capital; wait for better entry"
        advice["risk_management"] = "Stop loss at 5% or exit on next bounce"
    
    # Industry-specific adjustments
    valuation_score = analysis["valuation"]["score"]
    if valuation_score <= 3:  # Expensive
        advice["profit_strategy"] += ". Consider taking profits on overvaluation."
    elif valuation_score >= 7:  # Undervalued
        advice["position_sizing"] += ". Attractive valuation supports larger position."
    
    return advice

def generate_investor_summary(analysis: Dict[str, Any], recommendation: Dict[str, Any], portfolio_advice: Dict[str, Any]) -> str:
    """Generate a comprehensive investor summary."""
    symbol = analysis.get("symbol", "")
    signal = recommendation["signal"]
    confidence = recommendation["confidence"]
    weighted_score = recommendation["weighted_score"]
    
    summary_parts = [
        f"Investment Recommendation for {symbol}: {signal} (confidence: {confidence}, score: {weighted_score}/10).",
        recommendation["rationale"]
    ]
    
    # Portfolio guidance
    action = portfolio_advice.get("action", "")
    if action:
        summary_parts.append(f"Portfolio Action: {action}")
    
    # Risk context
    tech_score = recommendation["component_scores"]["technical"]
    trend_score = recommendation["component_scores"]["trend"]
    
    if tech_score <= 3 or trend_score <= 3:
        summary_parts.append("⚠️ Caution: Technical or trend weakness suggests waiting for better entry.")
    
    if recommendation["component_scores"]["financial"] <= 3:
        summary_parts.append("⚠️ Financial health concerns increase risk; consider smaller position size.")
    
    # Opportunity context
    if recommendation["component_scores"]["valuation"] >= 7:
        summary_parts.append("💡 Opportunity: Attractive valuation provides margin of safety.")
    
    return ". ".join(summary_parts)

def analyze_llm_sentiment(news_articles: List[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    """Placeholder for LLM sentiment analysis (can be integrated with OpenAI/Anthropic)."""
    if not news_articles:
        return {"sentiment": "Neutral", "confidence": 0, "summary": "No news available for sentiment analysis"}
    
    # Simple keyword-based sentiment as fallback
    positive_words = ["growth", "beat", "strong", "up", "rise", "bullish", "buy", "upgrade"]
    negative_words = ["decline", "fall", "miss", "weak", "down", "bearish", "sell", "downgrade"]
    
    sentiment_score = 0
    count = 0
    
    for article in news_articles[:5]:  # Analyze latest 5 articles
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        text = f"{title} {summary}"
        
        for word in positive_words:
            sentiment_score += text.count(word)
        for word in negative_words:
            sentiment_score -= text.count(word)
        count += 1
    
    if sentiment_score > 2:
        sentiment = "Positive"
    elif sentiment_score < -2:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"
    
    confidence = min(abs(sentiment_score) / 5, 1.0)  # Normalize to 0-1
    
    return {
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "summary": f"News sentiment appears {sentiment.lower()} based on {count} articles",
        "disclaimer": "This is basic keyword analysis. Enable LLM for advanced sentiment."
    }

def generate_comprehensive_report(symbol: str, analysis: Dict[str, Any], news: List[Dict[str, Any]], use_llm: bool = False) -> Dict[str, Any]:
    """Generate comprehensive investment report with optional LLM sentiment."""
    recommendation = calculate_overall_signal(analysis)
    portfolio_advice = generate_portfolio_advice(analysis, recommendation)
    investor_summary = generate_investor_summary(analysis, recommendation, portfolio_advice)
    
    report = {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "recommendation": recommendation,
        "portfolio_advice": portfolio_advice,
        "investor_summary": investor_summary,
        "analysis_sections": {
            "technical_momentum": analysis["technical_momentum"],
            "financial_strength": analysis["financial_strength"],
            "valuation": analysis["valuation"],
            "trend_strength": analysis["trend_strength"]
        }
    }
    
    # Add sentiment analysis if requested
    if use_llm:
        # Placeholder for LLM integration
        sentiment = analyze_llm_sentiment(news, symbol)
        report["sentiment_analysis"] = sentiment
        report["investor_summary"] += f" Sentiment: {sentiment['summary']}"
    else:
        report["sentiment_analysis"] = {"enabled": False, "note": "Enable LLM toggle for sentiment analysis"}
    
    return report
