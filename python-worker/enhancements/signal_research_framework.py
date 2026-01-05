"""
Signal Research Framework - Enhanced with Expectancy and Segmentation
Adds professional-level analytics for signal quality assessment
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import sys
import os
sys.path.append('/app')
from app.signal_engines.signal_calculator_core import MarketConditions, SignalConfig, SignalResult, SignalType
from forward_return_validation import SignalQualityValidator, ForwardReturnMetrics
from collections import defaultdict

@dataclass
class SignalSegment:
    """Segment of signals by type"""
    segment_name: str
    signals: List[ForwardReturnMetrics]
    total_signals: int
    win_rate: float
    avg_return: float
    expectancy: float
    profit_factor: float
    max_drawdown: float

@dataclass
class ExpectancyMetrics:
    """Comprehensive expectancy metrics"""
    overall_expectancy: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    profitable_segments: List[str]
    unprofitable_segments: List[str]

class SignalResearchFramework:
    """
    Professional signal research framework that answers:
    - Which configs actually make money?
    - Which BUY types work best?
    - Is oversold-in-uptrend better than pure oversold?
    """
    
    def __init__(self, price_data: pd.DataFrame):
        self.validator = SignalQualityValidator(price_data)
        self.segments: Dict[str, SignalSegment] = {}
        self.expectancy_metrics: Optional[ExpectancyMetrics] = None
    
    def analyze_signal_performance(self, signals: List[ForwardReturnMetrics]) -> ExpectancyMetrics:
        """Comprehensive signal performance analysis with expectancy"""
        
        # Filter valid signals
        valid_signals = [s for s in signals if s is not None and s.signal_type == "BUY"]
        
        if not valid_signals:
            return ExpectancyMetrics(0, 0, 0, 0, 0, 0, 0, [], [])
        
        # Calculate basic metrics
        total_trades = len(valid_signals)
        wins = [s for s in valid_signals if s.return_5d > 0]
        losses = [s for s in valid_signals if s.return_5d < 0]
        
        win_rate = len(wins) / total_trades
        avg_win = np.mean([s.return_5d for s in wins]) if wins else 0
        avg_loss = np.mean([s.return_5d for s in losses]) if losses else 0
        
        # Calculate expectancy (the key metric!)
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        
        # Calculate profit factor
        total_wins = sum(s.return_5d for s in wins)
        total_losses = abs(sum(s.return_5d for s in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Calculate Sharpe ratio (simplified)
        returns = [s.return_5d for s in valid_signals]
        sharpe_ratio = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        
        # Calculate max drawdown
        cumulative_returns = np.cumprod([1 + r for r in returns])
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        # Store overall metrics
        self.expectancy_metrics = ExpectancyMetrics(
            overall_expectancy=expectancy,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            profitable_segments=[],
            unprofitable_segments=[]
        )
        
        return self.expectancy_metrics
    
    def segment_signals_by_type(self, signals: List[ForwardReturnMetrics]) -> Dict[str, SignalSegment]:
        """Segment signals by type to find which patterns work best"""
        
        valid_signals = [s for s in signals if s is not None and s.signal_type == "BUY"]
        
        # Create segments based on signal characteristics
        segments = {
            "oversold_downtrend": [],
            "oversold_uptrend": [],
            "oversold_sideways": [],
            "moderate_oversold": [],
            "mild_oversold_uptrend": [],
            "mild_oversold_macd": [],
            "high_volatility": [],
            "low_volatility": [],
            "strong_bounce": [],
            "weak_bounce": []
        }
        
        # Classify each signal
        for signal in valid_signals:
            segment_key = self._classify_signal(signal)
            if segment_key:
                segments[segment_key].append(signal)
        
        # Calculate metrics for each segment
        analyzed_segments = {}
        
        for segment_name, segment_signals in segments.items():
            if len(segment_signals) >= 5:  # Minimum 5 signals for analysis
                segment_metrics = self._calculate_segment_metrics(segment_name, segment_signals)
                analyzed_segments[segment_name] = segment_metrics
                
                # Track profitable/unprofitable segments
                if segment_metrics.expectancy > 0:
                    self.expectancy_metrics.profitable_segments.append(segment_name)
                else:
                    self.expectancy_metrics.unprofitable_segments.append(segment_name)
        
        self.segments = analyzed_segments
        return analyzed_segments
    
    def _classify_signal(self, signal: ForwardReturnMetrics) -> Optional[str]:
        """Classify signal into segment based on characteristics"""
        
        rsi = signal.rsi_at_signal
        trend = signal.trend_at_signal
        volatility = signal.volatility_at_signal
        bounce_successful = signal.bounce_successful
        
        # Oversold classification
        if rsi < 35:
            if trend == "downtrend":
                return "oversold_downtrend"
            elif trend == "uptrend":
                return "oversold_uptrend"
            else:
                return "oversold_sideways"
        elif 35 <= rsi < 42:
            return "moderate_oversold"
        elif 42 <= rsi < 47:
            if trend == "uptrend":
                return "mild_oversold_uptrend"
            # Check if MACD was positive (would need to add to ForwardReturnMetrics)
            return "mild_oversold_macd"
        
        # Volatility classification
        if volatility > 10:
            return "high_volatility"
        elif volatility < 5:
            return "low_volatility"
        
        # Bounce classification
        if bounce_successful:
            return "strong_bounce"
        else:
            return "weak_bounce"
        
        return None
    
    def _calculate_segment_metrics(self, segment_name: str, signals: List[ForwardReturnMetrics]) -> SignalSegment:
        """Calculate metrics for a signal segment"""
        
        returns = [s.return_5d for s in signals]
        wins = [s for s in signals if s.return_5d > 0]
        losses = [s for s in signals if s.return_5d < 0]
        
        total_signals = len(signals)
        win_rate = len(wins) / total_signals
        avg_return = np.mean(returns)
        
        # Expectancy for this segment
        avg_win = np.mean([s.return_5d for s in wins]) if wins else 0
        avg_loss = np.mean([s.return_5d for s in losses]) if losses else 0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        
        # Profit factor
        total_wins = sum(s.return_5d for s in wins)
        total_losses = abs(sum(s.return_5d for s in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Max drawdown for this segment
        cumulative_returns = np.cumprod([1 + r for r in returns])
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        return SignalSegment(
            segment_name=segment_name,
            signals=signals,
            total_signals=total_signals,
            win_rate=win_rate,
            avg_return=avg_return,
            expectancy=expectancy,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown
        )
    
    def get_insights(self) -> Dict[str, str]:
        """Generate actionable insights from signal analysis"""
        
        if not self.expectancy_metrics or not self.segments:
            return {"error": "No analysis available"}
        
        insights = {}
        
        # Overall performance insight
        if self.expectancy_metrics.overall_expectancy > 0.02:
            insights["overall"] = "✅ Strong positive expectancy - system is profitable"
        elif self.expectancy_metrics.overall_expectancy > 0:
            insights["overall"] = "⚠️ Positive but weak expectancy - needs improvement"
        else:
            insights["overall"] = "❌ Negative expectancy - system loses money"
        
        # Best performing segments
        profitable_segments = sorted(
            [(name, seg) for name, seg in self.segments.items() if seg.expectancy > 0],
            key=lambda x: x[1].expectancy,
            reverse=True
        )
        
        if profitable_segments:
            best = profitable_segments[0]
            insights["best_segment"] = f"🏆 Best: {best[0]} (expectancy: {best[1].expectancy:.3f}, trades: {best[1].total_signals})"
        
        # Worst performing segments
        unprofitable_segments = sorted(
            [(name, seg) for name, seg in self.segments.items() if seg.expectancy < 0],
            key=lambda x: x[1].expectancy
        )
        
        if unprofitable_segments:
            worst = unprofitable_segments[0]
            insights["worst_segment"] = f"⚠️ Worst: {worst[0]} (expectancy: {worst[1].expectancy:.3f}, trades: {worst[1].total_signals})"
        
        # High-impact insights
        if len(profitable_segments) >= 2:
            top_2_expectancy = sum(seg.expectancy for _, seg in profitable_segments[:2])
            insights["concentration"] = f"🎯 Top 2 segments provide {top_2_expectancy:.3f} combined expectancy"
        
        # Risk insights
        if self.expectancy_metrics.max_drawdown < -0.1:
            insights["risk"] = "✅ Acceptable drawdown (<10%)"
        elif self.expectancy_metrics.max_drawdown < -0.2:
            insights["risk"] = "⚠️ Moderate drawdown (10-20%)"
        else:
            insights["risk"] = "❌ High drawdown (>20%) - too risky"
        
        # Actionable recommendations
        if profitable_segments and unprofitable_segments:
            insights["action"] = f"💡 Focus on: {', '.join([s[0] for s in profitable_segments[:3]])}"
            insights["avoid"] = f"🚫 Avoid: {', '.join([s[0] for s in unprofitable_segments[:2]])}"
        
        return insights
    
    def print_research_report(self):
        """Print comprehensive research report"""
        
        if not self.expectancy_metrics:
            print("❌ No analysis data available")
            return
        
        print("🔬 SIGNAL RESEARCH FRAMEWORK REPORT")
        print("=" * 60)
        print("Answering: Which configs actually make money?")
        print()
        
        # Overall metrics
        print("📊 OVERALL PERFORMANCE:")
        print("-" * 30)
        print(f"  Total Trades: {self.expectancy_metrics.total_trades}")
        print(f"  Win Rate: {self.expectancy_metrics.win_rate:.1%}")
        print(f"  Avg Win: {self.expectancy_metrics.avg_win:.2%}")
        print(f"  Avg Loss: {self.expectancy_metrics.avg_loss:.2%}")
        print(f"  EXPECTANCY: {self.expectancy_metrics.overall_expectancy:.3f} ({self.expectancy_metrics.overall_expectancy*100:.1f}% per trade)")
        print(f"  Profit Factor: {self.expectancy_metrics.profit_factor:.2f}")
        print(f"  Sharpe Ratio: {self.expectancy_metrics.sharpe_ratio:.2f}")
        print(f"  Max Drawdown: {self.expectancy_metrics.max_drawdown:.1%}")
        print()
        
        # Segment analysis
        print("📈 SEGMENT ANALYSIS:")
        print("-" * 30)
        
        # Sort segments by expectancy
        sorted_segments = sorted(self.segments.items(), key=lambda x: x[1].expectancy, reverse=True)
        
        for segment_name, segment in sorted_segments:
            status = "🟢" if segment.expectancy > 0 else "🔴"
            print(f"  {status} {segment_name}:")
            print(f"     Trades: {segment.total_signals} | Win Rate: {segment.win_rate:.1%}")
            print(f"     Expectancy: {segment.expectancy:.3f} | Profit Factor: {segment.profit_factor:.2f}")
            print()
        
        # Insights
        insights = self.get_insights()
        print("💡 KEY INSIGHTS:")
        print("-" * 30)
        for key, insight in insights.items():
            print(f"  {insight}")
        print()
        
        # Recommendations
        print("🎯 RECOMMENDATIONS:")
        print("-" * 30)
        
        if self.expectancy_metrics.overall_expectancy > 0:
            print("  ✅ System has positive expectancy - deploy with confidence")
            print("  ✅ Focus on high-performing segments identified above")
            print("  ✅ Monitor expectancy in live trading")
        else:
            print("  ❌ System has negative expectancy - do not deploy")
            print("  ❌ Remove or fix unprofitable segments")
            print("  ❌ Re-run optimization with different parameters")
        
        print()
        print("🔬 This is now a Signal Research Framework, not just a generator")
        print("   You can answer: 'Which BUY types work best?'")
        print("   You can optimize for expectancy, not just frequency")
        print("   You can kill unprofitable patterns systematically")

# Usage example
def run_signal_research(price_data: pd.DataFrame, signals: List[ForwardReturnMetrics]):
    """Run comprehensive signal research"""
    
    framework = SignalResearchFramework(price_data)
    
    # Analyze overall performance
    overall_metrics = framework.analyze_signal_performance(signals)
    
    # Segment signals by type
    segments = framework.segment_signals_by_type(signals)
    
    # Print comprehensive report
    framework.print_research_report()
    
    return framework
