"""Morning regime card — a rendering of the canonical engine.

One engine, one verdict: state.py builds the MarketSnapshot, facts.py
derives the dimension facts, agent._compose_rules assigns the regime.
This module does NOT fetch or classify independently — it maps the
canonical verdict onto the legacy 5-class morning vocabulary (journal
compat) and renders the morning-specific context the shared engine
doesn't own:

    canonical MarketSnapshot → DimensionFacts → MarketRegime (rules)
        ↓  5-class map + AI sleeve + cross-asset confirmation + events
    strong_risk_on / risk_on / neutral / risk_off / stress
        ↓
    LLM explains (evidence: source_id required) → journal → grade 5/20d

Event days still layer `event_day` on top — this is the base state.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any, Optional

from .models import DimensionFacts, MarketRegime, MarketSnapshot, \
    RegimeLabel

logger = logging.getLogger(__name__)

_AI_BASKET = ("NVDA AVGO AMD MU PLTR COHR IREN CRDO")  # book's growth core

# canonical 8-class regime → legacy 5-class morning vocabulary.
# The journal + grading contract uses the 5-class labels — the map
# preserves that while the underlying verdict comes from one engine.
_FIVE = {
    RegimeLabel.BULL_LOW_VOL: "risk_on",
    RegimeLabel.BULL_HIGH_VOL: "risk_on",
    RegimeLabel.BULLISH_CORRECTION: "neutral",
    RegimeLabel.DISTRIBUTION_RISK: "neutral",
    RegimeLabel.DISTRIBUTION: "risk_off",
    RegimeLabel.MACRO_RISK_OFF: "risk_off",
    RegimeLabel.BEAR: "stress",
    RegimeLabel.TRANSITION: "neutral",
}


def _dim_changes(prev_buckets: dict, facts: DimensionFacts) -> list:
    """'What changed' — today's dimension scores vs the last journaled
    card's. ≥8pts (of 100) is a real move, not noise."""
    out = []
    prev = (prev_buckets or {}).get("_canonical") or {}
    pscores = prev.get("scores") or {}
    for dim, cur in (facts.scores or {}).items():
        pv = pscores.get(dim)
        if pv is None or cur is None:
            continue
        # same 0-100 render the buckets use
        d = round(50 + 50 * cur) - round(50 + 50 * pv)
        if abs(d) >= 8:
            out.append(f"{dim} {round(50+50*pv)} → "
                       f"{round(50+50*cur)}")
    return out


def _five_class(reg: MarketRegime,
                facts: DimensionFacts) -> tuple[str, int]:
    """Canonical regime → (5-class label, 0-100 composite).

    The composite keeps the legacy 0-100 scale by blending the two
    scores the shared engine already produces: trend_score answers
    "is the market still bullish?", deterioration_score answers
    "is it weakening?". Deterioration weighs more — regime labels
    lag, momentum of decay leads."""
    five = _FIVE.get(reg.regime, "neutral")
    tr = facts.trend_score or 0.0
    det = facts.deterioration_score or 0.0
    composite = round(50 + 50 * (0.45 * tr + 0.55 * det))
    composite = max(0, min(100, composite))
    if five == "risk_on" and tr > 0.6 and det > 0.3 \
            and facts.breadth in ("strong", "improving"):
        five = "strong_risk_on"
    return five, composite


def _ai_basket() -> dict[str, Any]:
    """AI/growth sleeve — RS vs SPY over 5/20d + basket breadth. Its own
    regime because the book is AI-heavy: SPY can be fine while the
    sleeve isn't."""
    try:
        import yfinance as yf
        import pandas as pd
        d = yf.download(_AI_BASKET + " QQQ SPY", period="6mo",
                        interval="1d", group_by="ticker",
                        progress=False, auto_adjust=True, timeout=25)
        close = d.xs("Close", axis=1, level=1) \
            if isinstance(d.columns, pd.MultiIndex) else d["Close"]
        spy = close["SPY"].dropna()
        spy_20 = spy.iloc[-1] / spy.iloc[-21] - 1 if len(spy) > 21 else 0
        spy_5 = spy.iloc[-1] / spy.iloc[-6] - 1 if len(spy) > 6 else 0
        out, wins5, wins20, n = [], 0, 0, 0
        for s in _AI_BASKET.split():
            if s not in close:
                continue
            px = close[s].dropna()
            if len(px) < 25:
                continue
            r5 = px.iloc[-1] / px.iloc[-6] - 1
            r20 = px.iloc[-1] / px.iloc[-21] - 1
            n += 1
            wins5 += r5 > spy_5
            wins20 += r20 > spy_20
            out.append({"sym": s, "r5": round(r5 * 100, 2),
                        "r20": round(r20 * 100, 2)})
        qqq = close["QQQ"].dropna()
        smh = close["SMH"].dropna() if "SMH" in close else None
        return {
            "basket": out,
            "breadth5": round(wins5 / n, 2) if n else None,
            "breadth20": round(wins20 / n, 2) if n else None,
            "qqq_vs_spy_20d": round(
                (qqq.iloc[-1] / qqq.iloc[-21] - 1 - spy_20) * 100, 2)
            if len(qqq) > 21 else None,
            "smh_vs_spy_20d": round(
                (smh.iloc[-1] / smh.iloc[-21] - 1 - spy_20) * 100, 2)
            if smh is not None and len(smh) > 21 else None}
    except Exception as exc:
        logger.debug("ai basket failed: %s", exc)
        return {}


