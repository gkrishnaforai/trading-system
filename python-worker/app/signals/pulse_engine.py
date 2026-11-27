"""Deterministic action engine — a small interpreter over
pulse_action_rules.yaml. The YAML is the policy; this file holds NO
business rules, only mechanics:

  normalize → stage0 (computed inputs) → stage1 (annotations) →
  stage2 (first-match-wins rules; `add` candidates pass add_policy).

Missing-data contract: a condition on a missing/non-finite input is
FALSE and journals `missing:<field>`. `in`/`not_in` on null are both
false — "not in D" is not the same as "is C". Every fv_* condition
implicitly requires fv_valid — suspect FV is invisible to rules.

The result dict is the journal row: matched rule, every evaluated
condition, annotations, gate outcomes, input snapshot, versions.
"""
from __future__ import annotations

import hashlib
import math
import operator
from pathlib import Path
from typing import Any, Optional

import yaml

RULES_PATH = Path(__file__).parent / "pulse_action_rules.yaml"
ENGINE_VERSION = "pulse_engine.v1"

_OPS = {"gt": operator.gt, "gte": operator.ge,
        "lt": operator.lt, "lte": operator.le}

_spec: Optional[dict] = None


def _load() -> dict:
    global _spec
    if _spec is None:
        _spec = yaml.safe_load(RULES_PATH.read_text())
    return _spec


# |fv_upside| beyond this band is model-blind, not evidence — the
# single source for the stage-0 plausibility gate (the rules yaml's
# fv_valid precedence prose mirrors this bound). Every consumer of a
# fair-value gap — action rules AND the thesis stance — must gate on
# the same band or the pages contradict each other.
FV_SUSPECT_BAND = 75


def fv_usable(fv) -> tuple[bool, Optional[str]]:
    """Stage-0 fv_valid policy — (usable, note). None/non-finite →
    (False, 'missing'); outside ±FV_SUSPECT_BAND → (False, 'suspect
    band'); else (True, None)."""
    if fv is None:
        return False, "missing"
    try:
        f = float(fv)
    except (TypeError, ValueError):
        return False, "missing"
    if not math.isfinite(f):
        return False, "missing"
    if f > FV_SUSPECT_BAND or f < -FV_SUSPECT_BAND:
        return False, "suspect band"
    return True, None


def tape_groups() -> dict:
    """The spec's `groups:` block — shared tape vocabulary
    (broken / weak / constructive / extensible / hostile_entry) so
    other consumers don't re-hardcode state lists."""
    return _load().get("groups") or {}


# decel_cause values the fundamental classifier can call benign —
# candidates for a low-severity `slowing`, never automatic proof.
# Mirrors _decel_cause() in fundamental_health.py.
_BENIGN_DECEL = {"base_normalization", "capacity_investment",
                 "rd_investment", "conversion_delay"}


_spec_hash_cache: dict = {}


def spec_version(prefix: str, spec_path, spec: dict) -> str:
    """version: field + content hash — the learning-lab attribution
    key. Without the hash, editing a threshold while forgetting the
    version bump reuses the journal key: evals from different specs
    become indistinguishable and version-vs-version grading lies.
    Hash cached per file mtime — a mid-process spec swap rehashes."""
    p = Path(spec_path)
    mt = p.stat().st_mtime
    if _spec_hash_cache.get(str(p), (None,))[0] != mt:
        _spec_hash_cache[str(p)] = (
            mt, hashlib.sha1(p.read_bytes()).hexdigest()[:8])
    return f"{prefix}.v{spec.get('version')}+{_spec_hash_cache[str(p)][1]}"


_registered_specs: set = set()


def register_spec(engine: str, version: str, spec: dict) -> None:
    """One row per (engine, version) in spec_versions — the registry
    every journaled rules_version joins against to recover the exact
    YAML that produced the eval. Memoized; journal-first failures
    are non-fatal (the registry catches up next eval)."""
    if (engine, version) in _registered_specs:
        return
    try:
        import json as _j
        from app.database import db
        db.execute_update(
            "INSERT INTO spec_versions (engine, version, spec)"
            " VALUES (:e, :v, CAST(:s AS jsonb))"
            " ON CONFLICT (engine, version) DO NOTHING",
            {"e": engine, "v": version, "s": _j.dumps(spec)})
        _registered_specs.add((engine, version))
    except Exception:
        pass


def rules_version() -> str:
    return spec_version("rules", RULES_PATH, _load())


