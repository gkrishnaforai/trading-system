"""June–July 2026 acceptance replay — did the early-warning legs
fire BEFORE SMH's price broke, and did the leaderboard name the
real destination (Industrials per the June flow data, not Energy)?

Assertions:
  A1  breadth_break < price_break — %above20d SMA rolls under 50%
      before SMH ret20 turns negative
  A2  RS roll-over precedes price roll-over — SMH/QQQ 20d RS delta
      negative before SMH absolute ret20 negative
  A3  leaderboard names XLI top-3 by mid-June (flow data says
      Industrials attracted the allocations, not Energy)
  A4  flow_status = 'unavailable' on every row — no confirmation
      the engine couldn't see
  A5  false-alarm rate — count of rotation_probable+ days

Run inside the worker container:
  python -m scripts.replay_june2026
"""
from datetime import date

from app.signals import sector_rotation_ew as ew


def run() -> dict:
    rows = ew.replay("SMH", date(2026, 6, 1), date(2026, 7, 31))
    if not rows:
        return {"error": "no SMH bars in window"}

    # A1: breadth break (pct_above20 < 50) vs price break (ret20<0)
    b_break = next(
        (r["as_of"] for r in rows
         if (r["legs"]["constituent_breadth"]
             .get("pct_above20") or 100) < 50), None)
    p_break = next(
        (r["as_of"] for r in rows
         if ew._ret(ew._cl(ew._bars("SMH", 26, date.fromisoformat(
             r["as_of"]))), 20) or 0 < 0), None)

    # A2: SMH/QQQ RS 20d delta negative before price negative
    rs_neg = next(
        (r["as_of"] for r in rows
         if (r["legs"]["pairwise_rs"].get("deltas_20d", {})
             .get("QQQ", 0) or 0) < 0), None)

    # A3: XLI in top-3 destinations by mid-June
    mid = [r for r in rows if "2026-06-10" <= r["as_of"] <= "2026-06-20"]
    xli_top3 = sum(
        any(d["etf"] == "XLI" for d in r["dest_scores"][:3])
        for r in mid)

    # A4/A5
    flow_ok = all(r["flow_status"] == "unavailable" for r in rows)
    probable = [r["as_of"] for r in rows
                if r["state"] in ("rotation_probable",)]
    states = {}
    for r in rows:
        states[r["state"]] = states.get(r["state"], 0) + 1

    return {
        "window": f"{rows[0]['as_of']} → {rows[-1]['as_of']}",
        "days": len(rows), "states": states,
        "A1_breadth_breaks_first": b_break, "A1_price_break": p_break,
        "A1_pass": bool(b_break and p_break and b_break < p_break),
        "A2_rs_negative_before_price": rs_neg,
        "A3_xli_top3_midjune_days": f"{xli_top3}/{len(mid)}",
        "A4_no_flow_claims": flow_ok,
        "A5_probable_days": len(probable), "A5_dates": probable[:12],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