def _fact_buckets(facts: DimensionFacts, snap: MarketSnapshot,
                  reg: MarketRegime) -> dict[str, Any]:
    """Render the shared dimension facts in the card's bucket shape —
    score 0-100 + label, plus the raw cross-asset evidence under
    `macro.detail` so the LLM can cite source_ids. This is display
    mapping only — no second classifier."""
    out: dict[str, Any] = {}
    for dim in ("trend", "momentum", "breadth", "volatility",
                "participation", "macro", "structure"):
        sc = facts.scores.get(dim)
        out[dim] = {"score": (round(50 + 50 * sc)
                              if sc is not None else None),
                    "label": getattr(facts, dim)}
    # macro detail — the cross-asset evidence the old engine showed
    detail = {}
    for k in ("us10y", "us30y", "ust3m", "dxy", "hyg", "lqd", "tips",
              "tsy13", "wti", "copper", "gold", "vvix", "btc", "move"):
        m = snap.macro.instruments.get(k)
        if m and m.value is not None:
            detail[k] = {"value": round(m.value, 2),
                         "chg5d": (round(m.chg5d, 4)
                                   if m.chg5d is not None else None)}
    out["macro"]["detail"] = detail
    perm = reg.market_permissions
    out["evidence"] = {"drivers": facts.drivers,
                       "permissions": perm.model_dump() if perm else {}}
    return out


def _confirmation(snap: MarketSnapshot) -> dict[str, Any]:
    """Cross-asset confirmation — do the OTHER markets agree with
    equities? Stocks 🟢 + yields 🔴 + credit 🔴 + VIX 🔴 = a rally
    nobody is underwriting. Each asset votes risk_on/risk_off vs its
    own 5d move, read from the canonical snapshot — no separate fetch."""
    votes: dict[str, str] = {}
    eq5 = snap.momentum.ret5
    eq_dir = ("up" if (eq5 or 0) > 0.005 else
              "down" if (eq5 or 0) < -0.005 else "flat")
    checks = {                    # vote: does this asset confirm
        "yields_10y": ("us10y", True),   # falling yield confirms stocks
        "dollar":     ("dxy", True),     # falling DXY confirms
        "credit":     ("hyg", False),    # HYG rising confirms
        "oil":        ("wti", False),    # modest — growth proxy
        "btc":        ("btc", False),    # risk appetite witness
    }
    for name, (key, invert) in checks.items():
        m = snap.macro.instruments.get(key)
        if not m or m.chg5d is None:
            continue
        risk_on = m.chg5d < -0.003 if invert else m.chg5d > 0.003
        votes[name] = ("confirm" if (risk_on == (eq_dir == "up"))
                       else "against")
    v5 = snap.volatility.vix_chg_5d
    if v5 is not None:
        risk_on = v5 < -0.25              # VIX points falling = calming
        votes["vix"] = ("confirm" if (risk_on == (eq_dir == "up"))
                        else "against")
    conf = sum(1 for v in votes.values() if v == "confirm")
    n = len(votes) or 1
    ratio = conf / n
    return {"votes": votes, "ratio": round(ratio, 2),
            "label": ("high" if ratio >= 0.7 else
                      "low" if ratio <= 0.4 else "mixed")}


