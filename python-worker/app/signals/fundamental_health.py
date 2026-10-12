"""Fundamental health flag — the fundamental-axis classifier, sibling of
momentum_regime (which classifies the tape). Reads the flywheel metrics
already computed in symbol_flywheel plus stocks.cyclical, and distills
them into one persisted state per symbol:

    accelerating  growth rate improving on multiple legs
    growing       solid growth, no material deterioration
    slowing       still growing but decelerating — early warning
    declining     several metrics deteriorating — thesis weakening
    deteriorating >=4 independent negatives — serious deterioration
    turnaround    trailing weak but the street is revising UP —
                  the quadrant a pure trailing ladder can't see
    pressured     trailing fine but estimates being cut —
                  the early top, before the bad quarter prints
    cyclical      weakness may be cycle-driven; judge by leading legs
    watch         mixed / insufficient signal
    unknown       no data

Separate axes persisted alongside:
    risk          low | medium | high | very_high   (valuation/coverage)
    alert         normal | attention | warning | critical
                  (how much DETERIORATED vs the previous snapshot)

"What changed" deltas live in fundamental_detail.changes so every
surface can answer "why the flag" in one line.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_METRICS = ("rev_growth", "rev_accel", "eps_growth", "eps_accel",
            "eps_growth_ttm", "gm_now", "gm_slope", "gm_qoq", "beat_streak",
            "est_revision_pct", "rev_breadth_30d", "surprise_trend",
            "capex_eff", "capex_rev",
            "fwd_pe", "num_analysts", "muted_reaction")

_STATE_RANK = {"accelerating": 0, "growing": 1, "cyclical": 2,
               "watch": 3, "slowing": 4, "turnaround": 4, "pressured": 4,
               "declining": 5, "deteriorating": 6, "unknown": 7}


def _decel_cause(m: dict, n_neg: int) -> Optional[str]:
    """WHY growth is decelerating or margins compressing — the cause
    overlay the state ladder can't express. States stay canonical;
    this explains them.

    Order is deliberate: the hard negative states test first (a real
    demand collapse can't hide behind a capacity story), the benign
    explanations require demand evidence to be intact.

      economic_breakdown    >=4 negs AND a demand leg weak
      demand_deterioration  revenue itself decaying (not just margins)
      capacity_investment   capex-heavy + demand strong + revisions ok
                            — compression is the buildout, not demand
      base_normalization    decel fired but level still >40% growth
      mixed                 anything else"""
    rg, ra = m.get("rev_growth"), m.get("rev_accel")
    ea = m.get("eps_accel")
    er = m.get("est_revision_pct")
    gms, gmq = m.get("gm_slope"), m.get("gm_qoq")
    cr = m.get("capex_rev")

    decel = ((ra is not None and ra < -0.05)
             or (ea is not None and ea < -0.05))
    margin_down = ((gms is not None and gms < -0.01)
                   or (gmq is not None and gmq < -0.01))
    if not decel and not margin_down:
        return None
    demand_weak = ((rg is not None and rg < 0.10)
                   or (er is not None and er < -0.02))
    if (n_neg >= 4 and demand_weak
            and rg is not None and rg < 0.15):
        return "economic_breakdown"     # needs OBSERVED revenue
        # softness — a +28% grower with an estimate trim and capex
        # squeeze is investment stress, not breakdown (META); and no
        # revenue data at all isn't evidence of revenue weakness
    if rg is not None and rg < 0.10:
        return "demand_deterioration"
    if (cr is not None and cr > 0.30
            and rg is not None and rg > 0.20
            and (er is None or er > 0)):
        return "capacity_investment"
    if rg is not None and rg > 0.40 and n_neg <= 3:
        return "base_normalization"     # high base decel — but a real
        # hard-negative pile (EPS collapse + margin loss + cuts) isn't
        # normalization just because the revenue level is still high
        # (TGTX: eps -71%, margin down, cuts → 'mixed', not base-effect)
    return "mixed"


def classify(m: dict, cyclical: bool = False) -> tuple[str, str, dict]:
    """flywheel metrics + cyclical flag → (state, risk, detail).

    detail carries the evidence: pos/neg signal lists, counts, and the
    human-readable reason chain — never a bare label.
    """
    rg, ra = m.get("rev_growth"), m.get("rev_accel")
    eg, ea = m.get("eps_growth"), m.get("eps_accel")
    gms, bs = m.get("gm_slope"), m.get("beat_streak")
    gmq = m.get("gm_qoq")
    er, pe = m.get("est_revision_pct"), m.get("fwd_pe")
    # |revision| > 100% is sign-flip arithmetic (estimates crossed zero
    # — e.g. consensus went positive→negative), not a magnitude. Treat
    # as missing: PL showed er -137%, which is junk, not a 137% cut.
    if er is not None and abs(er) > 1.0:
        er = None
    rb, tr = m.get("rev_breadth_30d"), m.get("surprise_trend")

    neg, pos, why = [], [], []
    # --- independent negative signals (the deterioration counter) ---
    if rg is not None and rg < 0.08:
        neg.append(f"rev growth weak {rg * 100:+.0f}%")
    if ra is not None and ra < -0.10:
        neg.append(f"rev decel {ra * 100:+.0f}pts")
    # EPS level judged on TTM where available — single-quarter YoY is
    # lumpy (tax timing, SBC vesting, deal amortization): NOW printed
    # -21.6% on the quarterly compare while TTM EPS was flat (+0.6%).
    # Quarterly stays as eps_accel momentum, not a level verdict.
    egt = m.get("eps_growth_ttm")
    eg_level = egt if egt is not None else eg
    if eg_level is not None and eg_level < -0.02:
        neg.append(f"eps shrinking {eg_level * 100:+.0f}%"
                   + (" ttm" if egt is not None else ""))   # -1.5% is
        # flat EPS, not shrinking — noise-threshold so mature growers
        # don't pick up phantom level-deterioration legs (INTU)
    if ea is not None and ea < -0.10:
        neg.append(f"eps decel {ea * 100:+.0f}pts")
    if gms is not None and gms < -0.01:
        neg.append(f"margin down {gms * 100:+.1f}pts")
    elif gmq is not None and gmq < -0.01:
        # sequential margin drop without YoY deterioration — one leg,
        # not two; the QoQ-vs-YoY divergence itself is the capacity-
        # compression signature scored in decel_cause
        neg.append(f"margin down {gmq * 100:+.1f}pts qoq")
    if er is not None and er < -0.01:
        neg.append(f"estimates cut {er * 100:+.0f}%")   # sub-1% drift
        # is marking noise, not a cut — AVGO at -0.3% is not the street
        # slashing numbers
    if bs is not None and bs <= 0:
        neg.append("no recent beat")
    ce, cr = m.get("capex_eff"), m.get("capex_rev")
    if cr is not None and cr > 0.30 and ce is not None and ce < 0:
        neg.append("capex not converting to GP")   # buildout burning
        # capital without the gross-profit payoff — NBIS's key risk
        # leg; only fires on genuinely capital-intensive names
    if tr is not None and tr < -5 and bs and bs > 0:
        neg.append(f"beats shrinking {tr:+.0f}pts")   # still beating
        # but smaller — a miss is already counted by the streak leg
    # --- improving legs (the acceleration counter) ---
    if rg is not None and rg > 0.15:
        pos.append(f"rev {rg * 100:+.0f}%")
    if ra is not None and ra > 0.10:
        pos.append(f"rev accel {ra * 100:+.0f}pts")
    if eg is not None and eg > 0.15:
        pos.append(f"eps {eg * 100:+.0f}%")
    if ea is not None and ea > 0.10:
        pos.append(f"eps accel {ea * 100:+.0f}pts")
    if gms is not None and gms > 0.01:
        pos.append(f"margin +{gms * 100:.0f}pts")
    if er is not None and er > 0.02:
        pos.append(f"estimates {er * 100:+.0f}% ↑")
    if bs is not None and bs >= 3:
        pos.append(f"{bs}q beats")
    if tr is not None and tr > 5:
        pos.append(f"beats growing {tr:+.0f}pts")
    if cr is not None and cr > 0.30 and ce is not None and ce > 0.3:
        pos.append(f"capex → GP at {ce:.0%}")
    if m.get("muted_reaction"):
        pos.append("muted reaction")

    # forward axis — what the street is doing to estimates, kept
    # distinct from the trailing legs so trailing×forward quadrants
    # (turnaround / pressured) are visible
    fwd_up = ((er is not None and er > 0.02)
              or (rb is not None and rb >= 2))
    fwd_dn = ((er is not None and er < -0.02)
              or (rb is not None and rb <= -2))

    n_neg, n_pos = len(neg), len(pos)
    # trailing-only negatives — the estimates-cut leg is forward, not
    # trailing, so it can't make a turnaround invisible
    trail_neg = n_neg - (1 if (er is not None and er < -0.01) else 0)
    # hard trailing negatives = level deterioration (weak rev level,
    # shrinking eps, missed quarter, YoY margin loss, capex not
    # converting). Pure decel legs off a strong base aren't a 'weak
    # trailing picture' — CBRS (-20pts decel off +103%) isn't a
    # turnaround; CAT (eps shrinking + street revising up) is
    hard_neg = sum(1 for leg in neg if any(
        leg.startswith(p) for p in
        ("rev growth weak", "eps shrinking", "no recent beat",
         "margin down", "capex not converting")))
    # a qoq-only margin leg is decel, not level deterioration
    if gmq is not None and gmq < -0.01 and not (
            gms is not None and gms < -0.01):
        hard_neg -= 1
    # a mild YoY margin drift is compression noise, not trailing level
    # damage — ALAB at -2.6pts isn't CBRS at -16.9pts
    if gms is not None and -0.05 <= gms < -0.01:
        hard_neg -= 1
    have_data = any(m.get(k) is not None for k in
                    ("rev_growth", "eps_growth", "beat_streak"))

    # acceleration evidence — trailing accel legs OR a forward revision
    # surge (the street accelerating estimates IS acceleration evidence;
    # CIEN's +28% revisions with flat trailing accel is still accelerating)
    accel_evidence = ((ra is not None and ra > 0.05)
                      or (ea is not None and ea > 0.05)
                      or (er is not None and er > 0.10))
    # demand-side accel for the accelerating state itself: revenue
    # accelerating or the street raising estimates materially. EPS-only
    # accel on a mature grower is margin/buyback math, not business
    # acceleration (CRM: eps accel +67pts on +11% rev = growing, not
    # accelerating). revision BREADTH alone isn't evidence either —
    # many small re-marks aren't a thesis upgrade
    demand_accel = ((ra is not None and ra > 0.05)
                    or (er is not None and er > 0.10))

    if not have_data:
        state = "unknown"
    elif n_neg >= 4 and ((rg is not None and rg < 0.08)
                         or (er is not None and er < -0.02)
                         or (rb is not None and rb <= -5)):
        state = "deteriorating"          # >=4 negs AND a real demand leg
        # — capex/margin negatives without weak revenue or meaningful
        # estimate cuts are investment-cycle stress, not breakdown (CBRS)
    elif n_neg >= 4:
        state = "declining"              # broad stress, demand intact
    elif cyclical:
        state = "cyclical"               # judge by leading legs, not
        # trailing earnings — the detail records which way the cycle leans
    elif (trail_neg >= 2 and hard_neg >= 1 and fwd_up
          and (rg is None or rg < 0.15)):
        state = "turnaround"             # trailing LEVEL weak, street
        # revising UP — early-CAT quadrant. A +30%/+100% grower with
        # margin compression isn't 'recovering from weakness' — the
        # weak trailing level is what makes it a turnaround
    elif (trail_neg <= 1 and n_pos >= 2 and fwd_dn
          and not accel_evidence and (rg is None or rg > 0)):
        state = "pressured"              # trailing fine, cuts coming —
        # the top before the bad quarter prints. Strong accel evidence
        # overrides: net breadth trims during a beat-and-raise quarter
        # are caution, not a stall. rg > 0 floor: 'pressured' means the
        # trailing business is FINE — a company already shrinking
        # revenue is declining, not pressured
    elif rg is not None and rg <= 0:
        state = "declining"              # growth actually negative
    elif rg is not None and rg > 0.08 and n_neg <= 3 and (
            (ra is not None and ra < -0.05)
            or (ea is not None and ea < -0.05)):
        state = "slowing"                # still growing, rate falling —
        # runs before the weak-grower gate: a mature co at +13% with
        # soft negatives is 'slowing', not 'declining' (INTU)
    elif n_neg >= 2 and (rg is None or rg < 0.15):
        state = "declining"              # several metrics worsening, weak
    elif (rg is not None and rg > 0.10                     # the early warn
          and demand_accel and n_pos >= 3
          and not (er is not None and er < -0.05)
          and (n_neg <= 1 or (n_neg <= 2 and hard_neg == 0))):
        state = "accelerating"           # multiple leading legs improving
        # AND nothing material going the other way — EPS halving or
        # estimate cuts can't ride along with an accelerating label;
        # two soft legs (mild margin drift, shrinking beats) can.
        # A real estimate cut (>5%) vetoes it entirely: accelerating
        # WITH the street slashing forward numbers is exactly the
        # false-acceleration error class (PL: rev +58% but er -137%)
    elif (rg is not None and rg > 1.0
          and n_pos >= 3 and n_neg == 0
          and not (er is not None and er < -0.05)):
        state = "accelerating"           # hypergrowth with clean legs —
        # accel is nulled at +400% growth by base-effect guards, but the
        # level itself is the acceleration evidence (NBIS)
    elif (rg is not None and rg > 0.08 and
          (n_neg <= 1 or (n_neg <= 2 and rg > 0.25))):
        state = "growing"
    else:
        state = "watch"

    # --- risk is its own axis (valuation/coverage), per the design ---
    if pe is not None and pe > 60 and n_neg >= 2:
        risk = "very_high"
    elif (pe is not None and pe > 60) or (
            m.get("num_analysts") is not None
            and m["num_analysts"] < 4 and (pe or 0) > 30):
        risk = "high"
    elif (pe is not None and pe > 25) or n_neg >= 2:
        risk = "medium"
    else:
        risk = "low"

    if state == "cyclical":
        lean = ("accelerating — upcycle with leading legs confirming"
                if (n_pos >= 4 and n_pos > n_neg
                    and ((ra is not None and ra > 0.05)
                         or (er is not None and er > 0.10)))
                else "recovery leaning — leading legs improving while "
                     "trailing earnings weak" if n_pos > n_neg
                else "downturn leaning — leading legs also falling")
        why.append(lean)

    # cause overlay — WHY growth is decelerating/margins compressing.
    # demand_health runs on the legs we actually have (rev growth +
    # revisions; RPO/customer-usage/guidance aren't deterministic
    # inputs yet) — partial is flagged, never fabricated
    cause = _decel_cause(m, n_neg)
    margin_recovery = (gmq is not None and gmq < -0.01
                       and gms is not None and gms > 0
                       and (cr is None or ce is None or ce >= 0))
    demand = ("strong" if (rg is not None and rg > 0.40
                           and (er is None or er > 0))
              else "healthy" if (rg is not None and rg > 0.15
                                 and (er is None or er >= 0))
              else "weak" if (rg is not None and rg < 0.05)
              else "mixed")
    # degree annotation — accelerating is canonical; "strong" requires
    # hypergrowth-level revenue AND forward estimate support AND strong
    # demand. ALAB/NBIS qualify; AVGO doesn't (fwd_dn), CIEN doesn't
    # (37% rev growth is fast but below the hypergrowth bar)
    accel_grade = ("strong" if (state == "accelerating"
                               and rg is not None and rg > 0.40
                               and fwd_up and demand == "strong")
                   else None)
    monitor = None
    if cause == "capacity_investment":
        monitor = ["margin fails to recover next print",
                   "rev growth falls below 20%",
                   "estimate revisions turn negative"]
    elif cause == "demand_deterioration":
        monitor = ["rev growth continues lower",
                   "revisions stay negative"]
    detail = {"neg": neg, "pos": pos, "n_neg": n_neg, "n_pos": n_pos,
              "fwd": ("up" if fwd_up else "down" if fwd_dn else "flat"),
              "why": (neg[:3] + pos[:3] if n_neg >= 2 else pos[:4]
                      + neg[:2]), "cyclical_lean": None,
              "decel_cause": cause,
              "accel_grade": accel_grade,
              "demand_health": demand,
              "demand_data_partial": True,
              "margin_compression_transient": margin_recovery or None,
              "monitor": monitor}
    if state == "cyclical":
        detail["cyclical_lean"] = (
            "accelerating" if (n_pos >= 4 and n_pos > n_neg
                               and ((ra is not None and ra > 0.05)
                                    or (er is not None and er > 0.10)))
            else "recovery" if n_pos > n_neg else "downturn")
    return state, risk, detail


# --- revision grade -----------------------------------------------------------
# Street estimate-revision momentum as a standalone flag (SA-quant-style
# letter grade) — deliberately separate from fundamental_state: revisions
# are the FORWARD axis; a turnaround can carry A+ revisions while the
# trailing business is still weak. Composite = 60% revision magnitude
# (est_revision_pct) + 40% net breadth (rev_breadth_30d), each
# percentile-ranked against the tracked universe.

_REV_BANDS = [(90, "A+"), (80, "A"), (70, "A-"), (60, "B+"), (50, "B"),
              (40, "B-"), (30, "C+"), (20, "C"), (10, "C-"), (5, "D")]


def _revision_grade(m: dict, er_dist: list, rb_dist: list) -> Optional[dict]:
    """One symbol → {score 0-100, grade, legs}. Percentiles are computed
    against the full universe passed in, so single-symbol refreshes stay
    universe-relative. Missing data ≠ bad grade — a name with no revision
    signal gets None, not F. Thin coverage (<3 analysts) caps at B+: a
    lone analyst re-marking isn't a revision trend (IDCC lesson)."""
    import bisect
    er, rb, na = (m.get("est_revision_pct"), m.get("rev_breadth_30d"),
                  m.get("num_analysts"))
    legs, weights = [], []
    if er is not None and er_dist:
        legs.append((bisect.bisect_right(er_dist, er)
                     / len(er_dist) * 100, 0.6, "er"))
        weights.append(0.6)
    if rb is not None and rb_dist:
        legs.append((bisect.bisect_right(rb_dist, rb)
                     / len(rb_dist) * 100, 0.4, "rb"))
        weights.append(0.4)
    if not legs:
        return None
    score = sum(p * w for p, w, _ in legs) / sum(weights)
    score = round(score, 1)
    grade = next((g for floor, g in _REV_BANDS if score >= floor), "F")
    capped = bool(na is not None and na < 3
                  and grade in ("A+", "A", "A-"))
    if capped:
        grade = "B+"
    return {"score": score, "grade": grade, "capped_thin_coverage": capped,
            "er": er, "er_pctl": next((round(p, 1) for p, w, k in legs
                                      if k == "er"), None),
            "rb": rb, "rb_pctl": next((round(p, 1) for p, w, k in legs
                                      if k == "rb"), None),
            "num_analysts": na}


def _pct(x):  return f"{x * 100:+.0f}%" if x is not None else None


def diff(prev: Optional[dict], cur: dict) -> tuple[list[str], str]:
    """Compare today's metrics vs the previous snapshot → (changes, alert).

    Alert level counts negative material changes:
        0 → normal · 1-2 → attention · 3 → warning · 4+ → critical
    """
    changes: list[str] = []
    if not prev:
        return changes, "normal"
    bad = 0

    def _d(key: str, label: str, scale: float = 100.0,
           bad_below: float = -5.0, suffix: str = "pts") -> None:
        nonlocal bad
        a, b = prev.get(key), cur.get(key)
        if a is None or b is None:
            return
        d = (b - a) * scale
        if abs(d) < 1:
            return
        arrow = "↑" if d > 0 else "↓"
        changes.append(f"{label} {d:+.0f}{suffix} {arrow}")
        if d <= bad_below:
            bad += 1

    _d("rev_growth", "rev growth")
    _d("eps_growth", "eps growth")
    _d("gm_now", "gross margin", scale=100.0, bad_below=-1.0)
    _d("est_revision_pct", "estimates", scale=100.0, bad_below=-2.0,
       suffix="%")
    a, b = prev.get("beat_streak"), cur.get("beat_streak")
    if a is not None and b is not None and b < a:
        changes.append(f"beat streak {a}→{b} ↓")
        bad += 1
    a, b = prev.get("fwd_pe"), cur.get("fwd_pe")
    if a and b:
        re_rate = b / a - 1
        if abs(re_rate) > 0.10:
            changes.append(f"fwd P/E {re_rate * 100:+.0f}% "
                           f"{'⚠️' if re_rate > 0 else ''}")
            if re_rate > 0.20:
                bad += 1                  # sharp valuation expansion
    if _STATE_RANK.get(cur.get("state"), 7) > \
            _STATE_RANK.get(prev.get("state"), 7):
        bad += 1
        changes.append(f"status {prev.get('state')}→{cur.get('state')} ↓")

    level = ("critical" if bad >= 4 else "warning" if bad == 3
             else "attention" if bad >= 1 else "normal")
    return changes, level


# --- persistence --------------------------------------------------------------

def _persist(sym: str, state: str, risk: str, detail: dict) -> None:
    from app.database import db
    rev = detail.get("revision") or {}
    db.execute_query(
        "UPDATE stocks SET fundamental_state=:st, fundamental_risk=:rk,"
        " fundamental_detail=CAST(:d AS jsonb),"
        " fundamental_updated_at=now(),"
        " revision_score=:rs, revision_grade=:rg WHERE symbol=:s",
        {"st": state, "rk": risk, "d": __import__("json").dumps(detail),
         "s": sym, "rs": rev.get("score"), "rg": rev.get("grade")})
    metrics = {k: detail.get("cur", {}).get(k) for k in _METRICS}
    db.execute_query(
        "INSERT INTO fundamental_snapshots (symbol, as_of, state, risk,"
        " metrics) VALUES (:s,:d,:st,:rk,CAST(:m AS jsonb)) "
        "ON CONFLICT (symbol, as_of) DO UPDATE SET state=EXCLUDED.state,"
        " risk=EXCLUDED.risk, metrics=EXCLUDED.metrics",
        {"s": sym, "d": date.today().isoformat(), "st": state, "rk": risk,
         "m": __import__("json").dumps(metrics)})


def refresh_all(symbols: list[str] = None) -> dict:
    """Recompute the flag for every symbol with a flywheel row. Called
    at the tail of the flywheel refresh job (and from the board's
    refresh panel)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT f.symbol, f.rev_growth, f.rev_accel, f.eps_growth,"
        " f.eps_accel, f.eps_growth_ttm, f.gm_now, f.gm_slope, f.beat_streak,"
        " f.est_revision_pct, f.fwd_pe, f.num_analysts,"
        " f.muted_reaction, f.rev_breadth_30d, f.surprise_trend,"
        " f.gm_qoq,"
        " f.capex_eff, f.capex_rev, s.cyclical, f.updated_at "
        "FROM symbol_flywheel f JOIN stocks s ON s.symbol = f.symbol"
        + (" WHERE f.symbol = ANY(:syms)" if symbols else ""),
        {"syms": symbols} if symbols else None)
    prev = {r["symbol"]: r for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, metrics, state "
        "FROM fundamental_snapshots WHERE as_of < :d "
        "ORDER BY symbol, as_of DESC", {"d": date.today().isoformat()})}
    # revision percentiles are universe-relative — always computed
    # against the full flywheel, never the refresh subset
    dist = db.execute_query(
        "SELECT est_revision_pct er, rev_breadth_30d rb"
        " FROM symbol_flywheel")
    er_dist = sorted(float(x["er"]) for x in dist
                     if x["er"] is not None)
    rb_dist = sorted(float(x["rb"]) for x in dist
                     if x["rb"] is not None)

    counts: dict[str, int] = {}
    for r in rows:
        m = {k: r.get(k) for k in _METRICS}
        state, risk, detail = classify(m, bool(r.get("cyclical")))
        detail["revision"] = _revision_grade(m, er_dist, rb_dist)
        p = prev.get(r["symbol"]) or {}
        changes, level = diff({**(p.get("metrics") or {}),
                               "state": p.get("state") or "unknown"},
                              {**m, "state": state})
        detail["cur"], detail["changes"], detail["alert"] = m, changes, level
        # staleness visibility — the classifier runs on whatever the
        # flywheel row holds; a confident label on 3-week-old metrics
        # must say so rather than read as a fresh verdict
        ua = r.get("updated_at")
        if ua is not None:
            age = (date.today()
                   - (ua.date() if hasattr(ua, "date") else ua)).days
            detail["flywheel_age_days"] = age
            if age > 21:
                detail["stale_inputs"] = True
                detail["why"] = ([f"flywheel {age}d stale"]
                                 + (detail.get("why") or []))
        try:
            _persist(r["symbol"], state, risk, detail)
        except Exception as exc:
            logger.debug("fund flag %s: %s", r["symbol"], exc)
        counts[state] = counts.get(state, 0) + 1
    return {"refreshed": len(rows), "states": counts}
