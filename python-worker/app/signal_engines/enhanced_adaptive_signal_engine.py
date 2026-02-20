"""
Enhanced Adaptive Signal Engine
Integrates fundamental analysis with technical signals for optimal entry timing
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from app.signal_engines.adaptive_signal_engine import AdaptiveSignalEngine, SignalScore, MarketConditions
from app.services.fair_value_service import FairValueService, FairValueResult
from app.observability.logging import get_logger

logger = get_logger(__name__)

@dataclass
class FundamentalScore:
    buy_score: float = 0.0
    sell_score: float = 0.0
    hold_score: float = 0.0
    reduce_score: float = 0.0
    confidence: float = 0.0
    reasoning: list = None
    fair_value_analysis: Optional[FairValueResult] = None
    
    def __post_init__(self):
        if self.reasoning is None:
            self.reasoning = []

@dataclass
class EnhancedSignalScore:
    technical: SignalScore
    fundamental: FundamentalScore
    combined: SignalScore
    fair_value_analysis: FairValueResult
    quality_score: float
    entry_signal: Dict[str, Any]
    updated_at: datetime

@dataclass
class EntrySignal:
    signal: str  # BUY, WAIT, HOLD
    confidence: float
    reason: str
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    watch_price: Optional[float] = None

class EnhancedAdaptiveSignalEngine(AdaptiveSignalEngine):
    """Enhanced signal engine with fundamental analysis integration"""
    
    def __init__(self):
        super().__init__()
        self.fair_value_service = FairValueService()
        
    def generate_enhanced_signal_score(self, symbol: str, conditions: MarketConditions) -> EnhancedSignalScore:
        """Generate enhanced signal with fundamental analysis integration"""
        
        try:
            # Get technical signal score (existing adaptive system)
            technical_score = self.generate_signal_score(symbol, conditions)
            
            # Get fundamental analysis
            fair_value_result = self.fair_value_service.calculate_fair_value(symbol)
            
            # Calculate fundamental score
            fundamental_score = self._calculate_fundamental_score(fair_value_result)
            
            # Combine technical and fundamental scores
            combined_score = self._combine_technical_fundamental(technical_score, fundamental_score)
            
            # Determine optimal entry signal
            entry_signal = self._determine_optimal_entry(technical_score, fundamental_score, fair_value_result)
            
            return EnhancedSignalScore(
                technical=technical_score,
                fundamental=fundamental_score,
                combined=combined_score,
                fair_value_analysis=fair_value_result,
                quality_score=fair_value_result.quality_score,
                entry_signal=entry_signal,
                updated_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error generating enhanced signal for {symbol}: {e}")
            # Fallback to technical-only signal
            technical_score = self.generate_signal_score(symbol, conditions)
            return EnhancedSignalScore(
                technical=technical_score,
                fundamental=FundamentalScore(buy_score=0, sell_score=0, hold_score=1, confidence=0),
                combined=technical_score,
                fair_value_analysis=FairValueResult(
                    symbol=symbol, current_price=0, fair_value=0, valuation_metrics={},
                    quality_score=0, individual_valuations={}, fundamentals={}, updated_at=datetime.now()
                ),
                quality_score=0,
                entry_signal={'signal': 'HOLD', 'confidence': 0, 'reason': 'Error in fundamental analysis'},
                updated_at=datetime.now()
            )
    
    def _calculate_fundamental_score(self, fair_value_result: FairValueResult) -> FundamentalScore:
        """Calculate fundamental-based signal score"""
        
        score = FundamentalScore()
        score.fair_value_analysis = fair_value_result
        
        # Valuation-based scoring
        current_price = fair_value_result.current_price
        fair_value = fair_value_result.fair_value
        
        if fair_value <= 0:
            score.hold_score = 1.0
            score.reasoning.append("Invalid fair value calculation")
            score.confidence = 0.0
            return score
        
        valuation_ratio = current_price / fair_value
        
        if valuation_ratio < 0.8:  # 20% undervalued
            score.buy_score = 0.8
            score.reasoning.append(f"Deep undervaluation: {valuation_ratio:.2f}x fair value")
        elif valuation_ratio < 0.9:  # 10% undervalued
            score.buy_score = 0.6
            score.reasoning.append(f"Moderate undervaluation: {valuation_ratio:.2f}x fair value")
        elif valuation_ratio < 1.0:  # Fair value or slightly undervalued
            score.buy_score = 0.4
            score.reasoning.append(f"Slight undervaluation: {valuation_ratio:.2f}x fair value")
        elif valuation_ratio > 1.2:  # 20% overvalued
            score.sell_score = 0.6
            score.reasoning.append(f"Overvaluation: {valuation_ratio:.2f}x fair value")
        elif valuation_ratio > 1.1:  # 10% overvalued
            score.sell_score = 0.4
            score.reasoning.append(f"Mild overvaluation: {valuation_ratio:.2f}x fair value")
        else:
            score.hold_score = 0.6
            score.reasoning.append(f"Fair valuation: {valuation_ratio:.2f}x fair value")
        
        # Quality adjustment
        quality_score = fair_value_result.quality_score
        
        if quality_score > 80:
            score.buy_score = min(score.buy_score * 1.2, 1.0)  # Boost high-quality stocks
            score.reasoning.append(f"High quality: {quality_score}/100")
        elif quality_score < 40:
            score.buy_score *= 0.7  # Penalize low-quality stocks
            score.reasoning.append(f"Low quality: {quality_score}/100")
            if score.sell_score > 0:
                score.sell_score = min(score.sell_score * 1.3, 1.0)  # Boost sell signals for low quality
        
        # Growth and momentum adjustments
        fundamentals = fair_value_result.fundamentals
        eps_growth = fundamentals.get('eps_yoy_growth', 0)
        
        if eps_growth > 15:  # Strong growth
            score.buy_score = min(score.buy_score * 1.1, 1.0)
            score.reasoning.append(f"Strong EPS growth: {eps_growth:.1f}%")
        elif eps_growth < 0:  # Negative growth
            score.buy_score *= 0.8
            score.sell_score = min(score.sell_score * 1.2, 1.0)
            score.reasoning.append(f"Negative EPS growth: {eps_growth:.1f}%")
        
        # PEG ratio adjustment
        peg_ratio = fundamentals.get('peg_ratio', 0)
        if 0 < peg_ratio < 1.0:  # Good PEG
            score.buy_score = min(score.buy_score * 1.1, 1.0)
            score.reasoning.append(f"Attractive PEG: {peg_ratio:.2f}")
        elif peg_ratio > 2.0:  # Expensive PEG
            score.buy_score *= 0.8
            score.reasoning.append(f"Expensive PEG: {peg_ratio:.2f}")
        
        # Calculate confidence based on data quality and valuation gap
        valuation_gap = abs(valuation_ratio - 1.0)
        base_confidence = min(valuation_gap * 2, 0.8)  # Higher confidence for larger gaps
        
        # Adjust confidence based on quality
        quality_adjustment = (quality_score - 50) / 100  # -0.5 to +0.5
        
        score.confidence = max(0.1, min(1.0, base_confidence + quality_adjustment))
        
        return score
    
    def _combine_technical_fundamental(self, technical: SignalScore, fundamental: FundamentalScore) -> SignalScore:
        """Combine technical and fundamental scores"""
        
        combined = SignalScore()
        
        # Dynamic weighting based on market conditions and data quality
        tech_weight = 0.6
        fund_weight = 0.4
        
        # Adjust weights based on fundamental confidence
        if fundamental.confidence > 0.7:
            fund_weight = 0.5
            tech_weight = 0.5
        elif fundamental.confidence < 0.3:
            fund_weight = 0.2
            tech_weight = 0.8
        
        # Combine buy scores
        combined.buy_score = (technical.buy_score * tech_weight + fundamental.buy_score * fund_weight)
        
        # Combine sell scores
        combined.sell_score = (technical.sell_score * tech_weight + fundamental.sell_score * fund_weight)
        
        # Combine hold scores
        combined.hold_score = (technical.hold_score * tech_weight + fundamental.hold_score * fund_weight)
        
        # Combine reduce scores
        combined.reduce_score = (technical.reduce_score * tech_weight + fundamental.reduce_score * fund_weight)
        
        # Combine reasoning
        combined.reasoning = technical.reasoning + fundamental.reasoning
        
        # Combined confidence
        combined.confidence = (technical.confidence * tech_weight + fundamental.confidence * fund_weight)
        
        # Include metadata from both
        combined.metadata = technical.metadata.copy()
        combined.metadata.update({
            'fundamental_confidence': fundamental.confidence,
            'quality_score': fundamental.fair_value_analysis.quality_score if fundamental.fair_value_analysis else 0,
            'valuation_ratio': fundamental.fair_value_analysis.current_price / fundamental.fair_value_analysis.fair_value if fundamental.fair_value_analysis.fair_value > 0 else 1.0,
            'tech_weight': tech_weight,
            'fund_weight': fund_weight
        })
        
        return combined
    
    def _determine_optimal_entry(self, technical: SignalScore, fundamental: FundamentalScore, 
                               fair_value_result: FairValueResult) -> EntrySignal:
        """Determine optimal entry timing combining technical and fundamental factors"""
        
        current_price = fair_value_result.current_price
        fair_value = fair_value_result.fair_value
        quality_score = fair_value_result.quality_score
        
        # Fundamental filter - only consider undervalued or fair value stocks
        if fair_value > 0:
            valuation_ratio = current_price / fair_value
            if valuation_ratio > 1.15:  # More than 15% overvalued
                return EntrySignal(
                    signal="HOLD",
                    confidence=0.8,
                    reason=f"Overvalued: {valuation_ratio:.2f}x fair value - wait for better price",
                    watch_price=fair_value * 0.95
                )
        
        # Quality filter - only consider high-quality stocks for long positions
        if quality_score < 40 and fundamental.buy_score > 0.3:
            return EntrySignal(
                signal="HOLD",
                confidence=0.7,
                reason=f"Low quality: {quality_score}/100 - avoid position despite valuation"
            )
        
        # Strong fundamental + technical alignment
        if fundamental.buy_score > 0.6 and technical.buy_score > 0.5:
            confidence = (fundamental.buy_score + technical.buy_score) / 2
            
            # Calculate target and stop loss based on fair value
            target_price = fair_value * 1.2 if fair_value > 0 else current_price * 1.15
            stop_loss = fair_value * 0.85 if fair_value > 0 else current_price * 0.92
            
            return EntrySignal(
                signal="BUY",
                confidence=confidence,
                reason=f"Strong fundamental value + Technical momentum",
                entry_price=current_price,
                target_price=target_price,
                stop_loss=stop_loss
            )
        
        # Good fundamentals, waiting for technical confirmation
        elif fundamental.buy_score > 0.4 and technical.hold_score > 0.4:
            return EntrySignal(
                signal="WAIT",
                confidence=0.6,
                reason=f"Good fundamentals but waiting for technical confirmation",
                entry_price=current_price,
                watch_price=fair_value * 0.95 if fair_value > 0 else current_price * 0.97
            )
        
        # Technical signal without fundamental support
        elif technical.buy_score > 0.6 and fundamental.buy_score < 0.3:
            return EntrySignal(
                signal="WAIT",
                confidence=0.5,
                reason=f"Technical momentum but poor fundamentals - wait for better entry",
                watch_price=fair_value * 0.9 if fair_value > 0 else current_price * 0.95
            )
        
        # Sell signals
        elif fundamental.sell_score > 0.5 or technical.sell_score > 0.5:
            confidence = max(fundamental.sell_score, technical.sell_score)
            
            return EntrySignal(
                signal="SELL",
                confidence=confidence,
                reason=f"Fundamental/technical sell signals detected",
                entry_price=current_price,
                target_price=fair_value * 0.8 if fair_value > 0 else current_price * 0.9
            )
        
        # Reduce signals (profit taking)
        elif (fundamental.reduce_score > 0.4 or technical.reduce_score > 0.4) and valuation_ratio > 1.05:
            confidence = max(fundamental.reduce_score, technical.reduce_score)
            
            return EntrySignal(
                signal="REDUCE",
                confidence=confidence,
                reason=f"Overvalued - consider taking profits",
                entry_price=current_price
            )
        
        # Default to hold
        else:
            return EntrySignal(
                signal="HOLD",
                confidence=0.4,
                reason=f"No clear entry opportunity - monitor conditions",
                watch_price=fair_value * 0.95 if fair_value > 0 else current_price * 0.97
            )
    
    def generate_enhanced_signal_result(self, symbol: str, conditions: MarketConditions):
        """Generate enhanced signal result for API compatibility"""
        
        enhanced_score = self.generate_enhanced_signal_score(symbol, conditions)
        
        # Convert to SignalResult for compatibility
        from app.signal_engines.signal_calculator_core import SignalResult, SignalType
        
        primary_signal = enhanced_score.combined.get_primary_signal()
        
        return SignalResult(
            signal=primary_signal,
            confidence=enhanced_score.combined.confidence,
            reasoning=enhanced_score.combined.reasoning,
            metadata={
                **enhanced_score.combined.metadata,
                'fundamental_analysis': {
                    'fair_value': enhanced_score.fair_value_analysis.fair_value,
                    'current_price': enhanced_score.fair_value_analysis.current_price,
                    'valuation_ratio': enhanced_score.fair_value_analysis.current_price / enhanced_score.fair_value_analysis.fair_value if enhanced_score.fair_value_analysis.fair_value > 0 else 1.0,
                    'quality_score': enhanced_score.quality_score,
                    'individual_valuations': enhanced_score.fair_value_analysis.individual_valuations,
                    'fundamentals': enhanced_score.fair_value_analysis.fundamentals
                },
                'entry_signal': enhanced_score.entry_signal,
                'technical_scores': {
                    'buy_score': enhanced_score.technical.buy_score,
                    'sell_score': enhanced_score.technical.sell_score,
                    'hold_score': enhanced_score.technical.hold_score,
                    'reduce_score': enhanced_score.technical.reduce_score
                },
                'fundamental_scores': {
                    'buy_score': enhanced_score.fundamental.buy_score,
                    'sell_score': enhanced_score.fundamental.sell_score,
                    'hold_score': enhanced_score.fundamental.hold_score,
                    'reduce_score': enhanced_score.fundamental.reduce_score
                }
            }
        )
    
    def get_fundamental_filter_criteria(self) -> Dict[str, Any]:
        """Get fundamental filtering criteria for stock screening"""
        
        return {
            'min_quality_score': 60,  # Minimum quality score
            'max_valuation_ratio': 1.1,  # Maximum price/fair value ratio
            'min_eps_growth': 5.0,  # Minimum EPS growth (%)
            'max_peg_ratio': 2.0,  # Maximum PEG ratio
            'min_roic': 8.0,  # Minimum ROIC (%)
            'max_debt_to_equity': 1.0,  # Maximum debt-to-equity
            'min_gross_margin': 15.0,  # Minimum gross margin (%)
            'required_metrics': [
                'eps_ttm', 'eps_forward', 'eps_yoy_growth',
                'gross_margin', 'roic', 'debt_to_equity',
                'pe_ttm', 'peg_ratio'
            ]
        }
    
    def screen_fundamental_stocks(self, symbols: list) -> list:
        """Screen stocks based on fundamental criteria"""
        
        criteria = self.get_fundamental_filter_criteria()
        screened_stocks = []
        
        for symbol in symbols:
            try:
                fair_value_result = self.fair_value_service.calculate_fair_value(symbol)
                
                # Apply fundamental filters
                if fair_value_result.quality_score < criteria['min_quality_score']:
                    continue
                
                if fair_value_result.fair_value > 0:
                    valuation_ratio = fair_value_result.current_price / fair_value_result.fair_value
                    if valuation_ratio > criteria['max_valuation_ratio']:
                        continue
                
                fundamentals = fair_value_result.fundamentals
                
                if (fundamentals.get('eps_yoy_growth', 0) < criteria['min_eps_growth'] or
                    fundamentals.get('peg_ratio', 999) > criteria['max_peg_ratio'] or
                    fundamentals.get('roic', 0) < criteria['min_roic'] or
                    fundamentals.get('debt_to_equity', 999) > criteria['max_debt_to_equity'] or
                    fundamentals.get('gross_margin', 0) < criteria['min_gross_margin']):
                    continue
                
                # Stock passes all filters
                screened_stocks.append({
                    'symbol': symbol,
                    'quality_score': fair_value_result.quality_score,
                    'valuation_ratio': valuation_ratio if fair_value_result.fair_value > 0 else 1.0,
                    'fair_value': fair_value_result.fair_value,
                    'current_price': fair_value_result.current_price,
                    'fundamentals': fundamentals
                })
                
            except Exception as e:
                logger.warning(f"Error screening {symbol}: {e}")
                continue
        
        # Sort by quality and valuation
        screened_stocks.sort(key=lambda x: (x['quality_score'], 1/x['valuation_ratio']), reverse=True)
        
        return screened_stocks
