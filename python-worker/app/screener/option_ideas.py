"""Option structure ideas — rules-only suggestions mapped from the existing
screener/monitor facts. No options-chain or greeks data on the plan, so the
output is *which structure fits this situation and roughly where* — the
human still prices and places it.

Mapping (standard covered-call / protective-put / spread playbook):
  held + extended/climax    → covered call at/above the 20d-high pivot
                              (sell the strength you already own)
  held + weakening regime   → protective put near the ATR stop
  ready entry setup         → bull call spread at entry→target, plus a
                              cash-secured put at support when you'd
                              happily own the name at that strike
  not held + %b-extended    → cash-secured put at the SMA20 mean —
                              get paid to wait for the reversion level
                              instead of chasing the stretch
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ENTRY_SETUPS = {"first_pullback", "mean_reversion", "breakout",
                 "breakout_retest", "episodic_pivot"}


def option_ideas(max_items: int = 10) -> dict[str, Any]:
    try:
        from app.database import db
        run = db.execute_query(
            "SELECT results FROM screen_runs ORDER BY ran_at DESC LIMIT 1")
        if not run:
            return {"ideas": [], "note": "no screen run yet"}
        rows = run[0].get("results") or []
    except Exception as exc:
        logger.debug("option ideas query failed: %s", exc)
        return {"ideas": [], "note": "screen data unavailable"}

    ideas: list[dict] = []

    for r in rows:
        price, stop, pivot = r.get("price"), r.get("stop"), r.get("pivot")
        if not price:
            continue
        ret20, perm = r.get("ret20") or 0, r.get("stock_permission")
        extended = (ret20 or 0) >= 0.20 and (r.get("dd20") or -1) >= -0.05

        if r.get("in_portfolio"):
            if extended:
                ideas.append({
                    "symbol": r["symbol"], "context": "held · extended",
                    "structure": "covered call",
                    "zone": f"call strike ≥ ${pivot:,.0f} (20d-high pivot), 30–45d"
                            if pivot else "OTM 5–8%, 30–45d",
                    "why": f"ret20 {ret20 * 100:+.0f}% — harvest premium into "
                           "strength; called away at resistance is a good exit",
                })
            elif perm in {"restricted", "disabled"} or (ret20 or 0) < -0.05:
                ideas.append({
                    "symbol": r["symbol"], "context": "held · weakening",
                    "structure": "protective put",
                    "zone": f"put strike ≈ ${stop:,.0f} (ATR stop), 30–60d"
                            if stop else "5–8% OTM, 30–60d",
                    "why": f"stock regime {perm} — insure the position "
                           "instead of guessing the bottom",
                })
            elif perm == "allowed" and pivot:
                ideas.append({
                    "symbol": r["symbol"], "context": "held · strong",
                    "structure": "covered call",
                    "zone": f"call strike ≈ ${pivot:,.0f} (resistance), 30–45d",
                    "why": "quiet uptrend — sell the level that caps you anyway",
                })
        # Cash-secured put — on a held name this is wheel accumulation:
        # get paid to add more at the support level. Needs a live entry
        # setup or a quiet uptrend, acceptable fundamentals, no knife.
        add_ctx = "held · add-on" if r.get("in_portfolio") else "entry"
        if perm in {"allowed", "limited"} and not r.get("falling_knife") \
                and r.get("fund_signal") != "weak" and stop:
            if (r.get("score") or 0) >= 60 \
                    and r.get("setup_type") in _ENTRY_SETUPS:
                ideas.append({
                    "symbol": r["symbol"], "context": f"entry · {r['setup_type']}",
                    "structure": "bull call spread",
                    "zone": (f"buy ~${price:,.0f} call / sell ~${r['target']:,.0f} "
                             f"call, 30–45d — max loss = debit"
                             if r.get("target") else "defined-risk spread"),
                    "why": f"score {r['score']:.0f} — defined-risk entry, "
                           "capped upside but no assignment",
                })
                ideas.append({
                    "symbol": r["symbol"], "context": f"{add_ctx} · {r['setup_type']}",
                    "structure": "cash-secured put",
                    "zone": f"put strike ≈ ${stop:,.0f} (ATR stop/support), "
                            f"30–45d · reserve ${stop * 100:,.0f}/contract",
                    "why": f"score {r['score']:.0f} + fund "
                           f"{r.get('fund_signal') or 'n/a'} — get paid to "
                           "buy the pullback level; assigned = you add a "
                           "name you wanted at support anyway",
                })
            elif perm == "allowed" and not extended and r.get("sma20") \
                    and (r.get("pctb") or 0) < 1.0:
                sma20 = r["sma20"]
                ideas.append({
                    "symbol": r["symbol"], "context": add_ctx,
                    "structure": "cash-secured put",
                    "zone": f"put strike ≈ ${sma20:,.0f} (SMA20 mean), "
                            f"30–45d · reserve ${sma20 * 100:,.0f}/contract",
                    "why": "quiet uptrend — sell a put at the mean to add "
                           "on the next dip; assigned = more of a name "
                           "you already like at SMA20",
                })

    # Structure-priority order with a per-structure cap — one type can't
    # crowd out the rest of the board.
    def _pri(i: dict) -> int:
        s, c = i["structure"], i["context"]
        if s == "covered call" and "extended" in c:
            return 0
        if s == "cash-secured put":
            return 1
        if s == "bull call spread":
            return 2
        if s == "protective put":
            return 3
        return 4

    ideas.sort(key=_pri)
    out, counts = [], {}
    for i in ideas:
        s = i["structure"]
        if counts.get(s, 0) >= 8:
            continue
        counts[s] = counts.get(s, 0) + 1
        out.append(i)
    return {
        "ideas": out[:max_items * 2],
        "note": "Structure suggestions only — no greeks/chain pricing on "
                "this plan; check the chain before acting.",
    }
