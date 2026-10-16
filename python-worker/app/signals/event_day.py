"""Macro event-day judge — focused reads on dates that move regime.

On scheduled event days (NFP, CPI, PPI, PCE, FOMC) the engine gathers
the full deterministic context — tape, VIX, breadth, forward
probabilities, dip character, sector money flow, book risk, geo — and
asks for a bounded same-day verdict: green / red / choppy.

An LLM interprets the bundle when configured (bounded JSON, no
freeform); a rules scorer is the deterministic fallback so a call is
always journaled. Every call is versioned in event_day_calls and
graded against the realized SPY day — each event KIND accrues its own
track record, so "the model says red on jobs day" earns credibility
only after out-of-sample hits.

The verdict reflects INTO the regime card as an advisory overlay —
"event day: jobs report → judge: RED (55%)" — but never overrides the
deterministic regime or executes anything.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def todays_event() -> Optional[dict[str, Any]]:
    """The macro event scheduled for today, if any."""
    from app.market_events.calendar import upcoming_macro_events
    today = datetime.now(timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York")).date()
    for e in upcoming_macro_events(1):
        if e["days_away"] == 0 and e["date"] == str(today):
            return e
    return None


def _premarket_spy(sym: str = "SPY") -> Optional[float]:
    """Today's pre-market/early move vs prior close — the market's
    first vote on the release. 5m bars incl. extended hours."""
    try:
        import yfinance as yf
        d = yf.download(sym, period="2d", interval="5m",
                        prepost=True, progress=False, auto_adjust=True,
                        timeout=20)
        if d.empty:
            return None
        close = d["Close"].dropna()
        if hasattr(close, "columns"):           # multi-index safety
            close = close.iloc[:, 0]
        # prior regular-session close = last close before today's date
        idx_dates = close.index.tz_convert("America/New_York").date
        today = datetime.now(timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("America/New_York")).date()
        prior = close[[i < today for i in idx_dates]]
        now_px = float(close.iloc[-1])
        if prior.empty:
            return None
        return round(now_px / float(prior.iloc[-1]) - 1, 4)
    except Exception as exc:
        logger.debug("premarket fetch failed: %s", exc)
        return None


def _rates_dollar() -> dict[str, Any]:
    """The rate-repricing channel — 10Y yield + dollar. On NFP/CPI/PCE
    days THIS is the transmission mechanism: weak data → yields drop →
    cut odds rise → risk rallies (when rates are the binding
    constraint). A hot print does the reverse. Watch the move, not
    just the level."""
    try:
        import yfinance as yf
        d = yf.download("^TNX DX-Y.NYB", period="1mo", interval="1d",
                        group_by="ticker", progress=False,
                        auto_adjust=True, timeout=20)
        out: dict[str, Any] = {}
        for sym, key in (("^TNX", "y10"), ("DX-Y.NYB", "dxy")):
            try:
                s = d[sym]["Close"].dropna()
                out[f"{key}"] = round(float(s.iloc[-1]), 2)
                out[f"{key}_5d_chg"] = round(
                    float(s.iloc[-1]) - float(s.iloc[-6]), 2)
            except Exception:
                pass
        return out
    except Exception as exc:
        logger.debug("rates/dollar fetch failed: %s", exc)
        return {}


_EVENT_PRINT_KEYS = {
    "nfp": ("Non Farm Payrolls", "Nonfarm Payrolls Private",
            "Unemployment Rate"),
    "cpi": ("CPI", "Core CPI"),
    "ppi": ("PPI", "Core PPI"),
    "pce": ("Core PCE Price Index", "PCE Price"),
}


def _the_print(kind: str) -> Optional[list[dict]]:
    """Actual vs estimate for today's release — FMP economic calendar.
    The print is the fact; the reaction is the judge. Journaled so
    future meta can test 'surprise size vs realized move'."""
    keys = _EVENT_PRINT_KEYS.get(kind)
    if not keys:
        return None
    try:
        import requests
        from app.config import settings
        if not settings.fmp_api_key:
            return None
        today = date.today().isoformat()
        r = requests.get(
            f"{settings.fmp_base_url}/economic-calendar",
            params={"from": today, "to": today,
                    "apikey": settings.fmp_api_key}, timeout=15)
        items = r.json()
        if not isinstance(items, list):
            return None
        out = []
        for e in items:
            if e.get("country") != "US":
                continue
            name = e.get("event") or ""
            if not any(k.lower() in name.lower() for k in keys):
                continue
            est, act = e.get("estimate"), e.get("actual")
            surprise = None
            if est is not None and act is not None:
                surprise = ("beat" if act > est * 1.05 else
                            "miss" if act < est * 0.95 else "inline")
            out.append({"event": name, "estimate": est,
                        "actual": act, "previous": e.get("previous"),
                        "surprise": surprise})
        return out or None
    except Exception as exc:
        logger.debug("print fetch failed: %s", exc)
        return None


def _policy_setup(tape: Optional[dict] = None,
                  breadth: Optional[dict] = None,
                  dip_char: Optional[dict] = None
                  ) -> dict[str, Any]:
    """Where we sit vs the rate path — the reason a 'bad' print can be
    bullish. Includes a deterministic hint for which constraint binds:
    when the tape is calm above the 200dma, the market trades RATE
    expectations (bad data → green); when breadth/deleveraging already
    dominates, the same print trades as a GROWTH scare (bad → red)."""
    from app.market_events.calendar import upcoming_macro_events
    evts = upcoming_macro_events(60)
    fomc = next((e for e in evts if e["kind"] == "fomc"
                 and e["days_away"] > 0), None)
    t, b, d = tape or {}, breadth or {}, dip_char or {}
    calm = (t.get("spy_vs_200") or 0) > 0 and (t.get("vix") or 99) < 20
    broken = (t.get("spy_vs_200") or 1) < 0 or \
        (b.get("pct_above_50") or 50) < 35 or \
        d.get("character") == "broad_deleveraging"
    binding = ("growth_scare" if broken else
               "rate_expectations" if calm else "contested")
    return {"next_fomc": fomc["date"] if fomc else None,
            "fomc_days_away": fomc["days_away"] if fomc else None,
            "binding_constraint": binding,
            "binding_read": {
                "rate_expectations":
                    "calm tape >200dma — bad data likely rallies "
                    "(rate relief); hot data is the real risk",
                "growth_scare":
                    "broken breadth/vix — bad data reads as earnings "
                    "fear, not rate relief",
                "contested":
                    "mixed — could go either way, weight the "
                    "premarket vote heavier"}[binding]}


def gather_context() -> dict[str, Any]:
    """The full deterministic bundle handed to the judge — everything
    already computed by the regime stack, fetched once."""
    ctx: dict[str, Any] = {}
    try:                                # tape: SPY vs 200dma, VIX
        from app.signals.daily_board import _tape
        ctx["tape"] = _tape()
    except Exception:
        ctx["tape"] = {}
    for name, loader in (
        ("breadth",       "app.signals.breadth"),
        ("book_risk",     "app.signals.book_risk"),
        ("geo",           "app.signals.geo_context"),
        ("capex",         "app.signals.capex_cycle"),
    ):
        try:
            mod = __import__(loader, fromlist=["read"])
            ctx[name] = mod.read() if hasattr(mod, "read") else None
        except Exception:
            ctx[name] = None
    try:                                # regime detail + forward probs
        from app.market_regime import build_market_regime_graph
        reg = build_market_regime_graph() or {}
        inner = reg.get("regime_detail") or reg
        ctx["regime"] = {k: inner.get(k) for k in
                         ("condition", "direction", "confidence",
                          "risk_level", "dip_buying_environment",
                          "transition_stage", "key_drivers")}
        from app.market_regime.forward import forward_probs
        ctx["forward"] = forward_probs(
            {**ctx["regime"],
             "spy_vs_200": (ctx["tape"] or {}).get("spy_vs_200")},
            ctx.get("breadth"), ctx.get("geo"),
            vix=(ctx["tape"] or {}).get("vix"),
            vix_rising=bool((ctx["tape"] or {}).get("vix_rising")))
    except Exception as exc:
        logger.debug("event context regime failed: %s", exc)
        ctx["regime"], ctx["forward"] = None, None
    try:
        from app.market_regime.dip_character import classify as _dip
        ctx["dip_character"] = _dip()
    except Exception:
        ctx["dip_character"] = None
    try:                                # rotation flows — money moving
        from app.market_regime.allocation import plan as _alloc
        al = _alloc(ctx.get("dip_character"), ctx.get("forward"),
                    (ctx["tape"] or {}).get("vix")) or {}
        ctx["flows"] = {k: al.get(k) for k in
                        ("rotate_to", "rotate_away", "rotate_confirmed",
                         "rotate_note") if al.get(k)}
        ctx["sector_rows"] = [
            {k: r.get(k) for k in ("sym", "flow", "money5",
                                   "vol_ratio", "vol_confirmed")}
            for r in (al.get("sector_rows") or [])[:8]]
    except Exception:
        ctx["flows"] = None
    bk = ctx.get("book_risk")
    if isinstance(bk, dict):            # keep the prompt compact —
        ctx["book_risk"] = {            # legs detail isn't signal
            k: bk.get(k) for k in
            ("book_beta", "top_sector", "top_sector_pct",
             "warnings", "n_legs")}
    ctx["rates"] = _rates_dollar()      # the repricing channel
    ctx["policy"] = _policy_setup(ctx.get("tape"), ctx.get("breadth"),
                                  ctx.get("dip_character"))
    try:                                # engine prior — today's morning
        from app.database import db     # regime, computed daily
        mr = db.execute_query(
            "SELECT regime, score, ai_regime, verdict "
            "FROM morning_regime_snapshots ORDER BY as_of DESC "
            "LIMIT 1")
        if mr:
            v = mr[0].get("verdict")
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = {}
            ctx["morning_regime"] = {
                "regime": mr[0]["regime"], "score": mr[0]["score"],
                "ai_regime": mr[0].get("ai_regime"),
                "confirmation": (v or {}).get("confirmation"),
                "event_risk": (v or {}).get("event_risk")}
    except Exception:
        ctx["morning_regime"] = None
    ctx["premarket_spy"] = _premarket_spy()
    ctx["premarket_qqq"] = _premarket_spy("QQQ")   # tech's first vote
    return ctx


def _rules_verdict(ctx: dict) -> dict[str, Any]:
    """Deterministic fallback when no LLM is configured — scores the
    bundle into green/red/choppy. Always available, always journaled."""
    tape = ctx.get("tape") or {}
    fwd = ctx.get("forward") or {}
    breadth = ctx.get("breadth") or {}
    score = 0.0
    notes = []
    pre = ctx.get("premarket_spy")
    if pre is not None:                 # the market's first vote
        score += pre * 2000             # ±1% ≈ ±20 pts
        notes.append(f"premarket {pre:+.1%}")
    p_bull = fwd.get("p_bullish_20d")   # 0-100 pct from forward_probs
    p_deep = fwd.get("p_deeper_dip_20d")
    if p_bull is not None and p_deep is not None:
        score += (p_bull - p_deep) * 0.3   # tilt vs the bear leg
    vix = tape.get("vix")
    if vix:
        score += -3 if vix >= 25 else (-1.5 if vix >= 20 else 1)
        if tape.get("vix_rising"):
            score -= 2; notes.append("vix rising")
    above50 = breadth.get("pct_above_50")
    if above50 is not None:
        score += (above50 - 0.5) * 30
    s1d = tape.get("spy_1d")
    if s1d is not None:                 # momentum into the print
        score += s1d * 60
    flows = ctx.get("flows") or {}
    away = flows.get("rotate_away") or []
    conf_in = set(flows.get("rotate_confirmed") or [])
    score += 2 * len(conf_in) - 1.5 * len(away)
    if conf_in:
        notes.append(f"confirmed inflow {','.join(conf_in)}")
    if away:
        notes.append(f"money leaving {','.join(away[:3])}")
    rates = ctx.get("rates") or {}
    y5 = rates.get("y10_5d_chg")        # the repricing tell — falling
    binding = ((ctx.get("policy") or {})  # yields on calm tape = cut
               .get("binding_constraint"))  # odds rising = risk bid
    if y5 is not None:
        if binding == "rate_expectations":
            score += -y5 * 4            # yields down → cut odds up → green
            if y5 < -0.10:
                notes.append(f"y10 {y5:+.2f} — rate relief bid")
        else:
            score += y5 * 3             # yields up = inflation fear
            if y5 > 0.10:
                notes.append(f"y10 {y5:+.2f} — hot-print risk")
    verdict = ("green" if score >= 4 else
               "red" if score <= -4 else "choppy")
    conf = min(75, int(35 + abs(score)))
    s = max(-30, min(30, score))        # soft probs — rules are crude
    # floor each leg: a 0% claim is indefensible and Brier-punishing —
    # rules get "likely", never "certain"
    pg, pc, pr = (max(5.0, 33 + s * 1.1), 34.0,
                  max(5.0, 33 - s * 1.1))
    tot = pg + pc + pr
    return {"verdict": verdict, "confidence": conf,
            "probs": {"p_green": round(pg / tot * 100, 1),
                      "p_red": round(pr / tot * 100, 1),
                      "p_choppy": round(pc / tot * 100, 1)},
            "regime_read": binding or "rules",
            "qqq_lean": "up" if score > 0 else "down" if score < 0
            else "flat",
            "qqq_note": "rules: follows SPY lean",
            "thesis": ("; ".join(notes) or "mixed signals")[:300],
            "judge": "rules", "_score": round(score, 1)}


_PROMPT = """You are a macro tape reader judging today's reaction to a
scheduled release. The deterministic engine has ALREADY classified
the regime — your job is the print's effect within it, not re-deriving
the regime.