def _event_risk(events: list[dict]) -> str:
    """Today's + tomorrow's calendar severity as one label — a quiet
    Tuesday and an FOMC day are not the same environment."""
    sev = {"extreme": 4, "high": 3, "medium": 2, "low": 1}
    worst = max(
        (sev.get(e.get("severity", "low"), 1) +
         (0 if e["days_away"] == 0 else (0 if e["days_away"] > 1 else -0.5))
         for e in events), default=0)
    return ("extreme" if worst >= 4 else "high" if worst >= 3 else
            "medium" if worst >= 2 else "low")


def _rules_matrix(regime: str, ai_regime: str,
                  event_risk: str) -> dict[str, Any]:
    """Regime → portfolio posture — the rule engine the LLM never
    touches. Deterministic actions keyed off the classified state."""
    on = regime in ("strong_risk_on", "risk_on")
    off = regime in ("risk_off", "stress")
    stress = regime == "stress"
    ai_on = ai_regime == "risk_on"
    if stress:
        return {"core": "HOLD", "ai": "HOLD", "leaps": "RESTRICTED",
                "hedge": "ACTIVATE_CRASH_RULES", "cash": "RAISE",
                "note": "no new speculative positions — review "
                        "concentration, prep redeploy triggers"}
    if off:
        return {"core": "HOLD", "ai": "SELECTIVE" if ai_on else "HOLD",
                "leaps": "RESTRICTED", "hedge": "STEP_UP",
                "cash": "RAISE",
                "note": "defensive — hedge per schedule, no "
                        "high-beta adds"}
    if regime == "neutral":
        return {"core": "HOLD", "ai": "SELECTIVE" if ai_on else "HOLD",
                "leaps": "SELECTIVE", "hedge": "BASELINE",
                "cash": "MAINTAIN",
                "note": "conflicting signals — let the tape resolve"}
    return {"core": "HOLD", "ai": "ALLOWED" if ai_on else "SELECTIVE",
            "leaps": "ALLOWED", "hedge": "BASELINE",
            "cash": "MAINTAIN",
            "note": ("risk-on — adds allowed within limits"
                     if on else "")}


def _ai_score(ai: dict[str, Any]) -> Optional[int]:
    """Numeric AI-sleeve score for the weighted composite."""
    if not ai:
        return None
    q = ai.get("qqq_vs_spy_20d")
    s = ai.get("smh_vs_spy_20d")
    b20 = ai.get("breadth20")
    sc = 50.0
    if q is not None:
        sc += q * 4                      # ±5pts RS ≈ ±20 score
    if s is not None:
        sc += s * 4
    if b20 is not None:
        sc += (b20 - 0.5) * 40
    return round(max(0, min(100, sc)))


def _ai_regime(ai: dict[str, Any]) -> str:
    """The book is AI-heavy — the sleeve gets its own state. SPY calm
    while SMH/QQQ break = portfolio pain regardless of index."""
    if not ai:
        return "unknown"
    q = ai.get("qqq_vs_spy_20d")
    s = ai.get("smh_vs_spy_20d")
    b20 = ai.get("breadth20")
    pts = 0
    pts += 2 if (q or 0) > 1 else (-2 if (q or 0) < -1 else 0)
    pts += 2 if (s or 0) > 1 else (-2 if (s or 0) < -1 else 0)
    pts += 1 if (b20 or 0) > 0.55 else (-1 if (b20 or 0) < 0.4 else 0)
    return ("risk_on" if pts >= 2 else
            "risk_off" if pts <= -2 else "neutral")


_PROMPT = """You are the interpretation layer of a quantitative
market-regime system. The score is already computed — you do NOT
re-derive it. You explain WHY, citing only supplied inputs.

DO NOT: invent data, use unstated facts, assume missing values,
fabricate news, predict index prices, or force a directional answer.
If evidence conflicts, say MIXED — choppy is a valid read.

Output ONLY compact JSON:
{"regime":"strong_risk_on|risk_on|neutral|risk_off|stress",
 "confidence":"low|moderate|high",
 "ai_regime":"risk_on|neutral|risk_off",
 "factor_signals":{"trend":"bullish|neutral|bearish|mixed",
                   "momentum":"...","breadth":"...",
                   "volatility":"...","participation":"...",
                   "macro":"...","structure":"...",
                   "ai_growth":"..."},
 "drivers":[{"factor":"bucket","observation":"<=80 chars",
             "source_id":"bucket.field"}],
 "contradictions":[{"observation":"<=80 chars",
                    "source_id":"bucket.field"}],
 "invalidations":["<=80 chars"],
 "qqq_lean":"up|down|flat"}

factor_signals: classify EVERY dimension bullish/neutral/bearish/mixed
from its inputs — this is journaled and graded per factor.
Every driver/contradiction must cite a real source_id or it's dropped.
invalidations = the 2-3 conditions that would flip the regime.
qqq_lean: the AI/growth sleeve — rate moves hit it ~1.3x SPY.
Cross-asset evidence (yields, credit, dollar, breakevens, VVIX) lives
under macro.detail — cite it as macro.detail.<key>.

SCORE: SCORE_PLACEHOLDER · REGIME: REGIME_PLACEHOLDER
CONFIRMATION: CONF_PLACEHOLDER · EVENT_RISK: EVRISK_PLACEHOLDER
BUCKETS: CTX_PLACEHOLDER
EVENTS: EVENTS_PLACEHOLDER
"""


