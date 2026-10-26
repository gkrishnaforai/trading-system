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

# Core US index regime set — each gets a full technical card
# (price vs SMA20/50/200, RSI, streaks). RSP adds the equal-weight
# read: S&P breadth showing through the index surface itself.
INDEX_UNIVERSE = ["SPY", "QQQ", "DIA", "IWM", "MDY", "RSP"]
# Global-risk overlay — confirms/diverges from US risk appetite;
# shown with the index cards but not blended into the US score.
GLOBAL_OVERLAY = ["EFA", "EEM"]

# canonical name -> symbol (Yahoo conventions)
MACRO_SYMBOLS = {
    "us10y": "^TNX",
    "us30y": "^TYX",
    "ust3m": "^IRX",       # front end — curve shape
    "dxy":   "DX-Y.NYB",
    "usdjpy": "JPY=X",      # carry-trade unwind proxy — JPY=X falling
                            # = yen bid = deleveraging risk
    "wti":   "CL=F",
    "brent": "BZ=F",
    "gold":  "GC=F",
    "copper": "HG=F",      # growth proxy (Cu/Au)
    "btc":   "BTC-USD",
    "move":  "^MOVE",
    "hyg":   "HYG",        # credit — junk vs IG is the real risk gauge
    "lqd":   "LQD",
    "tlt":   "TLT",        # duration bid — read WITH yields, not alone
    "tips":  "TIP",        # breakevens proxy (TIP/IEI)
    "tsy13": "IEI",
    "vvix":  "^VVIX",      # tail-hedge demand — vol of vol
}

# ~100 liquid mega/large-cap names — the institutional-breadth leg.
# Paired with MIDCAP_BASKET this yields the large-cap vs broad-market
# divergence reading (S&P members holding while the median stock
# weakens) from a single fetch pass.
LARGECAP_BASKET = [
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

# ~50 liquid mid/small names — the broad-market leg. Below the mega
# caps: when these %s diverge from the large-cap leg, the index
# surface is lying about participation.
MIDCAP_BASKET = [
    # tech / growth
    "APP", "PLTR", "SNOW", "NET", "DDOG", "CRWD", "ZS", "OKTA",
    "DOCU", "BILL", "HUBS", "MDB", "TEAM", "TWLO", "U", "RBLX",
    # consumer / services
    "ABNB", "DASH", "RCL", "RBRK", "ARMK", "DPZ", "WING", "SHAK",
    # financials / fintech
    "SOFI", "HOOD", "COIN", "AFRM", "UPST", "LC", "MQ", "PAGS",
    # health / biotech-ish liquid
    "DXCM", "INCY", "BMRN", "ALNY", "EXEL", "SRPT", "PCVX", "RGEN",
    # industrials / energy / materials
    "AXON", "JBL", "FLEX", "GNRC", "FSLR", "ENPH", "CF", "ALB",
    "MLM", "VMC",
]

BREADTH_BASKET = LARGECAP_BASKET + MIDCAP_BASKET
