"""Fundamental quarterly journal — point-in-time financials.

FMP's statement endpoints return `filingDate` per row — the date the
filing was accepted, i.e. the look-ahead-safe "when did we learn it"
key. Journaling income + balance-sheet + cash-flow quarterly gives
Hidden Gems real ROE / FCF / dilution / balance-sheet factors and lets
the backtest replay rev_accel / gm_slope honestly instead of proxied.

Backfill once (~3 calls/symbol — FMP returns ~20 quarters per call),
then the nightly job just upserts whatever's new; UPSERT is keyed on
(symbol, period_end) so reruns are idempotent.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_INC_KEYS = {"revenue": "revenue", "grossProfit": "gross_profit",
             "operatingIncome": "operating_income",
             "netIncome": "net_income", "epsDiluted": "eps_diluted",
             "weightedAverageShsOutDil": "shares_diluted"}
_BS_KEYS = {"totalAssets": "total_assets",
            "totalLiabilities": "total_liabilities",
            "totalStockholdersEquity": "equity",
            "totalDebt": "total_debt",
            "cashAndCashEquivalents": "cash"}
_CF_KEYS = {"operatingCashFlow": "operating_cf",
            "capitalExpenditure": "capex", "freeCashFlow": "free_cf"}


def _rows(fmp, sym: str) -> dict[str, dict]:
    """Fetch all three statements; merge on period_end."""
    out: dict[str, dict] = {}

    def put(rows, keys, filing_key="filingDate"):
        for q in rows or []:
            pe = q.get("date")
            if not pe:
                continue
            r = out.setdefault(pe, {"period_end": pe})
            if q.get(filing_key) and "filing_date" not in r:
                r["filing_date"] = q[filing_key]
            for api, col in keys.items():
                if q.get(api) is not None:
                    r[col] = q[api]

    put(fmp._make_request("/income-statement",
                          {"symbol": sym, "period": "quarter",
                           "limit": 20}), _INC_KEYS)
    put(fmp._make_request("/balance-sheet-statement",
                          {"symbol": sym, "period": "quarter",
                           "limit": 20}), _BS_KEYS)
    put(fmp._make_request("/cash-flow-statement",
                          {"symbol": sym, "period": "quarter",
                           "limit": 20}), _CF_KEYS)
    return out


def journal_symbol(fmp, sym: str) -> int:
    """Upsert all fetched quarters for one symbol. Returns rows."""
    from app.database import db
    rows = _rows(fmp, sym)
    n = 0
    for r in rows.values():
        db.execute_update(
            "INSERT INTO fundamental_quarterly "
            "(symbol, period_end, filing_date, revenue, gross_profit,"
            " operating_income, net_income, eps_diluted, "
            " shares_diluted, total_assets, total_liabilities, "
            " equity, total_debt, cash, operating_cf, capex, free_cf) "
            "VALUES (:s,:pe,:fd,:rv,:gp,:oi,:ni,:eps,:sh,:ta,:tl,:eq,"
            ":td,:ca,:ocf,:cx,:fcf) ON CONFLICT (symbol, period_end) "
            "DO UPDATE SET filing_date=COALESCE("
            " fundamental_quarterly.filing_date, EXCLUDED.filing_date),"
            " revenue=COALESCE(EXCLUDED.revenue,"
            " fundamental_quarterly.revenue),"
            " gross_profit=COALESCE(EXCLUDED.gross_profit,"
            " fundamental_quarterly.gross_profit),"
            " operating_income=COALESCE(EXCLUDED.operating_income,"
            " fundamental_quarterly.operating_income),"
            " net_income=COALESCE(EXCLUDED.net_income,"
            " fundamental_quarterly.net_income),"
            " eps_diluted=COALESCE(EXCLUDED.eps_diluted,"
            " fundamental_quarterly.eps_diluted),"
            " shares_diluted=COALESCE(EXCLUDED.shares_diluted,"
            " fundamental_quarterly.shares_diluted),"
            " total_assets=COALESCE(EXCLUDED.total_assets,"
            " fundamental_quarterly.total_assets),"
            " total_liabilities=COALESCE(EXCLUDED.total_liabilities,"
            " fundamental_quarterly.total_liabilities),"
            " equity=COALESCE(EXCLUDED.equity,"
            " fundamental_quarterly.equity),"
            " total_debt=COALESCE(EXCLUDED.total_debt,"
            " fundamental_quarterly.total_debt),"
            " cash=COALESCE(EXCLUDED.cash,"
            " fundamental_quarterly.cash),"
            " operating_cf=COALESCE(EXCLUDED.operating_cf,"
            " fundamental_quarterly.operating_cf),"
            " capex=COALESCE(EXCLUDED.capex,"
            " fundamental_quarterly.capex),"
            " free_cf=COALESCE(EXCLUDED.free_cf,"
            " fundamental_quarterly.free_cf)",
            {"s": sym, "pe": r.get("period_end"),
             "fd": r.get("filing_date"), "rv": r.get("revenue"),
             "gp": r.get("gross_profit"),
             "oi": r.get("operating_income"), "ni": r.get("net_income"),
             "eps": r.get("eps_diluted"), "sh": r.get("shares_diluted"),
             "ta": r.get("total_assets"),
             "tl": r.get("total_liabilities"), "eq": r.get("equity"),
             "td": r.get("total_debt"), "ca": r.get("cash"),
             "ocf": r.get("operating_cf"), "cx": r.get("capex"),
             "fcf": r.get("free_cf")})
        n += 1
    return n


def run(symbols: Optional[list[str]] = None,
        sleep_s: float = 0.25) -> dict[str, Any]:
    """Backfill/refresh the journal over the flywheel universe (or a
    caller-passed list). Idempotent — safe to rerun."""
    from app.database import db
    from app.providers.financial_modeling_prep.client import \
        EnhancedFMPClient
    if symbols is None:
        symbols = [r["symbol"] for r in db.execute_query(
            "SELECT symbol FROM symbol_flywheel")]
    fmp = EnhancedFMPClient.from_settings()
    done, rows, failed = 0, 0, []
    for sym in symbols:
        try:
            rows += journal_symbol(fmp, sym)
            done += 1
        except Exception as e:
            failed.append(sym)
            logger.warning("fq journal %s: %s", sym, e)
        time.sleep(sleep_s)
    return {"symbols": done, "quarters": rows, "failed": failed[:10],
            "failed_n": len(failed)}
