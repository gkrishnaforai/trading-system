"""insider_flow — open-market insider buying/selling → alert_items.

Thesis: executives buying their own stock with their own money is one
of the few public signals with real information content — especially
CLUSTERS (≥2 distinct insiders buying the same window), which say
"insiders agree" vs one person's tax timing. Sells get a higher bar —
sales happen for a dozen benign reasons; a lone sale is noise.

Rules (deterministic, no LLM):
  BUY cluster   ≥2 distinct insiders, code 'P', trailing 90d
                → UP / HIGH — corroborates, never forces a buy
  Large buy     single 'P' ≥ $250k in 90d
                → UP / MEDIUM
  SELL cluster  ≥3 distinct insiders, code 'S', trailing 90d
                → DOWN / MEDIUM — trips the NEGATIVE gate in
                daily_calls the same way any material alert does
  Grant/award/option codes are journaled but never drive alerts.

Universe: book + watchlist only — every call costs a provider hit,
and insider flow matters most where we can act on it.
Fingerprint: insider:{sym}:{dir}:{latest transaction_date in the
cluster} — reruns dedup; a new filing inside the window re-alerts.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 90
_BUY_MIN_INSIDERS = 2
_SELL_MIN_INSIDERS = 3
_LARGE_BUY_USD = 250_000


# ── SEC EDGAR source — primary: free, authoritative Form 4s ─────────
# Finnhub's /stock/insider-transactions is paid-tier and fails silently
# on free keys (returns [], not an error) — EDGAR is the source of
# record. All HTTP rides the shared breaker/ledger like every provider.

# SEC rejects requests without a real-format contact UA (403, not 429)
_EDGAR_UA = {"User-Agent": "trading-system research contact@example.com"}
_TICKER_CIK: dict = {}
_TICKER_CIK_AT = 0.0


def _edgar_get(url: str) -> bytes:
    """Breaker-gated fetch — EDGAR outages ledger like any provider."""
    import requests
    from app.utils.http_resilience import breaker, fail, ProviderDown
    if not breaker("sec_edgar").allow():
        raise ProviderDown("sec_edgar circuit open — failing fast")
    try:
        r = requests.get(url, headers=_EDGAR_UA, timeout=15)
        r.raise_for_status()
        breaker("sec_edgar").success()
        return r.content
    except Exception as e:
        fail("sec_edgar", url, e)
        raise


def _cik_for(symbol: str) -> Optional[str]:
    """ticker → 10-digit CIK via the SEC mapping file (cached 24h)."""
    import json as _json
    import time
    global _TICKER_CIK, _TICKER_CIK_AT
    if not _TICKER_CIK or time.time() - _TICKER_CIK_AT > 86400:
        data = _json.loads(_edgar_get(
            "https://www.sec.gov/files/company_tickers.json"))
        _TICKER_CIK = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                       for v in data.values()}
        _TICKER_CIK_AT = time.time()
    return _TICKER_CIK.get(symbol.upper())


def _parse_form4(xml: bytes, accession: str, filing_date: str) -> list[dict]:
    """form4.xml → normalized tx rows — same shape the Finnhub path
    emits so downstream logic is source-agnostic."""
    import re as _re

    x = xml.decode("utf-8", "ignore")

    def tag(t: str) -> str:
        m = _re.search(rf"<{t}>\s*(?:<value>)?\s*([^<]+?)\s*"
                       rf"(?:</value>)?\s*</{t}>", x, _re.S)
        return m.group(1).strip() if m else ""

    owner = tag("rptOwnerName")
    out = []
    # each nonDerivativeTransaction block → one row; code P/S are the
    # signal, F/A/M are journaled for completeness
    for block in _re.findall(
            r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>",
            x, _re.S):
        def btag(t: str, blk=block) -> str:
            m = _re.search(rf"<{t}>\s*(?:<value>)?\s*([^<]+?)\s*"
                           rf"(?:</value>)?\s*</{t}>", blk, _re.S)
            return m.group(1).strip() if m else ""
        code = btag("transactionCode")
        if not code:
            continue
        try:
            shares = float(btag("transactionShares").replace(",", "") or 0)
        except ValueError:
            shares = None
        try:
            price = float(
                btag("transactionPricePerShare").replace(",", "") or 0)
        except ValueError:
            price = None
        out.append({"name": owner,
                    "transactionCode": code,
                    "share": shares,
                    "transactionPrice": price,
                    "transactionDate": btag("transactionDate"),
                    "filingDate": filing_date,
                    "source_ref": accession})
    return out


def _edgar_transactions(symbol: str, max_filings: int = 8) -> list[dict]:
    """Recent Form 4s for a symbol from EDGAR — real filings, parsed
    tx rows, accession refs for audit."""
    import json as _json
    cik = _cik_for(symbol)
    if not cik:
        return []
    sub = _json.loads(_edgar_get(
        f"https://data.sec.gov/submissions/CIK{cik}.json"))
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms, accs, dates, docs = (rec.get("form") or [],
                              rec.get("accessionNumber") or [],
                              rec.get("filingDate") or [],
                              rec.get("primaryDocument") or [])
    out = []
    n = 0
    for i, form in enumerate(forms):
        if form != "4" or n >= max_filings:
            continue
        n += 1
        acc = accs[i].replace("-", "")
        try:
            # folder listing names the real doc — filers vary
            # (form4.xml vs xslF345X06/ownership.xml vs 4.xml)
            folder = _edgar_get(
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc}/")
            import re as _re2
            hrefs = _re2.findall(r'href="([^"]+\.xml)"',
                                 folder.decode("utf-8", "ignore"))
            want = (docs[i] if i < len(docs) and docs[i]
                    else "").split("/")[-1]
            doc = next((h for h in hrefs if h.endswith(f"/{want}")
                        or h == want), None) or next(
                (h for h in hrefs
                 if not _re2.search(r"(^|/)R\d+\.xml$|report", h)),
                hrefs[0] if hrefs else None)
            if not doc:
                continue
            xml = _edgar_get(
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc}/{doc.rsplit('/', 1)[-1]}")
            out.extend(_parse_form4(xml, accs[i], dates[i]))
        except Exception:
            logger.warning("edgar form4 fetch failed %s %s",
                           symbol, accs[i])
    return out


def _universe() -> list[str]:
    from app.database import db
    rows = db.execute_query(
        "SELECT DISTINCT s.symbol FROM ("
        " SELECT stock_id FROM portfolio_positions WHERE quantity>0"
        " UNION SELECT stock_id FROM watchlist_stocks) x"
        " JOIN stocks s ON s.id=x.stock_id")
    return [r["symbol"] for r in rows]


def _store(sym: str, txs: list[dict], source: str = "sec_edgar") -> int:
    """Append-only journal — every filing kept, deduped on the full
    natural key."""
    from app.database import db
    n = 0
    for t in txs:
        try:
            db.execute_update(
                "INSERT INTO insider_transactions (symbol, insider_name,"
                " transaction_code, shares, change, price,"
                " transaction_date, filing_date, source, source_ref)"
                " VALUES (:s,:n,:c,:sh,:ch,:p,:td,:fd,:src,:sr)"
                " ON CONFLICT DO NOTHING",
                {"s": sym, "n": (t.get("name") or "")[:160],
                 "c": (t.get("transactionCode") or "")[:8],
                 "sh": t.get("share"), "ch": t.get("change"),
                 "p": t.get("transactionPrice"),
                 "td": (t.get("transactionDate") or "")[:10] or None,
                 "fd": (t.get("filingDate") or "")[:10] or None,
                 "src": source, "sr": t.get("source_ref")})
            n += 1
        except Exception:
            pass
    return n


def _cluster(sym: str, code: str, days: int) -> dict:
    """Distinct insiders + notional for one code inside the window —
    read from the journal (finnhub's feed already covers ~12mo)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT insider_name, shares, price, transaction_date"
        " FROM insider_transactions WHERE symbol=:s"
        " AND transaction_code=:c"
        " AND transaction_date >= CURRENT_DATE - (:d * INTERVAL '1 day')"
        " ORDER BY transaction_date DESC",
        {"s": sym, "c": code, "d": days})
    names = {r["insider_name"] for r in rows if r.get("insider_name")}
    usd = sum((r.get("shares") or 0) * (r.get("price") or 0) for r in rows)
    latest = max((str(r.get("transaction_date")) for r in rows
                  if r.get("transaction_date")), default=None)
    return {"insiders": sorted(names), "n_tx": len(rows),
            "usd": usd, "latest": latest}


