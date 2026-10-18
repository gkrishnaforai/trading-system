"""SEC XBRL fundamentals — the facts FMP doesn't carry.

Per tracked symbol, pull the EDGAR companyfacts blob and distill:
  RPO / cRPO        backlog — remaining performance obligation
  goodwill          + % of assets — serial-acquirer flag
  acq spend (FY)    PaymentsToAcquireBusinessesNetOfCashAcquired
  share-count steps CommonStockSharesOutstanding history → split
                    detection. A step >1.8x means every per-share
                    series straddling that date is on a mixed basis —
                    the NOW Dec-2025 5:1 that poisoned pe_technology's
                    eps_ttm is exactly what this catches at the source.
Everything lands in symbol_sec_facts; a per-run journal row goes to
doc-style notes only when something changed (new split suspect,
first RPO print).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# XBRL tags in priority order — first non-empty wins. RPO shows up
# under a few names depending on filer vintage.
_RPO_TAGS = (
    "RevenueRemainingPerformanceObligation",
    "ContractWithCustomerLiabilityRevenueRecognized",  # not RPO but a
                                                      # backlog proxy
                                                      # when RPO absent
)
_CRPO_TAGS = (
    "RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPeriodOneYear",
)
_GOODWILL_TAGS = ("Goodwill",)
_ASSETS_TAGS = ("Assets",)
_ACQ_TAGS = ("PaymentsToAcquireBusinessesNetOfCashAcquired",
             "PaymentsToAcquireBusinessesGross")
_SHARES_TAGS = ("CommonStockSharesOutstanding",)
_DILUTED_SHARES_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding",)

_SPLIT_STEP = 1.8          # ≥1.8x share-count step = split (5:1, 4:1,
                           # 2:1, 3:2 all ≥1.5 — 1.8 skips noise like
                           # buyback drift while catching real splits)


def _facts_tbl(blob: dict, ns: str, tag: str,
               unit: str) -> list[dict]:
    """One fact's unit series, newest-first by end date."""
    fact = ((blob.get("facts") or {}).get(ns) or {}).get(tag) or {}
    rows = ((fact.get("units") or {}).get(unit) or [])
    return sorted(rows, key=lambda r: str(r.get("end") or ""),
                  reverse=True)


def _latest(blob: dict, tags: tuple, unit: str = "USD",
            annual: bool = False) -> Optional[dict]:
    """Newest fact across candidate tags. annual=True prefers ~1y
    frames so quarterly fragments don't win."""
    for tag in tags:
        for ns in ("us-gaap", "dei"):
            rows = _facts_tbl(blob, ns, tag, unit)
            if annual:
                rows = [r for r in rows
                        if _span_days(r) and _span_days(r) > 300]
            if rows:
                return {"tag": tag, **rows[0]}
    return None


def _span_days(row: dict) -> Optional[int]:
    try:
        s = date.fromisoformat(str(row["start"]))
        e = date.fromisoformat(str(row["end"]))
        return (e - s).days
    except Exception:
        return None


def _share_series(blob: dict) -> list[tuple[str, float]]:
    """(end_date, shares_out) over time — the split detector."""
    rows = _facts_tbl(blob, "dei", "CommonStockSharesOutstanding",
                      "shares")
    if not rows:
        rows = _facts_tbl(blob, "us-gaap",
                          "CommonStockSharesOutstanding", "shares")
    series = []
    for r in rows:
        try:
            series.append((str(r["end"]), float(r["val"])))
        except Exception:
            continue
    return list(reversed(series))          # oldest → newest


def _split_step(series: list[tuple[str, float]]
                ) -> tuple[Optional[float], Optional[str]]:
    """Largest consecutive share-count step + the date it happened."""
    best, when = None, None
    for (_, prev), (d, cur) in zip(series, series[1:]):
        if prev and prev > 0:
            r = cur / prev
            # a step is a step either direction (reverse splits too)
            step = r if r >= 1 else 1 / r
            if best is None or step > best:
                best, when = step, d
    return best, when


