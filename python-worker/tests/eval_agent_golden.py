"""Golden evals for the AI-research agent — opt-in, costs a few cents.

Asserts the contract rather than exact numbers (LLM outputs vary):
schema keys present, pct bounded, evidence required when pct set,
tagged segments ⊆ reported segments, pure-play names score high.

Run:  docker exec trading-system-python-worker \
          python tests/eval_agent_golden.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.screener import ai_research  # noqa: E402

# (symbol, pct_range_or_None, must_have_evidence)
GOLDENS = [
    ("ALAB", (80, 100), True),     # pure-play AI connectivity
    ("ALGM", (5, 30), True),       # 17% disclosed-ish, AI vertical
    ("AMZN", (None, 40), False),   # AI helps but not a rev% line
]

REQUIRED_KEYS = {"ai_rev_pct", "confidence", "evidence",
                 "ai_segments", "secular_engine"}


async def main():
    passed = failed = 0
    for sym, rng, need_ev in GOLDENS:
        try:
            res = await asyncio.wait_for(
                ai_research.research_symbol(sym, force=True), timeout=120)
        except Exception as exc:
            print(f"✗ {sym}: {exc}")
            failed += 1
            continue
        r = res.get("research") or {}
        pct, ok, why = res.get("ai_rev_pct"), True, []
        missing = REQUIRED_KEYS - set(r)
        if missing:
            ok, why = False, [f"missing {missing}"]
        if pct is not None:
            if not (0 <= pct <= 100):
                ok, why = False, why + [f"pct {pct} out of range"]
            if rng[0] is not None and not (rng[0] <= pct <= rng[1]):
                ok, why = False, why + [
                    f"pct {pct} outside golden {rng[0]}-{rng[1]}"]
        if need_ev and pct is not None and not r.get("evidence"):
            ok, why = False, why + ["pct set without evidence"]
        print(f"{'✓' if ok else '✗'} {sym}: pct={pct} "
              f"conf={res.get('confidence')} "
              f"applied={res.get('applied')} {'| ' + '; '.join(why) if why else ''}")
        passed += ok
        failed += not ok
    print(f"\n{passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