def _plain(*, canonical: str, regime: str, composite: int,
           facts, ai_regime: str | None, conf_label: str,
           event_risk: str, data_quality: str, rules: dict,
           struct: dict | None, divergent: bool) -> str:
    """Deterministic plain-English read of the card — same facts that
    produced the numbers, so the words can never contradict them."""
    posture = {
        "bull_low_vol": "Uptrend intact and volatility calm",
        "bull_high_vol": "Uptrend intact but volatility elevated — "
                         "expect chop, not collapse",
        "bullish_correction": "A pullback inside an uptrend — "
                              "normal correction, not a break",
        "distribution_risk": "Early distribution — the index is "
                             "holding but internals are fraying",
        "distribution": "Distribution underway — sellers in control "
                        "beneath the surface",
        "macro_risk_off": "Macro-driven risk-off — the headwind is the "
                          "environment, not the tape itself",
        "bear": "Downtrend confirmed",
        "transition": "Regime in flux — signals genuinely conflict",
    }.get(canonical, "Regime: " + regime.replace("_", " "))

    # tape texture — strengths from strong dims, caveat from weakest
    names = ("trend", "momentum", "breadth", "volatility",
             "participation", "macro", "structure")
    scores = getattr(facts, "scores", {}) or {}
    known = [(n, getattr(facts, n, "unknown"), scores.get(n))
             for n in names]
    known = [k for k in known if k[1] != "unknown"]
    strengths = [f"{n} is {lbl}" for n, lbl, sc in known
                 if (sc or 0) >= 0.5]
    benign = {"neutral", "mixed", "normal", "stable"}
    weak_dims = [k for k in known if k[1] not in benign]
    weakest = min(weak_dims, key=lambda kv: kv[2] or 0,
                  default=None)
    texture = ""
    if strengths:
        texture = ". " + ", ".join(strengths[:3])
    if weakest and (weakest[2] or 0) < 0 and composite >= 50:
        texture += (" — but " + f"{weakest[0]} is "
                    + weakest[1].replace("_", " ")
                    + ", which caps the score")

    # cross-asset caveat
    conf_txt = {"high": "credit, rates and vol all confirm the equity "
                        "signal",
                "mixed": "cross-asset signals only partially confirm — "
                         "don't lean as hard as the score implies",
                "low": "safety assets disagree with the equity "
                       "signal — treat the score with skepticism"}.get(
        conf_label, "")

    ev_txt = {"high": "major catalysts within days — overnight gaps "
                      "are possible",
              "medium": "a catalyst sits inside the week",
              "low": "no major scheduled catalysts near-term"}.get(
        event_risk, "")

    dq_txt = {"low": "inputs are thin — discount this read",
              "medium": "some inputs are missing"}.get(
        data_quality, "")

    # permissions → plain verbs (only the non-defaults get named first)
    _P = {"core": {"ADD": "adds permitted in core positions",
                   "HOLD": "hold core positions",
                   "REDUCE": "trim core exposure"},
          "ai": {"ALLOWED": "new AI-sleeve adds allowed",
                 "SELECTIVE": "AI adds only on pullbacks",
                 "BLOCKED": "no new AI exposure"},
          "leaps": {"ALLOWED": "LEAPS positioning allowed",
                    "BLOCKED": "no new LEAPS"},
          "hedge": {"BASELINE": "keep normal hedges",
                    "INCREASE": "add protection",
                    "REDUCE": "hedges can come off"},
          "cash": {"MAINTAIN": "hold the cash reserve",
                   "RAISE": "build cash",
                   "DEPLOY": "cash can be deployed"}}
    verbs = [_P[k].get(str(rules.get(k, "")).upper())
             for k in ("core", "ai", "leaps", "hedge", "cash")]
    action = " So today: " + "; ".join(v for v in verbs if v) + "."

    struct_txt = ""
    cap = (struct or {}).get("capex") or {}
    if cap.get("alert") and cap["alert"] != "clear":
        struct_txt = (f"Slower structural picture: the capex cycle "
                      f"reads '{cap.get('band')}' "
                      f"({str(cap['alert']).upper()}) — watch, don't "
                      f"act yet")

    div_txt = ("Internals disagree with the headline score — "
               "verdict capped at neutral" if divergent else "")
    body = ". ".join(t[:1].upper() + t[1:]
                     for t in (conf_txt, ev_txt, dq_txt,
                               struct_txt, div_txt) if t)
    tail = f"{posture}{texture}."
    tail = tail[:1].upper() + tail[1:]
    if strengths:
        # texture starts with ". " + lowercase dim name — capitalise it
        tail = (f"{posture}. "
                + texture[2:3].upper() + texture[3:] + ".")
    return f"{tail} {body}{'.' if body else ''}{action}".strip()


