"""
Unit tests for portfolio service
"""
import pytest
from unittest.mock import Mock, patch

from app.services.portfolio_service import PortfolioService


class TestPortfolioService:
    """Test portfolio signal generation"""
    
    @pytest.fixture
    def mock_indicator_service(self):
        """Mock indicator service"""
        service = Mock()
        service.get_latest_indicators.return_value = {
            'signal': 'buy',
            'long_term_trend': 'bullish',
            'medium_term_trend': 'bullish',
            'rsi': 55.0,
            'macd': 1.5,
            'macd_signal': 1.0,
            'atr': 2.0,
            'sma50': 100.0,
            'momentum_score': 65.0,
            'pullback_zone_lower': 98.0,
            'pullback_zone_upper': 102.0
        }
        return service
    
    def test_confidence_calculation(self, mock_indicator_service):
        """Test confidence score calculation"""
        service = PortfolioService()
        service.indicator_service = mock_indicator_service
        
        holding = {
            'stock_symbol': 'AAPL',
            'position_type': 'long',
            'strategy_tag': None
        }
        
        indicators = mock_indicator_service.get_latest_indicators('AAPL')
        confidence = service._calculate_confidence(indicators)
        
        assert 0.0 <= confidence <= 1.0
    
    def test_signal_generation(self, mock_indicator_service):
        """Test signal generation for holding"""
        service = PortfolioService()
        service.indicator_service = mock_indicator_service
        
        holding = {
            'stock_symbol': 'AAPL',
            'position_type': 'long',
            'strategy_tag': None
        }
        
        indicators = mock_indicator_service.get_latest_indicators('AAPL')
        signal = service._generate_signal_for_holding(holding, indicators, 'basic')
        
        assert signal is not None
        assert 'signal_type' in signal
        assert 'confidence_score' in signal
        assert signal['signal_type'] in ['buy', 'sell', 'hold']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

