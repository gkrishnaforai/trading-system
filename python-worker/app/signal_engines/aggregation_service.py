"""
Signal Aggregation Service
Runs multiple engines and aggregates results with conflict detection
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from datetime import datetime
from dataclasses import dataclass

from .base import (
    BaseSignalEngine, SignalResult, SignalType, MarketContext, 
    SignalEngineError
)
from .factory import SignalEngineFactory
from app.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AggregatedSignalResult:
    """Result from running multiple engines"""
    symbol: str
    consensus_signal: SignalType
    consensus_confidence: float
    recommended_engine: str
    engine_results: Dict[str, SignalResult]
    conflicts: List[str]
    reasoning: List[str]
    generated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'symbol': self.symbol,
            'consensus_signal': self.consensus_signal.value,
            'consensus_confidence': self.consensus_confidence,
            'recommended_engine': self.recommended_engine,
            'engine_results': {name: result.to_dict() for name, result in self.engine_results.items()},
            'conflicts': self.conflicts,
            'reasoning': self.reasoning,
            'generated_at': self.generated_at.isoformat()
        }


class SignalAggregationService:
    """Runs multiple engines and aggregates results"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    def generate_multi_engine_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context: MarketContext,
        engines: Optional[List[str]] = None
    ) -> AggregatedSignalResult:
        """
        Run all specified engines and aggregate
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data
            indicators: Technical indicators
            fundamentals: Fundamental data
            market_context: Market regime context
            engines: List of engine names to run (default: all available)
            
        Returns:
            AggregatedSignalResult with consensus and individual results
        """
        try:
            if engines is None:
                # Get all available engines
                available_engines = SignalEngineFactory.get_available_engines()
                engines = [engine['name'] for engine in available_engines]
            
            self.logger.info(f"Running signal engines for {symbol}: {engines}")
            
            # Run each engine
            engine_results = {}
            errors = []
            
            for engine_name in engines:
                try:
                    engine = SignalEngineFactory.get_engine(engine_name)
                    result = engine.generate_signal(
                        symbol, market_data, indicators, fundamentals, market_context
                    )
                    engine_results[engine_name] = result
                    self.logger.info(f"Engine {engine_name} generated {result.signal.value} signal for {symbol}")
                    
                except Exception as e:
                    error_msg = f"Engine {engine_name} failed: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(error_msg, extra={'symbol': symbol, 'engine': engine_name})
            
            if not engine_results:
                raise SignalEngineError(f"No engines produced results for {symbol}. Errors: {errors}")
            
            # Aggregate results
            consensus_signal, consensus_confidence = self._aggregate_signals(engine_results)
            conflicts = self._detect_conflicts(engine_results)
            recommended_engine = self._recommend_best_engine(engine_results, market_context)
            reasoning = self._generate_aggregated_reasoning(engine_results, market_context)
            
            return AggregatedSignalResult(
                symbol=symbol,
                consensus_signal=consensus_signal,
                consensus_confidence=consensus_confidence,
                recommended_engine=recommended_engine,
                engine_results=engine_results,
                conflicts=conflicts,
                reasoning=reasoning,
                generated_at=datetime.utcnow()
            )
            
        except Exception as e:
            if isinstance(e, SignalEngineError):
                raise
            raise SignalEngineError(f"Failed to generate multi-engine signal for {symbol}: {str(e)}")
    
    def _aggregate_signals(self, results: Dict[str, SignalResult]) -> tuple:
        """
        Aggregate signals from multiple engines using weighted voting
        
        Returns:
            Tuple of (consensus_signal, consensus_confidence)
        """
        if not results:
            return SignalType.HOLD, 0.0
        
        # Count signals
        signal_counts = {signal_type: 0 for signal_type in SignalType}
        total_confidence = 0.0
        total_weight = 0.0
        
        for engine_name, result in results.items():
            signal_counts[result.signal] += 1
            total_confidence += result.confidence
            total_weight += 1.0
        
        # Determine consensus by majority vote
        consensus_signal = max(signal_counts, key=signal_counts.get)
        
        # Calculate weighted average confidence
        consensus_confidence = total_confidence / total_weight if total_weight > 0 else 0.0
        
        # Boost confidence if there's strong agreement
        agreement_ratio = signal_counts[consensus_signal] / total_weight
        if agreement_ratio >= 0.75:  # 75%+ agreement
            consensus_confidence = min(1.0, consensus_confidence * 1.1)
        elif agreement_ratio <= 0.25:  # 25% or less agreement
            consensus_confidence = max(0.0, consensus_confidence * 0.8)
        
        return consensus_signal, consensus_confidence
    
    def _detect_conflicts(self, results: Dict[str, SignalResult]) -> List[str]:
        """
        Identify when engines disagree significantly
        
        Returns:
            List of conflict descriptions
        """
        conflicts = []
        
        if len(results) < 2:
            return conflicts
        
        # Check for signal disagreements
        signals = [result.signal for result in results.values()]
        unique_signals = set(signals)
        
        if len(unique_signals) > 1:
            # Group engines by signal
            signal_groups = {}
            for engine_name, result in results.items():
                signal = result.signal
                if signal not in signal_groups:
                    signal_groups[signal] = []
                signal_groups[signal].append(f"{engine_name} ({result.confidence:.2f})")
            
            # Create conflict descriptions
            for signal, engines in signal_groups.items():
                conflicts.append(f"{signal.value}: {', '.join(engines)}")
        
        # Check for confidence disagreements
        confidences = [result.confidence for result in results.values()]
        if max(confidences) - min(confidences) > 0.4:  # Large confidence gap
            high_conf = [name for name, result in results.items() if result.confidence > 0.7]
            low_conf = [name for name, result in results.items() if result.confidence < 0.4]
            conflicts.append(f"High confidence engines: {', '.join(high_conf)}")
            conflicts.append(f"Low confidence engines: {', '.join(low_conf)}")
        
        return conflicts
    
    def _recommend_best_engine(
        self, results: Dict[str, SignalResult], market_context: MarketContext
    ) -> str:
        """
        Suggest which engine to trust most based on regime and performance
        
        Returns:
            Name of recommended engine
        """
        if not results:
            return "none"
        
        # Engine preference by regime
        regime_preferences = {
            'BULL': ['adaptive_fundamental', 'position_regime', 'swing_regime', 'legacy'],
            'BEAR': ['adaptive_fundamental', 'position_regime', 'legacy', 'swing_regime'],
            'HIGH_VOL_CHOP': ['swing_regime', 'adaptive_fundamental', 'legacy'],
            'NO_TRADE': ['legacy']  # Conservative fallback
        }
        
        preferred_order = regime_preferences.get(market_context.regime.value, list(results.keys()))
        
        # Find the best available engine based on confidence and preference
        for engine_name in preferred_order:
            if engine_name in results:
                result = results[engine_name]
                # Only recommend if confidence is reasonable
                if result.confidence > 0.4:
                    return engine_name
        
        # Fallback to highest confidence engine
        best_engine = max(results.items(), key=lambda x: x[1].confidence)
        return best_engine[0]
    
    def _generate_aggregated_reasoning(
        self, results: Dict[str, SignalResult], market_context: MarketContext
    ) -> List[str]:
        """Generate aggregated reasoning from all engines"""
        reasoning = []
        
        # Add market context
        reasoning.append(f"Market regime: {market_context.regime.value}")
        
        # Add consensus information
        signals = [result.signal for result in results.values()]
        signal_counts = {signal_type: signals.count(signal_type) for signal_type in SignalType}
        consensus_signal = max(signal_counts, key=signal_counts.get)
        
        reasoning.append(f"Consensus: {consensus_signal.value} ({signal_counts[consensus_signal]}/{len(results)} engines)")
        
        # Add top reasons from highest confidence engine
        if results:
            best_engine = max(results.items(), key=lambda x: x[1].confidence)
            engine_name, best_result = best_engine
            reasoning.append(f"Primary reasoning from {engine_name}:")
            
            # Add top 3 reasons from best engine
            for reason in best_result.reasoning[:3]:
                reasoning.append(f"  • {reason}")
        
        # Add confidence summary
        confidences = [result.confidence for result in results.values()]
        avg_confidence = sum(confidences) / len(confidences)
        reasoning.append(f"Average confidence: {avg_confidence:.2f}")
        
        return reasoning
    
    def get_engine_comparison(self, symbol: str, results: Dict[str, SignalResult]) -> Dict[str, Any]:
        """
        Generate comparison of all engine results for analysis
        
        Returns:
            Dictionary with comparison metrics
        """
        if not results:
            return {}
        
        comparison = {
            'symbol': symbol,
            'engines_run': list(results.keys()),
            'signal_distribution': {},
            'confidence_stats': {},
            'position_sizes': {},
            'timeframes': {}
        }
        
        # Signal distribution
        signals = [result.signal.value for result in results.values()]
        for signal in set(signals):
            comparison['signal_distribution'][signal] = signals.count(signal)
        
        # Confidence statistics
        confidences = [result.confidence for result in results.values()]
        comparison['confidence_stats'] = {
            'average': sum(confidences) / len(confidences),
            'min': min(confidences),
            'max': max(confidences),
            'spread': max(confidences) - min(confidences)
        }
        
        # Position sizes by engine
        for engine_name, result in results.items():
            comparison['position_sizes'][engine_name] = result.position_size_pct
            comparison['timeframes'][engine_name] = result.timeframe
        
        return comparison