def _alert(sym: str, direction: str, materiality: str, priority: int,
           title: str, detail: dict, latest: str) -> None:
    from app.database import db
    fp = f"insider:{sym}:{direction}:{latest}"
    in_book = bool(db.execute_query(
        "SELECT 1 FROM portfolio_positions pp JOIN stocks s"
        " ON s.id=pp.stock_id WHERE s.symbol=:s AND pp.quantity>0"
        " LIMIT 1", {"s": sym}))
    in_wl = bool(db.execute_query(
        "SELECT 1 FROM watchlist_stocks ws JOIN stocks s"
        " ON s.id=ws.stock_id WHERE s.symbol=:s LIMIT 1",
        {"s": sym}))
    db.execute_update(
        "INSERT INTO alert_items (symbol, event_type, direction,"
        " materiality, title, detail, fingerprint, source,"
        " source_timestamp, in_portfolio, in_watchlist, status,"
        " priority_score) VALUES"
        " (:s,'insider',:di,:mat,:t,CAST(:de AS jsonb),:fp,"
        " 'insider_flow',now(),:ib,:iw,'new',:pr)"
        " ON CONFLICT (fingerprint) DO NOTHING",
        {"s": sym, "di": direction, "mat": materiality, "t": title,
         "de": json.dumps(detail, default=str), "fp": fp,
         "ib": in_book, "iw": in_wl, "pr": priority})


