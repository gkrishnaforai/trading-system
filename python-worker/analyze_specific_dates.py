#!/usr/bin/env python3
"""
Detailed Signal Analysis - Engine Predictions vs Actual Outcomes
Shows specific 2025 dates with engine prompts and actual results
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# Import core components - NO FALLBACKS - FAIL FAST
from app.signal_engines.signal_calculator_core import (
    SignalType, MarketConditions, SignalConfig, SignalResult
)

class DetailedSignalAnalyzer:
    """Analyzes specific dates with engine predictions vs actual outcomes"""
    
    def __init__(self):
        self.price_data = None
        self.results = []
    
    def load_2025_data_from_db(self):
        """Load 2025 TQQQ data from database"""
        
        print("📊 Loading 2025 TQQQ Data from Database")
        print("=" * 50)
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        try:
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            
            # Get 2025 data with all necessary columns
            cursor.execute("""
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = 'TQQQ' 
                AND i.date >= '2025-01-01' 
                AND i.date <= '2025-12-31'
                ORDER BY i.date
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                print("❌ No 2025 data found in database")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=[
                'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
            ])
            
            # Ensure date is datetime
            df['date'] = pd.to_datetime(df['date'])
            
            print(f"✅ Loaded {len(df)} records from 2025")
            print(f"📅 Date range: {df['date'].min()} to {df['date'].max()}")
            print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
            print(f"📈 RSI range: {df['rsi'].min():.1f} - {df['rsi'].max():.1f}")
            
            conn.close()
            return df
            
        except Exception as e:
            print(f"❌ Error loading data: {e}")
            return None
    
    def calculate_market_conditions(self, df: pd.DataFrame, index: int) -> MarketConditions:
        """Calculate market conditions for a specific date"""
        
        if index < 2 or index >= len(df):
            raise ValueError("Invalid index for market conditions calculation")
        
        # Current data
        current = df.iloc[index]
        
        # Recent change (last 3 days)
        recent_close = df.iloc[index-2]['close']
        current_close = current['close']
        recent_change = (current_close - recent_close) / recent_close
        
        # Calculate volatility (last 20 days)
        start_idx = max(0, index - 19)
        volatility_data = df.iloc[start_idx:index+1]['close'].pct_change().dropna()
        volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
        
        return MarketConditions(
            rsi=current['rsi'],
            sma_20=current['ema_20'],  # Use ema_20 for sma_20
            sma_50=current['sma_50'],
            ema_20=current['ema_20'],  # Add ema_20 field
            current_price=current['close'],
            recent_change=recent_change,
            macd=current['macd'],
            macd_signal=current['macd_signal'],
            volatility=volatility
        )
    
    def generate_signal_with_reasoning(self, conditions: MarketConditions, config: SignalConfig) -> SignalResult:
        """Generate signal with detailed reasoning using our optimized logic"""
        
        # Use optimized configuration from our research
        rsi_oversold = config.rsi_oversold
        rsi_moderately_oversold = config.rsi_moderately_oversold
        rsi_mildly_oversold = config.rsi_mildly_oversold
        
        # Determine conditions
        is_oversold = conditions.rsi < rsi_oversold
        is_moderately_oversold = conditions.rsi < rsi_moderately_oversold
        is_mildly_oversold = conditions.rsi < rsi_mildly_oversold
        is_overbought = conditions.rsi > 70
        
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        is_downtrend = conditions.sma_20 < conditions.sma_50 and conditions.current_price < conditions.sma_50
        is_recently_down = conditions.recent_change < -0.02
        is_recently_up = conditions.recent_change > 0.02
        
        macd_bullish = conditions.macd > conditions.macd_signal
        macd_bearish = conditions.macd < conditions.macd_signal
        
        reasoning = []
        confidence = 0.5
        
        # Optimized signal logic (from our research)
        if is_oversold and is_recently_down:
            signal = SignalType.BUY
            confidence = 0.7
            reasoning.extend([
                "Strong oversold buying opportunity",
                f"RSI oversold: {conditions.rsi:.1f} < {rsi_oversold}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Oversold stabilization",
                f"RSI oversold: {conditions.rsi:.1f} < {rsi_oversold}",
                "Bottoming pattern detected",
                "Mean reversion entry"
            ])
        elif is_oversold and is_uptrend:
            signal = SignalType.BUY
            confidence = 0.65
            reasoning.extend([
                "Oversold in uptrend",
                f"RSI oversold: {conditions.rsi:.1f} < {rsi_oversold}",
                "Uptrend support",
                "Bullish reversal"
            ])
        elif is_moderately_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Moderately oversold buying opportunity",
                f"RSI moderately oversold: {conditions.rsi:.1f} < {rsi_moderately_oversold}",
                "Support level likely",
                "Reversal potential"
            ])
        elif is_mildly_oversold and is_uptrend:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold in uptrend",
                f"RSI mildly oversold: {conditions.rsi:.1f} < {rsi_mildly_oversold}",
                "Uptrend support",
                "Conservative entry"
            ])
        elif is_mildly_oversold and macd_bullish:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold with MACD confirmation",
                f"RSI mildly oversold: {conditions.rsi:.1f} < {rsi_mildly_oversold}",
                "MACD bullish",
                "Technical confirmation"
            ])
        elif is_overbought and is_recently_up:
            signal = SignalType.SELL
            confidence = 0.6
            reasoning.extend([
                "Overbought selling opportunity",
                f"RSI overbought: {conditions.rsi:.1f} > 70",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_uptrend and macd_bullish and not is_overbought and conditions.rsi < 65 and not is_mildly_oversold:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Uptrend continuation",
                f"RSI strength: {conditions.rsi:.1f}",
                "MACD bullish confirmation",
                "Trend-following entry"
            ])
        elif is_downtrend and macd_bearish and not is_oversold:
            signal = SignalType.SELL
            confidence = 0.5
            reasoning.extend([
                "Downtrend continuation",
                f"RSI weakness: {conditions.rsi:.1f}",
                "MACD bearish confirmation",
                "Trend-following exit"
            ])
        else:
            signal = SignalType.HOLD
            confidence = 0.2
            reasoning.extend([
                "No clear signal",
                f"RSI neutral: {conditions.rsi:.1f}",
                "Wait for better setup"
            ])
        
        metadata = {
            "rsi": conditions.rsi,
            "current_price": conditions.current_price,
            "signal_strength": confidence,
            "is_uptrend": is_uptrend,
            "is_downtrend": is_downtrend,
            "macd_bullish": macd_bullish,
            "volatility": conditions.volatility
        }
        
        return SignalResult(signal, confidence, reasoning, metadata)
    
    def calculate_actual_outcome(self, df: pd.DataFrame, signal_date: str, signal_price: float, 
                               signal_type: str, days_forward: int = 5) -> Dict:
        """Calculate actual outcome for a signal"""
        
        try:
            signal_idx = df[df['date'] == signal_date].index[0]
            
            if signal_idx + days_forward >= len(df):
                return {"status": "insufficient_data"}
            
            # Get forward data
            future_data = df.iloc[signal_idx:signal_idx + days_forward + 1]
            
            # Calculate returns
            future_prices = future_data['close'].values
            entry_price = future_prices[0]
            
            # 3-day, 5-day returns
            return_3d = (future_prices[min(2, len(future_prices)-1)] - entry_price) / entry_price if len(future_prices) > 2 else 0
            return_5d = (future_prices[min(4, len(future_prices)-1)] - entry_price) / entry_price if len(future_prices) > 4 else 0
            
            # Max gain and max loss
            max_gain = (future_prices.max() - entry_price) / entry_price
            max_loss = (entry_price - future_prices.min()) / entry_price
            
            # Final outcome
            final_return = return_5d
            is_profitable = final_return > 0
            
            return {
                "status": "success",
                "return_3d": return_3d,
                "return_5d": return_5d,
                "max_gain": max_gain,
                "max_loss": max_loss,
                "final_return": final_return,
                "is_profitable": is_profitable,
                "final_price": future_prices[-1],
                "days_analyzed": len(future_prices) - 1
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def analyze_specific_dates(self):
        """Analyze specific dates with engine predictions vs actual outcomes"""
        
        print("🔍 DETAILED SIGNAL ANALYSIS - Engine Predictions vs Actual Outcomes")
        print("=" * 80)
        
        # Load data
        df = self.load_2025_data_from_db()
        if df is None:
            return
        
        self.price_data = df
        
        # Use optimized configuration from our research
        config = SignalConfig(
            rsi_oversold=47,           # Optimized from research
            rsi_moderately_oversold=35, # Optimized from research
            rsi_mildly_oversold=42,     # Optimized from research
            max_volatility=8.0,         # Optimized from research
            oversold_boost=0.12,
            trend_boost=0.1
        )
        
        print(f"\n⚙️ Using Optimized Configuration:")
        print(f"  RSI Oversold: {config.rsi_oversold}")
        print(f"  RSI Moderate: {config.rsi_moderately_oversold}")
        print(f"  RSI Mild: {config.rsi_mildly_oversold}")
        print(f"  Max Volatility: {config.max_volatility}%")
        print()
        
        # Select interesting dates to analyze
        # Pick dates with various RSI levels and market conditions
        analysis_dates = []
        
        # Find dates with different RSI conditions
        for i in range(10, len(df) - 10):
            date = df.iloc[i]['date']
            rsi = df.iloc[i]['rsi']
            
            # Select diverse examples
            if rsi < 30:  # Very oversold
                analysis_dates.append((date, i, "Very Oversold"))
            elif 30 <= rsi < 40:  # Oversold
                analysis_dates.append((date, i, "Oversold"))
            elif 40 <= rsi < 50:  # Neutral
                analysis_dates.append((date, i, "Neutral"))
            elif 50 <= rsi < 60:  # Mildly overbought
                analysis_dates.append((date, i, "Mildly Overbought"))
            elif rsi >= 60:  # Overbought
                analysis_dates.append((date, i, "Overbought"))
        
        # Limit to reasonable number for analysis
        analysis_dates = analysis_dates[:15]
        
        print(f"📅 Analyzing {len(analysis_dates)} specific dates in 2025:")
        print()
        
        results = []
        
        for date, idx, condition_type in analysis_dates:
            try:
                # Get market conditions
                conditions = self.calculate_market_conditions(df, idx)
                
                # Generate engine prediction
                signal_result = self.generate_signal_with_reasoning(conditions, config)
                
                # Calculate actual outcome
                actual_outcome = self.calculate_actual_outcome(df, date, conditions.current_price, 
                                                           signal_result.signal.value)
                
                if actual_outcome["status"] == "success":
                    result = {
                        "date": date.strftime('%Y-%m-%d'),
                        "condition_type": condition_type,
                        "signal": signal_result.signal.value,
                        "confidence": signal_result.confidence,
                        "engine_reasoning": signal_result.reasoning,
                        "engine_price": conditions.current_price,
                        "rsi": conditions.rsi,
                        "volatility": conditions.volatility,
                        "actual_return_5d": actual_outcome["return_5d"],
                        "actual_return_3d": actual_outcome["return_3d"],
                        "max_gain": actual_outcome["max_gain"],
                        "max_loss": actual_outcome["max_loss"],
                        "is_profitable": actual_outcome["is_profitable"],
                        "final_price": actual_outcome["final_price"],
                        "prediction_correct": (signal_result.signal.value == "BUY" and actual_outcome["is_profitable"]) or 
                                           (signal_result.signal.value == "SELL" and not actual_outcome["is_profitable"]) or
                                           (signal_result.signal.value == "HOLD")
                    }
                    results.append(result)
                
            except Exception as e:
                print(f"❌ Error analyzing {date}: {e}")
                continue
        
        # Print detailed results
        self.print_detailed_analysis(results)
        
        # Print summary statistics
        self.print_summary_statistics(results)
        
        return results
    
    def print_detailed_analysis(self, results: List[Dict]):
        """Print detailed analysis of each date"""
        
        print("📊 DETAILED SIGNAL ANALYSIS:")
        print("=" * 80)
        
        for i, result in enumerate(results, 1):
            # Fix signal icon display
            if result["signal"] == "BUY":
                signal_icon = "🟢"
            elif result["signal"] == "SELL":
                signal_icon = "🔴"
            else:
                signal_icon = "⚪"
            
            outcome_icon = "✅" if result["is_profitable"] else "❌" if result["signal"] != "HOLD" else "⚪"
            prediction_icon = "✅" if result["prediction_correct"] else "❌"
            
            print(f"\n{i}. {result['date']} - {result['condition_type']}")
            print("-" * 60)
            print(f"   Signal: {signal_icon} {result['signal'].upper()} (confidence: {result['confidence']:.2f})")
            print(f"   Price: ${result['engine_price']:.2f} → ${result['final_price']:.2f}")
            print(f"   RSI: {result['rsi']:.1f} | Volatility: {result['volatility']:.1f}%")
            print(f"   5-Day Return: {result['actual_return_5d']:+.2%} | 3-Day Return: {result['actual_return_3d']:+.2%}")
            print(f"   Max Gain: {result['max_gain']:+.2%} | Max Loss: {result['max_loss']:+.2%}")
            print(f"   Outcome: {outcome_icon} {'Profitable' if result['is_profitable'] else 'Not Profitable'}")
            print(f"   Prediction: {prediction_icon} {'Correct' if result['prediction_correct'] else 'Incorrect'}")
            
            print(f"\n   🤖 ENGINE REASONING:")
            for reason in result['engine_reasoning']:
                print(f"      • {reason}")
            
            print(f"\n   📈 ACTUAL PERFORMANCE:")
            if result['signal'] == 'BUY':
                if result['is_profitable']:
                    print(f"      ✅ Engine was RIGHT - BUY signal was profitable")
                else:
                    print(f"      ❌ Engine was WRONG - BUY signal lost money")
            elif result['signal'] == 'SELL':
                if not result['is_profitable']:
                    print(f"      ✅ Engine was RIGHT - SELL signal avoided loss")
                else:
                    print(f"      ❌ Engine was WRONG - SELL signal missed gains")
            else:
                print(f"      ⚪ Engine chose HOLD - market moved {result['actual_return_5d']:+.2%}")
            
            print()
    
    def print_summary_statistics(self, results: List[Dict]):
        """Print summary statistics"""
        
        print("\n📈 SUMMARY STATISTICS")
        print("=" * 80)
        
        if not results:
            print("❌ No results to analyze")
            return
        
        # Overall statistics
        total_signals = len(results)
        buy_signals = [r for r in results if r['signal'] == 'BUY']
        sell_signals = [r for r in results if r['signal'] == 'SELL']
        hold_signals = [r for r in results if r['signal'] == 'HOLD']
        
        profitable_buys = [r for r in buy_signals if r['is_profitable']]
        correct_sells = [r for r in sell_signals if not r['is_profitable']]
        correct_predictions = [r for r in results if r['prediction_correct']]
        
        # Performance metrics
        buy_accuracy = len(profitable_buys) / len(buy_signals) if buy_signals else 0
        sell_accuracy = len(correct_sells) / len(sell_signals) if sell_signals else 0
        overall_accuracy = len(correct_predictions) / total_signals
        
        avg_buy_return = np.mean([r['actual_return_5d'] for r in buy_signals]) if buy_signals else 0
        avg_sell_return = np.mean([r['actual_return_5d'] for r in sell_signals]) if sell_signals else 0
        
        # Print statistics
        print(f"Total Signals Analyzed: {total_signals}")
        print(f"  BUY Signals: {len(buy_signals)} ({len(buy_signals)/total_signals*100:.1f}%)")
        print(f"  SELL Signals: {len(sell_signals)} ({len(sell_signals)/total_signals*100:.1f}%)")
        print(f"  HOLD Signals: {len(hold_signals)} ({len(hold_signals)/total_signals*100:.1f}%)")
        print()
        
        print(f"Prediction Accuracy:")
        print(f"  BUY Signal Accuracy: {buy_accuracy:.1%} ({len(profitable_buys)}/{len(buy_signals)})")
        print(f"  SELL Signal Accuracy: {sell_accuracy:.1%} ({len(correct_sells)}/{len(sell_signals)})")
        print(f"  Overall Accuracy: {overall_accuracy:.1%} ({len(correct_predictions)}/{total_signals})")
        print()
        
        print(f"Performance Metrics:")
        print(f"  Average BUY Return: {avg_buy_return:+.2%}")
        print(f"  Average SELL Return: {avg_sell_return:+.2%}")
        print(f"  Best BUY Return: {max([r['actual_return_5d'] for r in buy_signals]):+.2%}" if buy_signals else "")
        print(f"  Worst BUY Return: {min([r['actual_return_5d'] for r in buy_signals]):+.2%}" if buy_signals else "")
        print()
        
        # Engine assessment
        if overall_accuracy >= 0.6:
            print(f"🎯 Engine Performance: EXCELLENT ({overall_accuracy:.1%} accuracy)")
        elif overall_accuracy >= 0.5:
            print(f"🎯 Engine Performance: GOOD ({overall_accuracy:.1%} accuracy)")
        elif overall_accuracy >= 0.4:
            print(f"⚠️  Engine Performance: FAIR ({overall_accuracy:.1%} accuracy)")
        else:
            print(f"❌ Engine Performance: POOR ({overall_accuracy:.1%} accuracy)")
        
        print(f"\n✅ Analysis Complete - Engine predictions vs actual outcomes compared!")

def main():
    """Main function"""
    
    print("🔍 DETAILED SIGNAL ANALYSIS")
    print("=" * 80)
    print("🤖 Engine Predictions vs 📈 Actual Outcomes")
    print("📅 Specific 2025 Dates with TQQQ Data")
    print("=" * 80)
    
    analyzer = DetailedSignalAnalyzer()
    results = analyzer.analyze_specific_dates()
    
    return results

if __name__ == "__main__":
    main()