def _explain_llm(score: int, regime: str, ctx: dict) -> dict[str, Any]:
    """LLM explains the computed regime — evidence must cite inputs."""
    try:
        from litellm import completion
        from app.config import settings
        model = getattr(settings, "litellm_model", None) or \
            "gpt-4o-mini"
        compact = json.dumps(ctx.get("buckets") or {}, default=str)[:2800]
        evts = json.dumps(ctx.get("events") or [], default=str)[:600]
        r = completion(
            model=model, temperature=0.1, timeout=30, max_tokens=450,
            messages=[{"role": "user", "content": _PROMPT
                       .replace("SCORE_PLACEHOLDER", str(score))
                       .replace("REGIME_PLACEHOLDER", regime)
                       .replace("CONF_PLACEHOLDER",
                                (ctx.get("confirmation") or {})
                                .get("label", "?"))
                       .replace("EVRISK_PLACEHOLDER",
                                str(ctx.get("event_risk") or "?"))
                       .replace("CTX_PLACEHOLDER", compact)
                       .replace("EVENTS_PLACEHOLDER", evts)}])
        raw = r.choices[0].message.content or ""
        js = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        # evidence must cite a real bucket — strip unsourced claims
        known = set((ctx.get("buckets") or {}).keys())
        drv = [e for e in (js.get("drivers") or [])
               if str(e.get("source_id") or "").split(".")[0] in known]
        con = [e for e in (js.get("contradictions") or [])
               if str(e.get("source_id") or "").split(".")[0] in known]
        # per-factor signals — keep only known buckets + valid labels
        valid = ("bullish", "neutral", "bearish", "mixed")
        fs = {k: v for k, v in (js.get("factor_signals") or {}).items()
              if k in known and str(v).lower() in valid}
        return {"regime": js.get("regime"), "confidence":
                js.get("confidence") or "moderate",
                "ai_regime": js.get("ai_regime"),
                "factor_signals": fs,
                "drivers": drv[:5], "contradictions": con[:4],
                "invalidations": (js.get("invalidations") or [])[:3],
                "qqq_lean": js.get("qqq_lean"),
                "judge": f"llm:{model}"}
    except Exception as exc:
        logger.info("morning llm unavailable (%s)", exc)
        return {"regime": regime, "confidence": "low",
                "judge": "rules"}


_SCENARIO_PROMPT = """You produce the 1-month and 3-month scenario layer of a
market-regime system. Do NOT predict a return. Produce a scenario
tree — what's most consistent with the evidence, what would produce
each alternative, and the measurable triggers that would move us
between them.

Output ONLY compact JSON — every "base/bull/bear/stress" field is ONE
of: strong_risk_on, risk_on, neutral, risk_off, stress:
{"m1":{"base":"<regime>","bull":"<regime>","bear":"<regime>",
        "stress":"<regime>","key_catalyst":"<=80 chars",
        "windows":["date range → what dominates","..."]},
 "q3":{"base":"<regime>","bull":"<regime>","bear":"<regime>",
        "stress":"<regime>",
        "key_risk":"<=80 chars","key_catalyst":"<=80 chars",
        "triggers":{"to_bull":["<=60 chars"],"to_bear":["<=60 chars"],
                    "to_stress":["<=60 chars"]}}}

m1 = this month — positioning, earnings, Fed path, event windows.
q3 = next ~60 trading days — growth trajectory, inflation direction,
policy, capex cycle. triggers = OBSERVABLE conditions (yield >X,
breadth <X), not events you can't verify. windows = the sub-periods
the calendar creates (e.g. "now→Oct14 CPI positioning").

REGIME_NOW: REGIME_PLACEHOLDER SCORE_PLACEHOLDER/100 · confirm CONFIRM_PLACEHOLDER
BUCKETS: CTX_PLACEHOLDER
EVENTS_60D: EVENTS_PLACEHOLDER
"""


