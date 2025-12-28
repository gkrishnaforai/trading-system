"""
Industry Standard Technical Indicator Calculator
Calculates derived indicators from raw price data after every data load
Follows best practices from TradingView, Yahoo Finance, Bloomberg
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class TechnicalIndicatorCalculator:
    """
    Industry-standard technical indicator calculator
    Calculates derived indicators from raw OHLCV data
    """
    
    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return prices.rolling(window=period).mean()
    
    @staticmethod
    def calculate_macd_signal(macd_line: pd.Series, signal_period: int = 9) -> pd.Series:
        """Calculate MACD Signal Line (EMA of MACD line)"""
        return macd_line.ewm(span=signal_period, adjust=False).mean()
    
    @staticmethod
    def calculate_volume_sma(volume: pd.Series, period: int = 50) -> pd.Series:
        """Calculate Volume Simple Moving Average"""
        return volume.rolling(window=period).mean()
    
    @staticmethod
    def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    @staticmethod
    def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        
        return {
            'bb_upper': sma + (std * std_dev),
            'bb_middle': sma,
            'bb_lower': sma - (std * std_dev)
        }
    
    @staticmethod
    def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index (simplified)"""
        # Calculate True Range
        tr = TechnicalIndicatorCalculator.calculate_atr(high, low, close, 1)
        
        # Calculate directional movements
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Convert to Series
        plus_dm = pd.Series(plus_dm, index=high.index)
        minus_dm = pd.Series(minus_dm, index=high.index)
        
        # Calculate ADX (simplified version)
        atr_smoothed = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_smoothed)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_smoothed)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    def calculate_all_derived_indicators(self, price_data: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        Calculate all derived technical indicators from raw price data
        Returns data in the same format as expected by our database
        """
        try:
            logger.info(f"🔧 Calculating derived indicators from {len(price_data)} price records")
            
            # Ensure we have required columns
            required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in price_data.columns for col in required_cols):
                raise ValueError(f"Price data missing required columns. Need: {required_cols}")
            
            # Sort by date
            price_data = price_data.sort_values('date')
            price_data = price_data.reset_index(drop=True)
            
            # Calculate derived indicators
            derived_indicators = {}
            
            # 1. EMA_50 (missing from our data)
            ema_50 = self.calculate_ema(price_data['close'], 50)
            derived_indicators['EMA_50'] = [
                {
                    'date': row['date'],
                    'value': ema_50.iloc[i],
                    'period': 50
                }
                for i, row in price_data.iterrows()
                if not pd.isna(ema_50.iloc[i])
            ]
            
            # 2. SMA_200 (missing from our data)
            sma_200 = self.calculate_sma(price_data['close'], 200)
            derived_indicators['SMA_200'] = [
                {
                    'date': row['date'],
                    'value': sma_200.iloc[i],
                    'period': 200
                }
                for i, row in price_data.iterrows()
                if not pd.isna(sma_200.iloc[i])
            ]
            
            # 3. MACD_Signal (calculate from existing MACD)
            # First get MACD line from existing data or calculate it
            ema_12 = self.calculate_ema(price_data['close'], 12)
            ema_26 = self.calculate_ema(price_data['close'], 26)
            macd_line = ema_12 - ema_26
            
            macd_signal = self.calculate_macd_signal(macd_line, 9)
            derived_indicators['MACD_Signal'] = [
                {
                    'date': row['date'],
                    'value': macd_signal.iloc[i],
                    'period': 9
                }
                for i, row in price_data.iterrows()
                if not pd.isna(macd_signal.iloc[i])
            ]
            
            # 4. Volume SMA_50 (for volume analysis)
            volume_sma_50 = self.calculate_volume_sma(price_data['volume'], 50)
            derived_indicators['Volume_SMA_50'] = [
                {
                    'date': row['date'],
                    'value': volume_sma_50.iloc[i],
                    'period': 50
                }
                for i, row in price_data.iterrows()
                if not pd.isna(volume_sma_50.iloc[i])
            ]
            
            # 5. ATR (volatility indicator)
            atr_series = self.calculate_atr(price_data['high'], price_data['low'], price_data['close'], 14)
            derived_indicators['ATR'] = [
                {
                    'date': row['date'],
                    'value': atr_series.iloc[i],
                    'period': 14
                }
                for i, row in price_data.iterrows()
                if not pd.isna(atr_series.iloc[i])
            ]
            
            # 6. Bollinger Bands (using existing method that takes price series)
            bb_series = self.calculate_bollinger_bands(price_data['close'], 20, 2)
            derived_indicators['bb_upper'] = [
                {
                    'date': row['date'],
                    'value': bb_series['bb_upper'].iloc[i],
                    'period': 20
                }
                for i, row in price_data.iterrows()
                if not pd.isna(bb_series['bb_upper'].iloc[i])
            ]
            derived_indicators['bb_middle'] = [
                {
                    'date': row['date'],
                    'value': bb_series['bb_middle'].iloc[i],
                    'period': 20
                }
                for i, row in price_data.iterrows()
                if not pd.isna(bb_series['bb_middle'].iloc[i])
            ]
            derived_indicators['bb_lower'] = [
                {
                    'date': row['date'],
                    'value': bb_series['bb_lower'].iloc[i],
                    'period': 20
                }
                for i, row in price_data.iterrows()
                if not pd.isna(bb_series['bb_lower'].iloc[i])
            ]
            
            # 7. ADX (trend strength)
            adx = self.calculate_adx(price_data['high'], price_data['low'], price_data['close'], 14)
            derived_indicators['ADX'] = [
                {
                    'date': row['date'],
                    'value': adx.iloc[i],
                    'period': 14
                }
                for i, row in price_data.iterrows()
                if not pd.isna(adx.iloc[i])
            ]
            
            # Log results
            total_derived = sum(len(indicators) for indicators in derived_indicators.values())
            logger.info(f"✅ Calculated {total_derived} derived indicator records")
            
            for indicator_name, indicators in derived_indicators.items():
                logger.info(f"   • {indicator_name}: {len(indicators)} records")
            
            return derived_indicators
            
        except Exception as e:
            logger.error(f"❌ Error calculating derived indicators: {e}")
            return {}
    
    def validate_signal_data_requirements(self, symbol: str) -> Dict[str, Any]:
        """
        Validate that we have all required data for signal generation
        Returns detailed validation report
        """
        from app.database import db
        from sqlalchemy import text
        
        try:
            with db.get_session() as session:
                validation_result = {
                    'symbol': symbol,
                    'is_valid': False,
                    'missing_critical': [],
                    'missing_optional': [],
                    'data_quality': 'insufficient',
                    'recommendations': []
                }
                
                # Required indicators for signal generation
                required_indicators = {
                    'RSI': 'Momentum analysis',
                    'MACD': 'Momentum confirmation', 
                    'MACD_Signal': 'MACD crossover signals',
                    'EMA_20': 'Short-term trend',
                    'EMA_50': 'Medium-term trend',
                    'SMA_50': 'Trend confirmation',
                    'SMA_200': 'Long-term trend'
                }
                
                # Optional but helpful indicators
                optional_indicators = {
                    'Volume_SMA_50': 'Volume analysis',
                    'ATR': 'Volatility measurement',
                    'bb_upper': 'Volatility bands',
                    'ADX': 'Trend strength'
                }
                
                # Check required indicators
                available_indicators = session.execute(text("""
                    SELECT DISTINCT indicator_name 
                    FROM indicators_daily 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchall()
                
                available_set = {row[0] for row in available_indicators}
                
                # Find missing required indicators
                for indicator, purpose in required_indicators.items():
                    if indicator not in available_set:
                        validation_result['missing_critical'].append({
                            'indicator': indicator,
                            'purpose': purpose,
                            'severity': 'critical'
                        })
                
                # Find missing optional indicators  
                for indicator, purpose in optional_indicators.items():
                    if indicator not in available_set:
                        validation_result['missing_optional'].append({
                            'indicator': indicator,
                            'purpose': purpose,
                            'severity': 'optional'
                        })
                
                # Check data freshness
                latest_data = session.execute(text("""
                    SELECT MAX(date) as latest_date, COUNT(*) as total_records
                    FROM indicators_daily 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchone()
                
                if latest_data and latest_data[0]:
                    days_old = (pd.Timestamp.now().date() - latest_data[0]).days
                    if days_old <= 2:
                        validation_result['data_freshness'] = 'fresh'
                    elif days_old <= 7:
                        validation_result['data_freshness'] = 'acceptable'
                    else:
                        validation_result['data_freshness'] = 'stale'
                        validation_result['recommendations'].append('Data is stale - refresh price data')
                
                # Determine overall validity
                if not validation_result['missing_critical']:
                    validation_result['is_valid'] = True
                    validation_result['data_quality'] = 'excellent' if not validation_result['missing_optional'] else 'good'
                elif len(validation_result['missing_critical']) <= 2:
                    validation_result['data_quality'] = 'fair'
                    validation_result['recommendations'].append('Can generate basic signals with reduced confidence')
                else:
                    validation_result['data_quality'] = 'poor'
                    validation_result['recommendations'].append('Too many critical indicators missing - cannot generate reliable signals')
                
                return validation_result
                
        except Exception as e:
            logger.error(f"❌ Error validating signal data requirements: {e}")
            return {
                'symbol': symbol,
                'is_valid': False,
                'error': str(e),
                'data_quality': 'error'
            }
