"""Causal event map — 'if the world is HERE, this is the chain'.

We can't predict the war. We CAN say where the world stands right now
(headline scan + defensive/oil flows), then trace the propagation:

    war escalation  → oil ↑ → inflation ↑ → hawkish Fed → yields ↑
                    → growth/tech ↓ · energy ↑ · airlines ↓ · vol ↑
    ceasefire/de-esc → the SAME chain in reverse

Each hop carries its own confidence — the further down the chain, the
less certain (macro second-orders diverge in ways first-orders don't).
Sector impacts are cross-referenced with the live book so "energy ↑,
transports ↓" also answers "what in MY book moves".

Chains are the honest structure: they don't claim the future, they map
the mechanism — and each step lists its own disconfirming evidence.
"""
from __future__ import annotations

from typing import Any, Optional

# --- the world state detector -------------------------------------------------
# headline vocabulary → geopolitical 'state'. Detection is bounded: a
# term set on recent headlines plus oil-flow confirmation from the tape.

_STATES = {
    "escalating": ["escalat", "retaliat", "expands", "mobiliz", "invade",
                   "strike on", "attack on", "missile", "airstrike",
                   "offensive", "declares war"],
    "war_ongoing": ["war", "conflict", "frontline", "troops", "siege",
                    "attacks", "casualt"],
    "de_escalating": ["ceasefire", "truce", "peace talk", "de-escalat",
                      "withdraw", "deal reached", "hostage deal",
                      "peace plan", "armistice"],
    "trade_war": ["tariff", "trade war", "export control", "sanction",
                  "embargo", "import tax", "retaliatory tar"],
}


def detect_state(headlines: list[str]) -> dict[str, Any]:
    """Score each world-state from flagged headlines → dominant state."""
    scores = {k: 0 for k in _STATES}
    hits = {k: [] for k in _STATES}
    for h in headlines:
        hl = h.lower()
        for state, terms in _STATES.items():
            w = sum(1 for t in terms if t in hl)
            if w:
                scores[state] += min(w, 3)
                if len(hits[state]) < 3:
                    hits[state].append(h[:80])
    dom = max(scores, key=scores.get)
    # 'war_ongoing' is the ambient state; only call it when real terms hit
    if scores[dom] == 0:
        dom = "calm"
    return {"state": dom, "scores": scores,
            "evidence": hits.get(dom) or []}


# --- the chain library --------------------------------------------------------
# each chain: trigger condition → ordered hops. hop confidence decays
# ×0.75 per step — first-order effects are legible, third-order is not.