def _scenarios_llm(regime: str, score: int, conf_label: str,
                   ctx: dict, events60: list) -> dict[str, Any]:
    """The 1m/3m scenario tree — qualitative, not a forecast. Each
    scenario gets observable triggers so 'what would change the call'
    is checkable."""
    try:
        from litellm import completion
        from app.config import settings
        model = getattr(settings, "litellm_model", None) or \
            "gpt-4o-mini"
        r = completion(
            model=model, temperature=0.1, timeout=35, max_tokens=500,
            messages=[{"role": "user", "content": _SCENARIO_PROMPT
                .replace("REGIME_PLACEHOLDER", regime)
                .replace("SCORE_PLACEHOLDER", str(score))
                .replace("CONFIRM_PLACEHOLDER", conf_label)
                .replace("CTX_PLACEHOLDER",
                         json.dumps(ctx.get("buckets") or {},
                                    default=str)[:2200])
                .replace("EVENTS_PLACEHOLDER",
                         json.dumps(events60, default=str)[:800])}])
        raw = r.choices[0].message.content or ""
        js = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        valid = {"strong_risk_on", "risk_on", "neutral", "risk_off",
                 "stress"}
        out = {}
        for k in ("m1", "q3"):
            h = js.get(k) or {}
            if not isinstance(h, dict):
                continue
            for fld in ("base", "bull", "bear", "stress"):
                if h.get(fld) not in valid:
                    h[fld] = regime if fld == "base" else None
            out[k] = h
        return out
    except Exception as exc:
        logger.info("scenario llm unavailable (%s)", exc)
        return {}


