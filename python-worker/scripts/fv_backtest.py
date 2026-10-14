"""FV v2 backtest CLI — thin wrapper over app.fair_value_v2.backtest.

Usage (inside the python-worker container or with DATABASE_URL set):
    python scripts/fv_backtest.py [--symbol NVDA] [--horizons 90,180,365]
"""

import argparse
import sys

sys.path.insert(0, ".")

from app.fair_value_v2.backtest import run_backtest  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--horizons", default="90,180,365")
    args = ap.parse_args()
    hs = [int(x) for x in args.horizons.split(",") if x.strip()]

    res = run_backtest(args.symbol, hs)
    if not res["total_runs"]:
        print("no runs")
        return

    print(f"{'h':>5} {'n':>4} {'fv_bias':>8} {'fv_mae':>7} "
          f"{'bear%':>6} {'gate%':>6} {'ret<=bb':>8} {'ret>bb':>8}")
    f = lambda x: f"{x:+.1%}" if x is not None else "—"
    g = lambda x: f"{x:.0%}" if x is not None else "—"
    for h in res["horizons"]:
        if not h["n"]:
            print(f"{h['days']:>5} {0:>4}  — horizon not elapsed")
            continue
        print(f"{h['days']:>5} {h['n']:>4} {f(h['fv_bias']):>8} "
              f"{f(h['fv_mae']):>7} "
              f"{g(h['bear_breach']):>6} {g(h['gate_reach']):>6} "
              f"{f(h['ret_inside_gate']):>8} {f(h['ret_outside_gate']):>8}")


if __name__ == "__main__":
    main()
