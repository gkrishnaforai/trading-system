"""Allocation guidance — WHERE money goes when the tape warns.

The forward card says a dip is likely; dip_character says what kind.
This layer answers the operator's actual question: how much cash to
hold, which sectors are absorbing the rotation, and what signal says
'put the cash back to work'.

All reads are daily_bars — the sector/theme ETFs get a live top-up
on first pass via bars.load, then accrue with the daily refresh.

Output contract (deterministic, advisory):

  cash_buffer_pct    0-50 — staged, never 100%; this cockpit trades
                     around a core book, it doesn't go flat
  rotate_to          sectors showing inflow/rotating-in flow
  rotate_away        sectors showing outflow
  within_ai          which AI sleeve (builders vs operators) leads
  redeploy_when      the specific conditions that release the cash

The cash math is intentionally coarse — tranches, not decimals:
dip probability × dip character × VIX level. Professional desks stage
buffers; they don't pretend to know the bottom tick.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.market_regime.rotation import SECTOR_NAMES, THEME_ETFS

logger = logging.getLogger(__name__)

# sleeves the AI book actually splits into — matches capex_cycle's
# new-build vs operator baskets, expressed as tradable reads
_AI_SLEEVES = {
    "builders":  ["SMH", "ARKK"],          # high-beta construction trade
    "operators": ["QQQ"],                  # mega-cap monetizers
    "defensive": ["XLU", "XLP", "XLV"],    # where money hides
}


def _closes(books: dict, sym: str) -> list[float]:
    return [b.close for b in (books.get(sym) or [])]


def _ret(closes: list[float], n: int) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    a, b = closes[-n - 1], closes[-1]
    return b / a - 1 if a else None


def _sector_flows() -> dict[str, Any]:
    """Sync mini rotation board from stored bars — the same read as
    the async endpoint, cheap enough for every board render."""
    from app.market_data import bars as bars_mod
    etfs = list(dict.fromkeys(
        list(SECTOR_NAMES) + list(THEME_ETFS) + ["SPY", "QQQ"]))
    books = bars_mod.load(etfs, days=70)
    spy = _closes(books, "SPY")
    if len(spy) < 25:
        return {}
    spy20 = _ret(spy, 20) or 0.0
    rows = []
    for sym in etfs:
        if sym == "SPY":
            continue
        c = _closes(books, sym)
        if len(c) < 25:
            continue
        r5, r20 = _ret(c, 5), _ret(c, 20)
        if r5 is None or r20 is None:
            continue
        s50 = sum(c[-50:]) / min(50, len(c))
        above50 = c[-1] > s50
        vs_spy = r20 - spy20
        vols = [b.volume or 0 for b in (books.get(sym) or [])]
        money5 = vol_ratio = None
        if len(vols) >= 21 and sum(vols[-5:]) > 0:
            signed = sum((1 if c[-i] >= c[-i - 1] else -1)
                         * vols[-i] for i in range(1, 6))
            money5 = signed / sum(vols[-5:])      # -1..+1 net money dir
            avg20 = sum(vols[-21:-1]) / 20
            vol_ratio = (sum(vols[-5:]) / 5) / avg20 if avg20 else None
        if r5 > 0.01 and not above50:
            flow = "rotating_in"
        elif r5 > 0.005 and above50:
            flow = "inflow"
        elif r5 < -0.01 and above50 is False:
            flow = "outflow"
        else:
            flow = "quiet"
        # money confirms the label: signed volume agrees + expanding
        vol_conf = (money5 is not None and vol_ratio is not None
                    and ((flow in ("rotating_in", "inflow")
                          and money5 > 0 and vol_ratio > 1.0)
                         or (flow == "outflow" and money5 < 0)))
        rows.append({"etf": sym,
                     "name": SECTOR_NAMES.get(sym) or THEME_ETFS.get(sym),
                     "ret5": round(r5, 4), "ret20": round(r20, 4),
                     "vs_spy20": round(vs_spy, 4),
                     "above50": above50, "flow": flow,
                     "money5": round(money5, 2) if money5 is not None
                     else None,
                     "vol_ratio": round(vol_ratio, 2)
                     if vol_ratio is not None else None,
                     "vol_confirmed": vol_conf})
    rows.sort(key=lambda r: r["ret5"], reverse=True)
    return {"rows": rows,
            "inflow": [r["etf"] for r in rows if r["flow"] == "inflow"],
            "rotating_in": [r["etf"] for r in rows
                            if r["flow"] == "rotating_in"],
            "outflow": [r["etf"] for r in rows if r["flow"] == "outflow"]}


def plan(dip_char: Optional[dict], forward: Optional[dict],
         vix: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Compose the allocation read. Returns None if no bars at all."""
    flows = _sector_flows()
    if not flows:
        return None
    dc = dip_char or {}
    fw = forward or {}
    char = dc.get("character") or "no_dip"
    p_deep = fw.get("p_deeper_dip_20d") or 0

    # ---- cash buffer: staged, bounded, and explained ----
    cash, why = 0, []
    if p_deep >= 65:
        cash += 25; why.append(f"deep-dip odds {p_deep}% — stage a real buffer")
    elif p_deep >= 50:
        cash += 15; why.append(f"dip odds {p_deep}% — light buffer")
    elif p_deep >= 40:
        cash += 10
    if char == "broad_deleveraging":
        cash += 20
        why.append("deleveraging pattern — correlation kills diversification")
    elif char == "rotation_out_of_ai":
        cash += 10
        why.append("stealth unwind — raise cash where it's bleeding, "
                   "not blanket")
    elif char == "narrow_leadership":
        cash += 5
        why.append("AI is the shelter — small buffer only, the risk "
                   "is leaders cracking late")
    if vix is not None and vix >= 25:
        cash += 10; why.append(f"VIX {vix:.0f} — vol tax on being early")
    elif vix is not None and vix >= 20:
        cash += 5
    if char == "no_dip" and p_deep < 40:
        cash = 0
        why = ["no staged buffer needed — deploy on setups, not calendar"]
    cash = min(50, cash)

    # ---- where the money is actually going ----
    # Backtested split: volume-confirmed rotation hits ~80% at 20d,
    # price-only hits ~34% — so vol_confirmed names lead the list and
    # unconfirmed ones are marked thin rather than trusted.
    rows = {r["etf"]: r for r in flows.get("rows") or []}
    def _ranked(cands):
        conf = [s for s in cands
                if (rows.get(s) or {}).get("vol_confirmed")]
        thin = [s for s in cands if s not in conf]
        return conf, thin
    rotating_in = flows.get("rotating_in") or []
    inflow = flows.get("inflow") or []
    outflow = flows.get("outflow") or []
    rotate_to, rotate_away = [], []
    defensive_names = set(_AI_SLEEVES["defensive"])
    if char == "rotation_out_of_ai":
        # destination: whoever is absorbing the flow that ISN'T AI
        cands = [s for s in (rotating_in + inflow)
                 if s not in ("SMH", "ARKK")]
        conf, thin = _ranked(cands)
        rotate_to = (conf + thin)[:3]
    elif char == "broad_deleveraging":
        # in deleveraging, sectors don't protect — but show which
        # defensives are catching the bid for partial rotation
        cands = [s for s in rotating_in + inflow
                 if s in defensive_names]
        conf, thin = _ranked(cands or rotating_in[:2])
        rotate_to = (conf + thin)[:3]
    else:
        conf, thin = _ranked(rotating_in + inflow)
        rotate_to = (conf + thin)[:3]
    # outflow requires the money read too — a price dip on shrinking
    # volume is a lull, not distribution
    conf_out, thin_out = _ranked(outflow)
    rotate_away = (conf_out + thin_out)[:3]
    rotate_note = None
    if rotate_to and not conf:
        rotate_note = ("no volume confirmation — flows marked are "
                       "price drift, not repositioning; size small")

    # ---- within-AI split — builders vs operators ----
    builders = [rows[s]["ret5"] for s in _AI_SLEEVES["builders"]
                if s in rows]
    operators = [rows[s]["ret5"] for s in _AI_SLEEVES["operators"]
                 if s in rows]
    within_ai = None
    if builders and operators:
        b, o = sum(builders) / len(builders), sum(operators) / len(operators)
        if b - o > 0.01:
            within_ai = "builders leading — new-build beta is catching "
            "the flow"
        elif o - b > 0.01:
            within_ai = ("operators leading — money prefers the "
                         "monetizers over construction")
        else:
            within_ai = "AI sleeves moving together"

    # ---- redeploy triggers — what releases the buffer ----
    if cash > 0:
        redeploy = [
            "dip_phase 'turning_up' on leaders (≥3 of 5 health legs)",
            "VIX back under 20 or 5d change negative",
            "SPY reclaims EMA20 / breadth stops falling 2 days",
        ]
        if char == "narrow_leadership":
            redeploy.insert(0, "AI RS still widening — leaders first, "
                               "in tranches")
        elif char == "broad_deleveraging":
            redeploy.insert(0, "correlation breaking down — sectors "
                               "stop moving as one")
    else:
        redeploy = []

    return {
        "cash_buffer_pct": cash, "cash_why": why,
        "rotate_to": rotate_to, "rotate_away": rotate_away,
        "rotate_confirmed": conf,
        "rotate_note": rotate_note,
        "within_ai": within_ai,
        "redeploy_when": redeploy,
        "sector_rows": flows.get("rows") or [],
        "note": ("staged buffer, not a market call — deploy in "
                 "tranches on the triggers, never all-at-once"),
    }