_CHAINS = [
    {
        "id": "war_escalation",
        "title": "War escalation",
        "related": {"war_ongoing", "escalating"},
        "trigger": {"state": "escalating", "oil_hot": True,
                    "oil_or": True},          # state OR oil spike
        "steps": [
            {"driver": "conflict widens",
             "market": "crude ↑ on supply-risk premium",
             "sectors": {"Energy": "+", "Industrials": "−",
                         "Consumer Cyclical": "−"},
             "assets": "oil↑ gold↑ vol↑ stocks↓"},
            {"driver": "oil feeds headline inflation",
             "market": "CPI/PPI firm — energy passes through",
             "sectors": {"Energy": "+"},
             "assets": "breakevens↑ real-yields↑"},
            {"driver": "inflation firm → hawkish Fed path",
             "market": "rate-cut odds fade, yields ↑",
             "sectors": {"Technology": "−", "Financial Services": "+"},
             "assets": "10y↑ growth↓ value>growth"},
            {"driver": "higher-for-longer + risk-off",
             "market": "multiples compress; defensives lead",
             "sectors": {"Technology": "−", "Utilities": "+",
                         "Healthcare": "+"},
             "assets": "SPX↓ gold↑ dollar↑"},
        ],
        "watch_for": "oil spiking +3%/5d vs SPY · gold+dollar bid · "
                     "escalation language broadening",
        "watch_against": "ceasefire/talks language · oil fading while "
                         "headlines still hot (the fade IS the tell)",
    },
    {
        "id": "war_deescalation",
        "title": "Ceasefire / de-escalation",
        "related": {"war_ongoing", "escalating", "de_escalating"},
        "trigger": {"state": "de_escalating"},
        "steps": [
            {"driver": "war-risk premium unwinds",
             "market": "crude ↓ — supply fear leaves the price",
             "sectors": {"Energy": "−", "Industrials": "+",
                         "Consumer Cyclical": "+"},
             "assets": "oil↓ gold↓ stocks↑ vol↓"},
            {"driver": "energy drag cools inflation path",
             "market": "CPI expectations soften",
             "sectors": {},
             "assets": "breakevens↓ yields↓"},
            {"driver": "softer inflation → dovish repricing",
             "market": "rate-cut odds return, yields ↓",
             "sectors": {"Technology": "+"},
             "assets": "10y↓ growth↑ long-duration↑"},
            {"driver": "risk-on + easier policy",
             "market": "multiple expansion, beaten-down leaders run",
             "sectors": {"Technology": "+", "Consumer Cyclical": "+",
                         "Communication Services": "+"},
             "assets": "SPX↑ high-beta↑ dollar↓"},
        ],
        "watch_for": "oil fading on ANY headline risk · peace-talk "
                     "language · XLU/TLT risk-off unwinding",
        "watch_against": "talks stalling before signature — paper "
                         "ceasefires die fast",
    },
    {
        "id": "trade_war",
        "title": "Trade war / tariff shock",
        "related": {"trade_war"},
        "trigger": {"state": "trade_war"},
        "steps": [
            {"driver": "tariffs raise import costs",
             "market": "margin squeeze on importers; input inflation",
             "sectors": {"Consumer Cyclical": "−", "Industrials": "−",
                         "Technology": "−"},
             "assets": "import-heavy names↓ dollar vol↑"},
            {"driver": "import inflation → sticky CPI",
             "market": "Fed can't cut into a tariff impulse",
             "sectors": {"Technology": "−"},
             "assets": "yields↑ growth↓"},
            {"driver": "supply reshoring rotates leadership",
             "market": "domestic producers + pricing power win",
             "sectors": {"Basic Materials": "+", "Industrials": "mixed"},
             "assets": "relative: domestic>importers"},
        ],
        "watch_for": "tariff/sanction/export-control headlines stacking",
        "watch_against": "exemptions, carve-outs, negotiation headlines",
    },
    {
        "id": "inflation_cooling",
        "title": "Inflation cooling (any cause)",
        "related": {"calm", "de_escalating"},
        "trigger": {"flag": "cpi_soft"},       # external trigger
        "steps": [
            {"driver": "CPI/PPI soft",
             "market": "disinflation confirmed",
             "sectors": {},
             "assets": "yields↓"},
            {"driver": "dovish repricing",
             "market": "cut odds ↑ → growth long-duration bid",
             "sectors": {"Technology": "+", "Real Estate": "+"},
             "assets": "growth↑ value<growth dollar↓"},
        ],
        "watch_for": "soft CPI/PCE prints · energy not re-heating",
        "watch_against": "oil spike or tariff shock re-igniting input "
                         "costs",
    },
]


def evaluate(geo: dict | None, breadth: dict | None = None,
             book: dict | None = None) -> dict[str, Any]:
    """Detect world state → active chains with hop-level confidence +
    personalized sector impact from the live book."""
    geo = geo or {}
    heads = geo.get("drivers") or []
    state = detect_state(heads)
    oil = None
    for l in ((geo.get("defensive") or {}).get("legs") or []):
        if l["etf"] == "USO":
            oil = l
    oil_hot = bool(oil and (oil["rs_5d"] or 0) > 1.5)

    # the book's own sector mix → which chains hit THIS portfolio
    sec_mix = (book or {}).get("sector_mix") or {}

    def _build(ch, conf, fired):
        steps, c = [], conf
        for s in ch["steps"]:
            hit_sectors = {k: v for k, v in s["sectors"].items()
                           if k in sec_mix}
            steps.append({**s, "conf": round(c),
                          "book_impact": {
                              k: f"{v} ({sec_mix[k]:.0f}% of book)"
                              for k, v in hit_sectors.items()}})
            c *= 0.75                     # per-hop decay — honest depth
        return {"id": ch["id"], "title": ch["title"],
                "fired_by": fired, "conf": conf, "steps": steps,
                "watch_for": ch["watch_for"],
                "watch_against": ch["watch_against"]}

    active, watching = [], []
    for ch in _CHAINS:
        trig = ch["trigger"]
        fired = None
        if trig.get("state") == state.get("state"):
            fired = f"headlines: {state['state']}"
        if not fired and trig.get("oil_or") and oil_hot:
            fired = "oil RS +1.5%/5d vs SPY — supply stress in the tape"
        if fired:
            conf = 70 if state["scores"].get(
                trig.get("state", ""), 0) >= 2 else 55
            if fired.startswith("oil"):
                conf = 55
            active.append({**_build(ch, conf, fired), "status": "active"})
        elif state.get("state") in (ch.get("related") or set()):
            # in play but not triggered — the "what if" tier
            watching.append({**_build(ch, 45,
                                      f"armed — {state['state']} in play, "
                                      f"awaits trigger"),
                             "status": "watching"})

    return {"world_state": state["state"],
            "state_scores": state["scores"],
            "state_evidence": state["evidence"],
            "oil_rs_5d": (oil or {}).get("rs_5d"),
            "chains": active, "watching": watching,
            "note": ("mechanism map, not prophecy — each hop loses "
                     "conviction; the disconfirming evidence is listed "
                     "so you know when the chain died")}