def snapshot() -> Optional[dict[str, Any]]:
    """Daily morning snapshot — idempotent per day.

    One engine: the canonical MarketSnapshot → DimensionFacts → rules
    regime. This renders that single verdict into the morning card's
    vocabulary + journal."""
    from app.database import db
    today = date.today()
    if db.execute_query(
            "SELECT id FROM morning_regime_snapshots WHERE as_of=%s",
            (today,)):
        return None
    try:                               # the canonical engine — the ONLY
        from app.market_data import MarketDataService   # classifier
        from .agent import _compose_rules
        from .facts import derive_facts
        from .state import build_market_snapshot
        from . import structural as _struct
        struct = _struct.read()         # slow-monitor journals
        snap = asyncio.run(build_market_snapshot(MarketDataService()))
        facts = derive_facts(snap, structural=struct)
        reg = _compose_rules(snap, facts)
    except Exception as exc:
        logger.warning("morning: canonical engine failed: %s", exc)
        return None
    regime, composite = _five_class(reg, facts)
    # "what changed" — diff today's dims + structural block against the
    # last journaled card; this is the transition layer, not the level
    try:
        prev_row = db.execute_query(
            "SELECT buckets FROM morning_regime_snapshots "
            "ORDER BY as_of DESC LIMIT 1")
        prev_buckets = (prev_row[0].get("buckets")
                        if prev_row else None) or {}
        if isinstance(prev_buckets, str):
            prev_buckets = json.loads(prev_buckets)
    except Exception:
        prev_buckets = {}
    changes = _dim_changes(prev_buckets, facts)
    changes += _struct.changes(prev_buckets.get("structural"), struct)
    ai = _ai_basket()                  # book sleeve — unique to the card
    ai_regime = _ai_regime(ai)
    buckets = _fact_buckets(facts, snap, reg)
    buckets["ai_growth"] = {"score": _ai_score(ai), "regime": ai_regime,
                            "detail": ai}
    # divergence safeguard — a bullish verdict with broken internals is
    # not risk-on; cap at neutral and flag it
    stress_legs = [d for d in ("macro", "volatility", "breadth")
                   if (buckets[d]["score"] or 50) < 40]
    divergent = regime in ("strong_risk_on", "risk_on") \
        and len(stress_legs) >= 2
    if divergent:
        regime = "neutral"
    try:                                # event calendar — today + next 5d
        from app.market_events.calendar import upcoming_macro_events
        events = [e for e in upcoming_macro_events(7)
                  if e["days_away"] <= 5]
    except Exception:
        events = []
    event_risk = _event_risk(events)
    conf_x = _confirmation(snap)
    # data quality — unknown dimensions shouldn't look like signal
    dims = ("trend", "momentum", "breadth", "volatility",
            "participation", "macro", "structure")
    dq = round(sum(1 for d in dims
                   if getattr(facts, d) != "unknown") / len(dims), 2)
    data_quality = ("high" if dq >= 0.9 else
                    "medium" if dq >= 0.7 else "low")
    rules = _rules_matrix(regime, ai_regime, event_risk)
    plain = _plain(canonical=reg.regime.value, regime=regime,
                   composite=composite, facts=facts,
                   ai_regime=ai_regime, conf_label=conf_x["label"],
                   event_risk=event_risk, data_quality=data_quality,
                   rules=rules, struct=struct, divergent=divergent)
    ctx = {"buckets": buckets, "events": events,
           "confirmation": conf_x, "event_risk": event_risk}
    expl = _explain_llm(composite, regime, ctx)
    # the model's own regime read vs the deterministic one — dissent
    # is journaled, not obeyed
    llm_regime = (expl.get("regime") or regime)
    disagreement = str(llm_regime).lower() != regime
    # 1m + 3m scenario trees — the longer-horizon layer
    try:
        from app.market_events.calendar import upcoming_macro_events
        events60 = upcoming_macro_events(60)
    except Exception:
        events60 = []
    scen = _scenarios_llm(regime, composite, conf_x["label"], ctx,
                          events60)
    db.execute_update(
        """INSERT INTO morning_regime_snapshots
             (as_of, regime, ai_regime, score, confidence, buckets,
              llm, verdict, horizon_1m, horizon_3m)
           VALUES (:d,:r,:ai,:s,:c,:b,:l,:v,:h1,:h3)
           ON CONFLICT (as_of) DO NOTHING""",
        {"d": today, "r": regime, "ai": ai_regime,
         "s": composite, "c": expl.get("confidence"),
         "b": json.dumps({**buckets,
                          "structural": struct,
                          "_canonical": {
                              "label": reg.regime.value,
                              "secondary": (reg.secondary_regime.value
                                            if reg.secondary_regime
                                            else None),
                              "trend_score": facts.trend_score,
                              "deterioration_score":
                                  facts.deterioration_score,
                              "scores": facts.scores,
                              "engine": "state+facts+rules"},
                          "_confirmation": conf_x,
                          "_event_risk": event_risk,
                          "_data_quality": data_quality,
                          "_divergent": divergent,
                          "_stress_legs": stress_legs},
                         default=str),
         "l": json.dumps(expl, default=str),
         "v": json.dumps({"regime": regime, "llm_regime": llm_regime,
                          "llm_dissent": disagreement,
                          "canonical_regime": reg.regime.value,
                          "changes": changes,
                          "qqq_lean": expl.get("qqq_lean"),
                          "event_risk": event_risk,
                          "confirmation": conf_x["label"],
                          "data_quality": data_quality,
                          "plain": plain,
                          "rules": rules}, default=str),
         "h1": json.dumps(scen.get("m1") or {}, default=str),
         "h3": json.dumps(scen.get("q3") or {}, default=str)})
    logger.info("morning regime: %s (%d) · canonical=%s · ai=%s · "
                "conf=%s · ev=%s",
                regime, composite, reg.regime.value, ai_regime,
                conf_x["label"], event_risk)
    return {"regime": regime, "score": composite,
            "canonical_regime": reg.regime.value,
            "changes": changes, "structural": struct,
            "trend_score": facts.trend_score,
            "deterioration_score": facts.deterioration_score,
            "ai_regime": ai_regime, "buckets": buckets,
            "confirmation": conf_x, "event_risk": event_risk,
            "data_quality": data_quality, "divergent": divergent,
            "plain": plain,
            "rules": rules, "llm": expl,
            "horizon_1m": scen.get("m1"), "horizon_3m": scen.get("q3")}


