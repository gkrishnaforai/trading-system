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
}

# Stage-2 components deliberately unpriced in stage 1. The score
# renormalizes over available legs and reports these as gaps — the
# same missing-data convention the research engine uses.
STAGE2_PENDING = [
    "cot_positioning",        # CFTC disaggregated — Friday release,
                            # Tuesday positions (release lag matters)
    "exchange_inventories",   # LME + COMEX + SHFE — never one alone
    "etf_flows",              # GLD/SLV/CPER + WGC CB-purchase data
    "futures_curve",          # backwardation/contango — physical tightness
    "mine_supply",            # production guidance, TC/RC for copper
]
