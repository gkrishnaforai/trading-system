"""Curated scenario priors + per-theme sensitivity matrix.

12-month macro scenarios — deliberately few and distinct:

  growth_accel_falling_rates   expansion + easing — high-multiple
                               growth gets both legs
  growth_sticky_inflation      demand holds, inflation stays hot —
                               real-asset capex wins, long-duration
                               multiples compressed
  moderate_stable              base case — quality growth compounds
  slowdown_falling_rates       demand weakens, Fed eases into it —
                               quality/resilience over beta
  recession_stress             credit event — almost everything
                               sells; cash-flow resilience is the
                               only shelter

Sensitivity = expected theme attractiveness 0-100 under that
scenario (not a return forecast — a ranking input). Curated like
the metals STRUCTURAL baselines: static, reviewable, and the live
score shifts only through probabilities, never through price.
"""
from __future__ import annotations

SCENARIO_PRIORS = {
    "growth_accel_falling_rates": 18.0,
    "growth_sticky_inflation": 22.0,
    "moderate_stable": 32.0,
    "slowdown_falling_rates": 18.0,
    "recession_stress": 10.0,
}

STAGE_BASE = {"emerging": 55, "inflecting": 80, "mainstream": 62,
              "exhausted": 30, "watching": 40}

THEME_SENSITIVITY = {
    "ai_inference": {
        "growth_accel_falling_rates": 85, "growth_sticky_inflation": 75,
        "moderate_stable": 78, "slowdown_falling_rates": 45,
        "recession_stress": 25,
        "_note": "inference volume structural; semis are cyclical beta",
    },
    "ai_optics": {
        "growth_accel_falling_rates": 88, "growth_sticky_inflation": 70,
        "moderate_stable": 75, "slowdown_falling_rates": 40,
        "recession_stress": 20,
        "_note": "emerging — highest beta of the AI sleeves",
    },
    "dc_power_cooling": {
        "growth_accel_falling_rates": 80, "growth_sticky_inflation": 80,
        "moderate_stable": 80, "slowdown_falling_rates": 55,
        "recession_stress": 35,
        "_note": "MW/rack demand persists through cycles — mandated capex",
    },
    "grid_electrification": {
        "growth_accel_falling_rates": 78, "growth_sticky_inflation": 85,
        "moderate_stable": 80, "slowdown_falling_rates": 55,
        "recession_stress": 40,
        "_note": "backlog-backed grid spend — most scenario-robust",
    },
    "hbm_memory": {
        "growth_accel_falling_rates": 82, "growth_sticky_inflation": 70,
        "moderate_stable": 72, "slowdown_falling_rates": 38,
        "recession_stress": 20,
        "_note": "most cyclical of the AI chain — memory pricing swings",
    },
    "robotics_edge": {
        "growth_accel_falling_rates": 85, "growth_sticky_inflation": 65,
        "moderate_stable": 70, "slowdown_falling_rates": 45,
        "recession_stress": 25,
        "_note": "emerging — earnings conversion still unproven",
    },
    "ai_software": {
        "growth_accel_falling_rates": 88, "growth_sticky_inflation": 72,
        "moderate_stable": 80, "slowdown_falling_rates": 55,
        "recession_stress": 30,
        "_note": "long-duration — loves easing, fears enterprise cuts",
    },
    "space_defense": {
        "growth_accel_falling_rates": 75, "growth_sticky_inflation": 80,
        "moderate_stable": 78, "slowdown_falling_rates": 60,
        "recession_stress": 50,
        "_note": "budgets hold through cycles — most resilient equity theme",
    },
    "_default": {
        "growth_accel_falling_rates": 70, "growth_sticky_inflation": 65,
        "moderate_stable": 70, "slowdown_falling_rates": 50,
        "recession_stress": 35,
        "_note": "generic equity theme",
    },
}

# Curated one-line "why this name" for pool candidates — the analyst
# note the tier-based template can't supply. Keyed by symbol; absent
# symbols fall back to the generated tier note.
SYMBOL_WHY = {
    "MYRG":  "T&D construction EPC — grid build-out is contracted "
             "backlog, not hope",
    "IESC":  "datacenter + grid electrical integrator — dual exposure "
             "to both demand legs",
    "NVEE":  "grid engineering/consulting — upstream signal before "
             "EPC awards land",
    "PLPC":  "transmission/distribution hardware — small pure-play, "
             "thin coverage",
    "AMBA":  "edge-AI vision SoCs — inference at the edge "
             "(auto/IoT/security)",
    "SYNA":  "edge AI SoC + sensing — device-level inference silicon",
    "CEVA":  "DSP/edge-AI IP licensing — royalty model on edge "
             "inference volume",
    "VLN":   "high-speed connectivity for auto/industrial AI — "
             "speculative link",
    "AAOI":  "datacenter transceivers — mid-cap optical exposure "
             "to AI bandwidth",
    "POET":  "photonic interposer — CPO-adjacent, unproven economics",
    "LPTH":  "infrared optics — adjacent optical chain, small",
    "NVTS":  "GaN/SiC power conversion — efficiency layer for DC "
             "power density",
    "AEIS":  "precision power for semi/DC — the conversion layer",
    "POWI":  "high-voltage power ICs — board-level efficiency",
    "ACLS":  "ion implant incl. SiC — power-device capex adjacency",
    "SIMO":  "NAND controllers — memory-interface derivative on AI "
             "storage growth",
    "ICHR":  "gas/fluid delivery into semi equip — picks-and-shovels",
    "UCTT":  "ultra-clean subsystems — same leverage, higher beta",
    "COHU":  "test/handlers — HBM & advanced-package test exposure",
    "OUST":  "digital lidar — robot/machine-vision perception",
    "ARBE":  "4D imaging radar — autonomy perception silicon",
    "INVZ":  "automotive lidar — thin commercial traction",
    "RR":    "service robots — very speculative, revenue tiny",
    "GTLB":  "DevOps platform monetizing AI code-gen — real seats",
    "PATH":  "automation + agentic workflows — enterprise AI plumbing",
    "AI":    "enterprise AI apps — narrative-rich, execution-thin",
    "BBAI":  "defense/intel AI analytics — contract-driven, lumpy",
    "SOUN":  "voice AI — consumer/restaurant demand, unprofitable",
    "IRDM":  "satcom operator — recurring revenue, less binary",
    "RDW":   "space infrastructure components — manufacturing spec",
    "BKSY":  "earth-observation + AI analytics — defense demand",
    "SPIR":  "satellite data subscription — small, cash-burning",
}
