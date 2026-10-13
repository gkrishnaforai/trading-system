"""Fair-value v2 run persistence and reuse.

Fair value is price-independent: it depends on fundamentals, estimates,
statements, consensus and method configuration — never on the live quote.
That means a stored run stays valid until its *inputs* change, and the
displayed price-vs-fair-value ratio can be recomputed cheaply against the
live price without re-running the engine.

Reuse policy:
  - recompute when any input source has data newer than the stored run's
    inputs_watermark (estimate revisions, earnings statements, refreshed
    fundamentals snapshots, category overrides, macro data)
  - recompute when the run exceeds the max-age floor (env-configurable),
    catching silent provider updates that don't move a timestamp
  - force=True bypasses reuse entirely
Each recompute appends a new versioned row — history is never mutated.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.database import db
from app.fair_value_v2.schemas import FairValueV2Result, MethodResult
from app.fair_value_v2.service import FairValueV2Service

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}

# Safety floor: recompute at least this often even when inputs appear unchanged.
FAIR_VALUE_V2_MAX_AGE_HOURS = float(os.getenv("FAIR_VALUE_V2_MAX_AGE_HOURS", "24"))

# Snapshot sources that feed valuation inputs. fmp_quote is deliberately
# excluded — it carries the live price, which is not a fair-value input and
# would invalidate every run.
_SNAPSHOT_SOURCES = (
    "fmp_fundamentals",
    "fmp_key_metrics_ttm",
    "fmp_financial_growth",
)

# (table, timestamp column) — per-symbol statement inputs.
_STATEMENT_SOURCES = (
    ("financial_ratios", "fiscal_date_ending"),
    ("balance_sheets", "fiscal_date_ending"),
    ("income_statements", "fiscal_date_ending"),
    ("cash_flow_statements", "fiscal_date_ending"),
    ("consensus_data", "consensus_date"),
    ("fundamental_estimate_snapshots", "as_of_date"),
)


class FairValueV2Resolver:
    """Resolve the effective v2 fair value, reusing stored runs when safe."""

    def __init__(self, service: Optional[FairValueV2Service] = None):
        self._service = service or FairValueV2Service()

    # -- inputs freshness ----------------------------------------------------

    def _inputs_watermark(self, symbol: str) -> Optional[datetime]:
        """Newest timestamp across all valuation-input sources for the symbol."""
        marks: List[Any] = []
        with db.get_session() as session:
            marks.append(
                session.execute(
                    text(
                        """
                        SELECT MAX(generated_at)
                        FROM stock_insights_snapshots
                        WHERE stock_symbol = :symbol AND source = ANY(:sources)
                        """
                    ),
                    {"symbol": symbol, "sources": list(_SNAPSHOT_SOURCES)},
                ).scalar()
            )
            for table, col in _STATEMENT_SOURCES:
                try:
                    marks.append(
                        session.execute(
                            text(f"SELECT MAX({col}) FROM {table} WHERE symbol = :symbol"),
                            {"symbol": symbol},
                        ).scalar()
                    )
                except Exception:
                    continue  # table/column absent — not an input for this symbol
            try:
                marks.append(
                    session.execute(
                        text(
                            """
                            SELECT MAX(updated_at)
                            FROM fair_value_v2_category_overrides
                            WHERE symbol = :symbol AND enabled = TRUE
                            """
                        ),
                        {"symbol": symbol},
                    ).scalar()
                )
            except Exception:
                pass
            try:
                marks.append(
                    session.execute(text("SELECT MAX(data_date) FROM macro_market_data")).scalar()
                )
            except Exception:
                pass
        stamps = [self._as_datetime(m) for m in marks if m is not None]
        stamps = [s for s in stamps if s is not None]
        return max(stamps) if stamps else None

    @staticmethod
    def _as_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        return None

    # -- user overrides --------------------------------------------------------

    def _active_override(self, symbol: str) -> Optional[Dict[str, Any]]:
        """User-supplied fair value, when one is enabled and unexpired."""
        try:
            with db.get_session() as session:
                row = session.execute(
                    text(
                        """
                        SELECT symbol, fair_value, bear_fair_value, bull_fair_value,
                               regime, reason, updated_by, updated_at
                        FROM fair_value_overrides
                        WHERE symbol = :symbol
                          AND enabled = TRUE
                          AND (expires_at IS NULL OR expires_at > now())
                        """
                    ),
                    {"symbol": symbol},
                ).mappings().fetchone()
            return dict(row) if row else None
        except Exception:
            return None  # table absent on older deployments — degrade to engine

    @staticmethod
    def _override_to_result(row: Dict[str, Any]) -> FairValueV2Result:
        scenario: Dict[str, Optional[float]] = {}
        if row.get("bear_fair_value") is not None:
            scenario["bear"] = float(row["bear_fair_value"])
        if row.get("bull_fair_value") is not None:
            scenario["bull"] = float(row["bull_fair_value"])
        warnings = [{"code": "user_override", "reason": row.get("reason")}]
        return FairValueV2Result(
            run_id=f"override:{row['symbol']}",
            symbol=row["symbol"],
            as_of_ts=row["updated_at"],
            fair_value=float(row["fair_value"]),
            scenario_fair_values=scenario,
            regime=row.get("regime"),
            warnings=warnings,
            model_version="user_override",
        )

    # -- stored runs ----------------------------------------------------------

    def _latest_run(self, symbol: str) -> Optional[Dict[str, Any]]:
        with db.get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT run_id, symbol, as_of, inputs_watermark, features_hash,
                           fair_value, scenario_fair_values, expected_fair_value,
                           quality_flags, regime,
                           method_results, warnings, model_version, decision
                    FROM fair_value_v2_runs
                    WHERE symbol = :symbol
                    ORDER BY as_of DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol},
            ).mappings().fetchone()
        return dict(row) if row else None

    def _persist(self, result: FairValueV2Result, inputs_watermark: Optional[datetime]) -> None:
        method_results = [mr.model_dump() for mr in (result.method_results or [])]
        warnings = list(result.warnings or [])
        quality_flags = list(result.quality_flags or [])

        # spot at run time — provenance for the training journal and the
        # extreme-gap flag; never feeds back into the calculation.
        spot = None
        try:
            row = db.execute_query(
                "SELECT close FROM daily_bars WHERE symbol=:s"
                " AND date <= :d ORDER BY date DESC LIMIT 1",
                {"s": result.symbol,
                 "d": result.as_of_ts.date()})
            if row and row[0].get("close"):
                spot = float(row[0]["close"])
        except Exception:
            spot = None
        if spot and result.fair_value:
            ratio = float(result.fair_value) / spot
            # asymmetric-insanity guard: +150% blowout OR a model claiming
            # the business is worth <35% of price (NBIS-class input
            # breakage) are equally suspect data, not real signals.
            if (ratio - 1.0 > 1.5 or ratio < 0.35) \
                    and "extreme_gap" not in quality_flags:
                quality_flags.append("extreme_gap")

        # decision layer — fair value → buy price. mos_policy.yaml sets
        # the per-category discount; company-level uncertainty adds on
        # top. Persisted alongside the run so consumers gate on
        # buy_below, not raw upside.
        decision = None
        try:
            from app.fair_value_v2.decision import (
                decide, _scalars_from_methods)
            from app.fair_value_v2.demand import build_profile
            from app.fair_value_v2.demand_evidence import (
                claims_for, derive_axes, market_claims)
            from app.fair_value_v2.demand_score import (
                ai_capex_regime, cycle_warning_score, demand_gate,
                demand_scenarios, durability_score)
            cat = (result.regime or "").split(":")[0] or None
            archs = (result.classification or {}).get("all")
            # demand/funding exposure — separate questions, kept separate:
            # demand axes from priors upgraded by approved evidence,
            # funding risk measured from inputs
            evidence = derive_axes(claims_for(result.symbol))
            scalars = _scalars_from_methods(result.method_results)
            demand = build_profile(
                result.symbol, archs or ([cat] if cat else []),
                scalars, evidence=evidence)
            # Phase 2 scorers — deterministic over the evidence pool.
            # Gate + regime are persisted but SHADOW: they inform the
            # decision payload without changing the action.
            mc = market_claims()
            regime = ai_capex_regime(mc)
            warning = cycle_warning_score(mc)
            dur = durability_score(demand, evidence)
            demand["durability"] = dur
            demand["ai_capex_regime"] = regime
            demand["ai_cycle_warning"] = warning
            demand["scenarios"] = demand_scenarios(demand, scalars)
            demand["gate"] = demand_gate(demand, regime, dur)
            self._persist_market_regime(regime, warning)
            decision = decide(
                cat, result.fair_value, result.expected_fair_value,
                result.scenario_fair_values, quality_flags, spot,
                result.method_results,
                archetypes=archs, demand=demand)
            self._upsert_demand_profile(result, demand, archs)
        except Exception as exc:
            logger.warning("fv decision layer failed for %s: %s",
                           result.symbol, exc)
        if decision is not None and result.classification:
            decision["classification"] = result.classification
        try:
            result.decision = decision
        except Exception:
            pass

        db.execute_update(
            """
            INSERT INTO fair_value_v2_runs
            (run_id, symbol, as_of, inputs_watermark, features_hash, fair_value,
             scenario_fair_values, expected_fair_value, spot_at_run,
             quality_flags, regime, method_results, warnings, model_version,
             decision, buy_below, valuation_confidence, expected_return_2y,
             fv_upside_pct)
            VALUES
            (:run_id, :symbol, :as_of, :inputs_watermark, :features_hash, :fair_value,
             :scenario_fair_values, :expected_fair_value, :spot_at_run,
             :quality_flags, :regime, :method_results, :warnings, :model_version,
             :decision, :buy_below, :valuation_confidence, :expected_return_2y,
             :fv_upside_pct)
            """,
            {
                "run_id": result.run_id,
                "symbol": result.symbol,
                "as_of": result.as_of_ts,
                "inputs_watermark": inputs_watermark,
                "features_hash": result.features_hash,
                "fair_value": result.fair_value,
                "scenario_fair_values": json.dumps(result.scenario_fair_values or {}),
                "expected_fair_value": result.expected_fair_value,
                "spot_at_run": spot,
                "quality_flags": json.dumps(quality_flags),
                "regime": result.regime,
                "method_results": json.dumps(method_results, default=str),
                "warnings": json.dumps(warnings, default=str),
                "model_version": "fair_value_v2.1",
                "decision": json.dumps(decision, default=str)
                            if decision else None,
                "buy_below": (decision or {}).get("buy_below"),
                "valuation_confidence": (decision or {}).get(
                    "valuation_confidence"),
                "expected_return_2y": (decision or {}).get(
                    "expected_return_2y"),
                "fv_upside_pct": (decision or {}).get("fv_upside_pct"),
            },
        )

    def _persist_market_regime(self, regime: Dict[str, Any],
                               warning: Dict[str, Any]) -> None:
        """Daily upsert of the market-level AI-capex regime — shared
        consensus, written once per day regardless of run volume."""
        try:
            db.execute_update(
                """
                INSERT INTO market_ai_regime
                    (as_of_date, regime, warning_score, groups,
                     down_groups, up_groups, computed_by, updated_at)
                VALUES (CURRENT_DATE, :r, :w, :g, :dg, :ug,
                        'fv_engine', now())
                ON CONFLICT (as_of_date) DO UPDATE SET
                    regime = EXCLUDED.regime,
                    warning_score = EXCLUDED.warning_score,
                    groups = EXCLUDED.groups,
                    down_groups = EXCLUDED.down_groups,
                    up_groups = EXCLUDED.up_groups,
                    updated_at = now()
                """,
                {"r": regime.get("regime"),
                 "w": warning.get("score"),
                 "g": json.dumps(regime.get("groups") or {}),
                 "dg": json.dumps(regime.get("down_groups") or []),
                 "ug": json.dumps(regime.get("up_groups") or [])})
        except Exception as exc:
            logger.warning("market regime persist failed: %s", exc)

    def _upsert_demand_profile(self, result: FairValueV2Result,
                               demand: Dict[str, Any],
                               archs: Optional[List[str]]) -> None:
        """Persist the canonical demand profile. Rules-grade writes only
        replace rules-grade rows — a human/LLM-approved classification
        is never silently clobbered by a scheduled run."""
        try:
            db.execute_update(
                """
                INSERT INTO company_demand_profile
                    (symbol, demand_model, capex_sensitivity,
                     demand_durability, utilization_health,
                     capital_funding_risk, ai_monetization,
                     archetypes, evidence, source,
                     updated_by, as_of, updated_at)
                VALUES (:s, :dm, :cs, :dd, :uh, :fr, :am,
                        :archs, :ev, :src, 'fv_engine', now(), now())
                ON CONFLICT (symbol) DO UPDATE SET
                    demand_model = EXCLUDED.demand_model,
                    capex_sensitivity = EXCLUDED.capex_sensitivity,
                    demand_durability = EXCLUDED.demand_durability,
                    utilization_health = EXCLUDED.utilization_health,
                    capital_funding_risk = EXCLUDED.capital_funding_risk,
                    ai_monetization = EXCLUDED.ai_monetization,
                    archetypes = EXCLUDED.archetypes,
                    evidence = EXCLUDED.evidence,
                    source = EXCLUDED.source,
                    as_of = EXCLUDED.as_of,
                    updated_at = now()
                WHERE company_demand_profile.source IN
                    ('rules', 'symbol_seed', 'archetype_prior',
                     'evidence', 'fv_engine')
                """,
                {"s": result.symbol,
                 "dm": demand.get("demand_model"),
                 "cs": demand.get("capex_sensitivity"),
                 "dd": demand.get("demand_durability"),
                 "uh": demand.get("utilization_health"),
                 "fr": demand.get("capital_funding_risk"),
                 "am": demand.get("ai_monetization"),
                 "archs": json.dumps(archs or []),
                 "ev": json.dumps({
                     "evidence_axes": demand.get("evidence_axes") or [],
                     "conflicts": demand.get("conflicts") or [],
                     "confidence": demand.get("evidence_confidence"),
                     "impact_mult": demand.get("impact_mult"),
                     "durability": demand.get("durability"),
                     "gate": demand.get("gate"),
                     "scenarios": demand.get("scenarios"),
                     "ai_cycle_warning":
                         (demand.get("ai_cycle_warning") or {})
                         .get("score"),
                 }),
                 "src": demand.get("source") or "rules",
                 })
        except Exception as exc:
            logger.warning("demand profile upsert failed for %s: %s",
                           result.symbol, exc)

    @staticmethod
    def _to_result(row: Dict[str, Any]) -> FairValueV2Result:
        method_results = [
            MethodResult(**mr) for mr in (row.get("method_results") or [])
        ]
        return FairValueV2Result(
            run_id=row["run_id"],
            symbol=row["symbol"],
            as_of_ts=row["as_of"],
            fair_value=row.get("fair_value"),
            scenario_fair_values=row.get("scenario_fair_values") or {},
            expected_fair_value=row.get("expected_fair_value"),
            quality_flags=row.get("quality_flags") or [],
            regime=row.get("regime"),
            method_results=method_results,
            features_hash=row.get("features_hash"),
            warnings=row.get("warnings") or [],
            decision=row.get("decision"),
            model_version=row.get("model_version") or "fair_value_v2",
        )

    # -- resolve --------------------------------------------------------------

    def resolve(
        self, symbol: str, force: bool = False
    ) -> Tuple[FairValueV2Result, Dict[str, Any]]:
        """Effective v2 fair value plus provenance metadata.

        Returns (result, meta) where meta describes reuse:
            reused, run_id, run_as_of, inputs_watermark, reason

        An enabled user override always wins — over stored runs and over
        force=True — because it represents a deliberate human correction. To
        see the engine's value again, disable the override.
        """
        symbol = symbol.upper()

        override = self._active_override(symbol)
        if override is not None:
            return self._override_to_result(override), {
                "reused": True,
                "run_id": f"override:{symbol}",
                "run_as_of": override["updated_at"].isoformat(),
                "inputs_watermark": None,
                "reason": "user_override",
                "source": "user_override",
            }

        latest = self._latest_run(symbol)
        watermark = self._inputs_watermark(symbol)
        now = datetime.now(timezone.utc)

        if latest and latest.get("fair_value") and not force:
            run_as_of = self._as_datetime(latest["as_of"])
            stored_wm = self._as_datetime(latest.get("inputs_watermark"))
            age_ok = run_as_of is not None and (now - run_as_of) <= timedelta(
                hours=FAIR_VALUE_V2_MAX_AGE_HOURS
            )
            inputs_fresh = (
                watermark is None
                or (stored_wm is not None and stored_wm >= watermark)
            )
            if age_ok and inputs_fresh:
                return self._to_result(latest), {
                    "reused": True,
                    "run_id": latest["run_id"],
                    "run_as_of": latest["as_of"].isoformat(),
                    "inputs_watermark": stored_wm.isoformat() if stored_wm else None,
                    "reason": "inputs_unchanged",
                }

        result = self._service.calculate(symbol)
        meta: Dict[str, Any] = {
            "reused": False,
            "run_id": result.run_id,
            "run_as_of": result.as_of_ts.isoformat(),
            "inputs_watermark": watermark.isoformat() if watermark else None,
            "reason": "forced" if force else (
                "inputs_changed" if latest else "no_prior_run"
            ),
        }
        if result.fair_value and float(result.fair_value) > 0:
            try:
                self._persist(result, watermark)
            except Exception as exc:
                logger.warning("fair_value_v2 run persist skipped for %s: %s", symbol, exc)
        return result, meta