def _transactions(sym: str) -> tuple[list[dict], str]:
    """EDGAR primary — authoritative Form 4s, free, parseable codes.
    Finnhub fallback only when EDGAR yields nothing (coverage gap or
    a paid-tier key that does work). Source recorded for audit."""
    try:
        txs = _edgar_transactions(sym)
        if txs:
            return txs, "sec_edgar"
    except Exception as e:
        logger.warning("edgar insider fetch failed %s: %s", sym, e)
    try:
        from app.providers.finnhub.client import FinnhubClient
        txs = FinnhubClient.from_settings().fetch_insider_transactions(sym)
        return txs, "finnhub"
    except Exception as e:
        logger.warning("finnhub insider fetch failed %s: %s", sym, e)
        return [], "none"


def refresh_symbol(sym: str, window_days: int = _WINDOW_DAYS) -> dict:
    """Pull one symbol, journal filings, alert on clusters."""
    txs, src = _transactions(sym)
    stored = _store(sym, txs, src)

    buys = _cluster(sym, "P", window_days)
    sells = _cluster(sym, "S", window_days)
    out = {"symbol": sym, "source": src, "txs": len(txs),
           "stored": stored,
           "buy_insiders": len(buys["insiders"]),
           "sell_insiders": len(sells["insiders"]),
           "buy_usd": round(buys["usd"]), "sell_usd": round(sells["usd"])}

    if len(buys["insiders"]) >= _BUY_MIN_INSIDERS and buys["latest"]:
        _alert(sym, "POSITIVE", "HIGH", 145,
               f"{sym} insider buy cluster — {len(buys['insiders'])} insiders"
               f" bought ~${buys['usd']/1e3:.0f}k in {window_days}d"
               f" ({', '.join(buys['insiders'][:4])})",
               {"buy": buys, "sell": sells}, buys["latest"])
        out["alert"] = "buy_cluster"
    elif buys["usd"] >= _LARGE_BUY_USD and buys["latest"]:
        _alert(sym, "POSITIVE", "MEDIUM", 110,
               f"{sym} insider buy — ~${buys['usd']/1e3:.0f}k open-market"
               f" purchase in {window_days}d",
               {"buy": buys, "sell": sells}, buys["latest"])
        out["alert"] = "large_buy"
    if len(sells["insiders"]) >= _SELL_MIN_INSIDERS and sells["latest"]:
        _alert(sym, "NEGATIVE", "MEDIUM", 115,
               f"{sym} insider sell cluster — {len(sells['insiders'])} insiders"
               f" sold ~${sells['usd']/1e3:.0f}k in {window_days}d",
               {"buy": buys, "sell": sells}, sells["latest"])
        out["alert"] = (out.get("alert") or "") + "+sell_cluster"
    return out


def run(symbols: Optional[list[str]] = None) -> dict:
    """Refresh book + watchlist — bounded provider cost, insider flow
    only matters where we can act."""
    syms = symbols or _universe()
    out, errs = {}, []
    for s in syms:
        try:
            out[s] = refresh_symbol(s)
        except Exception as exc:
            errs.append(f"{s}: {exc}")
    return {"symbols": len(syms), "evaluated": len(out),
            "alerts": sum(1 for v in out.values() if v.get("alert")),
            "errors": errs}