Output ONLY compact JSON:
{"p_green":0-100,"p_red":0-100,"p_choppy":0-100,
 "verdict":"green|red|choppy","confidence":0-100,
 "regime_read":"rate_expectations|growth_scare|hot_print|contested",
 "qqq_lean":"up|down|flat","qqq_note":"<=80 chars",
 "thesis":"<=160 chars"}

p_* = probability of each SPY outcome today (sum ~100); verdict is
the argmax. green > +0.3%, red < -0.3%, choppy inside ±0.3%.

How prints move markets — the headline isn't the signal, the
rate-path repricing is:
· Weak jobs / cool inflation on a calm tape → yields drop → hike
  odds fall → rallies (bad news = good news)
· The SAME weak print on a fragile tape (VIX elevated, breadth
  broken, deleveraging) → earnings fear → red
· A hot print with hikes live → yields spike → red
· Watch rates.y10 + premarket_spy — the first real vote. Falling
  yield + rising tape = rate-relief bid.

context.morning_regime is the ENGINE's state; ENGINE also carries
binding_constraint — the computed lens. 'rate_expectations' on a calm
tape means a weak print is BULLISH (rate relief) — the bigger the
miss, the bigger the repricing. Dissenting requires tape evidence:
yields rising + premarket red + credit stress, not just an ugly
headline number. regime_read is your own call (journaled + graded);
verdict calls the DAY. qqq_lean = Nasdaq — ~1.3x SPY on rate moves.
Choppy is valid — no edge, say so.

