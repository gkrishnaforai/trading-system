"""
Portfolio Management Utilities

This module provides utilities for managing portfolio data, analysis, and operations.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import os
from api_client import APIClient, APIError

class PortfolioManager:
    """Manages portfolio operations and data persistence"""
    
    def __init__(self):
        self.session_key = 'portfolio_data'
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize portfolio session state if not exists"""
        if self.session_key not in st.session_state:
            st.session_state[self.session_key] = {
                'symbols': [],
                'analysis': {},
                'last_updated': None,
                'settings': {
                    'auto_refresh': False,
                    'refresh_interval': 24,  # hours
                    'default_asset_type': 'stock'
                }
            }
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get portfolio data from session state"""
        return st.session_state[self.session_key]
    
    def add_symbol(self, symbol: str, asset_type: str = 'stock', notes: str = '') -> bool:
        """Add a symbol to the portfolio"""
        symbol = symbol.upper().strip()
        
        # Check if symbol already exists
        if self.get_symbol(symbol):
            return False
        
        # Add to portfolio
        symbol_data = {
            'symbol': symbol,
            'asset_type': asset_type,
            'notes': notes,
            'added_date': datetime.now().isoformat(),
            'last_analyzed': None,
            'status': 'pending'
        }
        
        self.data['symbols'].append(symbol_data)
        return True
    
    def remove_symbol(self, symbol: str) -> bool:
        """Remove a symbol from the portfolio"""
        symbol = symbol.upper().strip()
        
        original_count = len(self.data['symbols'])
        self.data['symbols'] = [s for s in self.data['symbols'] if s['symbol'] != symbol]
        
        # Also remove analysis data
        if symbol in self.data['analysis']:
            del self.data['analysis'][symbol]
        
        return len(self.data['symbols']) < original_count
    
    def get_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol data from portfolio"""
        symbol = symbol.upper().strip()
        return next((s for s in self.data['symbols'] if s['symbol'] == symbol), None)
    
    def update_symbol_status(self, symbol: str, status: str) -> bool:
        """Update symbol status"""
        symbol_data = self.get_symbol(symbol)
        if symbol_data:
            symbol_data['status'] = status
            if status == 'analyzed':
                symbol_data['last_analyzed'] = datetime.now().isoformat()
            return True
        return False
    
    def get_portfolio_dataframe(self) -> pd.DataFrame:
        """Get portfolio as pandas DataFrame"""
        if not self.data['symbols']:
            return pd.DataFrame()
        
        # Create base dataframe
        df = pd.DataFrame(self.data['symbols'])
        
        # Add analysis data
        analysis_data = []
        for symbol_data in self.data['symbols']:
            symbol = symbol_data['symbol']
            analysis = self.data['analysis'].get(symbol, {})
            
            analysis_data.append({
                'signal': analysis.get('signal', 'HOLD'),
                'confidence': analysis.get('confidence', 0),
                'price': analysis.get('price', 0),
                'recent_change': analysis.get('recent_change', 0),
                'rsi': analysis.get('rsi', 0),
                'volume': analysis.get('volume', 0),
                'ema_slope': analysis.get('ema_slope', 0),
                'market_cap': analysis.get('market_cap', 0)
            })
        
        # Combine data
        df_analysis = pd.DataFrame(analysis_data)
        df_combined = pd.concat([df, df_analysis], axis=1)
        
        return df_combined
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary statistics"""
        symbols = self.data['symbols']
        analysis = self.data['analysis']
        
        # Basic counts
        total_symbols = len(symbols)
        analyzed_symbols = len([s for s in symbols if s['symbol'] in analysis])
        
        # Signal distribution
        signal_counts = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        for symbol_analysis in analysis.values():
            signal = symbol_analysis.get('signal', 'HOLD')
            if signal in signal_counts:
                signal_counts[signal] += 1
        
        # Asset type distribution
        asset_type_counts = {}
        for symbol_data in symbols:
            asset_type = symbol_data['asset_type']
            asset_type_counts[asset_type] = asset_type_counts.get(asset_type, 0) + 1
        
        # Performance metrics
        total_value = sum(analysis.get(s['symbol'], {}).get('price', 0) * 100 
                         for s in symbols if s['symbol'] in analysis)  # Assume 100 shares each
        
        avg_confidence = sum(analysis.get(s['symbol'], {}).get('confidence', 0) 
                           for s in symbols if s['symbol'] in analysis) / max(analyzed_symbols, 1)
        
        return {
            'total_symbols': total_symbols,
            'analyzed_symbols': analyzed_symbols,
            'pending_symbols': total_symbols - analyzed_symbols,
            'signal_distribution': signal_counts,
            'asset_type_distribution': asset_type_counts,
            'total_value': total_value,
            'avg_confidence': avg_confidence,
            'last_updated': self.data['last_updated']
        }
    
    def clear_portfolio(self) -> None:
        """Clear all portfolio data"""
        st.session_state[self.session_key] = {
            'symbols': [],
            'analysis': {},
            'last_updated': None,
            'settings': self.data['settings']  # Preserve settings
        }
    
    def export_portfolio(self) -> str:
        """Export portfolio data as JSON"""
        export_data = {
            'portfolio': self.data,
            'export_date': datetime.now().isoformat(),
            'version': '1.0'
        }
        return json.dumps(export_data, indent=2)
    
    def import_portfolio(self, json_data: str) -> bool:
        """Import portfolio data from JSON"""
        try:
            import_data = json.loads(json_data)
            if 'portfolio' in import_data:
                st.session_state[self.session_key] = import_data['portfolio']
                return True
        except (json.JSONDecodeError, KeyError):
            pass
        return False

class PortfolioAnalyzer:
    """Handles portfolio analysis operations"""
    
    def __init__(self):
        """Initialize with API client"""
        python_api_url = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
        self.client = APIClient(python_api_url, timeout=30)
    
    def analyze_symbol(self, symbol: str, asset_type: str, target_date: str = None) -> Dict[str, Any]:
        """Analyze a single symbol"""
        try:
            if not target_date:
                target_date = datetime.now().strftime("%Y-%m-%d")
            
            payload = {
                "symbol": symbol,
                "date": target_date,
                "asset_type": asset_type
            }
            
            response = self.client.post("api/v1/universal/signal/universal", json_data=payload)
            
            if response.get("success"):
                return response["data"]
            else:
                return {"error": response.get("error", "Unknown error")}
                
        except Exception as e:
            return {"error": f"Request failed: {str(e)}"}
    
    def analyze_portfolio(self, symbols_data: List[Dict[str, str]], target_date: str = None) -> Dict[str, Any]:
        """Analyze multiple symbols"""
        results = {}
        errors = {}
        
        for symbol_info in symbols_data:
            symbol = symbol_info['symbol']
            asset_type = symbol_info['asset_type']
            
            try:
                analysis = self.analyze_symbol(symbol, asset_type, target_date)
                if 'error' not in analysis:
                    # Extract key metrics for summary
                    signal_data = analysis.get('signal', {})
                    market_data = analysis.get('market_data', {})
                    analysis_data = analysis.get('analysis', {})
                    
                    results[symbol] = {
                        'signal': signal_data.get('signal', 'HOLD'),
                        'confidence': signal_data.get('confidence', 0),
                        'price': market_data.get('price', 0),
                        'recent_change': analysis_data.get('recent_change', 0),
                        'rsi': market_data.get('rsi', 0),
                        'volume': market_data.get('volume', 0),
                        'ema_slope': analysis_data.get('ema_slope', 0),
                        'full_data': analysis
                    }
                else:
                    errors[symbol] = analysis['error']
                    
            except Exception as e:
                errors[symbol] = str(e)
        
        return {
            'results': results,
            'errors': errors,
            'analyzed_count': len(results),
            'error_count': len(errors),
            'target_date': target_date
        }
    
    def load_data_for_symbols(self, symbols: List[str], force_refresh: bool = True) -> Dict[str, Any]:
        """Load market data for multiple symbols"""
        try:
            response = self.client.post("refresh", json_data={
                "symbols": symbols,
                "data_types": ["price_historical", "indicators"],
                "force": force_refresh
            })
            
            return response
            
        except Exception as e:
            return {"success": False, "error": str(e)}

class PortfolioVisualizer:
    """Handles portfolio visualization and charts"""
    
    @staticmethod
    def create_signal_distribution_chart(signal_counts: Dict[str, int]) -> Dict[str, Any]:
        """Create signal distribution pie chart"""
        import plotly.graph_objects as go
        import plotly.express as px
        
        labels = list(signal_counts.keys())
        values = list(signal_counts.values())
        colors = ['#00C851', '#FF4444', '#FF8800']  # BUY, SELL, HOLD
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=colors,
            textinfo='label+percent',
            textfont_size=12
        )])
        
        fig.update_layout(
            title="Signal Distribution",
            font=dict(size=14),
            showlegend=True,
            height=400
        )
        
        return fig
    
    @staticmethod
    def create_confidence_histogram(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create confidence score histogram"""
        import plotly.graph_objects as go
        import plotly.express as px
        
        confidences = [data.get('confidence', 0) for data in analysis_data.values()]
        
        fig = go.Figure(data=[go.Histogram(
            x=confidences,
            nbinsx=10,
            marker_color='#667eea',
            opacity=0.7
        )])
        
        fig.update_layout(
            title="Confidence Score Distribution",
            xaxis_title="Confidence Score",
            yaxis_title="Number of Symbols",
            font=dict(size=14),
            height=400
        )
        
        return fig
    
    @staticmethod
    def create_portfolio_performance_chart(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create portfolio performance chart"""
        import plotly.graph_objects as go
        import plotly.express as px
        
        symbols = list(analysis_data.keys())
        prices = [data.get('price', 0) for data in analysis_data.values()]
        changes = [data.get('recent_change', 0) for data in analysis_data.values()]
        
        colors = ['#00C851' if change >= 0 else '#FF4444' for change in changes]
        
        fig = go.Figure(data=[go.Bar(
            x=symbols,
            y=changes,
            marker_color=colors,
            text=[f"{change:+.2%}" for change in changes],
            textposition='outside'
        )])
        
        fig.update_layout(
            title="Portfolio Performance (Recent Changes)",
            xaxis_title="Symbol",
            yaxis_title="Recent Change",
            font=dict(size=14),
            height=400
        )
        
        return fig

# Utility functions for the portfolio page
def format_signal_badge(signal: str) -> str:
    """Format signal as HTML badge"""
    signal_classes = {
        'BUY': 'buy-signal',
        'SELL': 'sell-signal', 
        'HOLD': 'hold-signal'
    }
    
    css_class = signal_classes.get(signal.upper(), 'hold-signal')
    return f'<span class="signal-badge {css_class}">{signal}</span>'

def format_confidence_bar(confidence: float) -> str:
    """Format confidence as progress bar"""
    confidence = float(confidence) if confidence else 0
    
    if confidence >= 0.6:
        color_class = 'high-confidence'
    elif confidence >= 0.4:
        color_class = 'medium-confidence'
    else:
        color_class = 'low-confidence'
    
    return f'''
    <div>
        {confidence:.1%}
        <div class="confidence-bar">
            <div class="confidence-fill {color_class}" style="width: {confidence * 100}%"></div>
        </div>
    </div>
    '''

def get_asset_type_icon(asset_type: str) -> str:
    """Get icon for asset type"""
    icons = {
        'stock': '📈',
        'regular_etf': '📊',
        '3x_etf': '🚀'
    }
    return icons.get(asset_type, '📋')

def get_asset_type_display(asset_type: str) -> str:
    """Get display name for asset type"""
    display_names = {
        'stock': 'Stock',
        'regular_etf': 'ETF',
        '3x_etf': '3x ETF'
    }
    return display_names.get(asset_type, asset_type.replace('_', ' ').title())