def extract(symbol: str) -> Optional[dict]:
    """Pull + distill one symbol. None when EDGAR has no CIK/facts."""
    from app.providers import sec_edgar
    blob = sec_edgar.company_facts(symbol)
    if not blob:
        return None
    out: dict[str, Any] = {"cik": sec_edgar.cik_for(symbol)}

    rpo = _latest(blob, _RPO_TAGS)
    if rpo:
        out["rpo"] = rpo.get("val")
        out["rpo_period"] = rpo.get("end")
        out["rpo_tag"] = rpo.get("tag")
    crpo = _latest(blob, _CRPO_TAGS)
    if crpo:
        out["crpo"] = crpo.get("val")
    gw = _latest(blob, _GOODWILL_TAGS)
    ta = _latest(blob, _ASSETS_TAGS)
    if gw:
        out["goodwill"] = gw.get("val")
        if ta and ta.get("val"):
            out["goodwill_assets_pct"] = round(
                gw["val"] / ta["val"], 4)
    acq = _latest(blob, _ACQ_TAGS, annual=True)
    if acq:
        out["acq_spend_fy"] = acq.get("val")
        out["acq_fy_end"] = acq.get("end")

    series = _share_series(blob)
    out["share_points"] = len(series)
    if series:
        out["shares_out"] = series[-1][1]
        step, when = _split_step(series)
        out["shares_step_ratio"] = (round(step, 2)
                                    if step is not None else None)
        out["split_suspect"] = bool(step and step >= _SPLIT_STEP)
        out["split_step_date"] = when if out["split_suspect"] else None
        out["share_tail"] = series[-6:]     # recent history, evidence

    ends = [str(r.get("end")) for r in (rpo, gw, ta, acq) if r]
    out["as_of"] = max(ends) if ends else None
    return out


def persist(sym: str, f: dict) -> None:
    from app.database import db
    import json
    db.execute_update(
        "INSERT INTO symbol_sec_facts "
        "(symbol, cik, rpo, crpo, rpo_period, goodwill,"
        " goodwill_assets_pct, acq_spend_fy, shares_out,"
        " shares_step_ratio, split_suspect, facts, as_of, fetched_at)"
        " VALUES (:s,:cik,:rpo,:crpo,:rp,:gw,:gap,:acq,:sh,:step,:sp,"
        " CAST(:f AS jsonb),:ao,now())"
        " ON CONFLICT (symbol) DO UPDATE SET"
        " cik=EXCLUDED.cik, rpo=EXCLUDED.rpo, crpo=EXCLUDED.crpo,"
        " rpo_period=EXCLUDED.rpo_period,"
        " goodwill=EXCLUDED.goodwill,"
        " goodwill_assets_pct=EXCLUDED.goodwill_assets_pct,"
        " acq_spend_fy=EXCLUDED.acq_spend_fy,"
        " shares_out=EXCLUDED.shares_out,"
        " shares_step_ratio=EXCLUDED.shares_step_ratio,"
        " split_suspect=EXCLUDED.split_suspect,"
        " facts=EXCLUDED.facts, as_of=EXCLUDED.as_of,"
        " fetched_at=now()",
        {"s": sym, "cik": f.get("cik"), "rpo": f.get("rpo"),
         "crpo": f.get("crpo"), "rp": f.get("rpo_period"),
         "gw": f.get("goodwill"),
         "gap": f.get("goodwill_assets_pct"),
         "acq": f.get("acq_spend_fy"), "sh": f.get("shares_out"),
         "step": f.get("shares_step_ratio"),
         "sp": bool(f.get("split_suspect")),
         "f": json.dumps(f), "ao": f.get("as_of")})


def ensure_table() -> None:
    """Self-provision (same pattern as admin ensure-* endpoints) so a
    cold deploy works before migrations run."""
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_sec_facts ("
        " symbol TEXT PRIMARY KEY, cik TEXT, rpo NUMERIC, crpo NUMERIC,"
        " rpo_period TEXT, goodwill NUMERIC, goodwill_assets_pct NUMERIC,"
        " acq_spend_fy NUMERIC, shares_out NUMERIC,"
        " shares_step_ratio NUMERIC,"
        " split_suspect BOOLEAN NOT NULL DEFAULT FALSE,"
        " facts JSONB, as_of DATE,"
        " fetched_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS sec_filings_processed ("
        " accession TEXT PRIMARY KEY, symbol TEXT NOT NULL,"
        " form TEXT NOT NULL, filed DATE, url TEXT, claims INT,"
        " processed_at TIMESTAMPTZ NOT NULL DEFAULT now())")


def run(symbols: list[str]) -> dict[str, Any]:
    """Weekly-ish refresh over the tracked universe. Sequential —
    the provider self-throttles; EDGAR is free and patient."""
    ensure_table()
    ok = no_cik = 0
    splits, errors = [], []
    for sym in symbols:
        try:
            f = extract(sym)
            if not f:
                no_cik += 1
                continue
            persist(sym, f)
            ok += 1
            if f.get("split_suspect"):
                splits.append(sym)
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
            if len(errors) >= 10:
                break
    return {"symbols": len(symbols), "ok": ok, "no_cik": no_cik,
            "split_suspects": splits, "errors": errors}
