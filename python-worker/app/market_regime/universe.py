"""Symbol universes for the regime snapshot.

Breadth basket: ~100 highly liquid US names spanning every sector —
big enough for real A/D, new-high/new-low and up/down-volume numbers,
small enough to fetch daily without a dedicated breadth feed.

Macro instruments use Yahoo symbol conventions; the router falls back
to Yahoo automatically when FMP doesn't serve them.
"""

SPY = "SPY"
VIX = "^VIX"
VIX3M = "^VIX3M"   # term structure — best effort, may be unavailable
VXN = "^VXN"       # Nasdaq-100 volatility — best effort, may be unavailable

SECTOR_ETFS = [
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
    "XLI", "XLU", "XLRE", "XLB", "XLC",
]

# Index + rotation proxies — relative strength vs SPY
INDEX_ETFS = ["QQQ", "DIA", "IWM"]
ROTATION_ETFS = ["QQQ", "SOXX", "IGV", "IWM"]

# canonical name -> symbol (Yahoo conventions)
MACRO_SYMBOLS = {
    "us10y": "^TNX",
    "us30y": "^TYX",
    "ust3m": "^IRX",       # front end — curve shape
    "dxy":   "DX-Y.NYB",
    "wti":   "CL=F",
    "brent": "BZ=F",
    "gold":  "GC=F",
    "copper": "HG=F",      # growth proxy (Cu/Au)
    "btc":   "BTC-USD",
    "move":  "^MOVE",
    "hyg":   "HYG",        # credit — junk vs IG is the real risk gauge
    "lqd":   "LQD",
    "tips":  "TIP",        # breakevens proxy (TIP/IEI)
    "tsy13": "IEI",
    "vvix":  "^VVIX",      # tail-hedge demand — vol of vol
}

# ~100 liquid names — breadth universe
BREADTH_BASKET = [
    # tech / semis
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "INTC",
    "CSCO", "QCOM", "TXN", "AMAT", "LRCX", "MU", "KLAC", "SNPS", "CDNS",
    "MRVL", "NOW", "INTU", "PANW", "IBM", "ACN",
    # comms / consumer
    "GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T",
    "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TGT",
    "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "CL",
    # financials
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "C", "AXP", "SCHW",
    "BLK", "SPGI", "CME", "ICE", "CB", "MRSH", "PGR", "TRV", "AIG", "MET",
    # health care
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR",
    "AMGN", "GILD", "VRTX", "REGN", "BMY", "CVS", "CI", "ELV", "HUM",
    "ISRG", "SYK", "MDT", "BDX", "EW", "ZTS",
    # energy
    "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC", "VLO", "PSX",
    "WMB", "KMI", "OKE",
    # industrials / materials
    "BA", "CAT", "GE", "HON", "UPS", "RTX", "LMT", "DE", "UNP", "FDX",
    "LIN", "SHW", "APD", "FCX", "NEM", "NUE",
    # utilities / real estate
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL",
    "PLD", "AMT", "EQIX", "SPG", "O",
]
