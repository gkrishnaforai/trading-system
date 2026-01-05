"""
Default stock symbols for the enhanced watchlist and portfolio system.
Organized by sector and investment style for comprehensive coverage.
"""

# Core default symbols - diverse representation across major sectors
DEFAULT_SYMBOLS = [
    # Technology Giants
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    
    # Financial Services
    "JPM", "BAC", "WFC", "V", "MA", "BRK.B",
    
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT",
    
    # Consumer Discretionary
    "HD", "MCD", "NKE", "LOW", "TGT", "COST", "SBUX",
    
    # Consumer Staples
    "WMT", "PG", "KO", "PEP", "CL",
    
    # Energy
    "XOM", "CVX", "COP",
    
    # Industrials
    "BA", "CAT", "GE", "MMM", "HON", "UPS",
    
    # Materials
    "DOW", "DD", "FCX", "NEM",
    
    # Utilities
    "NEE", "DUK", "SO", "AEP",
    
    # Communication Services
    "T", "VZ", "CMCSA", "DIS", "NFLX",
    
    # Real Estate
    "AMT", "PLD", "CCI", "EQIX", "PSA",
    
    # Key ETFs
    "SPY", "QQQ", "VTI", "IWM", "BND", "GLD", "TQQQ",
]

# Sector-specific watchlists
SECTOR_WATCHLISTS = {
    "technology": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", 
        "CRM", "ADBE", "INTC", "AMD", "NFLX", "PYPL", "SQ"
    ],
    
    "finance": [
        "JPM", "BAC", "WFC", "GS", "MS", "BRK.B", "V", "MA", "BLK"
    ],
    
    "healthcare": [
        "JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT", "DHR", "MRK", "BMY"
    ],
    
    "consumer_discretionary": [
        "HD", "MCD", "NKE", "LOW", "TGT", "COST", "SBUX", "AMZN", "TSLA"
    ],
    
    "consumer_staples": [
        "WMT", "PG", "KO", "PEP", "COST", "CL", "KMB", "GIS"
    ],
    
    "energy": [
        "XOM", "CVX", "COP", "SLB", "HAL", "BP", "TOT"
    ],
    
    "industrials": [
        "BA", "CAT", "GE", "MMM", "HON", "UPS", "RTX", "DE"
    ],
    
    "materials": [
        "DOW", "DD", "BHP", "RIO", "FCX", "NEM", "AA"
    ],
    
    "utilities": [
        "NEE", "DUK", "SO", "AEP", "XEL", "WEC"
    ],
    
    "real_estate": [
        "AMT", "PLD", "CCI", "EQIX", "PSA", "O"
    ],
    
    "communication": [
        "GOOGL", "META", "T", "VZ", "CMCSA", "DIS", "NFLX"
    ],
    
    "leveraged_etfs": [
        "TQQQ", "SOXL", "FNGU", "UPRO", "TECL", "WEBL", "NVDL", "TSLL"
    ]
}

# Investment style watchlists
STYLE_WATCHLISTS = {
    "dividend_aristocrats": [
        "JNJ", "PG", "KO", "MMM", "HD", "WMT", "MCD", "CL", "COST", 
        "ABT", "T", "XOM", "CVX", "IBM", "ADP", "LOW", "UNP", "SHW", 
        "CSCO", "EL", "SYY"
    ],
    
    "growth_stocks": [
        "NVDA", "AMD", "TSLA", "META", "GOOGL", "AMZN", "MSFT", "CRM", 
        "ADBE", "PYPL", "SQ", "SNOW", "PLTR", "CRWD", "ZS", "OKTA"
    ],
    
    "value_stocks": [
        "BRK.B", "JPM", "BAC", "WFC", "XOM", "CVX", "IBM", "INTC", 
        "CSCO", "VZ", "T", "KO", "PG", "JNJ"
    ],
    
    "ai_focused": [
        "NVDA", "MSFT", "GOOGL", "META", "AMD", "SNOW", "PLTR", "CRWD", 
        "ZS", "OKTA", "TSLA", "AMZN", "CRM", "ADBE"
    ],
    
    "clean_energy": [
        "TSLA", "ENPH", "SEDG", "FSLR", "BE", "PLUG", "NEE", "ORCL"
    ],
    
    "swing_trading": [
        # High volatility stocks good for swing trading
        "TSLA", "NVDA", "AMD", "META", "NFLX", "SQ", "PYPL", "COIN",
        # Leveraged ETFs for swing trading
        "TQQQ", "SOXL", "FNGU", "UPRO", "TECL", "NVDL",
        # ETFs with good swing characteristics
        "QQQ", "IWM", "ARKK", "ARKG", "ARKF"
    ]
}

# International exposure
INTERNATIONAL_SYMBOLS = [
    # Europe
    "ASML", "SAP", "NESN", "ROG", "BP", "SHEL", "TOT", "NSRGY",
    
    # Asia
    "TM", "SNE", "BABA", "TCEHY", "JD", "PDD", "BIDU", "NIO", "LI", "XPENG",
    
    # Emerging Markets
    "MELI", "ITUB", "BBDO", "MELI", "BBAJ3"  # Brazil, Latin America
]

