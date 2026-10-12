from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.database import db
from app.factor_engine.catalyst_score_engine import CatalystScoreEngine
from app.factor_engine.entry_score_engine import EntryScoreEngine
from app.factor_engine.providers.technical_provider import TechnicalProvider
from app.fair_value_v2.service import FairValueV2Service
from app.observability.logging import get_logger


logger = get_logger("investment_health_service")


@dataclass
class HealthScoreResult:
    symbol: str
    as_of_date: str
    fundamentals_score: float
    valuation_score: float
    industry_score: float
    technical_score: Optional[float]
    catalyst_score: Optional[float]
    overall_score: float
    action: str
    inputs: Dict[str, Any]
    reasons: List[str]


class InvestmentHealthService:
    def __init__(self):
        self._fv2 = FairValueV2Service()

        self._hyperscalers = ["AMZN", "MSFT", "GOOGL", "META", "AAPL"]
        self._capex_beneficiaries = {
            "NVDA",
            "AVGO",
            "ANET",
            "SMCI",
            "MU",
            "AMAT",
            "LRCX",
            "KLAC",
            "ASML",
            "TSM",
        }

    def ensure_tables(self) -> None:
        db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS investment_health_scores (
                portfolio_id UUID,
                symbol VARCHAR(32) NOT NULL,
                as_of_date DATE NOT NULL,
                fundamentals_score DOUBLE PRECISION,
                valuation_score DOUBLE PRECISION,
                industry_score DOUBLE PRECISION,
                technical_score DOUBLE PRECISION,
                catalyst_score DOUBLE PRECISION,
                overall_score DOUBLE PRECISION,
                action VARCHAR(32),
                inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
                reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (portfolio_id, symbol, as_of_date)
            );

            CREATE INDEX IF NOT EXISTS idx_inv_health_scores_portfolio_date
                ON investment_health_scores(portfolio_id, as_of_date DESC);

            CREATE INDEX IF NOT EXISTS idx_inv_health_scores_symbol_date
                ON investment_health_scores(symbol, as_of_date DESC);
            """
        )

        # Backward-compatible schema evolution for existing DBs.
        # These are safe no-ops when columns already exist.
        try:
            db.execute_query(
                """
                ALTER TABLE investment_health_scores
                    ADD COLUMN IF NOT EXISTS technical_score DOUBLE PRECISION;

                ALTER TABLE investment_health_scores
                    ADD COLUMN IF NOT EXISTS catalyst_score DOUBLE PRECISION;
                """
            )
        except Exception:
            # Table may not exist yet in some transient startup paths; CREATE TABLE above should handle.
            # If ALTER fails for any other reason, keep serving with legacy columns.
            return

    def _compute_technical(self, symbol: str, as_of_date_str: str) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
        """Compute a lightweight technical score using factor-engine providers.

        We keep this intentionally stable/defensive:
        - If factor providers have no data, return None and let overall weighting renormalize.
        - Store raw factor snapshots in inputs for explainability.
        """

        inputs: Dict[str, Any] = {}
        reasons: List[str] = []
        try:
            as_of = datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        except Exception:
            return None, inputs, ["Technical as_of_date invalid"]

        tech = None
        entry = None

        try:
            tech_res = TechnicalProvider().get_asof(symbol.upper(), as_of)
            if tech_res is not None:
                tech = tech_res
                inputs["technical_provider"] = {
                    "source": tech_res.source,
                    "factors": {
                        fid: {
                            "value": snap.value,
                            "confidence": snap.confidence,
                            "source": snap.source,
                        }
                        for fid, snap in tech_res.factors.items()
                    },
                }
        except Exception as e:
            inputs["technical_provider_error"] = str(e)

        try:
            entry_res = EntryScoreEngine().get_asof(symbol.upper(), as_of)
            if entry_res is not None:
                entry = entry_res
                inputs["entry_score_engine"] = {
                    "source": entry_res.source,
                    "factors": {
                        fid: {
                            "value": snap.value,
                            "confidence": snap.confidence,
                            "source": snap.source,
                        }
                        for fid, snap in entry_res.factors.items()
                    },
                }
        except Exception as e:
            inputs["entry_score_engine_error"] = str(e)

        # Heuristic scoring policy:
        # - If entry score exists, use it as primary (it tends to represent pullback/entry quality).
        # - Otherwise, if technical provider has a top-level score factor, use it.
        # - Otherwise, return None.
        score = None
        if entry is not None:
            s = (entry.factors or {}).get("entry.score")
            if s is not None:
                try:
                    score = float(s.value)
                    reasons.append(f"Entry score {score:.0f}/100")
                except Exception:
                    score = None

        if score is None and tech is not None:
            # Common convention: a provider may expose a canonical score factor; keep defensive.
            for fid in ["technical.score", "tech.score", "signal.technical_score"]:
                snap = (tech.factors or {}).get(fid)
                if snap is not None:
                    try:
                        score = float(snap.value)
                        reasons.append(f"Technical score {score:.0f}/100")
                    except Exception:
                        score = None
                    break

        return score, inputs, reasons

    def _compute_catalyst(self, symbol: str, as_of_date_str: str) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {}
        reasons: List[str] = []
        try:
            as_of = datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        except Exception:
            return None, inputs, ["Catalyst as_of_date invalid"]

        try:
            res = CatalystScoreEngine().get_asof(symbol.upper(), as_of)
        except Exception as e:
            return None, {"catalyst_score_engine_error": str(e)}, ["Catalyst unavailable"]

        if res is None:
            return None, inputs, ["No catalyst data"]

        snap = (res.factors or {}).get("catalyst.score")
        if snap is None:
            return None, {"catalyst_score_engine": {"source": res.source}}, ["No catalyst score"]

        score = None
        try:
            score = float(snap.value)
        except Exception:
            score = None

        inputs["catalyst_score_engine"] = {
            "source": res.source,
            "metadata": res.metadata,
            "factors": {
                fid: {
                    "value": fs.value,
                    "confidence": fs.confidence,
                    "source": fs.source,
                }
                for fid, fs in (res.factors or {}).items()
            },
        }

        if score is not None:
            days_to = (res.metadata or {}).get("days_to_earnings")
            if days_to is not None:
                reasons.append(f"Earnings in {days_to}d")
            reasons.append(f"Catalyst score {score:.0f}/100")
        else:
            reasons.append("Catalyst score invalid")

        return score, inputs, reasons

    def _peg_bucket(self, peg: Optional[float]) -> str:
        if peg is None:
            return "unknown"
        if peg < 0.8:
            return "undervalued"
        if peg < 1.2:
            return "fair"
        if peg < 1.5:
            return "rich"
        return "overpriced"

    def _peg_score(self, peg: Optional[float]) -> float:
        b = self._peg_bucket(peg)
        return {
            "undervalued": 90.0,
            "fair": 70.0,
            "rich": 45.0,
            "overpriced": 25.0,
            "unknown": 50.0,
        }.get(b, 50.0)

    def _action_from_score(self, overall_score: float) -> str:
        # Keep stable core action set.
        if overall_score >= 80:
            return "add"
        if overall_score >= 65:
            return "hold"
        if overall_score >= 55:
            return "no_trade"
        if overall_score >= 45:
            return "trim"
        if overall_score >= 30:
            return "reduce"
        return "sell"

    def _eps_cagr_3y(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any]]:
        details: Dict[str, Any] = {}
        try:
            rows = db.execute_query(
                """
                SELECT fiscal_date, eps
                FROM fmp_financial_statements
                WHERE symbol = :symbol
                  AND statement_type = 'income'
                  AND period = 'annual'
                  AND eps IS NOT NULL
                ORDER BY fiscal_date DESC
                LIMIT 5
                """,
                {"symbol": symbol},
            )
            data = [dict(r) for r in (rows or [])]
            if len(data) < 4:
                return None, details
            eps_latest = data[0].get("eps")
            eps_3y_ago = data[3].get("eps")
            details["eps_latest"] = eps_latest
            details["eps_3y_ago"] = eps_3y_ago
            if eps_latest is None or eps_3y_ago is None:
                return None, details
            eps_latest = float(eps_latest)
            eps_3y_ago = float(eps_3y_ago)
            if eps_latest <= 0 or eps_3y_ago <= 0:
                return None, details
            cagr = (eps_latest / eps_3y_ago) ** (1.0 / 3.0) - 1.0
            return cagr * 100.0, details
        except Exception:
            return None, details

    def _safe_float(self, v: Any) -> Optional[float]:
        try:
            if v is None or v == "":
                return None
            return float(v)
        except Exception:
            return None

    def _get_latest_stock_insights_snapshot(self, symbol: str, source: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            rows = db.execute_query(
                """
                SELECT payload, generated_at
                FROM stock_insights_snapshots
                WHERE stock_symbol = :symbol
                  AND source = :source
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                {"symbol": symbol.upper(), "source": source},
            )
            if not rows:
                return None, None
            r0 = dict(rows[0])
            payload = r0.get("payload")
            ts = r0.get("generated_at")
            return (payload if isinstance(payload, dict) else None), (str(ts) if ts is not None else None)
        except Exception:
            return None, None

    def _score_linear(self, *, x: Optional[float], x0: float, x1: float, y0: float, y1: float, clamp: bool = True) -> Optional[float]:
        if x is None:
            return None
        try:
            if x1 == x0:
                return None
            t = (float(x) - float(x0)) / (float(x1) - float(x0))
            y = float(y0) + t * (float(y1) - float(y0))
            if clamp:
                return max(0.0, min(100.0, y))
            return y
        except Exception:
            return None

    def _compute_business_quality(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {}
        reasons: List[str] = []

        km_payload, km_ts = self._get_latest_stock_insights_snapshot(symbol, "fmp_key_metrics_ttm")
        km = (km_payload or {}).get("key_metrics_ttm") if isinstance(km_payload, dict) else None
        if km is not None and not isinstance(km, dict):
            km = None

        gm_pct = self._safe_float((km or {}).get("grossMarginTTM"))
        if gm_pct is None:
            gm_pct = self._safe_float((km or {}).get("grossMargin"))
        if gm_pct is not None and gm_pct <= 1.0:
            gm_pct = gm_pct * 100.0

        opm_pct = self._safe_float((km or {}).get("operatingMarginTTM"))
        if opm_pct is None:
            opm_pct = self._safe_float((km or {}).get("operatingMargin"))
        if opm_pct is not None and opm_pct <= 1.0:
            opm_pct = opm_pct * 100.0

        roic_pct = self._safe_float((km or {}).get("returnOnInvestedCapitalTTM"))
        if roic_pct is None:
            roic_pct = self._safe_float((km or {}).get("roicTTM"))
        if roic_pct is not None and roic_pct <= 1.0:
            roic_pct = roic_pct * 100.0

        fcf_margin_pct = self._safe_float((km or {}).get("freeCashFlowMarginTTM"))
        if fcf_margin_pct is None:
            fcf_margin_pct = self._safe_float((km or {}).get("freeCashFlowMargin"))
        if fcf_margin_pct is not None and fcf_margin_pct <= 1.0:
            fcf_margin_pct = fcf_margin_pct * 100.0

        inputs["key_metrics_ttm_generated_at"] = km_ts
        inputs["gross_margin_pct_ttm"] = gm_pct
        inputs["operating_margin_pct_ttm"] = opm_pct
        inputs["roic_pct_ttm"] = roic_pct
        inputs["fcf_margin_pct_ttm"] = fcf_margin_pct

        gm_score = self._score_linear(x=gm_pct, x0=20.0, x1=60.0, y0=30.0, y1=95.0) or 50.0
        opm_score = self._score_linear(x=opm_pct, x0=5.0, x1=35.0, y0=25.0, y1=95.0) or 50.0
        roic_score = self._score_linear(x=roic_pct, x0=5.0, x1=25.0, y0=25.0, y1=95.0) or 50.0
        fcfm_score = self._score_linear(x=fcf_margin_pct, x0=0.0, x1=25.0, y0=35.0, y1=95.0) or 50.0

        if gm_pct is not None:
            reasons.append(f"Gross margin {gm_pct:.1f}%")
        else:
            reasons.append("Gross margin unavailable")
        if opm_pct is not None:
            reasons.append(f"Operating margin {opm_pct:.1f}%")
        else:
            reasons.append("Operating margin unavailable")
        if roic_pct is not None:
            reasons.append(f"ROIC {roic_pct:.1f}%")
        else:
            reasons.append("ROIC unavailable")
        if fcf_margin_pct is not None:
            reasons.append(f"FCF margin {fcf_margin_pct:.1f}%")
        else:
            reasons.append("FCF margin unavailable")

        score = 0.30 * gm_score + 0.30 * opm_score + 0.25 * roic_score + 0.15 * fcfm_score
        return float(score), inputs, reasons

    def _compute_financial_quality(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {}
        reasons: List[str] = []

        km_payload, km_ts = self._get_latest_stock_insights_snapshot(symbol, "fmp_key_metrics_ttm")
        km = (km_payload or {}).get("key_metrics_ttm") if isinstance(km_payload, dict) else None
        if km is not None and not isinstance(km, dict):
            km = None

        fs_payload, fs_ts = self._get_latest_stock_insights_snapshot(symbol, "fmp_financial_scores")
        fs = (fs_payload or {}).get("financial_scores") if isinstance(fs_payload, dict) else None
        if isinstance(fs, list) and fs:
            fs0 = fs[0]
            fs = fs0 if isinstance(fs0, dict) else None
        if fs is not None and not isinstance(fs, dict):
            fs = None

        debt_to_equity = self._safe_float((km or {}).get("debtToEquityTTM"))
        current_ratio = self._safe_float((km or {}).get("currentRatioTTM"))
        interest_cov = self._safe_float((km or {}).get("interestCoverageTTM"))

        altman_z = self._safe_float((fs or {}).get("altmanZScore"))
        piotroski = self._safe_float((fs or {}).get("piotroskiScore"))

        inputs["key_metrics_ttm_generated_at"] = km_ts
        inputs["financial_scores_generated_at"] = fs_ts
        inputs["debt_to_equity_ttm"] = debt_to_equity
        inputs["current_ratio_ttm"] = current_ratio
        inputs["interest_coverage_ttm"] = interest_cov
        inputs["altman_z"] = altman_z
        inputs["piotroski_score"] = piotroski

        dte_score = None
        if debt_to_equity is not None:
            dte_score = self._score_linear(x=debt_to_equity, x0=2.0, x1=0.0, y0=25.0, y1=95.0)
        cr_score = self._score_linear(x=current_ratio, x0=0.8, x1=2.0, y0=25.0, y1=90.0)
        ic_score = self._score_linear(x=interest_cov, x0=1.0, x1=10.0, y0=20.0, y1=95.0)
        z_score = self._score_linear(x=altman_z, x0=1.8, x1=3.0, y0=30.0, y1=90.0)
        p_score = self._score_linear(x=piotroski, x0=3.0, x1=8.0, y0=25.0, y1=90.0)

        parts: List[Tuple[str, Optional[float], float]] = [
            ("dte", dte_score, 0.30),
            ("cr", cr_score, 0.20),
            ("ic", ic_score, 0.20),
            ("z", z_score, 0.15),
            ("p", p_score, 0.15),
        ]
        avail = [(s, w) for _, s, w in parts if s is not None]
        if not avail:
            return None, inputs, ["No financial quality data"]
        denom = sum(w for _, w in avail)
        score = 0.0
        for _, s, w in parts:
            if s is None:
                continue
            score += (w / denom) * float(s)

        if debt_to_equity is not None:
            reasons.append(f"Debt/Equity {debt_to_equity:.2f}")
        else:
            reasons.append("Debt/Equity unavailable")
        if current_ratio is not None:
            reasons.append(f"Current ratio {current_ratio:.2f}")
        else:
            reasons.append("Current ratio unavailable")
        if interest_cov is not None:
            reasons.append(f"Interest coverage {interest_cov:.1f}")
        if altman_z is not None:
            reasons.append(f"Altman Z {altman_z:.2f}")
        if piotroski is not None:
            reasons.append(f"Piotroski {piotroski:.0f}/9")

        return float(score), inputs, reasons

    def _compute_ai_growth(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {}
        reasons: List[str] = []

        rev_cagr, rev_details = self._revenue_cagr_3y(symbol)
        eps_cagr, eps_details = self._eps_cagr_3y(symbol)
        inputs["revenue_cagr_3y_pct"] = rev_cagr
        inputs["eps_cagr_3y_pct"] = eps_cagr
        for k, v in (rev_details or {}).items():
            inputs[f"revenue_cagr_3y.{k}"] = v
        for k, v in (eps_details or {}).items():
            inputs[f"eps_cagr_3y.{k}"] = v

        txt = self._latest_transcript_text(symbol) or ""
        t = txt.lower()
        ai_terms = [
            "artificial intelligence",
            "generative ai",
            "genai",
            "llm",
            "foundation model",
            "inference",
            "training",
            "copilot",
            "agent",
        ]
        ai_hits = sum(1 for term in ai_terms if term in t)
        inputs["ai_transcript_keyword_hits"] = ai_hits

        rev_score = self._score_linear(x=rev_cagr, x0=0.0, x1=30.0, y0=40.0, y1=95.0) or 50.0
        eps_score = self._score_linear(x=eps_cagr, x0=0.0, x1=35.0, y0=35.0, y1=95.0) or 50.0
        ai_signal_score = 50.0
        if ai_hits > 0:
            ai_signal_score = min(95.0, 55.0 + 10.0 * float(min(ai_hits, 4)))

        if rev_cagr is not None:
            reasons.append(f"Revenue CAGR(3y) {rev_cagr:.1f}%")
        else:
            reasons.append("Revenue CAGR(3y) unavailable")
        if eps_cagr is not None:
            reasons.append(f"EPS CAGR(3y) {eps_cagr:.1f}%")
        else:
            reasons.append("EPS CAGR(3y) unavailable")
        if ai_hits > 0:
            reasons.append(f"AI keyword hits in transcript: {ai_hits}")
        else:
            reasons.append("No AI keywords found in latest transcript")

        score = 0.45 * rev_score + 0.35 * eps_score + 0.20 * ai_signal_score
        return float(score), inputs, reasons

    def _compute_fgbi(self, *, business_quality_score: Optional[float], ai_growth_score: Optional[float]) -> Tuple[Optional[float], Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {
            "business_quality_score": business_quality_score,
            "ai_growth_score": ai_growth_score,
        }
        reasons: List[str] = []

        if business_quality_score is None and ai_growth_score is None:
            return None, inputs, ["FGBI unavailable"]

        if business_quality_score is not None:
            reasons.append(f"Business quality {business_quality_score:.0f}/100")
        if ai_growth_score is not None:
            reasons.append(f"AI growth {ai_growth_score:.0f}/100")

        b = business_quality_score if business_quality_score is not None else 50.0
        g = ai_growth_score if ai_growth_score is not None else 50.0
        score = 0.55 * float(g) + 0.45 * float(b)
        return float(score), inputs, reasons

    def _revenue_cagr_3y(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any]]:
        details: Dict[str, Any] = {}
        try:
            rows = db.execute_query(
                """
                SELECT fiscal_date, revenue
                FROM fmp_financial_statements
                WHERE symbol = :symbol
                  AND statement_type = 'income'
                  AND period = 'annual'
                  AND revenue IS NOT NULL
                ORDER BY fiscal_date DESC
                LIMIT 5
                """,
                {"symbol": symbol},
            )
            data = [dict(r) for r in (rows or [])]
            if len(data) < 4:
                return None, details
            rev_latest = data[0].get("revenue")
            rev_3y_ago = data[3].get("revenue")
            details["revenue_latest"] = rev_latest
            details["revenue_3y_ago"] = rev_3y_ago
            if rev_latest is None or rev_3y_ago is None:
                return None, details
            rev_latest = float(rev_latest)
            rev_3y_ago = float(rev_3y_ago)
            if rev_latest <= 0 or rev_3y_ago <= 0:
                return None, details
            cagr = (rev_latest / rev_3y_ago) ** (1.0 / 3.0) - 1.0
            return cagr * 100.0, details
        except Exception:
            return None, details

    def _latest_transcript_text(self, symbol: str) -> Optional[str]:
        try:
            rows = db.execute_query(
                """
                SELECT full_content
                FROM blog_content_metadata
                WHERE stock_symbol = :symbol
                  AND LOWER(title) LIKE '%earnings transcript%'
                ORDER BY publish_date DESC NULLS LAST, updated_at DESC NULLS LAST
                LIMIT 1
                """,
                {"symbol": symbol},
            )
            if not rows:
                return None
            r0 = dict(rows[0])
            txt = r0.get("full_content")
            if not txt:
                return None
            return str(txt)
        except Exception:
            return None

    def _earnings_tone_score(self, symbol: str) -> Tuple[Optional[float], Dict[str, Any]]:
        """Very lightweight heuristic sentiment score from latest transcript text."""
        txt = self._latest_transcript_text(symbol)
        if not txt:
            return None, {"transcript_available": False}
        t = txt.lower()
        pos = ["strong demand", "accelerat", "record", "margin expansion", "upside", "beat", "tailwind"]
        neg = ["weak demand", "deceler", "guidance down", "margin pressure", "headwind", "miss", "uncertain"]
        pos_hits = sum(1 for p in pos if p in t)
        neg_hits = sum(1 for n in neg if n in t)
        # Map to 0-100 with 50 neutral
        raw = 50.0 + 8.0 * (pos_hits - neg_hits)
        score = max(0.0, min(100.0, raw))
        return score, {"transcript_available": True, "pos_hits": pos_hits, "neg_hits": neg_hits}

    def _compute_valuation(self, symbol: str) -> Tuple[float, Dict[str, Any], List[str]]:
        """Compute valuation score using PEG rules.

        PEG = Forward P/E / (forward growth %)

        Notes:
        - We currently use FV2 feature sourcing for eps_forward and forward_growth_pct_1y.
        - This can be upgraded to true 3-year EPS CAGR once we persist that feature.
        """

        reasons: List[str] = []
        inputs: Dict[str, Any] = {}

        v2 = self._fv2.calculate_method(method_key="pe_forward", symbol=symbol)
        # Feature hash exists even if missing; pull scalars from method result details if present.
        eps_forward = None
        forward_growth_pct_1y = None
        try:
            if v2.method_results:
                mr0 = v2.method_results[0]
                if mr0 and mr0.inputs_used:
                    eps_forward = mr0.inputs_used.get("eps_forward")
                    forward_growth_pct_1y = mr0.inputs_used.get("optional.forward_growth_pct_1y") or mr0.inputs_used.get(
                        "forward_growth_pct_1y"
                    )
        except Exception:
            eps_forward = None
            forward_growth_pct_1y = None

        current_price = None
        try:
            # prefer v2 top-level price if present in inputs_used
            if v2.method_results and v2.method_results[0] and v2.method_results[0].inputs_used:
                current_price = v2.method_results[0].inputs_used.get("current_price")
        except Exception:
            current_price = None

        forward_pe = None
        try:
            if current_price is not None and eps_forward is not None and float(eps_forward) > 0:
                forward_pe = float(current_price) / float(eps_forward)
        except Exception:
            forward_pe = None

        eps_cagr_3y, _ = self._eps_cagr_3y(symbol)

        peg = None
        try:
            g = float(eps_cagr_3y) if eps_cagr_3y is not None else (float(forward_growth_pct_1y) if forward_growth_pct_1y is not None else None)
            if forward_pe is not None and g is not None and g > 0:
                peg = float(forward_pe) / (g / 100.0)
        except Exception:
            peg = None

        inputs.update(
            {
                "current_price": current_price,
                "eps_forward": eps_forward,
                "forward_growth_pct_1y": forward_growth_pct_1y,
                "eps_cagr_3y_pct": eps_cagr_3y,
                "growth_pct_used": eps_cagr_3y if eps_cagr_3y is not None else forward_growth_pct_1y,
                "forward_pe": forward_pe,
                "peg": peg,
                "peg_bucket": self._peg_bucket(peg),
            }
        )

        if peg is None:
            reasons.append("PEG unavailable (missing forward PE or growth)")
        else:
            reasons.append(f"PEG {peg:.2f} -> {inputs['peg_bucket']}")

        return self._peg_score(peg), inputs, reasons

    def _compute_fundamentals(self, symbol: str) -> Tuple[float, Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {}
        reasons: List[str] = []

        bq_score, bq_inputs, bq_reasons = self._compute_business_quality(symbol)
        fq_score, fq_inputs, fq_reasons = self._compute_financial_quality(symbol)
        ai_score, ai_inputs, ai_reasons = self._compute_ai_growth(symbol)
        fgbi_score, fgbi_inputs, fgbi_reasons = self._compute_fgbi(business_quality_score=bq_score, ai_growth_score=ai_score)

        inputs["modules"] = {
            "business_quality": {"score": bq_score, "inputs": bq_inputs, "reasons": bq_reasons},
            "ai_growth": {"score": ai_score, "inputs": ai_inputs, "reasons": ai_reasons},
            "fgbi": {"score": fgbi_score, "inputs": fgbi_inputs, "reasons": fgbi_reasons},
            "financial_quality": {"score": fq_score, "inputs": fq_inputs, "reasons": fq_reasons},
        }

        for r in (bq_reasons or []):
            reasons.append(f"[business_quality] {r}")
        for r in (ai_reasons or []):
            reasons.append(f"[ai_growth] {r}")
        for r in (fgbi_reasons or []):
            reasons.append(f"[fgbi] {r}")
        for r in (fq_reasons or []):
            reasons.append(f"[financial_quality] {r}")

        weights = {
            "business_quality": 0.30,
            "ai_growth": 0.20,
            "fgbi": 0.25,
            "financial_quality": 0.25,
        }
        components: Dict[str, Optional[float]] = {
            "business_quality": bq_score,
            "ai_growth": ai_score,
            "fgbi": fgbi_score,
            "financial_quality": fq_score,
        }
        available = {k: v for k, v in components.items() if v is not None}
        denom = sum(weights[k] for k in available.keys()) if available else 1.0
        score = 0.0
        for k, v in available.items():
            score += (weights[k] / denom) * float(v)

        inputs["weights"] = weights
        inputs["weights_normalized"] = {k: (weights[k] / denom) for k in available.keys()} if denom else {}

        return float(score), inputs, reasons

    def _hyperscaler_capex_signals(self) -> Dict[str, Dict[str, Optional[float]]]:
        """Compute simple capex YoY% and FCF coverage for each hyperscaler from stored cash flow statements."""
        out: Dict[str, Dict[str, Optional[float]]] = {}
        for sym in self._hyperscalers:
            capex_yoy = None
            fcf_cov = None
            try:
                rows = db.execute_query(
                    """
                    SELECT fiscal_date, capital_expenditure, free_cash_flow
                    FROM fmp_financial_statements
                    WHERE symbol = :symbol
                      AND statement_type = 'cash_flow'
                      AND period = 'annual'
                    ORDER BY fiscal_date DESC
                    LIMIT 2
                    """,
                    {"symbol": sym},
                )
                data = [dict(r) for r in (rows or [])]
                if len(data) >= 2:
                    c0 = data[0].get("capital_expenditure")
                    c1 = data[1].get("capital_expenditure")
                    f0 = data[0].get("free_cash_flow")
                    if c0 is not None and c1 not in (None, 0, 0.0):
                        capex_yoy = (float(c0) - float(c1)) / abs(float(c1)) * 100.0
                    # coverage = FCF / |capex| (higher better)
                    if f0 is not None and c0 not in (None, 0, 0.0):
                        fcf_cov = float(f0) / abs(float(c0))
            except Exception:
                capex_yoy = None
                fcf_cov = None
            out[sym] = {"capex_yoy_pct": capex_yoy, "fcf_coverage": fcf_cov}
        return out

    def _capex_index_score(self) -> Tuple[float, Dict[str, Any], List[str]]:
        """Aggregate hyperscaler capex trend into a 0-100 index score."""
        signals = self._hyperscaler_capex_signals()
        yoy_vals: List[float] = []
        cov_vals: List[float] = []
        for _, s in signals.items():
            if s.get("capex_yoy_pct") is not None:
                yoy_vals.append(float(s["capex_yoy_pct"]))
            if s.get("fcf_coverage") is not None:
                cov_vals.append(float(s["fcf_coverage"]))

        avg_yoy = sum(yoy_vals) / len(yoy_vals) if yoy_vals else None
        avg_cov = sum(cov_vals) / len(cov_vals) if cov_vals else None

        # Map: capex YoY -20%..+40% => 35..90 (more capex = demand tailwind)
        capex_component = 50.0
        if avg_yoy is not None:
            capex_component = max(0.0, min(100.0, 60.0 + 0.75 * float(avg_yoy)))

        # Coverage: 0.5..2.0 => 30..90
        cov_component = 50.0
        if avg_cov is not None:
            cov_component = max(0.0, min(100.0, 10.0 + 40.0 * float(avg_cov)))

        score = 0.65 * capex_component + 0.35 * cov_component
        reasons = []
        if avg_yoy is not None:
            reasons.append(f"Hyperscaler capex YoY avg {avg_yoy:.1f}%")
        else:
            reasons.append("Hyperscaler capex YoY unavailable")
        if avg_cov is not None:
            reasons.append(f"Hyperscaler FCF/|capex| avg {avg_cov:.2f}")
        else:
            reasons.append("Hyperscaler capex coverage unavailable")

        inputs: Dict[str, Any] = {"hyperscaler_signals": signals, "capex_yoy_avg_pct": avg_yoy, "fcf_coverage_avg": avg_cov}
        return float(score), inputs, reasons

    def _compute_industry(self, symbol: str) -> Tuple[float, Dict[str, Any], List[str]]:
        inputs: Dict[str, Any] = {}
        reasons: List[str] = []

        capex_index_score, capex_inputs, capex_reasons = self._capex_index_score()
        inputs.update({f"capex_index.{k}": v for k, v in (capex_inputs or {}).items()})
        reasons.extend(capex_reasons)

        sym_u = (symbol or "").strip().upper()
        if sym_u in self._hyperscalers:
            # Hyperscalers: capex up is positive only if coverage is ok.
            sig = (capex_inputs or {}).get("hyperscaler_signals", {}).get(sym_u, {})
            cov = sig.get("fcf_coverage")
            if cov is not None and float(cov) < 0.8:
                reasons.append("FCF coverage weak for capex")
                score = 0.55 * capex_index_score + 0.45 * 35.0
            else:
                score = 0.75 * capex_index_score + 0.25 * 60.0
            inputs["industry_role"] = "hyperscaler"
            inputs["hyperscaler_fcf_coverage"] = cov
            return float(score), inputs, reasons

        if sym_u in self._capex_beneficiaries:
            # Beneficiaries: higher capex index = higher demand tailwind
            score = capex_index_score
            inputs["industry_role"] = "capex_beneficiary"
            return float(score), inputs, reasons

        # Default: neutral with mild sensitivity to capex index
        inputs["industry_role"] = "neutral"
        score = 0.65 * 50.0 + 0.35 * capex_index_score
        return float(score), inputs, reasons

    def compute_for_symbol(self, *, portfolio_id: str, symbol: str, as_of_date_str: str) -> HealthScoreResult:
        self.ensure_tables()

        valuation_score, valuation_inputs, valuation_reasons = self._compute_valuation(symbol)

        fundamentals_score, fundamentals_inputs, fundamentals_reasons = self._compute_fundamentals(symbol)
        industry_score, industry_inputs, industry_reasons = self._compute_industry(symbol)

        technical_score, technical_inputs, technical_reasons = self._compute_technical(symbol, as_of_date_str)
        catalyst_score, catalyst_inputs, catalyst_reasons = self._compute_catalyst(symbol, as_of_date_str)

        # Weighting policy: keep legacy core (fund/val/industry) as baseline, then blend in technical + catalyst
        # when available. Missing components are renormalized.
        weights: Dict[str, float] = {
            "fundamentals": 0.34,
            "valuation": 0.28,
            "industry": 0.18,
            "technical": 0.12,
            "catalyst": 0.08,
        }

        components: Dict[str, Optional[float]] = {
            "fundamentals": fundamentals_score,
            "valuation": valuation_score,
            "industry": industry_score,
            "technical": technical_score,
            "catalyst": catalyst_score,
        }

        available = {k: v for k, v in components.items() if v is not None}
        denom = sum(weights[k] for k in available.keys()) if available else 1.0
        overall = 0.0
        for k, v in available.items():
            overall += (weights[k] / denom) * float(v)

        action = self._action_from_score(overall)

        reasons: List[str] = []
        reasons.extend([f"[fundamentals] {r}" for r in (fundamentals_reasons or [])])
        reasons.extend([f"[valuation] {r}" for r in (valuation_reasons or [])])
        reasons.extend([f"[industry] {r}" for r in (industry_reasons or [])])
        reasons.extend([f"[technical] {r}" for r in (technical_reasons or [])])
        reasons.extend([f"[catalyst] {r}" for r in (catalyst_reasons or [])])

        inputs: Dict[str, Any] = {
            "fundamentals": fundamentals_inputs,
            "valuation": valuation_inputs,
            "industry": industry_inputs,
            "technical": technical_inputs,
            "catalyst": catalyst_inputs,
            "weights": weights,
            "weights_normalized": {k: (weights[k] / denom) for k in available.keys()} if denom else {},
        }

        return HealthScoreResult(
            symbol=symbol,
            as_of_date=as_of_date_str,
            fundamentals_score=fundamentals_score,
            valuation_score=valuation_score,
            industry_score=industry_score,
            technical_score=technical_score,
            catalyst_score=catalyst_score,
            overall_score=overall,
            action=action,
            inputs=inputs,
            reasons=reasons,
        )

    def upsert_score(self, *, portfolio_id: str, score: HealthScoreResult) -> None:
        self.ensure_tables()
        db.execute_update(
            """
            INSERT INTO investment_health_scores (
                portfolio_id, symbol, as_of_date,
                fundamentals_score, valuation_score, industry_score, technical_score, catalyst_score, overall_score,
                action, inputs, reasons, updated_at
            ) VALUES (
                CAST(:portfolio_id AS uuid), :symbol, CAST(:as_of_date AS date),
                :fundamentals_score, :valuation_score, :industry_score, :technical_score, :catalyst_score, :overall_score,
                :action, CAST(:inputs AS jsonb), CAST(:reasons AS jsonb), NOW()
            )
            ON CONFLICT (portfolio_id, symbol, as_of_date)
            DO UPDATE SET
                fundamentals_score = EXCLUDED.fundamentals_score,
                valuation_score = EXCLUDED.valuation_score,
                industry_score = EXCLUDED.industry_score,
                technical_score = EXCLUDED.technical_score,
                catalyst_score = EXCLUDED.catalyst_score,
                overall_score = EXCLUDED.overall_score,
                action = EXCLUDED.action,
                inputs = EXCLUDED.inputs,
                reasons = EXCLUDED.reasons,
                updated_at = NOW();
            """,
            {
                "portfolio_id": portfolio_id,
                "symbol": score.symbol,
                "as_of_date": score.as_of_date,
                "fundamentals_score": score.fundamentals_score,
                "valuation_score": score.valuation_score,
                "industry_score": score.industry_score,
                "technical_score": score.technical_score,
                "catalyst_score": score.catalyst_score,
                "overall_score": score.overall_score,
                "action": score.action,
                "inputs": score.inputs,
                "reasons": score.reasons,
            },
        )

    def latest_and_previous(
        self, *, portfolio_id: str, as_of_date_str: str, lookback_days: int = 14
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        self.ensure_tables()
        latest = db.execute_query(
            """
            SELECT *
            FROM investment_health_scores
            WHERE portfolio_id = CAST(:portfolio_id AS uuid)
              AND as_of_date = CAST(:as_of_date AS date)
            ORDER BY overall_score DESC NULLS LAST
            """,
            {"portfolio_id": portfolio_id, "as_of_date": as_of_date_str},
        )

        prev = db.execute_query(
            """
            SELECT *
            FROM investment_health_scores
            WHERE portfolio_id = CAST(:portfolio_id AS uuid)
              AND as_of_date < CAST(:as_of_date AS date)
              AND as_of_date >= CAST(:as_of_date AS date) - (:lookback_days || ' days')::interval
            ORDER BY as_of_date DESC
            LIMIT 10000
            """,
            {"portfolio_id": portfolio_id, "as_of_date": as_of_date_str, "lookback_days": int(lookback_days)},
        )

        # Keep only most recent previous row per symbol
        prev_by_symbol: Dict[str, Dict[str, Any]] = {}
        for r in prev or []:
            d = dict(r)
            sym = str(d.get("symbol") or "").strip().upper()
            if not sym:
                continue
            if sym not in prev_by_symbol:
                prev_by_symbol[sym] = d

        return [dict(x) for x in (latest or [])], list(prev_by_symbol.values())

    def compute_changes(
        self, *, portfolio_id: str, as_of_date_str: str, lookback_days: int = 14
    ) -> List[Dict[str, Any]]:
        latest_rows, prev_rows = self.latest_and_previous(
            portfolio_id=portfolio_id,
            as_of_date_str=as_of_date_str,
            lookback_days=lookback_days,
        )
        prev_by_symbol = {str(r.get("symbol") or "").strip().upper(): r for r in (prev_rows or [])}

        changes: List[Dict[str, Any]] = []
        for r in latest_rows:
            sym = str(r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            prev = prev_by_symbol.get(sym) or {}
            cur_score = r.get("overall_score")
            prev_score = prev.get("overall_score")
            cur_action = r.get("action")
            prev_action = prev.get("action")

            delta = None
            try:
                if cur_score is not None and prev_score is not None:
                    delta = float(cur_score) - float(prev_score)
            except Exception:
                delta = None

            changed = False
            if prev:
                if prev_action != cur_action:
                    changed = True
                if delta is not None and abs(delta) >= 3.0:
                    changed = True
            else:
                changed = True

            if not changed:
                continue

            changes.append(
                {
                    "symbol": sym,
                    "as_of_date": as_of_date_str,
                    "overall_score": cur_score,
                    "prev_overall_score": prev_score,
                    "delta": delta,
                    "action": cur_action,
                    "prev_action": prev_action,
                    "valuation_score": r.get("valuation_score"),
                    "technical_score": r.get("technical_score"),
                    "catalyst_score": r.get("catalyst_score"),
                    "inputs": r.get("inputs"),
                    "reasons": r.get("reasons"),
                }
            )

        # Largest absolute change first
        def _abs_delta(x: Dict[str, Any]) -> float:
            try:
                return abs(float(x.get("delta") or 0.0))
            except Exception:
                return 0.0

        changes.sort(key=_abs_delta, reverse=True)
        return changes


investment_health_service = InvestmentHealthService()