def _num(v) -> Optional[float]:
    """finite float or None — NaN/inf/str/bool are all missing."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ---------------- stage -1: normalize ---------------------------------

_MISSING_TOKENS = {"", "N/A", "NA", "NONE", "-", "—", "UNKNOWN",
                   "NULL"}


def _norm_grade(v) -> Optional[str]:
    """revision_grade → canonical letter or None. Strips whitespace,
    uppercases, maps missing-tokens to None. A non-null value that
    maps to no class later becomes rev_class=malformed."""
    if v is None:
        return None
    g = str(v).strip().upper()
    return None if g in _MISSING_TOKENS else g


def _normalize(row: dict) -> dict:
    """Raw pulse row → typed input ctx. 'unknown'/'—' states are
    unclassified = missing, not a value."""
    def _state(v):
        return v if v not in (None, "", "unknown", "—") else None
    det = row.get("momentum_detail") or {}
    if isinstance(det, str):
        import json
        det = json.loads(det)
    if not isinstance(det, dict):
        det = {}
    # free-form jsonb: swing can arrive as a string/list — normalizing
    # once here keeps every (det.get("swing") or {}).get() below safe
    _sw = det.get("swing") if isinstance(det.get("swing"), dict) else {}
    return {
        "tape": _state(row.get("mom_state")),
        "tape_dir": row.get("tape_dir"),          # improving|degrading|flat
        "fund": _state(row.get("fund_state")),
        "rev": _norm_grade(row.get("revision_grade")),
        "priced": _state(row.get("priced_status")),
        "fv": _num(row.get("fv_upside")),
        "rsi": _num(row.get("rsi") if row.get("rsi") is not None
                    else det.get("rsi")),
        "vs50": _num(row.get("vs_sma50") if row.get("vs_sma50") is not None
                     else det.get("vs_sma50")),
        "pct_b": _num(det.get("pct_b")),
        "earn_days": _num(row.get("earn_days")),
        "num_analysts": _num(row.get("num_analysts")),
        "flywheel_age_days": _num(row.get("flywheel_age_days")),
        "momentum_age_days": _num(row.get("momentum_age_days")),
        "flags": set(row.get("gq_flags") or []),
        "flags_known": row.get("gq_flags") is not None,
        "sector": (row.get("sector") or "").lower() or None,
        "is_etf": row.get("is_etf"),   # tri-state: True/False/None
        # readiness / repair inputs — momentum_detail subfields plus
        # flywheel, conviction and growth-quality scalars the use-case
        # checklists reference
        "dip_phase": det.get("dip_phase") or row.get("dip_phase"),
        "hist_dir": _num(det.get("hist_dir")
                         if row.get("hist_dir") is None
                         else row.get("hist_dir")),
        "swing_struct": bool(
            _sw.get("hl_seq") or _sw.get("phase")
            or _sw.get("confirm_level")),
        "swing_phase": _sw.get("phase"),
        "vol_dip": _num(det.get("vol_dip")),
        "vol_dip_trend": det.get("vol_dip_trend"),
        "confirm_level": _num(_sw.get("confirm_level")),
        "rev_growth": _num(row.get("rev_growth")),
        "eps_growth": _num(row.get("eps_growth")),
        # Layer-B slowing severity inputs — the cause/demand context
        # the classifier journaled in stocks.fundamental_detail; the
        # raw `fund` label stays canonical, these only modulate how
        # much a `slowing` leg weighs in the action rules
        "decel_cause": row.get("decel_cause"),
        "demand_health": row.get("demand_health"),
        # earnings-trajectory fact — direction of the last-3 journaled
        # earnings_watch verdicts (improving|deteriorating|mixed|
        # insufficient). An explicit 'insufficient' value means the
        # add gate can only fire on MEASURED deterioration — absent
        # watcher coverage never invents a block.
        "earn_traj": row.get("earn_traj") or "insufficient",
        # cyclical is a business-model label, not a health verdict —
        # the lean is the leading-legs judgment fundamental_health
        # computed for exactly this kind of conditional gate
        "cyclical_lean": row.get("cyclical_lean"),
        "gm_slope": _num(row.get("gm_slope")),
        # balance-sheet vulnerability (axis 2) — flywheel leverage +
        # cash-generation legs; sector-banded in stage 0, exempt where
        # leverage IS the business model
        "net_debt_ebitda": _num(row.get("net_debt_ebitda")),
        "debt_to_equity": _num(row.get("debt_to_equity")),
        "fcf_ttm": _num(row.get("fcf_ttm")),
        "fcf_margin": _num(row.get("fcf_margin")),
        # market-credit state (axis 1) — injected per-row by the caller
        # from credit_health; 'unknown' is a real state, never inferred
        "credit_state": row.get("credit_state") or "unknown",
        "credit_confidence": row.get("credit_confidence"),
        "future_score": _num(row.get("future_score")),
        "lane": row.get("lane"),
        "gq_score": _num(row.get("gq_score")),
        "structural_proof": _num(row.get("structural_proof")),
        # rank inputs — the candidate-ordering layer reads these
        "rs_pct": _num(det.get("rs_pct")),
        # resilience — sector-relative down-day defense / rebound
        # offense from the RS pass; selection inputs for rules like
        # "leader within the group", never entry triggers on their own
        "rs_quality": det.get("rs_quality"),
        "rs_bench": det.get("rs_bench"),
        "down_cap": _num(det.get("down_cap")),
        "up_cap": _num(det.get("up_cap")),
        "rebound_x": _num(det.get("rebound_x")),
        "vol_dip": _num(det.get("vol_dip")),
        "atr_pct": _num(det.get("atr_pct")),
        "px": _num(row.get("px") or row.get("close")),
        "swing_low": _num(_sw.get("swing_low")),
        "prior_low": _num(_sw.get("prior_low")),
        "gq_pct": _num(row.get("gq_pct")),
        "emerging": _state(row.get("emerging_growth")),
        "beat_streak": _num(row.get("beat_streak")),
        "est_rev": _num(row.get("est_revision_pct")),
        "sector_score": _num(row.get("sector_score")),
    }


# ---------------- stage 0: computed ------------------------------------

# balance-sheet bands — (stress_nde, watch_nde) net debt/EBITDA by
# sector; DEFAULT for the rest. Sector-aware because EBITDA/debt
# levels aren't comparable across business models. Exempt sectors
# mirror risk_flags.leverage_critical.sector_exempt — leverage IS the
# business model there and needs an FFO/coverage-style calc that
# doesn't exist yet, so they route to `exempt`, never `stressed`.
_BS_EXEMPT = {"financials", "financial services", "banks",
              "insurance", "reit", "real estate"}
_BS_BANDS = {"utilities": (6.0, 4.0),
             "energy": (4.0, 2.5),
             "communication services": (4.5, 3.0)}
_BS_DEFAULT = (4.0, 2.5)


def _balance_sheet(c: dict) -> tuple[str, str]:
    """(state, confidence) — the company-vulnerability axis.
    Corroboration required: a levered ratio alone is `watch`;
    `stressed` needs leverage AND weak cash generation (or extreme
    leverage alone — nde ≥ 1.5×band). All inputs missing →
    `unscorable`, never `healthy`."""
    if c.get("sector") in _BS_EXEMPT:
        return "exempt", "low"
    nde, dte = c.get("net_debt_ebitda"), c.get("debt_to_equity")
    fcfm, fcft = c.get("fcf_margin"), c.get("fcf_ttm")
    if all(v is None for v in (nde, dte, fcfm)):
        return "unscorable", "low"
    conf = "high" if (nde is not None and fcfm is not None) \
        else "medium"
    s_nde, w_nde = _BS_BANDS.get(c.get("sector"), _BS_DEFAULT)
    weak_cash = ((fcfm is not None and fcfm < 0)
                 or (fcft is not None and fcft <= 0))
    if ((nde is not None and nde >= s_nde and weak_cash)
            or (nde is not None and nde >= s_nde * 1.5)
            or (dte is not None and dte >= 4 and weak_cash)):
        return "stressed", conf
    if ((nde is not None and nde >= w_nde)
            or (dte is not None and dte >= 2
                and fcfm is not None and fcfm < 0.05)):
        return "watch", conf
    return "healthy", conf


def _credit_leg(credit_state: Optional[str], bs_state: str
                ) -> Optional[str]:
    """The two-axis decision cell — market credit × company balance
    sheet. severe×stressed is the only failing leg; a market shock
    alone is a moderate penalty; a stressed balance sheet in calm
    credit stays a company-level warning. `unknown` credit yields no
    leg — missing market data never invents company risk."""
    if credit_state == "severe":
        return ("severe_penalty" if bs_state == "stressed"
                else "market_penalty")
    if credit_state == "stress" and bs_state == "stressed":
        return "elevated_penalty"
    if bs_state == "stressed" and credit_state in \
            ("healthy", "caution"):
        return "company_risk"
    return None


def _stage0(c: dict) -> dict:
    """Single-assignment derived inputs — precedence explicit."""
    spec = _load()
    # fv_valid — shared policy, see fv_usable()
    fv_valid, fv_note = fv_usable(c["fv"])
    # rev_class — letter → policy class. Three outcomes: a real class,
    # `missing` (no grade at all), or the spec's configured fallback
    # (default `malformed`) for non-null unrecognized values — a feed
    # defect, not "no coverage"
    rev_spec = spec["computed"]["rev_class"]
    fallback = rev_spec.get("unmapped_non_null", "malformed")
    rev_class = "missing" if c["rev"] is None else fallback
    for cls, grades in rev_spec["map"].items():
        if cls != "missing" and c["rev"] in grades:
            rev_class = cls
            break
    # instrument — TRI-STATE: never default an unresolved instrument
    # to equity. unknown routes to its own review-only policy.
    instrument = ("etf" if c["is_etf"] is True
                  else "unknown" if c["is_etf"] is None else "equity")
    # stop geometry — same stop choice as trade_plans.suggest
    # (swing_low → prior_low → 2×ATR → −8%); distance in ATRs feeds
    # the rank's risk_atr component
    px, atr = c.get("px"), c.get("atr_pct")
    stop = c.get("swing_low") or c.get("prior_low")
    if stop is None and px and atr:
        stop = px * (1 - 2 * atr)
    elif stop is None and px:
        stop = px * 0.92
    risk_atr = (abs(px - stop) / (px * atr)
                if px and stop and atr else None)
    # balance-sheet vulnerability — axis 2 of the credit design.
    # Computed BEFORE slowing_severity: a `stressed` balance sheet is
    # a hard-risk override on the benign-cause modifier (a benign
    # slowdown doesn't neutralize when the capital structure is
    # deteriorating). Also feeds repair_eligible's credit gate.
    bs_state, bs_conf = _balance_sheet(c)
    credit_leg = _credit_leg(c.get("credit_state"), bs_state)
    # slowing_severity — Layer-B read of a `slowing` fund label. The
    # classifier's raw state stays canonical upstream (journal, stock
    # page); this computed input decides how much it weighs as a
    # FAILING leg in the action rules.
    #   low    — benign decel cause AND demand intact AND street
    #            raising AND growth level still strong — growth-rate
    #            normalization, not business deterioration
    #   normal — everything else, INCLUDING non-slowing states, so the
    #            modifier can never soften a real failing leg
    # Benign causes are candidates, not proof — the hard-risk override
    # restores full severity on estimate cuts, weak demand, FCF burn,
    # severe margin damage, or a stressed balance sheet. Missing
    # inputs never qualify as benign.
    if c["fund"] == "slowing":
        benign = (c.get("decel_cause") in _BENIGN_DECEL
                  and c.get("demand_health") in ("strong", "healthy")
                  and (c.get("est_rev") or 0) > 0
                  and (c.get("rev_growth") or 0) > 0.08)
        hard = (c.get("demand_health") == "weak"
                or (c.get("est_rev") is not None
                    and c["est_rev"] < -0.01)
                or "fcf_negative" in c["flags"]
                or bs_state == "stressed"
                or (c.get("gm_slope") is not None
                    and c["gm_slope"] < -0.05))
        severity = "low" if (benign and not hard) else "normal"
    else:
        severity = "normal"
    # repair_eligible — a broken-tape row whose dip structure is
    # repairing under a not-failing business while the street isn't
    # cutting. ONE definition, two consumers: broken_no_support
    # defers the reduce on it; base_repairing fires the stalk on it —
    # the same evidence can never be 'no support' in one rule and
    # 'repair' in the other. Safeguards:
    #   - fund must be neutral-or-good: slowing-normal / pressured /
    #     deteriorating legs keep their reduce (hard deterioration
    #     is never deferred by a technical turn)
    #   - rev must be A/B: the street still cutting (C/D) cancels
    #     the deferral
    #   - severe_credit × stressed balance sheet cancels it too —
    #     a technical turn doesn't repair a capital-structure
    #     problem inside a credit shock
    #   - missing inputs never infer repair (in-checks fail on None)
    groups = spec.get("groups") or {}
    neutral_or_good = (set(groups.get("fund_neutral") or [])
                       | set(groups.get("fund_good") or []))
    repair_eligible = (
        c.get("tape") in set(groups.get("tape_broken") or [])
        and c.get("dip_phase") in ("confirmed", "turning_up")
        and c.get("fund") in neutral_or_good
        and rev_class in ("A", "B")
        and credit_leg != "severe_penalty")
    return {"fv_valid": fv_valid, "fv_note": fv_note,
            "rev_class": rev_class, "instrument": instrument,
            "stop_px": round(stop, 2) if stop else None,
            "risk_atr": round(risk_atr, 2) if risk_atr else None,
            "slowing_severity": severity,
            "balance_sheet_state": bs_state,
            "bs_confidence": bs_conf,
            "credit_leg": credit_leg,
            "repair_eligible": repair_eligible}


# ---------------- condition interpreter ---------------------------------

def _resolve_set(v, groups) -> set:
    """Condition value → set of allowed values. Resolves group names
    and {union: [groups]}; explicit lists pass through."""
    if isinstance(v, dict) and "union" in v:
        out = set()
        for g in v["union"]:
            out |= set(groups.get(g, []))
        return out
    if isinstance(v, str) and v in groups:
        return set(groups[v])
    if isinstance(v, (list, set, tuple)):
        return set(v)
    return {v}


def _cond(c: dict, cond: dict, missing: list, groups=None) -> bool:
    """One {k: v} condition dict → bool; missing inputs record into
    `missing` and evaluate False. `groups` is the set `x_in`/`x_not_in`
    resolve against — defaults to this spec's groups; other specs
    (best_picks.yaml) pass their own so group references bind to the
    file the rules came from, never silently degrade to singletons."""
    if groups is None:
        groups = _load().get("groups") or {}
    for k, v in cond.items():
        if k == "any":
            # sub-conditions share the same missing log
            return any(_cond(c, s, missing, groups) for s in v)
        if k == "all":
            return all(_cond(c, s, missing, groups) for s in v)
        # multi-word suffixes first — rpartition alone would split
        # `priced_not_in` into field `priced_not` + suffix `in`
        if k.endswith("_not_in"):
            field, suffix = k[:-7], "not_in"
        elif k.endswith("_in"):
            field, suffix = k[:-3], "in"
        elif k.endswith("_is_not"):
            field, suffix = k[:-7], "is_not"
        elif k.endswith("_is"):
            field, suffix = k[:-3], "is"
        else:
            field, _, suffix = k.rpartition("_")
        if suffix in _OPS and field in c:
            actual = c.get(field)
            if field.startswith("fv") and not c["fv_valid"] \
                    and k != "fv_valid":
                missing.append("fv")
                return False
            if actual is None:
                missing.append(field)
                return False
            try:
                if not _OPS[suffix](actual, float(v)):
                    return False
            except TypeError:
                missing.append(field)
                return False
        elif suffix in ("in", "not_in"):
            actual = c.get(field)
            allowed = _resolve_set(v, groups)
            if actual is None:
                missing.append(field)
                return False                 # missing ∈ in AND ∉ not_in
            if suffix == "in" and actual not in allowed:
                return False
            if suffix == "not_in" and actual in allowed:
                return False
        elif suffix == "is":
            if (c.get(field) is None) != (v is None):
                return False
        elif suffix == "is_not":
            if (c.get(field) is not None) != (v is not None):
                return False
        elif k in ("flag", "not_flag"):
            has = v in c["flags"]
            if (k == "flag") != has:
                return False
        elif k == "any_missing":
            if not any(c.get(f) is None for f in v):
                return False
        elif k == "tape_dir":
            if c.get("tape_dir") != v:
                return False
        elif k == "default":
            if not v:
                return False
        elif k in c or k == "extended_metrics":
            # exact equality — bool, str class, or number. A missing
            # computed field is fail, never vacuous-true.
            actual = c.get(k)
            if actual is None:
                missing.append(k)
                return False
            if actual != v:
                return False
        elif k.endswith(("_gt", "_gte", "_lt", "_lte")):
            fld = k.rsplit("_", 1)[0]
            actual = c.get(fld)
            if actual is None:
                missing.append(fld)
                return False
            op = "gte" if k.endswith("_gte") else \
                 "lte" if k.endswith("_lte") else \
                 "gt" if k.endswith("_gt") else "lt"
            try:
                if not _OPS[op](actual, float(v)):
                    return False
            except TypeError:
                missing.append(fld)
                return False
        else:
            missing.append(f"unknown:{k}")    # unknown key ≠ pass
            return False
    return True


def _eval_when(c: dict, when: dict, groups=None) -> tuple[bool, dict]:
    """Whole `when` block ANDed; returns (matched, per-cond log)."""
    log, miss = {}, []
    ok = True
    for k, v in (when or {}).items():
        r = _cond(c, {k: v}, miss, groups)
        log[k] = ("missing" if any(m.startswith(k.rsplit("_", 1)[0])
                                   for m in miss) else
                  "pass" if r else "fail")
        ok = ok and r
    return ok, {"conditions": log, "missing": sorted(set(miss))}


# ---------------- stage 1: annotations -----------------------------------

def _stage1(c: dict) -> dict:
    spec = _load()["annotations"]
    blocking, confidence_notes = [], []
    for a in spec["blocking"]:
        if _cond(c, a["when"], []):
            blocking.append(a["name"])
    for a in spec["confidence"]:
        m: list = []
        if _cond(c, a.get("when") or {}, m):
            confidence_notes.append(a["name"])
    # risk flags — the contract is 4-state per flag:
    #   true           confirmed risk
    #   false          sufficient valid data confirms the risk absent
    #   unknown        active source, insufficient data to decide —
    #                  blocks `add`, never invents severity
    #   not_applicable sector-exempt — excluded from unverifiable AND
    #                  active (an exempt flag can't block an add)
    #   pending        uncalibrated calc — journaled, exempt from the
    #                  gate until calibrated
    flags, pending = {}, []
    for name, spec_f in (spec.get("risk_flags") or {}).items():
        exempt = {str(s).lower() for s in
                  spec_f.get("sector_exempt") or []}
        if c.get("sector") and c["sector"] in exempt:
            flags[name] = "not_applicable"
            continue
        if spec_f.get("status") == "pending_calibration":
            flags[name] = "pending"
            pending.append(name)
        elif name == "fcf_negative":
            flags[name] = ("fcf_negative" in c["flags"]
                           if c["flags_known"] else "unknown")
        else:
            flags[name] = "unknown"
    return {"blocking": blocking, "confidence": confidence_notes,
            "risk_flags": flags, "risk_pending": pending,
            "hard_risk_active": any(v is True for v in flags.values()),
            "risk_unverifiable": any(v == "unknown"
                                     for v in flags.values())}


# ---------------- formatting ---------------------------------------------

def _fmt(why: str, c: dict, extra: dict) -> str:
    def _fv():
        return f"{c['fv']:+.0f}%" if c["fv_valid"] else "—"
    def _pctf(k):
        return (f"{c[k]:+.0%}" if c.get(k) is not None else "—")
    def _numf(k, d=0):
        return (f"{c[k]:.{d}f}" if c.get(k) is not None else "—")
    vals = {"tape": c.get("tape") or "—", "fund": c.get("fund") or "—",
            "cyclical_lean": c.get("cyclical_lean") or "—",
            "rev": c.get("rev") or "—", "fv": _fv(),
            "priced": c.get("priced") or "—",
            "rsi": _numf("rsi"),
            "vs50": (f"{c['vs50']:+.1%}" if c.get("vs50") is not None
                     else "—"),
            "pct_b": _numf("pct_b", 2),
            "dip_phase": c.get("dip_phase") or "—",
            "hist_dir": _numf("hist_dir", 2),
            "swing_phase": c.get("swing_phase") or "—",
            "confirm": (f"${c['confirm_level']:.0f}"
                        if c.get("confirm_level") is not None else "—"),
            "vol_dip": _numf("vol_dip", 2),
            "vol_dip_trend": c.get("vol_dip_trend") or "—",
            "rev_growth": _pctf("rev_growth"),
            "eps_growth": _pctf("eps_growth"),
            "future_score": _numf("future_score"),
            "lane": c.get("lane") or "—",
            "gq_score": _numf("gq_score"),
            "structural_proof": _numf("structural_proof"),
            "n": (f"{int(c['num_analysts'])}"
                  if c.get("num_analysts") is not None else "—"),
            "age": "—", "gate": "—", "flags": "—",
            "notes": " · ".join(extra.get("notes") or []) or "—"}
    vals.update(extra)
    try:
        return why.format_map(vals)
    except Exception:
        return why


def _confidence(spec_val, c: dict) -> str:
    """'high' | '{high if fv_valid else low}' templates — the only
    supported form is `{A if <ctx_field> else B}` evaluated against
    Stage-0/normalized ctx (never raw inputs), so a template can
    downgrade but can never compute a different action."""
    if not isinstance(spec_val, str):
        return "medium"
    if spec_val.startswith("{"):
        try:
            expr = spec_val.strip("{}")
            a, _, rest = expr.partition(" if ")
            cond, _, b = rest.partition(" else ")
            return a if c.get(cond.strip()) else b
        except Exception:
            return "medium"
    return spec_val


# ---------------- the evaluator -------------------------------------------

def evaluate(row: dict) -> dict:
    spec = _load()
    c = _normalize(row)
    c.update(_stage0(c))
    c["extended_metrics"] = ((c["rsi"] or 0) > 65
                             or (c["vs50"] or 0) > 0.20)
    ann = _stage1(c)
    c["dq_block"] = bool(ann["blocking"])
    c["hard_risk_active"] = ann["hard_risk_active"]
    c["risk_unverifiable"] = ann["risk_unverifiable"]
    c["hard_risk_count"] = sum(1 for v in ann["risk_flags"].values()
                             if v is True)

    rules = (spec["etf_policy"]["rules"] if c["instrument"] == "etf"
             else spec["unknown_policy"]["rules"]
             if c["instrument"] == "unknown"
             else spec["rules"])
    journal: list[dict] = []
    gate_log: dict = {}
    action, label, matched, conf, why = "hold", None, "hold", "medium", \
        "no leg failing, no setup triggering"

    for rule in rules:
        ok, detail = _eval_when(c, rule.get("when"))
        detail["rule"] = rule["name"]
        journal.append(detail)
        if not ok:
            continue
        cand = rule["action"]
        why = _fmt(rule.get("why") or rule["name"], c, {})
        matched, conf = rule["name"], _confidence(
            rule.get("confidence"), c)
        label = rule.get("label")
        if cand == "add":
            # gate evaluates ONLY now — it can never downgrade a rule
            # that selected reduce/trim/watch
            fails = [g for g in spec["add_policy"]["require"]
                     if not _cond(c, g, [])]
            gate_log = {next(iter(g)): ("fail" if g in fails else "pass")
                        for g in spec["add_policy"]["require"]}
            if fails:
                gate = next(iter(fails[0]))
                cand = spec["add_policy"].get("on_fail", "watch")
                label = spec["add_policy"].get("on_fail_label")
                why = (f"add blocked — {gate}") + (
                    f" ({why})" if why else "")
        action = cand
        break

    # dq_block contract: it VETOES `add` via add_policy, and it caps
    # confidence on risk-reducing actions — but it never converts a
    # reduce/trim into hold. Stale data must not force holding risk.
    if ann["blocking"] and action in ("reduce", "trim"):
        conf = "low"

    notes = (ann["blocking"] + ann["confidence"])
    if c.get("tape_dir") == "degrading" and matched != "reduce":
        notes.append("tape degrading vs prior day")
    if c.get("tape_dir") == "improving" and action == "add":
        notes.append("tape improving vs prior day")
    if notes and label not in ("add_blocked",):
        why = f"{why} — {'; '.join(notes)}" if notes else why

    return {"action": action, "label": label, "matched_rule": matched,
            "confidence": conf, "why": why,
            "stage0": {k: c.get(k) for k in
                       ("fv_valid", "rev_class", "instrument",
                        "extended_metrics", "slowing_severity",
                        "balance_sheet_state", "bs_confidence",
                        "credit_leg", "repair_eligible")},
            "annotations": ann,
            "condition_log": journal,
            "gate_results": gate_log or None,
            "input_snapshot": c,
            "rules_version": rules_version(),
            "engine_version": ENGINE_VERSION}


# ---------------- use-case readiness (Stock page) ----------------------

def eval_use_case(row: dict, name: str) -> dict:
    """YAML-driven readiness checklist — `use_cases.<name>.checks` are
    the same `when` conditions evaluated by the same interpreter with
    the same missing-data semantics as the action rules. State:
    all-pass → ready, n-1 → close, else no."""
    spec = _load()
    register_spec("pulse", spec_version("rules", RULES_PATH, spec),
                  spec)
    c = _normalize(row)
    c.update(_stage0(c))
    checks = (spec.get("use_cases") or {}).get(name, {}) \
                  .get("checks") or []
    rules = []
    for ck in checks:
        miss: list = []
        ok = _cond(c, ck.get("when") or {}, miss)
        rules.append({"ok": bool(ok),
                      "line": _fmt(ck.get("line") or
                                   ck.get("name") or "check", c, {})})
    n = sum(r["ok"] for r in rules)
    state = ("ready" if rules and n == len(rules)
             else "close" if rules and n == len(rules) - 1 else "no")
    return {"state": state, "score": n, "of": len(rules),
            "rules": rules}


# ---------------- candidate ranking -----------------------------------
# Continuous 0-100 ordering INSIDE a use-case's `ready` set. The
# checklist is the binary gate; rank is the order the planner
# deploys capital by. Weights come from YAML `rank_weights`; the
# normalizer per component key lives here — each maps its ctx
# inputs to 0-100, None-able so a missing input drops the weight
# rather than scoring zero (the fv_unusable contract).

def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _dip(c):
    return {"confirmed": 100, "turning_up": 70,
            "stabilizing": 40}.get(c.get("dip_phase"), 10)


def _tapedir(c):
    return {"improving": 100, "flat": 50,
            "degrading": 0}.get(c.get("tape_dir"), 50)


def _room(c):
    pb = c.get("pct_b")
    rs = c.get("rsi")
    pb_part = (1 - min(pb, 1.3)) * 60 if pb is not None else 30
    rs_part = ((70 - min(rs, 70)) / 20) * 40 if rs is not None else 20
    return _clamp(pb_part + rs_part)


_RANK_NORM = {
    "rs_pct":        lambda c: _clamp(c["rs_pct"]),
    "gq_pct":        lambda c: _clamp(c["gq_pct"]),
    "sector_score":  lambda c: _clamp(c["sector_score"]),
    "dip_phase":     _dip,
    "tape_dir":      _tapedir,
    "vol_dip":       lambda c: _clamp(160 - c["vol_dip"] * 100),
                     # 0.6×vol→100, 1.0→60, ≥1.6→0 (dry-up → climax)
    "risk_atr":      lambda c: _clamp(100 - c["risk_atr"] * 40),
                     # 0.5ATR stop→80, 1.0→60, 2.0→20 — tighter is better
    "revision_grade": lambda c:
        {"A": 100, "B": 70, "C": 30, "D": 0}
        .get((c.get("rev") or "")[:1]),
    "priced_status": lambda c:
        {"not_priced": 100, "partial": 70, "substantial": 40,
         "full": 15, "beyond_lt_avg": 0, "unknown": 50}
        .get(c.get("priced")),
    "fv_upside":     lambda c: _clamp(50 + c["fv"] * 1.5),
                     # +33%→100, 0→50, −33%→0 (only called when fv_valid)
    "fwd_flags":     lambda c: _clamp(
        {"material": 100, "emerging": 70, "option": 40}
        .get(c.get("emerging"), 0)
        + min(c.get("beat_streak") or 0, 5) * 8),
    "trend_intact":  lambda c: 100 if (
        (c.get("vs50") or 0) > 0 and c.get("tape") != "climax") else 0,
    "room_to_run":   _room,
    # penalties — w<0 in YAML; 1.0 = triggered, 0.0 = not
    "earn_risk":     lambda c:
        1.0 if (c.get("earn_days") is not None
                and c["earn_days"] <= 7) else 0.0,
    # defense+offense hit-rate blend → 0-100; the sector-relative
    # "holds up on red, expands on green" selection axis
    "resilience":    lambda c: _clamp(
        (c["down_cap"] or 0) * 60 + (c["up_cap"] or 0) * 40),
}


_RANK_RAW_ALIAS = {"revision_grade": "rev", "priced_status": "priced"}
                   # yaml component name → normalized ctx key; without
                   # the alias the presence check reads a key that never
                   # exists and the weight silently drops out


def _rank_raw(k: str, c: dict):
    """Presence + raw value for `parts`. None → the component drops
    out and its weight renormalizes (missing ≠ zero)."""
    if k == "fv_upside":
        return c.get("fv") if c.get("fv_valid") else None
    if k == "fwd_flags":
        if c.get("emerging") is None and c.get("beat_streak") is None:
            return None
        return f"emerging={c.get('emerging') or '—'}·beats={c.get('beat_streak') or 0}"
    if k == "trend_intact":
        return c.get("vs50")
    if k == "room_to_run":
        if c.get("pct_b") is None and c.get("rsi") is None:
            return None
        return f"%B={c.get('pct_b')}·rsi={c.get('rsi')}"
    if k == "earn_risk":
        return c.get("earn_days")
    if k == "resilience":
        return None if c.get("down_cap") is None else (
            f"def={c['down_cap']}·reb={c.get('up_cap')}")
    return c.get(_RANK_RAW_ALIAS.get(k, k))


def rank(use_case: str, c: dict) -> dict:
    """ctx (normalized + stage0) → {rank, parts} for a use-case.
    score = Σ(w·norm)/Σw over present components, minus flat
    penalties, then clamped by the first matching `caps` rule."""
    spec = (_load().get("rank_weights") or {}).get(use_case) or {}
    num = den = pens = 0.0
    parts: dict = {}
    for comp in spec.get("weights") or []:
        k = comp.get("k")
        w = _num(comp.get("w"))
        fn = _RANK_NORM.get(k)
        if not fn or w is None:
            continue
        raw = _rank_raw(k, c)
        if raw is None:
            continue
        n = fn(c)
        if w < 0:                       # flat penalty, not a component
            if n:
                pens += abs(w)
            parts[k] = {"raw": raw, "penalty": abs(w) if n else 0}
            continue
        parts[k] = {"raw": raw, "norm": round(n, 1), "w": w}
        num += w * n
        den += w
    score = _clamp((num / den) if den else 0.0)
    score = _clamp(score - pens)
    for cap in spec.get("caps") or []:
        ok, _ = _eval_when(c, cap.get("when") or {})
        if ok:
            parts["_cap"] = {"cap": cap.get("cap"),
                             "when": cap.get("when")}
            score = min(score, _num(cap.get("cap")) or score)
            break
    return {"rank": round(score, 1), "parts": parts}