# ETF-focused watchlists
ETF_WATCHLISTS = {
    "core_us": ["SPY", "IVV", "VOO", "VTI"],
    "tech_growth": ["QQQ", "VGT", "XLK"],
    "small_cap": ["IWM", "VB", "IJR"],
    "international": ["EFA", "IEFA", "VT", "VXUS"],
    "emerging_markets": ["EEM", "IEMG", "VWO"],
    "bonds": ["BND", "AGG", "VCIT", "VCSH"],
    "commodities": ["GLD", "SLV", "USO", "DBA"],
    "real_estate": ["VNQ", "IYR", "SCHH"]
}

# Pre-built themed watchlists for different investment strategies
THEMED_WATCHLISTS = {
    "tech_leaders": {
        "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META"],
        "description": "Large-cap technology leaders with strong AI and cloud presence",
        "risk_level": "medium-high"
    },
    
    "dividend_kings": {
        "symbols": ["JNJ", "PG", "KO", "MMM", "HD", "WMT", "MCD", "CL"],
        "description": "Dividend aristocrats with 25+ years of dividend increases",
        "risk_level": "low-medium"
    },
    
    "ai_revolution": {
        "symbols": ["NVDA", "MSFT", "GOOGL", "META", "AMD", "SNOW", "PLTR", "CRWD"],
        "description": "Companies leading the artificial intelligence revolution",
        "risk_level": "high"
    },
    
    "energy_transition": {
        "symbols": ["TSLA", "ENPH", "SEDG", "FSLR", "NEE", "BEP", "PLUG"],
        "description": "Clean energy and sustainable technology companies",
        "risk_level": "medium-high"
    },
    
    "financial_powerhouses": {
        "symbols": ["JPM", "BAC", "WFC", "V", "MA", "BRK.B", "GS", "MS"],
        "description": "Major financial institutions and payment processors",
        "risk_level": "medium"
    },
    
    "healthcare_innovators": {
        "symbols": ["JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT", "DHR", "MRK"],
        "description": "Leading healthcare and pharmaceutical companies",
        "risk_level": "medium"
    },
    
    "consumer_giants": {
        "symbols": ["WMT", "PG", "KO", "PEP", "HD", "MCD", "NKE", "COST"],
        "description": "Dominant consumer brands with global reach",
        "risk_level": "low-medium"
    },
    
    "industrial_champions": {
        "symbols": ["BA", "CAT", "GE", "MMM", "HON", "UPS", "RTX", "DE"],
        "description": "Industrial and manufacturing leaders",
        "risk_level": "medium"
    }
}

def get_default_symbols():
    """Get the core default symbols list."""
    return DEFAULT_SYMBOLS.copy()

def get_sector_symbols(sector):
    """Get symbols for a specific sector."""
    return SECTOR_WATCHLISTS.get(sector.lower(), [])

def get_style_symbols(style):
    """Get symbols for a specific investment style."""
    return STYLE_WATCHLISTS.get(style.lower(), [])

def get_themed_watchlist(theme):
    """Get a themed watchlist with metadata."""
    return THEMED_WATCHLISTS.get(theme.lower(), {})

def get_all_themes():
    """Get all available themed watchlist names."""
    return list(THEMED_WATCHLISTS.keys())

def get_all_sectors():
    """Get all available sector names."""
    return list(SECTOR_WATCHLISTS.keys())

def get_all_styles():
    """Get all available investment style names."""
    return list(STYLE_WATCHLISTS.keys())

def validate_symbols(symbols):
    """Validate that symbols are in proper format."""
    valid_symbols = []
    for symbol in symbols:
        if isinstance(symbol, str) and len(symbol.strip()) > 0:
            valid_symbols.append(symbol.strip().upper())
    return valid_symbols

def get_symbol_info(symbol):
    """Get basic information about a symbol."""
    # This would be expanded to include real data from a symbol database
    symbol = symbol.upper()
    info = {
        "symbol": symbol,
        "name": f"{symbol} Corporation",  # Placeholder
        "sector": "Unknown",
        "industry": "Unknown",
        "market_cap": None,
        "description": f"Stock symbol {symbol}"
    }
    
    # Add some basic sector mappings for common symbols
    sector_mappings = {
        "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", 
        "AMZN": "Consumer Discretionary", "NVDA": "Technology", "META": "Technology",
        "JPM": "Finance", "BAC": "Finance", "WFC": "Finance", "V": "Finance",
        "JNJ": "Healthcare", "UNH": "Healthcare", "PFE": "Healthcare",
        "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
        "HD": "Consumer Discretionary", "MCD": "Consumer Discretionary",
        "WMT": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples"
    }
    
    if symbol in sector_mappings:
        info["sector"] = sector_mappings[symbol]
    
    return info