EVENT: NAME_PLACEHOLDER (KIND_PLACEHOLDER), releases TIME_PLACEHOLDER ET
ENGINE: ENGINE_PLACEHOLDER
PRINT: PRINT_PLACEHOLDER
CONTEXT: CTX_PLACEHOLDER
"""


_PROMPT_V = "v4"   # v4: engine prior — judge reaction within regime


def judge(context: dict, event: dict) -> dict[str, Any]:
    """LLM judge over the deterministic bundle; rules fallback."""
    try:
        from litellm import completion
        from app.config import settings
        model = (getattr(settings, "litellm_model", None) or
                 "gpt-4o-mini")
        # strip internals — model gets the engine's STATE, not the
        # deterministic parts that produced it
        blind = {k: v for k, v in context.items()
                 if v is not None and k not in ("policy",
                                                "morning_regime")}
        compact = json.dumps(blind, default=str)[:3500]
        # engine prior = morning regime + the binding constraint —
        # the deterministic lens the model interprets within
        engine = json.dumps({
            **(context.get("morning_regime") or {}),
            "binding_constraint": (context.get("policy") or {})
            .get("binding_constraint"),
            "binding_read": (context.get("policy") or {})
            .get("binding_read"),
            "next_fomc": (context.get("policy") or {})
            .get("next_fomc"),
            "fomc_days_away": (context.get("policy") or {})
            .get("fomc_days_away")}, default=str)
        print_txt = json.dumps(context.get("print_data") or
                               "not yet released / unavailable",
                               default=str)[:600]
        r = completion(
            model=model, temperature=0.1, timeout=30, max_tokens=300,
            messages=[{"role": "user", "content": _PROMPT
                       .replace("NAME_PLACEHOLDER", event["name"])
                       .replace("KIND_PLACEHOLDER", event["kind"])
                       .replace("TIME_PLACEHOLDER", event["time_et"])
                       .replace("PRINT_PLACEHOLDER", print_txt)
                       .replace("ENGINE_PLACEHOLDER", engine)
                       .replace("CTX_PLACEHOLDER", compact)}])
        raw = r.choices[0].message.content or ""
        js = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        # probabilities — normalize to ~100
        probs = {}
        for k in ("p_green", "p_red", "p_choppy"):
            try:
                probs[k] = max(0, float(js.get(k) or 0))
            except (TypeError, ValueError):
                probs[k] = 0.0
        tot = sum(probs.values())
        if tot > 0:
            probs = {k: round(v / tot * 100, 1)
                     for k, v in probs.items()}
        v = js.get("verdict")
        if isinstance(v, dict):          # some models nest it
            v = v.get("direction") or v.get("verdict")
        v = str(v).strip().lower() if v else None
        if v not in ("green", "red", "choppy"):
            v = (max(probs, key=probs.get)[2:]
                 if probs else None)     # argmax fallback
        if v not in ("green", "red", "choppy"):
            raise ValueError(f"bad verdict {v!r}")
        return {"verdict": v,
                "confidence": max(0, min(100, int(js.get("confidence") or 50))),
                "probs": probs,
                "regime_read": str(js.get("regime_read") or "")[:40],
                "qqq_lean": str(js.get("qqq_lean") or "")[:10],
                "qqq_note": str(js.get("qqq_note") or "")[:160],
                "thesis": str(js.get("thesis") or "")[:300],
                "judge": f"llm:{model}@{_PROMPT_V}"}
    except Exception as exc:
        logger.info("llm judge unavailable (%s) — rules verdict", exc)
        return _rules_verdict(context)


def snapshot() -> Optional[dict[str, Any]]:
    """Today's event call — journaled once per event kind."""
    from app.database import db
    ev = todays_event()
    if not ev:
        return None
    # stamp by the event's ET date — date.today() is server-local and
    # drifts a day ahead of ET after 20:00, orphaning the call from
    # the event it judged (calendar attaches by (kind, event_date))
    today = date.fromisoformat(ev["date"])
    prior = db.execute_query(
        "SELECT id FROM event_day_calls WHERE as_of = %s "
        "AND event_kind = %s", (today, ev["kind"]))
    if prior:
        return read_call(today)
    # Don't journal before 07:00 ET — a call frozen in the overnight
    # session locks premarket_spy near zero and wastes the market's
    # first real vote on the print (05:00 ET is when US futures/
    # premarket flow becomes meaningful). Pre-07:00 the day is simply
    # uncalled; the first fetch/job tick after the gate journals it.
    now_et = datetime.now(timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York"))
    if (now_et.hour, now_et.minute) < (7, 0):
        return None
    ctx = gather_context()
    ctx["print_data"] = _the_print(ev["kind"])   # actual vs estimate
    call = judge(ctx, ev)
    db.execute_query(
        """INSERT INTO event_day_calls
             (as_of, event_name, event_kind, verdict, confidence,
              thesis, premarket_spy, context, judge, probs,
              regime_read, qqq_lean, qqq_note, print_data)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (as_of, event_kind) DO NOTHING""",
        (today, ev["name"], ev["kind"], call["verdict"],
         call["confidence"], call["thesis"],
         ctx.get("premarket_spy"), json.dumps(ctx, default=str),
         call["judge"], json.dumps(call.get("probs") or {}),
         call.get("regime_read"), call.get("qqq_lean"),
         call.get("qqq_note"),
         json.dumps(ctx.get("print_data") or [], default=str)))
    logger.info("event-day call: %s → %s (%s%%, %s)",
                ev["kind"], call["verdict"], call["confidence"],
                call["judge"])
    return {**call, "event": ev, "as_of": str(today)}


def _spy_day_ret(day, sym: str = "SPY") -> Optional[float]:
    """Realized daily return for `day` from stored bars."""
    from app.database import db
    bars = db.execute_query(
        "SELECT d, c FROM daily_bars WHERE symbol=%s AND d >= %s "
        "ORDER BY d LIMIT 1", (sym, day))
    prev = db.execute_query(
        "SELECT c FROM daily_bars WHERE symbol=%s AND d < %s "
        "ORDER BY d DESC LIMIT 1", (sym, day))
    if not bars or not prev:
        return None
    return float(bars[0]["c"]) / float(prev[0]["c"]) - 1


_DEBRIEF = """You called an event-day tape and were graded. Reply with ONLY
compact JSON: {"missed":"<=180 chars","watch_next":"<=120 chars"}

YOUR CALL: verdict VERDICT_PLACEHOLDER, probs PROBS_PLACEHOLDER,
regime_read REGIME_PLACEHOLDER, thesis THESIS_PLACEHOLDER
REALIZED: SPY RET_PLACEHOLDER% (Q_RET_PLACEHOLDER% QQQ)
What did you overweight or miss? Be specific — this feeds prompt v4.
"""


def evaluate() -> dict[str, Any]:
    """Grade open calls: SPY+QQQ realized vs verdict, Brier on the
    probability triple, and a debrief pass on misses — the reflection
    that informs the next prompt version."""
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, verdict, probs, regime_read, thesis, "
        "qqq_lean, judge FROM event_day_calls "
        "WHERE graded_at IS NULL AND as_of < CURRENT_DATE")
    graded = 0
    for r in rows:
        spy_ret = _spy_day_ret(r["as_of"])
        if spy_ret is None:
            continue
        qqq_ret = _spy_day_ret(r["as_of"], "QQQ")
        v = r["verdict"]
        actual = ("green" if spy_ret > 0.003 else
                  "red" if spy_ret < -0.003 else "choppy")
        correct = v == actual
        # Brier on the probability triple — 0=perfect, 2=worst
        probs = r.get("probs") or {}
        brier = None
        if isinstance(probs, str):
            try:
                probs = json.loads(probs)
            except Exception:
                probs = {}
        if probs:
            brier = sum(((probs.get(f"p_{o}") or 0) / 100
                         - (1 if o == actual else 0)) ** 2
                        for o in ("green", "red", "choppy"))
        qqq_ok = None
        if qqq_ret is not None and r.get("qqq_lean") in ("up", "down",
                                                         "flat"):
            ql = r["qqq_lean"]
            qqq_ok = ((ql == "up" and qqq_ret > 0.002) or
                      (ql == "down" and qqq_ret < -0.002) or
                      (ql == "flat" and abs(qqq_ret) <= 0.002))
        # debrief on misses — the reflection that informs prompt v4
        debrief = None
        if not correct and str(r.get("judge") or "").startswith("llm"):
            try:
                from litellm import completion
                from app.config import settings
                model = getattr(settings, "litellm_model", None) or \
                    "gpt-4o-mini"
                resp = completion(
                    model=model, temperature=0.1, timeout=30,
                    max_tokens=200,
                    messages=[{"role": "user", "content": _DEBRIEF
                        .replace("VERDICT_PLACEHOLDER", str(v))
                        .replace("PROBS_PLACEHOLDER", json.dumps(probs))
                        .replace("REGIME_PLACEHOLDER",
                                 str(r.get("regime_read") or "?"))
                        .replace("THESIS_PLACEHOLDER",
                                 str(r.get("thesis") or "?"))
                        .replace("RET_PLACEHOLDER",
                                 f"{spy_ret * 100:+.2f}")
                        .replace("Q_RET_PLACEHOLDER",
                                 f"{(qqq_ret or 0) * 100:+.2f}")}])
                raw = resp.choices[0].message.content or ""
                dj = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
                debrief = json.dumps(dj)[:400]
            except Exception:
                debrief = None
        db.execute_query(
            """UPDATE event_day_calls SET spy_ret_1d=%s, correct=%s,
               qqq_ret_1d=%s, qqq_correct=%s, brier=%s, debrief=%s,
               graded_at=now()
               WHERE as_of=%s AND verdict=%s""",
            (round(spy_ret, 4), correct,
             round(qqq_ret, 4) if qqq_ret is not None else None,
             qqq_ok, round(brier, 4) if brier is not None else None,
             debrief, r["as_of"], v))
        graded += 1
    return {"graded": graded}


