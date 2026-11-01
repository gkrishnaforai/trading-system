"""Curated structural demand theses per metal — stage-1 constants.

These are deliberately static and honest: the *live* demand evidence
(COT positioning, LME/COMEX/SHFE inventories, ETF flows, mine supply)
is stage-2 work and is flagged as such in data_quality rather than
faked. What lives here is the structural direction of demand — the
same thesis our FDCE `materials` domain tracks for equities (grid
modernization, AI-datacenter power, solar build-out).

`structural_baseline` feeds the fundamental score as a fixed leg:
  it reflects multi-year secular demand direction, not today's price.
  Ranges: 50 = neutral demand, 65-75 = secular tailwind, <45 = secular
  headwind. Never modified by price action.
"""
from __future__ import annotations

STRUCTURAL: dict[str, dict] = {
    "gold": {
        "structural_baseline": 60,
        "thesis": ("Monetary hedge — central-bank accumulation "
                   "(~1,000t/yr pace since 2022), sovereign-debt "
                   "hedging and dedollarization reserve demand."),
        "recovery_drivers": [
            "10Y real yield rolls over — DFII10 decline is the "
            "primary repricing trigger",
            "DXY peak/decline — dollar-denominated relief",
            "Credit event or sovereign-debt stress → safe-haven bid",
            "Continued central-bank accumulation pace",
        ],
        "invalidates_when": ("Real yields re-accelerate above ~2.5% "
                             "with a firming dollar and stress-free "
                             "credit — the monetary case compresses."),
    },
    "silver": {
        "structural_baseline": 72,
        "thesis": ("Monetary + industrial — solar PV (~200Moz/yr and "
                   "growing), electronics, EVs and data-center power "
                   "build-out against flat mine supply. Trades at a "
                   "discount to gold when the G/S ratio is elevated."),
        "recovery_drivers": [
            "Gold/silver ratio mean-reversion toward its 1y median",
            "Gold-led monetary rally — silver is the high-beta leg",
            "Solar + electrical-infrastructure demand growth",
            "Industrial restock once manufacturing turns",
        ],
        "invalidates_when": ("Sustained deflationary-risk regime — "
                             "industrial leg deteriorates while gold "
                             "stays rangebound, leaving silver no "
                             "driver from either side."),
    },
    "copper": {
        "structural_baseline": 75,
        "thesis": ("Industrial growth — grid modernization, AI "
                   "data-center power build-out (the FDCE materials "
                   "thesis), EVs and renewables against thin mine "
                   "supply growth and low treatment charges."),
        "recovery_drivers": [
            "Manufacturing turn — global PMI/INDPRO inflection",
            "Grid + AI-datacenter capex continuing (tracked in FDCE)",
            "China stimulus / property stabilization",
            "Mine disruptions or supply guidance cuts",
        ],
        "invalidates_when": ("Deflationary-risk regime confirms — "
                             "industrial demand deteriorates with "
                             "credit stress; Dr. Copper diagnoses "
                             "recession, not accumulation."),
    },
    # --- crypto — the same engine, different legs. Crypto is a
    # liquidity asset, not a haven: credit stress that bids gold
    # sells bitcoin first. Structural = supply schedule + adoption
    # rails, honestly weaker the further from BTC you go.
    "bitcoin": {
        "structural_baseline": 68,
        "thesis": ("Monetary liquidity asset — fixed supply schedule "
                   "(next halving ~Apr 2028) and a spot-ETF "
                   "institutional bid; trades as the deepest "
                   "liquidity sponge in risk assets."),
        "recovery_drivers": [
            "Liquidity expansion — Fed BS/reserves is BTC's "
            "primary repricing trigger",
            "Real-yield decline + dollar softening",
            "ETF inflow re-acceleration (IBIT/FBTC)",
            "Post-drawdown supply tightening into halving",
        ],
        "invalidates_when": ("Sustained liquidity contraction or "
                             "credit stress — the highest-beta "
                             "liquidity asset sells first, the "
                             "halving story doesn't stop it."),
    },
    "ethereum": {
        "structural_baseline": 60,
        "thesis": ("Network economics — staking yield, EIP-1559 fee "
                   "burn and L2 settlement demand; a monetary + "
                   "utility hybrid, beta to BTC's liquidity cycle."),
        "recovery_drivers": [
            "Liquidity expansion + risk appetite return",
            "ETH/BTC ratio re-rating off depressed levels",
            "Staking/DeFi activity growth",
            "ETF inflows (ETHA and peers)",
        ],
        "invalidates_when": ("Credit stress with shrinking network "
                             "fees — neither the liquidity leg nor "
                             "the utility leg is paying."),
    },
    "solana": {
        "structural_baseline": 52,
        "thesis": ("High-beta network usage — DEX, consumer-app and "
                   "payments volume drives fees; the thinnest "
                   "structural claim of the three and the most "
                   "sensitive to risk appetite."),
        "recovery_drivers": [
            "Liquidity expansion + risk appetite return",
            "Network activity / fee growth resuming",
            "SOL/BTC relative strength rebuild",
        ],
        "invalidates_when": ("Risk-off regime — usage collapses with "
                             "speculative flow; no haven leg exists "
                             "to carry it."),
    },
}

# per-class scaling — crypto drawdowns are 2-3x metal drawdowns, so
# the same % means something different per class
ASSET_CLASS = {
    "gold": "metals", "silver": "metals", "copper": "metals",
    "bitcoin": "crypto", "ethereum": "crypto", "solana": "crypto",
}

# fear bands (drawdown-depth-for-100, below-200SMA-depth-for-100)
FEAR_BANDS = {"metals": (0.30, 0.20), "crypto": (0.50, 0.35)}
# knife thresholds (ret5%, ret20%) — crypto's routine 5d moves would
# trip the metal bands constantly
KNIFE_BANDS = {"metals": (-4.0, -5.0), "crypto": (-10.0, -15.0)}

# Stage-2 components deliberately unpriced in stage 1. The score
# renormalizes over available legs and reports these as gaps — the
# same missing-data convention the research engine uses.
STAGE2_PENDING = {
    "metals": [
        "cot_positioning",      # CFTC disaggregated — Friday release,
                                # Tuesday positions (release lag matters)
        "exchange_inventories", # LME + COMEX + SHFE — never one alone
        "etf_flows",            # GLD/SLV/CPER + WGC CB-purchase data
        "futures_curve",        # backwardation/contango — tightness
        "mine_supply",          # production guidance, TC/RC for copper
    ],
    "crypto": [
        "etf_flows",            # IBIT/FBTC/ETHA daily flows — public,
                                # just not wired yet
        "network_usage",        # fees, burn, active addresses, L2
                                # settlement — ETH/SOL's real demand leg
        "exchange_balances",    # coins leaving exchanges = accumulation
        "funding_rates",        # perpetual positioning — crowding read
    ],
}
