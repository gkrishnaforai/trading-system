"""Capital planner — 'I have $X, build me a book.'

Composes, doesn't invent: regime posture sets the aggressiveness
(market regime decides HOW aggressive, never WHAT to buy), readiness
boards supply candidates, trade_plans.suggest() supplies real
structure levels, and accepted books journal as trade_plans rows —
the status ladder, alert feed and email digest then track them free.

The honesty contract: sleeves fill only with names that qualified.
If the market offers 3 swing setups, you get 3 — the rest stays
cash, and the book says so.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# stance → (invest, swing, options, cash) sleeve mix. Regime scales
# risk appetite — never picks symbols.
_MIX = {
    "FEAR — DEPLOY":   (0.40, 0.35, 0.15, 0.10),
    "NEUTRAL":         (0.35, 0.30, 0.10, 0.25),
    "GREED — HARVEST": (0.30, 0.20, 0.10, 0.40),
    "DEFENSIVE":       (0.10, 0.05, 0.15, 0.70),
}
_DIP_RANK = {"confirmed": 3, "turning_up": 2, "stabilizing": 1}
_PUT_SIDE_MIN = 60.0   # put_entry.score floor — short-side alpha
                       # needs a real score, not just readiness
_PUT_SIDE_MAX = 0.4    # max share of the options sleeve in puts
                       # when the stance isn't defensive


def _top_parts(parts: dict, n: int = 3) -> str:
    """Top normalized rank contributors — 'rs_pct 90 · dip 100' —
    the 'why this rank' the page can display beside the score."""
    if not parts:
        return ""
    scored = sorted(
        ((k, v.get("norm") or 0) for k, v in parts.items()
         if isinstance(v, dict) and v.get("norm") is not None),
        key=lambda x: -x[1])
    return " · ".join(f"{k} {int(v)}" for k, v in scored[:n])
_MAX_PER_SECTOR = 2
_OPTION_DEBIT_PROXY = 0.35   # deep-ITM LEAP ≈ 35% of spot, per share


def _posture() -> dict[str, Any]:
    """Latest journaled regime card — stance + permissions + hedge
    tier + forward probs. Stored by the daily-board job; free."""
    from app.database import db
    r = db.execute_query(
        "SELECT as_of, stance, payload FROM regime_snapshots"
        " ORDER BY as_of DESC LIMIT 1")
    if not r:
        return {"stance": "NEUTRAL", "note": "no regime snapshot"}
    p = r[0]["payload"]
    if isinstance(p, str):
        p = json.loads(p)
    perm = (((p.get("morning") or {}).get("buckets") or {})
            .get("evidence") or {}).get("permissions") or {}
    return {"as_of": str(r[0]["as_of"]), "stance": r[0]["stance"],
            "regime": p.get("regime"), "note": p.get("note"),
            "size_mult": perm.get("size_multiplier") or 1.0,
            "dip_buying": bool(perm.get("dip_buying")),
            "shorts_allowed": bool(perm.get("shorts_allowed")),
            "p_deeper": (p.get("forward") or {}).get("p_deeper_dip_20d"),
            "hedge": p.get("hedge") or {}}


def _sectors(syms: list[str]) -> dict[str, str]:
    from app.database import db
    if not syms:
        return {}
    rows = db.execute_query(
        "SELECT symbol, COALESCE(sector, industry) s FROM stocks"
        " WHERE symbol = ANY(:x)", {"x": syms})
    return {r["symbol"]: r["s"] for r in rows}


def propose(capital: float, risk_pct: float = 1.0,
            target_pct: Optional[float] = None,
            sleeves: Optional[dict] = None) -> dict:
    """Deterministic book construction. Returns sleeves + positions
    with real levels, sizing math, honesty notes, and the hedge
    tranche. Advisory — nothing is entered anywhere."""
    import os
    from app.signals import stock_health, trade_plans, posture
    tgt = (target_pct if target_pct is not None else
           float(os.environ.get("PORTFOLIO_TARGET_PCT", "24")))
    po = _posture()
    stance = po["stance"] if po["stance"] in _MIX else "NEUTRAL"
    inv, sw, op, cash = sleeves or _MIX[stance]
    # forward-dip brake: >50% deeper-dip odds shifts 10pts to cash
    if (po.get("p_deeper") or 0) >= 50 and cash < 0.60:
        cash += 0.10
        sw = max(0.0, sw - 0.10)
    notes: list[str] = []
    # trade posture — the 'can we initiate today' layer over the
    # regime card. new_longs=false folds the long sleeves to cash;
    # shorts=true makes the options sleeve all-puts.
    pos = posture.current()
    if not pos.get("new_longs", True):
        cash += inv + sw
        inv = sw = 0.0
        notes.append(f"posture {pos['posture']} — no new longs "
                     f"today ({pos.get('matched') or '—'}); invest + "
                     "swing sleeves fold to cash")
    put_only = pos.get("shorts") and not pos.get("new_longs")
    if put_only:
        notes.append("posture permits shorts — options sleeve is "
                     "leap_put only")
    mult = po.get("size_mult") or 1.0
    alloc = {"invest": capital * inv * mult,
             "swing": capital * sw * mult,
             "options": capital * op * mult}
    alloc["cash"] = capital - sum(alloc.values())

    B = stock_health.board()
    sec = B.get("sections") or {}
    positions: list[dict] = []
    used_sec: dict[str, int] = {}
    used_sym: set[str] = set()
    risk_budget = capital * risk_pct / 100.0

    def _sec_ok(sym, smap):
        s = smap.get(sym) or "?"
        if used_sec.get(s, 0) >= _MAX_PER_SECTOR:
            return False
        used_sec[s] = used_sec.get(s, 0) + 1
        return True

    cands = {k: [r for r in (sec.get(k) or []) if r["state"] == "ready"]
             for k in ("invest", "swing", "leap_call", "leap_put")}
    all_syms = [r["symbol"] for v in cands.values() for r in v]
    smap = _sectors(list(set(all_syms)))

    # ---- invest sleeve — core positions, equal-weight slots
    inv_n = max(3, min(8, int(alloc["invest"] / max(capital, 1)
                              * 20 + 2))) if alloc["invest"] > 0 else 0
    inv_pick = 0
    for r in sorted(cands["invest"],
                    key=lambda x: (-(x.get("rank") or 0),
                                   x["symbol"])):
        sym = r["symbol"]
        if inv_pick >= inv_n or sym in used_sym:
            continue
        sug = trade_plans.suggest(sym, "invest")
        if not sug.get("entry_px"):
            continue
        if sug.get("pulse_action") in ("reduce", "avoid"):
            notes.append(f"{sym} skipped — readiness ready but pulse "
                         f"flags {sug['pulse_action']} (conflict)")
            continue
        if not _sec_ok(sym, smap):
            notes.append(f"{sym} skipped — sector cap ({smap.get(sym)})")
            continue
        slot = alloc["invest"] / max(inv_n, 1)
        qty = max(1, int(slot / sug["entry_px"]))
        positions.append({
            "symbol": sym, "sleeve": "invest", "use_case": "invest",
            "direction": "long", "qty": qty,
            "entry_px": sug["entry_px"], "stop_px": sug["stop_px"],
            "stop_basis": sug["stop_basis"],
            "target1_px": None, "target2_px": None,
            "est_cost": round(qty * sug["entry_px"], 0),
            "risk_usd": None,
            "trail_rule": sug["trail_rule"],
            "time_stop_days": sug["time_stop_days"],
            "thesis": f"invest-ready {r['score']}/{r['of']} · "
                      f"rank {r.get('rank') or '—'} "
                      f"({_top_parts(r.get('parts'))}) · "
                      f"{r['mom']}/{r['fund']} — core hold, "
                      "structure stop is the review line",
            "readiness": f"{r['score']}/{r['of']}",
            "rank": r.get("rank"),
            "why": _top_parts(r.get("parts"))})
        used_sym.add(sym)
        inv_pick += 1
    if inv_pick < inv_n:
        notes.append(f"invest sleeve: only {inv_pick}/{inv_n} slots "
                     "qualified — the market isn't offering that many "
                     "fully-ready long-term entries today")

    # ---- swing sleeve — risk-based sizing off the real stop.
    # Suggest once per candidate (DB hit), then rank score → dip
    # maturity: confirmed dips before early ones.
    swing_cands = []
    for r in cands["swing"]:
        if r["symbol"] not in used_sym:
            swing_cands.append(
                (r, trade_plans.suggest(r["symbol"], "swing")))
    swing_cands.sort(key=lambda x: (
        -(x[0].get("rank") or 0),
        -_DIP_RANK.get(x[1].get("dip_phase") or "", 0),
        x[0]["symbol"]))
    sw_notional = 0.0
    for r, sug in swing_cands:
        sym = r["symbol"]
        if sw_notional >= alloc["swing"]:
            break
        e, s = sug.get("entry_px"), sug.get("stop_px")
        if not e or not s or e <= s:
            notes.append(f"{sym} skipped — no structure stop to size")
            continue
        if sug.get("pulse_action") in ("reduce", "avoid"):
            notes.append(f"{sym} skipped — pulse flags "
                         f"{sug['pulse_action']}")
            continue
        if not _sec_ok(sym, smap):
            continue
        per_risk = e - s
        qty = int(risk_budget / per_risk)
        cap = min(alloc["swing"] * 0.30, alloc["swing"] - sw_notional)
        qty = min(qty, int(cap / e))
        if qty <= 0:
            continue
        cost = qty * e
        sw_notional += cost
        positions.append({
            "symbol": sym, "sleeve": "swing", "use_case": "swing",
            "direction": "long", "qty": qty,
            "entry_px": e, "stop_px": s, "stop_basis": sug["stop_basis"],
            "target1_px": sug["target1_px"],
            "target2_px": sug["target2_px"],
            "est_cost": round(cost, 0),
            "risk_usd": round(qty * per_risk, 0),
            "trail_rule": sug["trail_rule"],
            "time_stop_days": sug["time_stop_days"],
            "thesis": f"swing-ready {r['score']}/{r['of']} · "
                      f"rank {r.get('rank') or '—'} "
                      f"({_top_parts(r.get('parts'))}) · "
                      f"{r['mom']} · dip {sug.get('dip_phase') or '—'}",
            "readiness": f"{r['score']}/{r['of']}",
            "rank": r.get("rank"),
            "why": _top_parts(r.get("parts"))})
        used_sym.add(sym)
    if sw_notional < alloc["swing"] * 0.5 and alloc["swing"] > 0:
        notes.append(f"swing sleeve only ${sw_notional:,.0f} deployed "
                     f"of ${alloc['swing']:,.0f} — rest stays cash "
                     "until more setups confirm")

    # ---- options sleeve — leap calls when bullish-ish, puts when
    # defensive. Sizing by estimated debit (deep-ITM proxy). In
    # non-defensive stances the sleeve runs BOTH sides: top leap_call
    # names, plus leap_put-ready names whose put_entry.score clears
    # _PUT_SIDE_MIN — the short-side alpha slice earns up to
    # _PUT_SIDE_MAX of the sleeve (hedge-lite, not a hedge of beta).
    want_puts = (put_only or stance == "DEFENSIVE" or (
        (po.get("hedge") or {}).get("tier") in ("elevated", "crisis")))
    opt_debits: dict[str, float] = {}
    # posture gates each SIDE: a leap_call is a new long, a leap_put
    # is a short. Both blocked → the sleeve folds to cash.
    allow_calls = bool(pos.get("new_longs", True)) and not want_puts
    allow_puts = want_puts or bool(pos.get("shorts"))
    has_puts = (allow_puts and not want_puts
                and alloc["options"] > 0 and any(
                    (r.get("score") or 0) >= _PUT_SIDE_MIN
                    and r["symbol"] not in used_sym
                    for r in cands["leap_put"]))
    call_cap = (1 - _PUT_SIDE_MAX) if has_puts else 1.0
    side_caps: dict[str, float] = {}
    if want_puts:
        side_caps["leap_put"] = 1.0
    else:
        if allow_calls:
            side_caps["leap_call"] = call_cap
        if allow_puts:
            side_caps["leap_put"] = _PUT_SIDE_MAX
    if not side_caps and alloc["options"] > 0:
        alloc["cash"] += alloc["options"]
        alloc["options"] = 0.0
        notes.append(f"posture {pos['posture']} — neither longs "
                     "nor shorts permitted; options sleeve folds "
                     "to cash")
    for uc, cap_frac in side_caps.items():
        uc_cap = alloc["options"] * cap_frac
        rows = sorted(cands[uc],
                      key=lambda x: (-(x.get("rank") or 0),
                                     x["symbol"]))
        picked = 0
        for r in rows:
            if picked >= 4:
                break
            sym = r["symbol"]
            spent = sum(opt_debits.values())
            if (sym in used_sym or spent >= alloc["options"]
                    or opt_debits.get(uc, 0) >= uc_cap):
                continue
            if (not want_puts and uc == "leap_put"
                    and (r.get("score") or 0) < _PUT_SIDE_MIN):
                continue  # short-side alpha needs a real score, not
                          # just readiness
            sug = trade_plans.suggest(sym, uc)
            spot = sug.get("spot") or sug.get("entry_px")
            if not spot:
                continue
            est = spot * _OPTION_DEBIT_PROXY * 100
            qty = max(1, int(uc_cap * 0.4 / est)) if est else 0
            qty = min(qty, 3)
            debit = est * qty
            room = min(alloc["options"] - spent,
                       uc_cap - opt_debits.get(uc, 0))
            if debit > room:
                qty = int(room / est)
                if qty <= 0:
                    notes.append(
                        f"{sym} skipped — {uc} rank "
                        f"{r.get('rank') or '—'} qualified but one "
                        f"est contract ≈${est:,.0f} exceeds the "
                        f"${room:,.0f} left in its sleeve slice")
                    continue
                debit = est * qty
            opt_debits[uc] = opt_debits.get(uc, 0) + debit
            positions.append({
                "symbol": sym, "sleeve": "options", "use_case": uc,
                "direction": sug["direction"], "qty": qty,
                "entry_px": spot, "stop_px": sug["stop_px"],
                "stop_basis": sug["stop_basis"],
                "target1_px": sug["target1_px"],
                "target2_px": sug["target2_px"],
                "est_cost": round(debit, 0),
                "risk_usd": round(debit, 0),
                "trail_rule": sug["trail_rule"],
                "time_stop_days": sug["time_stop_days"],
                "thesis": f"{uc}-ready {r['score']}/{r['of']} · "
                          f"rank {r.get('rank') or '—'} "
                          f"({_top_parts(r.get('parts'))}) — "
                          "est debit ≈35% of spot; price the actual "
                          "contract on the LEAPS page",
                "readiness": f"{r['score']}/{r['of']}",
                "rank": r.get("rank"),
                "why": _top_parts(r.get("parts"))})
            used_sym.add(sym)
            picked += 1
    if not opt_debits and alloc["options"] > 0:
        notes.append("options sleeve: no options-ready names "
                     "qualified — sleeve folds back to cash")

    deployed = sum(p["est_cost"] for p in positions)
    book_cash = capital - deployed
    tot_risk = sum(p["risk_usd"] or 0 for p in positions)
    hedge = {}
    hc = po.get("hedge") or {}
    if (hc.get("coverage_target_pct") or 0) > 0:
        try:
            from app.options import hedge_book
            hedge = hedge_book.suggest_structure()
            hedge["budget_cap_usd"] = round(
                capital * (hc.get("budget_cap_pct") or 0) / 100, 0)
        except Exception:
            hedge = {}

    return {
        "capital": capital, "target_pct": tgt,
        "risk_pct": risk_pct,
        "posture": {"as_of": po.get("as_of"), "stance": stance,
                    "regime": po.get("regime"), "note": po.get("note"),
                    "size_mult": mult, "p_deeper": po.get("p_deeper"),
                    "dip_buying": po.get("dip_buying"),
                    "shorts_allowed": po.get("shorts_allowed"),
                    # the trade-posture layer — today's permissions
                    "trade": pos.get("posture"),
                    "trade_rule": pos.get("matched"),
                    "trade_note": pos.get("note"),
                    "new_longs": pos.get("new_longs"),
                    "shorts": pos.get("shorts"),
                    "hedge_on": pos.get("hedge_on")},
        "sleeves": {k: round(v, 0) for k, v in alloc.items()},
        "positions": positions,
        "hedge": hedge,
        "totals": {"deployed": round(deployed, 0),
                   "cash": round(book_cash, 0),
                   "risk_usd": round(tot_risk, 0),
                   "risk_pct": round(tot_risk / capital * 100, 1)
                              if capital else None,
                   "positions": len(positions)},
        "notes": notes,
        "goal_month_usd": round(capital *
                                ((1 + tgt / 100) ** (1 / 12) - 1), 0),
    }


def accept(payload: dict) -> dict:
    """Journal the accepted book + open one trade_plan per position —
    the status ladder / event feed / email digest then track them.
    thesis carries the book tag so the daily view can group."""
    from app.database import db
    row = db.execute_query(
        "INSERT INTO planner_books (capital, target_pct, risk_pct,"
        " stance, regime, payload, status)"
        " VALUES (:c, :t, :r, :s, :g, CAST(:p AS jsonb), 'accepted')"
        " RETURNING id",
        {"c": payload["capital"], "t": payload["target_pct"],
         "r": payload["risk_pct"], "s": (payload.get("posture") or {})
         .get("stance"), "g": (payload.get("posture") or {})
         .get("regime"), "p": json.dumps(payload, default=str)})
    bid = row[0]["id"]
    created = []
    for pos in payload.get("positions") or []:
        r = db.execute_query(
            "INSERT INTO trade_plans (symbol, use_case, direction,"
            " entry_px, entry_date, qty, stop_px, stop_basis,"
            " target1_px, target2_px, trail_rule, time_stop_days,"
            " thesis, entry_snapshot) VALUES (:s,:u,:d,:ep,CURRENT_DATE,"
            " :q,:sp,:sb,:t1,:t2,:tr,:ts,:th,CAST(:sn AS jsonb))"
            " RETURNING id",
            {"s": pos["symbol"], "u": pos["use_case"],
             "d": pos["direction"], "ep": pos["entry_px"],
             "q": pos["qty"], "sp": pos["stop_px"],
             "sb": pos["stop_basis"], "t1": pos["target1_px"],
             "t2": pos["target2_px"], "tr": pos["trail_rule"],
             "ts": pos["time_stop_days"],
             "th": f"[book#{bid}] {pos.get('thesis') or ''}",
             "sn": json.dumps(pos, default=str)})
        if r:
            created.append(r[0]["id"])
    return {"book_id": bid, "plan_ids": created}


def daily(book_id: Optional[int] = None) -> dict:
    """Today's plan for the accepted book: each plan's live status,
    plus what changed overnight (readiness/pulse transitions on book
    symbols, regime shift, unfilled sleeves gaining candidates)."""
    from app.database import db
    from app.signals import trade_plans
    bk = db.execute_query(
        "SELECT * FROM planner_books WHERE status='accepted'"
        + (" AND id=:b" if book_id else "")
        + " ORDER BY id DESC LIMIT 1",
        {"b": book_id} if book_id else {})
    if not bk:
        return {"book": None, "actions": [],
                "note": "no accepted book — propose one first"}
    book = bk[0]
    payload = book["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    plans = db.execute_query(
        "SELECT * FROM trade_plans WHERE status='open'"
        " AND thesis LIKE :t", {"t": f"[book#{book['id']}]%"})
    # book-payload positions carry the rank evidence captured at
    # proposal time — the 'why it was picked' the page displays
    _pick = {p["symbol"]: p for p in payload.get("positions") or []}
    actions, pos_status = [], []
    for p in plans:
        ev = trade_plans.eval_plan(dict(p))
        c = ev.get("ctx") or {}
        pk = _pick.get(p["symbol"]) or {}
        pos_status.append({"symbol": p["symbol"],
                           "use_case": p["use_case"],
                           "rank": pk.get("rank"),
                           "why": pk.get("why"),
                           "status": ev.get("status"),
                           "hint": ev.get("action_hint"),
                           "r": c.get("r"), "days": c.get("days"),
                           "dist_stop": c.get("dist_stop")})
        if ev.get("status") not in (None, "on_track"):
            actions.append({"kind": "plan_status",
                            "symbol": p["symbol"],
                            "status": ev["status"],
                            "detail": ev.get("why")})
    # overnight transitions on book symbols
    syms = [p["symbol"] for p in plans] or ["__none__"]
    tr = db.execute_query(
        """WITH daily AS (
             SELECT DISTINCT ON (symbol, use_case, as_of)
                    symbol, use_case, state, as_of
             FROM readiness_evals
             ORDER BY symbol, use_case, as_of, created_at DESC),
           ranked AS (
             SELECT *, row_number() OVER (PARTITION BY symbol, use_case
                                          ORDER BY as_of DESC) rn
             FROM daily)
        SELECT a.symbol, a.use_case, b.state prev, a.state cur
        FROM ranked a JOIN ranked b
          ON b.symbol=a.symbol AND b.use_case=a.use_case AND b.rn=2
        WHERE a.rn=1 AND a.state != b.state
          AND a.symbol = ANY(:s)""", {"s": syms})
    for r in tr:
        kind = ("entry_ready" if r["cur"] == "ready"
                else "degraded" if r["cur"] == "no" else "improving")
        actions.append({"kind": kind, "symbol": r["symbol"],
                        "detail": f"{r['use_case']} {r['prev']}→"
                                  f"{r['cur']}"})
    # regime shift since book date
    po = _posture()
    regime_note = None
    if po.get("stance") and po["stance"] != book.get("stance"):
        regime_note = (f"stance {book.get('stance')} → {po['stance']}"
                       " — re-run propose to re-mix sleeves")
        actions.append({"kind": "regime_shift", "symbol": None,
                        "detail": regime_note})
    return {"book": {"id": book["id"], "as_of": str(book["as_of"]),
                     "capital": float(book["capital"]),
                     "stance": book["stance"],
                     "target_pct": float(book["target_pct"])},
            "positions": pos_status, "actions": actions,
            "regime": {"stance": po.get("stance"),
                       "note": po.get("note"),
                       "as_of": po.get("as_of")},
            "regime_shift": regime_note}