def read_call(day: Optional[date] = None) -> Optional[dict[str, Any]]:
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, event_name, event_kind, verdict, confidence, "
        "thesis, premarket_spy, judge, spy_ret_1d, correct, probs, "
        "regime_read, qqq_lean, qqq_note, qqq_ret_1d, qqq_correct, "
        "print_data, brier, debrief "
        "FROM event_day_calls WHERE as_of = %s ORDER BY id DESC LIMIT 1",
        (day or date.today(),))
    return rows[0] if rows else None


def record() -> dict[str, Any]:
    """Per-event-kind track record — does the judge actually have edge
    on jobs days vs FOMC days? Fuels the regime-card credibility line."""
    from app.database import db
    rows = db.execute_query(
        """SELECT event_kind, verdict,
                  count(*) FILTER (WHERE graded_at IS NOT NULL) AS n,
                  count(*) FILTER (WHERE correct) AS hits,
                  round(avg(spy_ret_1d)
                        FILTER (WHERE graded_at IS NOT NULL)::numeric, 4)
                    AS avg_ret
           FROM event_day_calls GROUP BY event_kind, verdict
           ORDER BY event_kind, verdict""")
    out: dict[str, Any] = {}
    for r in rows:
        k = out.setdefault(r["event_kind"], {"calls": 0, "graded": 0,
                                             "hits": 0})
        k["calls"] += 1
        k["graded"] += int(r["n"])
        k["hits"] += int(r["hits"])
    for k, v in out.items():
        v["hit_rate"] = round(v["hits"] / v["graded"], 2) \
            if v["graded"] else None
    return out