def evaluate() -> dict[str, Any]:
    """Grade journaled regimes vs realized SPY/QQQ at 5/20 sessions —
    did the morning read match the tape?"""
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, regime FROM morning_regime_snapshots "
        "WHERE graded_at IS NULL AND as_of <= CURRENT_DATE - 21")
    graded = 0
    for r in rows:
        def _fwd(sym, n):
            b = db.execute_query(
                "SELECT close FROM daily_bars WHERE symbol=%s "
                "AND date>%s ORDER BY date LIMIT 1 "
                "OFFSET %s", (sym, r["as_of"], n - 1))
            p = db.execute_query(
                "SELECT close FROM daily_bars WHERE symbol=%s "
                "AND date<=%s ORDER BY date DESC LIMIT 1",
                (sym, r["as_of"]))
            return (float(b[0]["close"]) / float(p[0]["close"]) - 1
                    if b and p else None)
        s5, s20, s60 = (_fwd("SPY", n) for n in (5, 20, 60))
        q5, q20, q60 = (_fwd("QQQ", n) for n in (5, 20, 60))
        if s20 is None:
            continue
        reg = r["regime"]
        ok = ((reg in ("strong_risk_on", "risk_on") and s20 > 0.005) or
              (reg in ("risk_off", "stress") and s20 < -0.005) or
              (reg == "neutral" and abs(s20) <= 0.015))
        ok3 = None                       # 3-month grade needs 60d
        if s60 is not None:
            ok3 = ((reg in ("strong_risk_on", "risk_on")
                    and s60 > 0.01) or
                   (reg in ("risk_off", "stress") and s60 < -0.01) or
                   (reg == "neutral" and abs(s60) <= 0.03))
        db.execute_update(
            """UPDATE morning_regime_snapshots SET
               spy_ret_5d=%s, spy_ret_20d=%s, spy_ret_60d=%s,
               qqq_ret_5d=%s, qqq_ret_20d=%s, qqq_ret_60d=%s,
               regime_correct=%s, regime_3m_correct=%s, graded_at=now()
               WHERE as_of=%s""",
            (round(s5, 4) if s5 is not None else None,
             round(s20, 4),
             round(s60, 4) if s60 is not None else None,
             round(q5, 4) if q5 is not None else None,
             round(q20, 4) if q20 is not None else None,
             round(q60, 4) if q60 is not None else None,
             ok, ok3, r["as_of"]))
        graded += 1
    # second pass — 60d fields for rows already graded at 21d
    older = db.execute_query(
        "SELECT as_of, regime FROM morning_regime_snapshots "
        "WHERE spy_ret_60d IS NULL AND as_of <= CURRENT_DATE - 63")
    for r in older:
        def _fwd(sym, n):
            b = db.execute_query(
                "SELECT close FROM daily_bars WHERE symbol=%s "
                "AND date>%s ORDER BY date LIMIT 1 OFFSET %s",
                (sym, r["as_of"], n - 1))
            p = db.execute_query(
                "SELECT close FROM daily_bars WHERE symbol=%s "
                "AND date<=%s ORDER BY date DESC LIMIT 1",
                (sym, r["as_of"]))
            return (float(b[0]["close"]) / float(p[0]["close"]) - 1
                    if b and p else None)
        s60, q60 = _fwd("SPY", 60), _fwd("QQQ", 60)
        if s60 is None:
            continue
        reg = r["regime"]
        ok3 = ((reg in ("strong_risk_on", "risk_on") and s60 > 0.01) or
               (reg in ("risk_off", "stress") and s60 < -0.01) or
               (reg == "neutral" and abs(s60) <= 0.03))
        db.execute_update(
            "UPDATE morning_regime_snapshots SET spy_ret_60d=%s, "
            "qqq_ret_60d=%s, regime_3m_correct=%s WHERE as_of=%s",
            (round(s60, 4), round(q60, 4) if q60 is not None else None,
             ok3, r["as_of"]))
        graded += 1
    return {"graded": graded}


def record() -> dict[str, Any]:
    """Per-regime track record — is 'risk_on' actually bullish? The
    calibration the regime label has to earn."""
    from app.database import db
    return {"by_regime": db.execute_query(
        """SELECT regime, count(*) AS n,
                  count(*) FILTER (WHERE regime_correct) AS hits,
                  round(avg(spy_ret_20d)::numeric, 4) AS avg_spy20,
                  round(avg(qqq_ret_20d)::numeric, 4) AS avg_qqq20
           FROM morning_regime_snapshots
           WHERE graded_at IS NOT NULL
           GROUP BY regime ORDER BY regime""")}
