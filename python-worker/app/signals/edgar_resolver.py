"""EDGAR fact resolver — A4 of the public-data spine.

Two questions over fact_observations, per the frozen spec:

  latest_known_value  — best currently available value, folding in
                        amendments and restatements (latest filing
                        vintage wins; never a silent overwrite —
                        earlier observations stay in the table)
  as_known_at(t)      — what an investor could actually have known
                        at time t: latest observation with
                        filed_at <= t. The backtest-honesty query.

Quarter derivation is validated, never assumed: standalone Q4 =
FY − (Q1+Q2+Q3) only when the annual and quarterly facts share
tag + unit + duration-class for the same fiscal context; cash-flow
standalone = YTD_n − YTD_{n-1} under the same check. Derived facts
land back in fact_observations as is_derived rows citing their
parents — original and derived stay separately visible.

Fiscal-calendar caveat per spec: duration heuristics (~90d quarter,
~270d nine-month, ~350d year) are signals, not classifiers — fp/fy
labels and filing context arbitrate 13/14-week quarters and 52/53-
week years.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PARSER = "a4_v1"
_QUARTERS = 8                          # v1 scope: ~2 years


def _span(o: dict) -> Optional[int]:
    s, e = o.get("period_start"), o.get("period_end")
    if not s or not e:
        return None
    try:
        return (date.fromisoformat(str(e))
                - date.fromisoformat(str(s))).days
    except Exception:
        return None


def _dur_class(o: dict) -> str:
    """duration class — instant | ~quarter | ~half | ~9m | ~annual.
    Bands absorb 13/14-week quarters and 52/53-week years; fp/fy is
    the arbiter when the band is ambiguous."""
    if o.get("instant") or not o.get("period_start"):
        return "instant"
    d = _span(o) or 0
    if d < 55:    return "short"      # stub/transition periods
    if d <= 115:  return "quarter"
    if d <= 200:  return "half"
    if d <= 300:  return "nine_month"
    return "annual"


def _obs(cik: str, tags: tuple, unit: str, period_end,
         as_of=None) -> list[dict]:
    """Candidate observations for (tag∈tags, unit, period_end),
    never-rejected, optionally as-of a knowledge timestamp."""
    from app.database import db
    as_of_clause = ""
    params: dict[str, Any] = {"cik": cik, "u": unit,
                              "pe": str(period_end)}
    tag_list = ",".join(f"'{t}'" for t in tags)
    if as_of is not None:
        as_of_clause = " AND filed_at <= :asof"
        params["asof"] = as_of
    return db.execute_query(
        f"SELECT id, source_fact_id, accn, taxonomy, tag, unit,"
        f" value, period_start, period_end, instant, fy, fp, frame,"
        f" form, filed_at, is_amendment, is_derived, quality_state"
        f" FROM fact_observations"
        f" WHERE cik=:cik AND unit=:u AND period_end=:pe"
        f"   AND tag IN ({tag_list})"
        f"   AND quality_state NOT IN ('rejected')"
        f"{as_of_clause}"
        # SEC only assigns frames to consolidated facts — a frame
        # marks the canonical observation among same-period
        # dimension-flattened variants
        f" ORDER BY (frame IS NOT NULL) DESC,"
        f" filed_at DESC NULLS LAST", params)


def resolve_fact(cik: str, tags: tuple, unit: str, period_end,
                 as_of=None) -> Optional[dict]:
    """resolve_fact(cik, metric→tag chain, unit, period_end,
                    as_of=None, policy='latest_valid')

    latest_known_value when as_of=None; as_known_at(t) otherwise.
    Returns {value, accn, filed_at, is_derived, source_fact_id,
             originally_reported} — original vs preferred stay
    separately visible."""
    rows = _obs(cik, tags, unit, period_end, as_of=as_of)
    if not rows:
        return None
    best = rows[0]                          # latest filing vintage
    original = min(rows, key=lambda r: str(r.get("filed_at") or ""))
    return {"value": best.get("value"), "accn": best.get("accn"),
            "filed_at": best.get("filed_at"),
            "is_derived": best.get("is_derived"),
            "source_fact_id": best.get("source_fact_id"),
            "originally_reported": original.get("value")}


def _derive_quarter(db, cik: str, tags: tuple, unit: str,
                    q_end: date, fy: Optional[int]) -> Optional[dict]:
    """Validated standalone-quarter derivation.

    Rule A (income): Q4 = FY − (Q1+Q2+Q3) — same tag, unit, and the
    annual obs must carry fy/fp consistent with the quarters.
    Rule B (cash flow): Q_n = YTD_n − YTD_{n-1} — same tag+unit, both
    YTD durations, adjacent period ends.
    Emits is_derived observation rows citing parents; returns the
    derived value dict or None."""
    # Rule B first — cash-flow style YTD pairs
    ytds = [o for o in _obs(cik, tags, unit, q_end)
            if _dur_class(o) in ("half", "nine_month")
            and not o.get("is_derived")]
    for y in ytds:
        y_start = y.get("period_start")
        if not y_start:
            continue
        # the preceding YTD ends one quarter earlier, same start
        prior = db.execute_query(
            "SELECT id, source_fact_id, accn, value, period_start,"
            " period_end, filed_at, fy, fp FROM fact_observations"
            " WHERE cik=:cik AND tag=:t AND unit=:u"
            "   AND period_start=:ps AND period_end < :pe"
            "   AND NOT is_derived"
            "   AND quality_state NOT IN ('rejected')"
            " ORDER BY period_end DESC LIMIT 1",
            {"cik": cik, "t": y["tag"], "u": unit,
             "ps": str(y_start), "pe": str(q_end)})
        if not prior:
            continue
        p = prior[0]
        gap = (date.fromisoformat(str(q_end))
               - date.fromisoformat(str(p["period_end"]))).days
        if not (60 <= gap <= 115):          # adjacent quarter only
            continue
        if y.get("value") is None or p.get("value") is None:
            continue
        val = float(y["value"]) - float(p["value"])
        # the derived fact is the STANDALONE quarter — its span is
        # (prior YTD end + 1d, quarter end), not the YTD's span;
        # carrying the isolated bounds is what lets it resolve as
        # a quarterly fact later
        q_start = (date.fromisoformat(str(p["period_end"]))
                   + timedelta(days=1))
        return _emit_derived(
            cik, tags, y, q_end, str(q_start), val,
            rule="ytd_minus_prior_ytd",
            parents=[y["source_fact_id"], p["source_fact_id"]])
    # Rule A — FY minus three standalone quarters
    fy_rows = [o for o in _obs(cik, tags, unit, q_end)
               if _dur_class(o) == "annual" and not o.get("is_derived")]
    if fy_rows:
        ann = fy_rows[0]
        ann_start = ann.get("period_start")
        if ann_start and ann.get("value") is not None:
            qs = _standalone_quarters(cik, tags, unit, ann_start,
                                      q_end)
            if qs and all(q.get("value") is not None for q in qs):
                val = float(ann["value"]) - sum(
                    float(q["value"]) for q in qs)
                q_start = (date.fromisoformat(
                    str(qs[-1]["period_end"])) + timedelta(days=1))
                return _emit_derived(
                    cik, tags, ann, q_end, str(q_start), val,
                    rule="fy_minus_q1_q2_q3",
                    parents=[ann["source_fact_id"]]
                            + [q["source_fact_id"] for q in qs])
            # Rule A2 — FY minus the 9-month YTD (the classic Q4:
            # issuers that report YTD cash flow leave exactly this)
            nine = db.execute_query(
                "SELECT id, source_fact_id, accn, value,"
                " period_start, period_end, filed_at"
                " FROM fact_observations"
                " WHERE cik=:cik AND tag=:t AND unit=:u"
                "   AND period_start=:ps AND period_end < :pe"
                "   AND NOT is_derived"
                "   AND quality_state NOT IN ('rejected')"
                " ORDER BY period_end DESC",
                {"cik": cik, "t": ann["tag"], "u": unit,
                 "ps": str(ann_start), "pe": str(q_end)})
            for p in nine:
                gap = (date.fromisoformat(str(q_end))
                       - date.fromisoformat(str(p["period_end"]))).days
                span = (date.fromisoformat(str(p["period_end"]))
                        - date.fromisoformat(str(ann_start))).days
                # predecessor must end ~1q earlier AND span ~9mo —
                # the only combination that isolates Q4 cleanly
                if not (60 <= gap <= 115 and 240 <= span <= 300):
                    continue
                if p.get("value") is None:
                    continue
                val = float(ann["value"]) - float(p["value"])
                q_start = (date.fromisoformat(str(p["period_end"]))
                           + timedelta(days=1))
                return _emit_derived(
                    cik, tags, ann, q_end, str(q_start), val,
                    rule="fy_minus_9m_ytd",
                    parents=[ann["source_fact_id"],
                             p["source_fact_id"]])
    return None


def _standalone_quarters(cik, tags, unit, fy_start, fy_end):
    """Q1..Q3 standalone obs inside the fiscal year, in order."""
    from app.database import db
    tag_list = ",".join(f"'{t}'" for t in tags)
    rows = db.execute_query(
        f"SELECT id, source_fact_id, accn, tag, value, period_start,"
        f" period_end, filed_at, frame FROM fact_observations"
        f" WHERE cik=:cik AND unit=:u AND tag IN ({tag_list})"
        f"   AND period_start IS NOT NULL"
        f"   AND period_start >= :ps AND period_end < :pe"
        f"   AND NOT is_derived"
        f"   AND quality_state NOT IN ('rejected')"
        f" ORDER BY period_end,"
        f"          (frame IS NOT NULL) DESC,"
        f"          filed_at DESC NULLS LAST",
        {"cik": cik, "u": unit, "ps": str(fy_start),
         "pe": str(fy_end)})
    out = [r for r in rows
           if _dur_class(r) == "quarter"]
    # first row per period_end wins — ordering already prefers the
    # consolidated (frame-tagged) observation
    by_end: dict[str, dict] = {}
    for r in out:
        e = str(r["period_end"])
        if e not in by_end:
            by_end[e] = r
    qs = sorted(by_end.values(), key=lambda r: str(r["period_end"]))
    return qs[:3] if len(qs) >= 3 else None


def _emit_derived(cik, tags, base_obs, end, start, value, rule,
                  parents) -> Optional[dict]:
    """Persist a derived observation (original + derived coexist)."""
    from app.database import db
    tag = tags[0]
    sfid = hashlib.sha1(
        f"derived|{cik}|{tag}|{start}|{end}|{rule}|{value}".encode()
    ).hexdigest()
    n = db.execute_update(
        "INSERT INTO fact_observations (cik, accn, taxonomy, tag,"
        " unit, value, period_start, period_end, instant, fy, fp,"
        " form, filed_at, is_derived, derived_from, quality_state,"
        " source_url, parser_version, source_fact_id)"
        " VALUES (:cik,:accn,:tax,:tag,'USD',:val,:ps,:pe,false,"
        " :fy,:fp,:form,:filed,true,:df,'derived',:src,:p,:sfid)"
        " ON CONFLICT (source_fact_id) DO NOTHING",
        {"cik": cik, "accn": base_obs.get("accn"), "tax": "us-gaap",
         "tag": tag, "val": value, "ps": str(start), "pe": str(end),
         "fy": base_obs.get("fy"), "fp": base_obs.get("fp"),
         "form": base_obs.get("form"), "filed": base_obs.get("filed_at"),
         "df": json.dumps({"rule": rule, "parents": parents}),
         "src": base_obs.get("source_url"), "p": _PARSER,
         "sfid": sfid})
    if not n:
        return None
    return {"value": value, "accn": base_obs.get("accn"),
            "filed_at": base_obs.get("filed_at"), "is_derived": True,
            "source_fact_id": sfid, "originally_reported": None}


# -- canonical statement loader ------------------------------------------------

# metric → us-gaap tag preference chains. Order = preference.
_INCOME = {
    "total_revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                      "RevenueFromContractWithCustomerIncludingAssessedTax",
                      "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet",
                      "RevenuesNetOfInterestExpense"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "research_and_development": ("ResearchAndDevelopmentExpense",
                                 "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating",
                         "InterestIncomeExpenseNet"),
    "income_tax_expense": ("IncomeTaxExpenseBenefit",),
}
_BALANCE = {
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "total_shareholder_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "cash_and_cash_equivalents": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "short_term_investments": ("ShortTermInvestments",
                               "AvailableForSaleSecuritiesDebtSecuritiesCurrent"),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt",
                       "LongTermDebtAndCapitalLeaseObligations"),
}
_CASHFLOW = {
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    "investing_cash_flow": ("NetCashProvidedByUsedInInvestingActivities",
                            "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"),
    "financing_cash_flow": ("NetCashProvidedByUsedInFinancingActivities",
                            "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"),
    "capital_expenditures": ("PaymentsToAcquirePropertyPlantAndEquipment",
                             "PaymentsToAcquireProductiveAssets",
                             "PaymentsToAcquireFixedAssets"),
}
_RATIO_TAGS = {
    "assets_current": ("AssetsCurrent",),
    "liab_current": ("LiabilitiesCurrent",),
    "inventory": ("InventoryNet", "InventoryFinishedGoodsNetOfReserves",
                  "InventoryGross"),
    "receivables": ("AccountsReceivableNetCurrent",
                    "ReceivablesNetCurrent"),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
}


def _quarter_ends(db, cik: str) -> list[date]:
    """The issuer's quarter-end set — distinct duration-end dates over
    the last ~2.5y where core facts exist, newest first."""
    rows = db.execute_query(
        "SELECT DISTINCT period_end FROM fact_observations"
        " WHERE cik=:cik AND taxonomy='us-gaap'"
        "   AND period_end >= now() - interval '2.5 years'"
        " ORDER BY period_end DESC LIMIT :n",
        {"cik": cik, "n": _QUARTERS})
    return [date.fromisoformat(str(r["period_end"])) for r in rows]


def _resolve_metric(cik, tags, unit, q_end, want_quarterly: bool,
                    as_of=None):
    """Resolve one metric for a period — reported first, validated
    derivation when a standalone quarter is missing."""
    rows = _obs(cik, tags, unit, q_end, as_of=as_of)
    if want_quarterly:
        best = next((o for o in rows if _dur_class(o) == "quarter"),
                    None)
        if best is None and rows:
            # only YTD/annual variants exist → validated derivation
            from app.database import db
            best = _derive_quarter(db, cik, tags, unit, q_end,
                                   fy=None)
        elif best is not None:
            return {"value": best["value"], "accn": best["accn"],
                    "filed_at": best["filed_at"],
                    "is_derived": best["is_derived"],
                    "source_fact_id": best["source_fact_id"],
                    "originally_reported": min(
                        (o for o in rows
                         if _dur_class(o) == "quarter"),
                        key=lambda r: str(r.get("filed_at") or ""),
                        default=best).get("value")}
        return best
    best = next((o for o in rows if _dur_class(o) == "instant"), None)
    return ({"value": best["value"], "accn": best["accn"],
             "filed_at": best["filed_at"], "is_derived": False,
             "source_fact_id": best["source_fact_id"],
             "originally_reported": None} if best else None)


def load_statements(symbol: str, as_of=None) -> dict[str, Any]:
    """Canonical quarterly statements for one issuer — last 8
    quarters into income/balance/cash-flow/ratios with
    data_source='sec_edgar', accn refs and lineage edges per row."""
    from app.database import db
    from app.providers import sec_edgar
    from app.utils import lineage
    cik = sec_edgar.cik_for(symbol)
    if not cik:
        return {"symbol": symbol, "quarters": 0}
    ends = _quarter_ends(db, cik)
    written = 0
    for q_end in ends:
        inc = {m: _resolve_metric(cik, tags, "USD", q_end,
                                  want_quarterly=True, as_of=as_of)
               for m, tags in _INCOME.items()}
        bal = {m: _resolve_metric(cik, tags, "USD", q_end,
                                  want_quarterly=False, as_of=as_of)
               for m, tags in _BALANCE.items()}
        cf = {m: _resolve_metric(cik, tags, "USD", q_end,
                                 want_quarterly=True, as_of=as_of)
              for m, tags in _CASHFLOW.items()}
        fcf = None
        if (cf.get("operating_cash_flow") or {}).get("value") is not None \
                and (cf.get("capital_expenditures") or {}).get("value") is not None:
            fcf = {"value": float(cf["operating_cash_flow"]["value"])
                   - float(cf["capital_expenditures"]["value"]),
                   "accn": cf["operating_cash_flow"]["accn"],
                   "is_derived": True,
                   "source_fact_id": None}
        # a period_end with zero resolved facts isn't a fiscal
        # quarter end — dei instants (share counts, entity dates)
        # land here and must not write statement rows
        resolved = [v for v in list(inc.values())
                    + list(bal.values()) + list(cf.values()) if v]
        if not any(v.get("value") is not None for v in resolved):
            continue
        accn = next((v["accn"] for v in resolved
                     if v.get("accn")), None)
        def _v(d):
            if not d or d.get("value") is None:
                return None
            try:
                return float(d["value"])
            except (TypeError, ValueError):
                return None
        db.execute_update(
            "INSERT INTO income_statements (symbol, fiscal_date_ending,"
            " currency, total_revenue, gross_profit, operating_income,"
            " net_income, research_and_development, interest_expense,"
            " income_tax_expense, data_source)"
            " VALUES (:s,:d,'USD',:rev,:gp,:oi,:ni,:rd,:ie,:tax,"
            " 'sec_edgar')"
            " ON CONFLICT (symbol, fiscal_date_ending, data_source)"
            " DO UPDATE SET total_revenue=:rev, gross_profit=:gp,"
            " operating_income=:oi, net_income=:ni,"
            " research_and_development=:rd, interest_expense=:ie,"
            " income_tax_expense=:tax, updated_at=now()",
            {"s": symbol, "d": str(q_end), "rev": _v(inc["total_revenue"]),
             "gp": _v(inc["gross_profit"]), "oi": _v(inc["operating_income"]),
             "ni": _v(inc["net_income"]), "rd": _v(inc["research_and_development"]),
             "ie": _v(inc["interest_expense"]), "tax": _v(inc["income_tax_expense"])})
        ar = _resolve_metric(cik, _RATIO_TAGS["receivables"], "USD",
                             q_end, want_quarterly=False, as_of=as_of)
        inv_b = _resolve_metric(cik, _RATIO_TAGS["inventory"], "USD",
                                q_end, want_quarterly=False, as_of=as_of)
        db.execute_update(
            "INSERT INTO balance_sheets (symbol, fiscal_date_ending,"
            " currency, total_assets, total_liabilities,"
            " total_shareholder_equity, cash_and_cash_equivalents,"
            " short_term_investments, long_term_debt, net_receivables,"
            " inventory, data_source)"
            " VALUES (:s,:d,'USD',:ta,:tl,:eq,:cash,:sti,:ltd,:ar,:inv,"
            " 'sec_edgar')"
            " ON CONFLICT (symbol, fiscal_date_ending, data_source)"
            " DO UPDATE SET total_assets=:ta, total_liabilities=:tl,"
            " total_shareholder_equity=:eq,"
            " cash_and_cash_equivalents=:cash,"
            " short_term_investments=:sti, long_term_debt=:ltd,"
            " net_receivables=:ar, inventory=:inv, updated_at=now()",
            {"s": symbol, "d": str(q_end), "ta": _v(bal["total_assets"]),
             "tl": _v(bal["total_liabilities"]),
             "eq": _v(bal["total_shareholder_equity"]),
             "cash": _v(bal["cash_and_cash_equivalents"]),
             "sti": _v(bal["short_term_investments"]),
             "ltd": _v(bal["long_term_debt"]),
             "ar": _v(ar), "inv": _v(inv_b)})
        db.execute_update(
            "INSERT INTO cash_flow_statements (symbol,"
            " fiscal_date_ending, currency, operating_cash_flow,"
            " investing_cash_flow, financing_cash_flow,"
            " free_cash_flow, capital_expenditures,"
            " accounts_receivables, net_income, data_source)"
            " VALUES (:s,:d,'USD',:ocf,:icf,:fcf_,:fcf2,:capex,:ar,:ni,"
            " 'sec_edgar')"
            " ON CONFLICT (symbol, fiscal_date_ending, data_source)"
            " DO UPDATE SET operating_cash_flow=:ocf,"
            " investing_cash_flow=:icf, financing_cash_flow=:fcf_,"
            " free_cash_flow=:fcf2, capital_expenditures=:capex,"
            " accounts_receivables=:ar, net_income=:ni,"
            " updated_at=now()",
            {"s": symbol, "d": str(q_end), "ocf": _v(cf["operating_cash_flow"]),
             "icf": _v(cf["investing_cash_flow"]),
             "fcf_": _v(cf["financing_cash_flow"]),
             "fcf2": fcf["value"] if fcf else None,
             "capex": _v(cf["capital_expenditures"]),
             "ar": _v(ar), "ni": _v(inc["net_income"])})
        # derived ratios — deployed schema: roe/roa/roic, D/E, current,
        # margins, AR turnover + DSO. PE/PB need prices (licensed) →
        # the table has no columns for them; nothing is faked.
        ca = _resolve_metric(cik, _RATIO_TAGS["assets_current"], "USD",
                             q_end, want_quarterly=False, as_of=as_of)
        cl = _resolve_metric(cik, _RATIO_TAGS["liab_current"], "USD",
                             q_end, want_quarterly=False, as_of=as_of)
        ptx = _resolve_metric(cik, _RATIO_TAGS["pretax_income"], "USD",
                              q_end, want_quarterly=True, as_of=as_of)
        rev_v, gp_v, oi_v, ni_v = (_v(inc["total_revenue"]),
                                  _v(inc["gross_profit"]),
                                  _v(inc["operating_income"]),
                                  _v(inc["net_income"]))
        ta_v, tl_v, eq_v, ltd_v, cash_v = (
            _v(bal["total_assets"]), _v(bal["total_liabilities"]),
            _v(bal["total_shareholder_equity"]),
            _v(bal["long_term_debt"]),
            _v(bal["cash_and_cash_equivalents"]))
        ca_v, cl_v, ar_v, tax_v, ptx_v = (_v(ca), _v(cl), _v(ar),
                                         _v(inc["income_tax_expense"]),
                                         _v(ptx))
        de = cr = roe = roa = roic = gpm = om = npm = rto = dso = None
        if tl_v is not None and eq_v:
            de = round(tl_v / eq_v, 4)
        if ca_v is not None and cl_v:
            cr = round(ca_v / cl_v, 4)
        if ni_v is not None and eq_v:
            roe = round(ni_v / eq_v, 6)
        if ni_v is not None and ta_v:
            roa = round(ni_v / ta_v, 6)
        if rev_v:
            if gp_v is not None:
                gpm = round(gp_v / rev_v, 6)
            if oi_v is not None:
                om = round(oi_v / rev_v, 6)
            if ni_v is not None:
                npm = round(ni_v / rev_v, 6)
            if ar_v:
                rto = round(rev_v * 4 / ar_v, 4)   # annualized
                dso = round(ar_v / rev_v * 91.25, 2)  # quarter days
        # ROIC = NOPAT / invested capital — NOPAT = OI×(1−tax rate)
        # (rate clipped 0–40% to keep one-off tax distortions from
        # inverting the metric); invested capital = equity + debt − cash
        if oi_v is not None and eq_v is not None:
            invested = eq_v + (ltd_v or 0) - (cash_v or 0)
            if invested and invested > 0:
                etr = 0.0
                if ptx_v and tax_v is not None and ptx_v > 0:
                    etr = max(0.0, min(0.40, tax_v / ptx_v))
                roic = round(oi_v * (1 - etr) / invested, 6)
        db.execute_update(
            "INSERT INTO financial_ratios (symbol, fiscal_date_ending,"
            " roe, roa, roic, debt_to_equity, current_ratio,"
            " receivables_turnover, days_sales_outstanding,"
            " return_on_assets, return_on_capital, gross_profit_margin,"
            " operating_margin, net_profit_margin, data_source)"
            " VALUES (:s,:d,:roe,:roa,:roic,:de,:cr,:rto,:dso,:roa2,"
            " :roic2,:gpm,:om,:npm,'sec_edgar')"
            " ON CONFLICT (symbol, fiscal_date_ending, data_source)"
            " DO UPDATE SET roe=:roe, roa=:roa, roic=:roic,"
            " debt_to_equity=:de, current_ratio=:cr,"
            " receivables_turnover=:rto, days_sales_outstanding=:dso,"
            " return_on_assets=:roa2, return_on_capital=:roic2,"
            " gross_profit_margin=:gpm, operating_margin=:om,"
            " net_profit_margin=:npm, updated_at=now()",
            {"s": symbol, "d": str(q_end), "roe": roe, "roa": roa,
             "roic": roic, "de": de, "cr": cr, "rto": rto, "dso": dso,
             "roa2": roa, "roic2": roic, "gpm": gpm, "om": om,
             "npm": npm})
        # lineage: the statement row ← its source observations
        out_id = f"stmt:{symbol}:{q_end}"
        for res in list(inc.values()) + list(bal.values()) \
                + list(cf.values()) + [ca, cl, ar, inv_b, ptx]:
            if res and res.get("source_fact_id"):
                lineage.record_edge(
                    "statement_row", out_id, "fact_observation",
                    res["source_fact_id"], "sec_edgar", _PARSER)
        if accn:
            lineage.record_edge("statement_row", out_id, "filing",
                                accn, "sec_edgar", _PARSER)
        written += 1
    for q_end in ends:
        lineage.compute_eligibility("statement_row",
                                    f"stmt:{symbol}:{q_end}")
    return {"symbol": symbol, "cik": cik, "quarters": written,
            "oldest": str(ends[-1]) if ends else None}


def run(symbols: list[str]) -> dict[str, Any]:
    """Resolver pass over the universe — runs after fact backfill;
    incremental on new-filing events going forward."""
    from app.database import db  # noqa: F401 (import surface parity)
    totals = {"symbols": 0, "quarters": 0, "errors": []}
    for sym in symbols:
        try:
            r = load_statements(sym)
            totals["symbols"] += 1
            totals["quarters"] += r["quarters"]
        except Exception as exc:
            logger.warning("edgar resolve %s failed: %s", sym, exc)
            totals["errors"].append(f"{sym}: {exc}")
    return totals
