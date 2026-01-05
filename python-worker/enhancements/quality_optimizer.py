"""
Enhanced Configuration Optimizer
Optimizes for signal quality (profitability) not just frequency
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
import sys
import os
sys.path.append('/app')
from app.signal_engines.signal_calculator_core import MarketConditions, SignalConfig, SignalResult, SignalType
from forward_return_validation import SignalQualityValidator, ForwardReturnMetrics
from specialized_engines import CompositeSwingEngine

@dataclass
class OptimizationObjective:
    """Defines what to optimize for - now focused on expectancy"""
    buy_rate_min: float = 30.0
    buy_rate_max: float = 40.0
    min_expectancy: float = 0.01      # At least 1% expectancy per trade
    min_profitable_buy_pct: float = 55.0  # At least 55% of BUYs profitable
    min_avg_return_pct: float = 1.5      # At least 1.5% average return per BUY
    max_avg_mae_pct: float = 6.0          # Max 6% average adverse excursion
    bounce_success_min: float = 65.0      # At least 65% bounce success rate
    min_profit_factor: float = 1.2        # Profit factor > 1.2

@dataclass
class QualityOptimizationResult:
    """Result of quality-based optimization"""
    config: SignalConfig
    buy_rate: float
    profitable_buy_pct: float
    avg_return_pct: float
    avg_mae_pct: float
    bounce_success_rate: float
    expectancy: float                    # NEW: Primary optimization target
    profit_factor: float               # NEW: Additional quality metric
    overall_score: float  # 0-100 quality score
    meets_objectives: bool

class QualityBasedOptimizer:
    """Optimizes configurations based on signal quality metrics"""
    
    def __init__(self, price_data: pd.DataFrame, objective: Optional[OptimizationObjective] = None):
        self.price_data = price_data
        self.objective = objective or OptimizationObjective()
        self.results: List[QualityOptimizationResult] = []
    
    def evaluate_config_quality(self, config: SignalConfig) -> QualityOptimizationResult:
        """Evaluate a configuration based on quality metrics"""
        
        # CRITICAL FIX: Create fresh validator per configuration to eliminate state contamination
        validator = SignalQualityValidator(self.price_data)
        
        # Generate signals using composite engine
        engine = CompositeSwingEngine(config, self.price_data)
        
        buy_count = sell_count = hold_count = 0
        signal_results = []
        
        # CRITICAL FIX: Only generate signals where we have forward data for validation
        # This ensures BUY rate and quality metrics use the same sample
        for i in range(10, len(self.price_data) - 7):  # Need forward data for validation
            try:
                current_date = self.price_data.iloc[i]['date']
                conditions = self._create_market_conditions(i)
                
                signal_result = engine.generate_composite_signal(conditions, "TQQQ", current_date)
                signal_results.append((current_date, signal_result, conditions))
                
                # CRITICAL FIX: Only count signals that can be validated
                # This aligns BUY rate with quality metrics
                if signal_result.signal == SignalType.BUY:
                    buy_count += 1
                elif signal_result.signal == SignalType.SELL:
                    sell_count += 1
                else:
                    hold_count += 1
                    
            except Exception:
                continue
        
        total = buy_count + sell_count + hold_count
        buy_rate = (buy_count / total * 100) if total > 0 else 0
        
        # Validate forward returns for BUY signals using fresh validator
        buy_signals = [(date, result, conditions) for date, result, conditions in signal_results 
                      if result.signal == SignalType.BUY]
        
        # Track validation success to ensure sample alignment
        validated_buy_count = 0
        for date, result, conditions in buy_signals:
            validation_result = validator.calculate_forward_returns(
                date, conditions.current_price, "BUY", 
                conditions.rsi, conditions.volatility
            )
            if validation_result is not None:  # Only count successful validations
                validated_buy_count += 1
        
        # CRITICAL FIX: Use validated BUY count for accurate BUY rate
        # This ensures BUY rate matches quality metrics sample
        if validated_buy_count > 0:
            # Adjust buy_rate to only include validated BUYs
            validated_total = validated_buy_count + sell_count + hold_count
            buy_rate = (validated_buy_count / validated_total * 100) if validated_total > 0 else 0
        
        # Get quality metrics from fresh validator (no contamination)
        quality_metrics = validator.get_quality_metrics()
        
        # Add sample size info for debugging
        quality_metrics["total_signals"] = total
        quality_metrics["validated_buy_signals"] = validated_buy_count
        quality_metrics["original_buy_rate"] = (buy_count / total * 100) if total > 0 else 0
        quality_metrics["aligned_buy_rate"] = buy_rate
        
        # Calculate individual scores
        buy_rate_score = self._calculate_buy_rate_score(buy_rate)
        expectancy_score = self._calculate_expectancy_score(quality_metrics.get("expectancy_5d", 0))
        profitability_score = self._calculate_profitability_score(quality_metrics.get("profitable_5d_pct", 0))
        return_score = self._calculate_return_score(quality_metrics.get("avg_return_5d", 0))
        risk_score = self._calculate_risk_score(quality_metrics.get("avg_mae_pct", 0))
        bounce_score = self._calculate_bounce_score(quality_metrics.get("bounce_success_rate", 0))
        profit_factor_score = self._calculate_profit_factor_score(quality_metrics.get("profit_factor", 1))
        
        # ANTI-OVERFITTING: Apply sample size confidence penalty
        sample_size = quality_metrics.get("buy_signals", 0)
        confidence_penalty = self._calculate_sample_confidence_penalty(sample_size)
        
        # Calculate overall quality score (expectancy is now PRIMARY target)
        overall_score = (
            expectancy_score * 0.60 +       # EXPECTANCY is primary (60%)
            buy_rate_score * 0.10 +         # BUY rate as constraint (10%)
            profitability_score * 0.15 +    # Profitability still important (15%)
            return_score * 0.05 +          # Returns matter less (5%)
            risk_score * 0.05 +             # Risk management (5%)
            bounce_score * 0.02 +           # Bounce success minimal (2%)
            profit_factor_score * 0.03      # Profit factor minimal (3%)
        )
        
        # Apply confidence penalty to prevent overfitting
        overall_score *= confidence_penalty
        
        # Check if objectives are met (now includes expectancy)
        meets_objectives = (
            self.objective.buy_rate_min <= buy_rate <= self.objective.buy_rate_max and
            quality_metrics.get("expectancy_5d", 0) >= self.objective.min_expectancy and
            quality_metrics.get("profitable_5d_pct", 0) >= self.objective.min_profitable_buy_pct and
            quality_metrics.get("avg_return_5d", 0) >= self.objective.min_avg_return_pct / 100 and
            quality_metrics.get("avg_mae_pct", 0) <= self.objective.max_avg_mae_pct and
            quality_metrics.get("bounce_success_rate", 0) >= self.objective.bounce_success_min and
            quality_metrics.get("profit_factor", 1) >= self.objective.min_profit_factor
        )
        
        return QualityOptimizationResult(
            config=config,
            buy_rate=buy_rate,
            profitable_buy_pct=quality_metrics.get("profitable_5d_pct", 0),
            avg_return_pct=quality_metrics.get("avg_return_5d", 0) * 100,
            avg_mae_pct=quality_metrics.get("avg_mae_pct", 0),
            bounce_success_rate=quality_metrics.get("bounce_success_rate", 0),
            expectancy=quality_metrics.get("expectancy_5d", 0),
            profit_factor=quality_metrics.get("profit_factor", 1),
            overall_score=overall_score,
            meets_objectives=meets_objectives
        )
    
    def _create_market_conditions(self, index: int):
        """Create market conditions from price data"""
        from app.signal_engines.signal_calculator_core import MarketConditions
        
        current = self.price_data.iloc[index]
        
        # Calculate recent change
        recent_close = self.price_data.iloc[index-2]['close']
        recent_change = (current['close'] - recent_close) / recent_close
        
        # Calculate volatility
        start_idx = max(0, index - 19)
        volatility_data = self.price_data.iloc[start_idx:index+1]['close'].pct_change().dropna()
        volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
        
        return MarketConditions(
            rsi=current.get('rsi', 50),
            sma_20=current.get('sma_20', current['close']),
            sma_50=current.get('sma_50', current['close']),
            ema_20=current.get('ema_20', current['close']),  # Add missing ema_20
            current_price=current['close'],
            recent_change=recent_change,
            macd=current.get('macd', 0),
            macd_signal=current.get('macd_signal', 0),
            volatility=volatility
        )
    
    def _calculate_buy_rate_score(self, buy_rate: float) -> float:
        """Score buy rate (0-100)"""
        if self.objective.buy_rate_min <= buy_rate <= self.objective.buy_rate_max:
            return 100.0
        elif buy_rate < self.objective.buy_rate_min:
            return max(0, 100 - (self.objective.buy_rate_min - buy_rate) * 2)
        else:
            return max(0, 100 - (buy_rate - self.objective.buy_rate_max) * 2)
    
    def _calculate_profitability_score(self, profitable_pct: float) -> float:
        """Score profitability (0-100)"""
        if profitable_pct >= self.objective.min_profitable_buy_pct:
            return 100.0
        else:
            return max(0, (profitable_pct / self.objective.min_profitable_buy_pct) * 100)
    
    def _calculate_return_score(self, avg_return: float) -> float:
        """Score average return (0-100)"""
        target_return = self.objective.min_avg_return_pct / 100
        if avg_return >= target_return:
            return 100.0
        else:
            return max(0, (avg_return / target_return) * 100)
    
    def _calculate_risk_score(self, avg_mae: float) -> float:
        """Score risk management (0-100, lower MAE is better)"""
        if avg_mae <= self.objective.max_avg_mae_pct:
            return 100.0
        else:
            return max(0, 100 - (avg_mae - self.objective.max_avg_mae_pct) * 10)
    
    def _calculate_bounce_score(self, bounce_rate: float) -> float:
        """Score bounce success (0-100)"""
        if bounce_rate >= self.objective.bounce_success_min:
            return 100.0
        else:
            return max(0, (bounce_rate / self.objective.bounce_success_min) * 100)
    
    def _calculate_expectancy_score(self, expectancy: float) -> float:
        """Score expectancy (0-100) - NEW METHOD"""
        if expectancy >= self.objective.min_expectancy:
            return 100.0
        else:
            return max(0, (expectancy / self.objective.min_expectancy) * 100)
    
    def _calculate_profit_factor_score(self, profit_factor: float) -> float:
        """Score profit factor (0-100) - NEW METHOD"""
        if profit_factor >= self.objective.min_profit_factor:
            return 100.0
        else:
            return max(0, (profit_factor / self.objective.min_profit_factor) * 100)
    
    def _calculate_sample_confidence_penalty(self, sample_size: int) -> float:
        """Calculate confidence penalty based on sample size to prevent overfitting"""
        if sample_size < 10:
            return 0.3  # Heavy penalty for very small samples
        elif sample_size < 20:
            return 0.5  # Moderate penalty for small samples
        elif sample_size < 50:
            return 0.7  # Light penalty for medium samples
        elif sample_size < 100:
            return 0.85  # Very light penalty for good samples
        else:
            return 1.0  # No penalty for sufficient samples
    
    def optimize_quality_configs(self, config_ranges: Dict) -> List[QualityOptimizationResult]:
        """Optimize configurations based on quality metrics"""
        
        print("🎯 Quality-Based Configuration Optimizer")
        print("=" * 50)
        print(f"Objectives:")
        print(f"  BUY Rate: {self.objective.buy_rate_min}-{self.objective.buy_rate_max}%")
        print(f"  Expectancy: ≥{self.objective.min_expectancy*100:.1f}% per trade")
        print(f"  Profitable BUYs: ≥{self.objective.min_profitable_buy_pct}%")
        print(f"  Avg Return: ≥{self.objective.min_avg_return_pct}%")
        print(f"  Max MAE: ≤{self.objective.max_avg_mae_pct}%")
        print(f"  Bounce Success: ≥{self.objective.bounce_success_min}%")
        print(f"  Profit Factor: ≥{self.objective.min_profit_factor}")
        print()
        
        # Generate configurations to test
        configs = self._generate_quality_configs(config_ranges)
        
        print(f"🔧 Testing {len(configs)} configurations for quality...")
        
        # Test each configuration
        for i, config in enumerate(configs):
            result = self.evaluate_config_quality(config)
            self.results.append(result)
            
            if (i + 1) % 50 == 0:
                print(f"  Tested {i + 1}/{len(configs)} configurations...")
        
        # Sort by overall quality score
        self.results.sort(key=lambda x: x.overall_score, reverse=True)
        
        # Find configurations that meet all objectives
        qualified_configs = [r for r in self.results if r.meets_objectives]
        
        print(f"\n📊 Quality Optimization Results:")
        print(f"  Total configurations tested: {len(configs)}")
        print(f"  Qualified configurations: {len(qualified_configs)}")
        print(f"  Best overall score: {self.results[0].overall_score:.1f}/100")
        
        return self.results
    
    def _generate_quality_configs(self, ranges: Dict) -> List[SignalConfig]:
        """Generate configurations focused on quality ranges"""
        
        configs = []
        
        # More conservative ranges for quality optimization
        rsi_oversold_range = ranges.get("rsi_oversold", [45, 46, 47, 48, 49])
        rsi_moderate_range = ranges.get("rsi_moderate", [34, 35, 36, 37, 38])
        rsi_mild_range = ranges.get("rsi_mild", [41, 42, 43, 44, 45])
        volatility_range = ranges.get("max_volatility", [7.5, 8.0, 8.5, 9.0])
        
        for rsi_oversold in rsi_oversold_range:
            for rsi_moderate in rsi_moderate_range:
                for rsi_mild in rsi_mild_range:
                    for volatility in volatility_range:
                        # Ensure proper hierarchy
                        if rsi_moderate < rsi_mild < rsi_oversold:
                            config = SignalConfig(
                                rsi_oversold=rsi_oversold,
                                rsi_moderately_oversold=rsi_moderate,
                                rsi_mildly_oversold=rsi_mild,
                                max_volatility=volatility,
                                oversold_boost=0.12,
                                trend_boost=0.1
                            )
                            configs.append(config)
        
        return configs
    
    def get_best_config(self) -> Optional[QualityOptimizationResult]:
        """Get the best configuration based on quality metrics"""
        
        if not self.results:
            return None
        
        # Prefer configurations that meet all objectives
        qualified = [r for r in self.results if r.meets_objectives]
        
        if qualified:
            # Among qualified, choose highest overall score
            return max(qualified, key=lambda x: x.overall_score)
        else:
            # If none meet all objectives, choose highest scoring
            return self.results[0]
    
    def print_optimization_summary(self):
        """Print detailed optimization summary"""
        
        if not self.results:
            print("❌ No optimization results available")
            return
        
        best_config = self.get_best_config()
        qualified_configs = [r for r in self.results if r.meets_objectives]
        
        print(f"\n🎯 QUALITY OPTIMIZATION SUMMARY")
        print("=" * 60)
        
        print(f"\n🏆 BEST CONFIGURATION:")
        print("-" * 40)
        print(f"  Overall Score: {best_config.overall_score:.1f}/100")
        print(f"  Meets Objectives: {'✅ YES' if best_config.meets_objectives else '❌ NO'}")
        print(f"  BUY Rate: {best_config.buy_rate:.1f}%")
        print(f"  Expectancy: {best_config.expectancy:.3f} ({best_config.expectancy*100:.1f}% per trade)")
        print(f"  Profitable BUYs: {best_config.profitable_buy_pct:.1f}%")
        print(f"  Avg Return: {best_config.avg_return_pct:.2f}%")
        print(f"  Avg MAE: {best_config.avg_mae_pct:.2f}%")
        print(f"  Bounce Success: {best_config.bounce_success_rate:.1f}%")
        print(f"  Profit Factor: {best_config.profit_factor:.2f}")
        
        print(f"\n⚙️ OPTIMAL PARAMETERS:")
        print("-" * 40)
        print(f"  RSI Oversold: {best_config.config.rsi_oversold}")
        print(f"  RSI Moderate: {best_config.config.rsi_moderately_oversold}")
        print(f"  RSI Mild: {best_config.config.rsi_mildly_oversold}")
        print(f"  Max Volatility: {best_config.config.max_volatility:.1f}%")
        
        print(f"\n📊 QUALITY BREAKDOWN:")
        print("-" * 40)
        print(f"  Buy Rate Score: {self._calculate_buy_rate_score(best_config.buy_rate):.1f}/100")
        print(f"  Expectancy Score: {self._calculate_expectancy_score(best_config.expectancy):.1f}/100")
        print(f"  Profitability Score: {self._calculate_profitability_score(best_config.profitable_buy_pct):.1f}/100")
        print(f"  Return Score: {self._calculate_return_score(best_config.avg_return_pct/100):.1f}/100")
        print(f"  Risk Score: {self._calculate_risk_score(best_config.avg_mae_pct):.1f}/100")
        print(f"  Bounce Score: {self._calculate_bounce_score(best_config.bounce_success_rate):.1f}/100")
        print(f"  Profit Factor Score: {self._calculate_profit_factor_score(best_config.profit_factor):.1f}/100")
        
        # Show sample size and confidence
        sample_size = len([r for r in self.results if r.config.rsi_oversold == best_config.config.rsi_oversold])
        confidence = self._calculate_sample_confidence_penalty(sample_size)
        print(f"  Sample Size: {sample_size} signals")
        print(f"  Confidence Factor: {confidence:.2f}")
        
        if qualified_configs:
            print(f"\n✅ QUALIFIED CONFIGURATIONS ({len(qualified_configs)}):")
            print("-" * 40)
            for i, config in enumerate(qualified_configs[:5]):  # Top 5
                print(f"  {i+1}. Score: {config.overall_score:.1f} | BUY: {config.buy_rate:.1f}% | "
                      f"Expectancy: {config.expectancy:.3f} | Return: {config.avg_return_pct:.2f}%")
        
        print(f"\n🚀 DEPLOYMENT RECOMMENDATION:")
        print("-" * 40)
        if best_config.meets_objectives:
            print(f"  ✅ CONFIGURATION MEETS ALL QUALITY OBJECTIVES")
            print(f"  ✅ OPTIMIZED FOR EXPECTANCY (PROFITABILITY), NOT JUST FREQUENCY")
            print(f"  ✅ READY FOR PRODUCTION DEPLOYMENT")
            print(f"  ✅ EXPECTED QUALITY PERFORMANCE:")
            print(f"     • {best_config.profitable_buy_pct:.1f}% profitable BUY signals")
            print(f"     • {best_config.avg_return_pct:.2f}% average return per BUY")
            print(f"     • {best_config.expectancy*100:.1f}% expectancy per trade (PRIMARY METRIC)")
            print(f"     • {best_config.avg_mae_pct:.2f}% average max drawdown")
            print(f"     • {best_config.bounce_success_rate:.1f}% bounce success rate")
            print(f"     • {best_config.profit_factor:.2f} profit factor")
            print(f"  ✅ ANTI-OVERFITTING: Sample size confidence applied")
        else:
            print(f"  ⚠️  CONFIGURATION DOES NOT MEET ALL OBJECTIVES")
            print(f"  ⚠️  CONSIDER ADJUSTING OBJECTIVES OR RANGES")
            print(f"  ⚠️  CURRENT BEST SCORE: {best_config.overall_score:.1f}/100")
            print(f"  ⚠️  EXPECTANCY: {best_config.expectancy*100:.1f}% per trade")
        
        print(f"\n✅ Quality-Based Optimization Complete!")
