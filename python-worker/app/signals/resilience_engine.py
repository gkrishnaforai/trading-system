"""Resilience engine — the FICO-style company scorecard.

Three independent scores + two disclosures, never one opaque number:

  company_health   is the business financially strong?        (generic)
  ai_opportunity   does AI infra create measurable demand?    (classified names only)
  tape_resilience  is the stock showing relative strength?    (generic)
  deployment_risk  project-permitting/conversion risk         (reported, higher = worse)
  data_confidence  measured vs prior-filled vs missing        (reported)

Every score ships with its own proof — checks[] (earned/unearned
criteria), flags[] (validation findings), needs[] (the highest-weight
missing criterion). A 90 must show the checkmarks that earned 90;
missing evidence is reported, never silently filled by priors.

Scoring conventions (same as opportunity/fragility):
- legs renormalize over what's live; <40% coverage -> no score
- module priors are curated and tagged 'prior', never 'measured'
- RPO leg requires the real RevenueRemainingPerformanceObligation
  tag AND a fresh period (XBRL RPO is NOT universal backlog —
  contract-liability fallback tags feed deferred-rev, not backlog)
- growth fields are validated against SEC XBRL by the nightly
  fact-check pass (symbol_fact_checks); unverified != contradicted

Versioning: FORMULA_VERSION bumps when legs/thresholds change —
scores are only comparable within a version. run() journals
company_resilience_scores (append-only per day) and diffs vs the
prior row into alert_items: band crosses, |delta| >= 10, new flags,
check flips. FICO rules: the score travels with its reason codes.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

FORMULA_VERSION = 1

# ------------------------------------------------------------------
# Curated structural priors by business model (reviewed like
# THEME_SENSITIVITY/SYMBOL_WHY). Tuple: (bottleneck, permit_risk,
# complexity, global_exposure). permit_risk higher = MORE sensitive
# to local data-center permitting (worse), reported as deployment_risk.
# MODULE_DIR = AI-revenue directness by business model.
# ------------------------------------------------------------------
PRIOR = {
    'connectivity_silicon': (75, 15, 80, 85),
    'optical_photonics':    (70, 15, 75, 80),
    'networking_silicon':   (75, 15, 80, 85),
    'compute_accelerator':  (80, 15, 85, 90),
    'memory_storage':       (55, 15, 80, 85),
    'server_oem':           (30, 40, 30, 75),
    'power_delivery':       (55, 70, 40, 55),
    'thermal_cooling':      (50, 70, 40, 55),
    'power_gen':            (60, 75, 35, 40),
    'foundry_osat':         (85, 25, 90, 90),
    'ip_licensing':         (80, 10, 85, 90),
    'semicap_equipment':    (85, 20, 85, 90),
}
MODULE_DIR = {
    'compute_accelerator': 90, 'semicap_equipment': 85,
    'connectivity_silicon': 85, 'optical_photonics': 80,
    'networking_silicon': 80, 'foundry_osat': 85, 'ip_licensing': 80,
    'memory_storage': 75, 'server_oem': 60,
    'power_delivery': 55, 'thermal_cooling': 55, 'power_gen': 45,
}
# semicap/test names missing from ai_infra.yaml symbol_map — the
# overlay lands in the yaml next cycle; keep the fix explicit here.
MODULE_OVERLAY = {'LRCX': 'semicap_equipment', 'KLAC': 'semicap_equipment',
                  'ONTO': 'semicap_equipment', 'TER': 'semicap_equipment',
                  'AMAT': 'semicap_equipment', 'ASML': 'semicap_equipment'}

# per-module demand-leg weights: (backlog, rev_momentum, est_momentum,
# conversion). RPO semantics are weakest for WFE names — backlog leg
# gets less weight there, revenue momentum more.
DEMAND_W = {
    'semicap_equipment': (.20, .35, .30, .15),
    'optical_photonics': (.30, .30, .25, .15),
    'connectivity_silicon': (.20, .35, .30, .15),
    'power_delivery': (.40, .25, .20, .15),
    'power_gen': (.40, .25, .20, .15),
    'thermal_cooling': (.40, .25, .20, .15),
    'server_oem': (.20, .40, .25, .15),
    'memory_storage': (.20, .35, .30, .15),
    'compute_accelerator': (.25, .30, .30, .15),
    '_default': (.30, .30, .25, .15),
}
ORDERS_SCORE = {'accelerating': 80, 'stable': 55,
                'decelerating': 30, 'contracting': 10}
AI_THEMES = {'ai_inference', 'ai_optics', 'dc_power_cooling',
             'grid_electrification', 'hbm_memory', 'ai_software'}
EXPO_S = {'pure': 90, 'derivative': 60, 'speculative': 35}
NEG_STANCE = {'trim_candidate', 'exit_risk', 'exit_thesis'}
REAL_RPO = 'RevenueRemainingPerformanceObligation'

FRESH_DAYS = 550          # sec fact freshness
XBRL_FRESH = 550          # cross-check reference frame
FY_FRESH = 400            # fiscal-year frame for base-effect/fwd checks
COV_MIN = 0.05            # committed-demand coverage threshold
COVERAGE_FLOOR = 0.40     # below -> no score (codebase convention)

# plausible bounds — out-of-range input is invalid data, not a score.
# Feeds the '!' BAD DATA mark on score cards.
BOUNDS = {
    'rev_growth': (-0.9, 5.0), 'eps_growth': (-1.0, 10.0),
    'rev_accel': (-1.0, 1.0), 'gm_now': (0.0, 0.95),
    'gm_slope': (-0.5, 0.5), 'om_slope': (-0.5, 0.5),
    'fcf_margin': (-1.0, 0.9), 'net_debt_ebitda': (-10, 15),
    'sbc_rev': (0.0, 1.0), 'roic': (-1.0, 1.5),
    'est_revision_pct': (-0.8, 0.8), 'surprise_trend': (-200, 200),
    'capex_rev': (0.0, 2.0),
}


# --- small helpers ----------------------------------------------------

def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _map(v, lo, hi) -> Optional[float]:
    v = _f(v)
    if v is None:
        return None
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))


def _comp(parts) -> tuple[Optional[float], float, float]:
    """(score, coverage, measured_share) over live legs.
    parts: (score, weight, tag) tag in {'m','p'} measured|prior."""
    live = [(s, w, t) for s, w, t in parts if s is not None]
    if not live:
        return None, 0.0, 0.0
    tw = sum(w for _, w, _ in live)
    allw = sum(w for _, w, _ in parts)
    meas = sum(w for _, w, t in live if t == 'm')
    return sum(s * w for s, w, _ in live) / tw, tw / allw, meas / allw


def _bv(f: dict, k: str) -> tuple[Optional[float], bool]:
    """bounded value — (None, True) when implausible (bad data)."""
    v = _f(f.get(k))
    if v is None:
        return None, False
    lo, hi = BOUNDS.get(k, (-1e18, 1e18))
    return (v, False) if lo <= v <= hi else (None, True)


def _age(dstr) -> Optional[int]:
    try:
        return (date.today() - date.fromisoformat(str(dstr)[:10])).days
    except Exception:
        return None


def _check(label, ok, detail, wt=0.0, invalid=False):
    return {'label': label, 'ok': bool(ok), 'detail': detail,
            'wt': wt, 'invalid': invalid}


# --- data reads ---------------------------------------------------------

def _facts(sym: str) -> dict[str, Any]:
    """One query per store — journaled evidence, all optional."""
    from app.database import db
    out: dict[str, Any] = {}
    try:
        r = db.execute_query(
            "SELECT rev_growth, rev_accel, eps_growth, gm_now, gm_slope,"
            " om_slope, fcf_margin, net_debt_ebitda, sbc_rev, roic,"
            " est_revision_pct, surprise_trend, beat_streak, fwd_rev_avg,"
            " capex_rev, cust_top1_pct, as_of"
            " FROM symbol_flywheel WHERE symbol=:s", {"s": sym})
        out['flywheel'] = dict(r[0]) if r else {}
    except Exception as e:
        logger.debug('resilience flywheel %s: %s', sym, e)
        out['flywheel'] = {}
    try:
        r = db.execute_query(
            "SELECT rpo, rpo_yoy, crpo_share, def_rev_cur, def_rev_yoy,"
            " rpo_period, as_of, facts->'rpo_tag' rpo_tag"
            " FROM symbol_sec_facts WHERE symbol=:s", {"s": sym})
        out['sec'] = dict(r[0]) if r else {}
    except Exception as e:
        logger.debug('resilience sec %s: %s', sym, e)
        out['sec'] = {}
    try:
        r = db.execute_query(
            "SELECT DISTINCT ON (symbol) business_strength,"
            " ai_tailwind_score, business_model, recommendation, as_of"
            " FROM research_runs WHERE symbol=:s"
            " ORDER BY symbol, as_of DESC", {"s": sym})
        out['research'] = dict(r[0]) if r else {}
    except Exception as e:
        logger.debug('resilience research %s: %s', sym, e)
        out['research'] = {}
    try:
        r = db.execute_query(
            "SELECT momentum_detail FROM stocks WHERE symbol=:s",
            {"s": sym})
        md = r[0].get('momentum_detail') if r else None
        out['mom'] = md if isinstance(md, dict) else (
            json.loads(md) if isinstance(md, str) else {})
    except Exception:
        out['mom'] = {}
    try:
        r = db.execute_query(
            "SELECT DISTINCT ON (symbol) doc_period, orders_language,"
            " demand_score, confidence FROM transcript_scores"
            " WHERE symbol=:s ORDER BY symbol, doc_period DESC", {"s": sym})
        out['transcript'] = dict(r[0]) if r else {}
    except Exception:
        out['transcript'] = {}
    try:
        rows = db.execute_query(
            "SELECT close FROM (SELECT close, ROW_NUMBER() OVER"
            " (ORDER BY date DESC) rn FROM daily_bars"
            " WHERE symbol=:s) t WHERE rn<=70 ORDER BY rn DESC",
            {"s": sym})
        out['bars'] = [float(r['close']) for r in rows]
    except Exception:
        out['bars'] = []
    try:
        rows = db.execute_query(
            "SELECT theme_key, members FROM theme_registry"
            " WHERE status='active'")
        ths = []
        for r in rows:
            mem = r.get('members') or {}
            if isinstance(mem, str):
                mem = json.loads(mem)
            if sym in mem:
                ths.append((r['theme_key'], mem[sym]))
        out['themes'] = ths
    except Exception:
        out['themes'] = []
    try:
        rows = db.execute_query(
            "SELECT payload FROM symbol_flow"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        p = rows[0].get("payload") if rows else None
        out['flow'] = json.loads(p) if isinstance(p, str) else (p or {})
    except Exception:
        out['flow'] = {}
    try:
        rows = db.execute_query(
            "SELECT outlook, quality FROM symbol_guidance"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        out['guide'] = rows[0] if rows else {}
    except Exception:
        out['guide'] = {}
    try:
        rows = db.execute_query(
            "SELECT payload FROM symbol_earnings_quality"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        p = rows[0].get("payload") if rows else None
        out['eq'] = json.loads(p) if isinstance(p, str) else (p or {})
    except Exception:
        out['eq'] = {}
    try:
        rows = db.execute_query(
            "SELECT field, verdict, evidence FROM symbol_fact_checks"
            " WHERE symbol=:s AND field='rev_growth'"
            " ORDER BY checked_at DESC LIMIT 1", {"s": sym})
        out['fact_check'] = dict(rows[0]) if rows else {}
    except Exception:
        out['fact_check'] = {}
    return out


def _spy_closes() -> list[float]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT close FROM (SELECT close, ROW_NUMBER() OVER"
            " (ORDER BY date DESC) rn FROM daily_bars"
            " WHERE symbol='SPY') t WHERE rn<=70 ORDER BY rn DESC")
        return [float(r['close']) for r in rows]
    except Exception:
        return []


# --- validator (nightly, slow OK) ----------------------------------------

def validate_facts(sym: str) -> dict[str, Any]:
    """Cross-check provider fundamentals against SEC XBRL — slow is
    fine, EDGAR is free. Journals symbol_fact_checks rows; the scorer
    reads the latest verdict instead of trusting the flywheel raw."""
    from app.database import db
    from app.providers import sec_edgar
    f = _facts(sym)
    fl = f['flywheel']
    checks = []
    rg = _f(fl.get('rev_growth'))
    if rg is not None:
        try:
            blob = sec_edgar.company_facts(sym)
            gaap = (blob.get('facts') or {}).get('us-gaap') or {}
            best_q = None
            for tag in ('RevenueFromContractWithCustomerExcludingAssessedTax',
                        'Revenues', 'SalesRevenueNet'):
                rows = ((gaap.get(tag) or {}).get('units') or {}).get('USD') or []
                qs = {}
                for r in rows:
                    if not r.get('start') or not r.get('end'):
                        continue
                    span = (date.fromisoformat(r['end'])
                            - date.fromisoformat(r['start'])).days
                    if 70 <= span <= 100:
                        qs[r['end']] = max(qs.get(r['end'], 0),
                                           float(r['val']))
                if qs and (best_q is None or max(qs) > best_q[0]):
                    best_q = (max(qs), tag, qs)
            if best_q:
                _, tag, qs = best_q
                ends = sorted(qs)
                e0 = ends[-1]
                yoy = None
                for e in ends[:-1]:
                    dd = (date.fromisoformat(e0)
                          - date.fromisoformat(e)).days
                    if 320 <= dd <= 410 and qs[e] > 0:
                        yoy = qs[e0] / qs[e] - 1
                q_age = _age(e0)
                ev = {'q_end': e0, 'q_rev': qs[e0], 'q_yoy': yoy,
                      'tag': tag, 'flywheel': rg}
                if yoy is None or q_age is None or q_age > XBRL_FRESH:
                    checks.append({'field': 'rev_growth',
                                   'verdict': 'unverifiable_stale',
                                   'evidence': ev})
                else:
                    tol = max(0.15, abs(yoy) * 0.15)
                    checks.append({'field': 'rev_growth',
                                   'verdict': 'verified' if abs(rg - yoy) <= tol
                                   else 'contradicted', 'evidence': ev})
            else:
                checks.append({'field': 'rev_growth',
                               'verdict': 'unverifiable_missing',
                               'evidence': {'flywheel': rg}})
        except Exception as e:
            checks.append({'field': 'rev_growth',
                           'verdict': 'check_error',
                           'evidence': {'error': str(e)[:120]}})
    for c in checks:
        try:
            db.execute_update(
                "INSERT INTO symbol_fact_checks"
                " (symbol, field, verdict, evidence, checked_at)"
                " VALUES (:s,:f,:v,CAST(:e AS jsonb),now())",
                {"s": sym, "f": c['field'], "v": c['verdict'],
                 "e": json.dumps(c['evidence'], default=str)})
        except Exception as exc:
            logger.debug('fact_checks %s: %s', sym, exc)
    return {'symbol': sym, 'checks': checks}


# --- scorer --------------------------------------------------------------

def compute(sym: str) -> dict[str, Any]:
    """Full score card for one symbol — scores + checks + flags."""
    d = _facts(sym)
    f, sec, r = d['flywheel'], d['sec'], d['research']
    mom, t, ths = d['mom'], d['transcript'], d['themes']
    ai_ths = [q for q in ths if q[0] in AI_THEMES]
    bm = MODULE_OVERLAY.get(sym) or (
        r.get('business_model')
        if r.get('business_model') != 'unclassified' else None)
    pr = PRIOR.get(bm)
    mdir = MODULE_DIR.get(bm)

    # bounded inputs — implausible values are BAD DATA, not scores
    rg, bad_rg = _bv(f, 'rev_growth')
    ra, _ = _bv(f, 'rev_accel')
    eg, _ = _bv(f, 'eps_growth')
    gmn, _ = _bv(f, 'gm_now')
    gms, _ = _bv(f, 'gm_slope')
    oms, _ = _bv(f, 'om_slope')
    fcf, bad_fcf = _bv(f, 'fcf_margin')
    nde, _ = _bv(f, 'net_debt_ebitda')
    sbc, _ = _bv(f, 'sbc_rev')
    roic, _ = _bv(f, 'roic')
    er, bad_er = _bv(f, 'est_revision_pct')
    st, _ = _bv(f, 'surprise_trend')
    cr, _ = _bv(f, 'capex_rev')
    bs = _f(r.get('business_strength'))

    # cross-check verdict from the nightly fact pass
    fc = d['fact_check']
    verdict = (fc or {}).get('verdict')
    xq = _f((fc or {}).get('evidence', {}).get('q_yoy')
            if isinstance((fc or {}).get('evidence'), dict) else None)
    if verdict == 'verified':
        xstate = 'xbrl-verified'
    elif verdict in ('unverifiable_stale', 'unverifiable_missing',
                     'check_error', None):
        xstate = 'unverified'
    else:
        xstate = 'contradicted'
    xok = verdict == 'verified'

    rpo_ok = (sec.get('rpo_tag') == REAL_RPO
              and (_age(sec.get('rpo_period')) or 9999) <= FRESH_DAYS)
    sec_fresh = (_age(sec.get('as_of')) or 9999) <= FRESH_DAYS
    cov_ratio = None
    if (rpo_ok or (sec_fresh and _f(sec.get('def_rev_cur')))) \
            and _f(f.get('fwd_rev_avg')):
        cov = ((_f(sec.get('rpo')) or 0) if rpo_ok else 0) \
              + ((_f(sec.get('def_rev_cur')) or 0) if sec_fresh else 0)
        cov_ratio = cov / _f(f['fwd_rev_avg']) or None
    committed = cov_ratio is not None and cov_ratio >= COV_MIN
    ord_s = ORDERS_SCORE.get(t.get('orders_language')) if t else None
    conv_s = _map(sec.get('crpo_share') if rpo_ok else None, 0.2, 0.7)

    # ---- scores ----
    growth, _, _ = _comp([(_map(rg, 0, 0.5), .5, 'm'),
                          (_map(eg, 0, 1.0), .3, 'm'),
                          (_map(ra, -0.1, 0.1), .2, 'm')])
    marg, _, _ = _comp([(_map((gmn or 0) * 100, 10, 70), .4, 'm'),
                        (_map(gms, -0.05, 0.05), .3, 'm'),
                        (_map(oms, -0.05, 0.05), .3, 'm')])
    cash, _, _ = _comp([(_map(fcf, -0.05, 0.30), .5, 'm'),
                        (_map(nde, 3, -1), .3, 'm'),
                        (_map(sbc, 0.15, 0), .2, 'm')])
    revs, _, _ = _comp([(_map(er, -0.10, 0.20), .6, 'm'),
                        (_map(st, -30, 30), .4, 'm')])
    eq_row = d.get('eq') or {}
    eq_s = _f(eq_row.get('quality'))
    g_out = _f((d.get('guide') or {}).get('outlook'))
    eq, eq_cov, eq_m = _comp([(growth, .28, 'm'), (marg, .23, 'm'),
                              (cash, .18, 'm'), (revs, .18, 'm'),
                              (eq_s, .13, 'm'), (g_out, .10, 'm')])
    health, h_cov, h_m = _comp([(eq, .75, 'm'), (bs, .25, 'm')])
    if h_cov < COVERAGE_FLOOR:
        health = None

    def rel(n):
        bars, spy = d['bars'], _load_spy()
        if len(bars) < n + 1 or len(spy) < n + 1:
            return None
        a = bars[-1] / bars[-1 - n] - 1 if bars[-1 - n] else None
        b = spy[-1] / spy[-1 - n] - 1 if spy[-1 - n] else None
        return a - b if a is not None and b is not None else None
    # institutional flow — signed streak maps: accumulating supports
    # tape, distributing subtracts. Small weight — evidence, not thesis
    fl = d.get('flow') or {}
    fl_dir = {'accumulating': 80, 'distributing': 20}.get(
        fl.get('footprint'))
    tape, t_cov, _ = _comp([
        (_map(rel(1), -0.08, 0.08), .05, 'm'),
        (_map(rel(5), -0.10, 0.10), .15, 'm'),
        (_map(rel(20), -0.15, 0.15), .25, 'm'),
        (_map(rel(60), -0.20, 0.20), .25, 'm'),
        (_map(mom.get('down_cap'), 0.2, 0.8), .20, 'm'),
        (fl_dir, .10, 'm')])
    if t_cov < COVERAGE_FLOOR:
        tape = None

    deploy, _, _ = _comp([(pr[1] if pr else None, .6, 'p'),
                          (_map(cr, 0.1, 0.5), .4, 'm')])
    bl, _, _ = _comp([
        (_map(sec.get('rpo_yoy') if rpo_ok else None, -0.3, 0.5), .35, 'm'),
        (_map(cov_ratio, 0.05, 0.50), .35, 'm'),
        (_map(sec.get('def_rev_yoy') if sec_fresh else None,
              -0.3, 0.3), .20, 'm'),
        (ord_s, .10, 'm')])
    rvm, _, _ = _comp([(_map(rg, 0, 0.5), .6, 'm'),
                       (_map(ra, -0.1, 0.1), .4, 'm')])

    ai_ok = pr is not None or ai_ths
    struct = dem = ai = directness = None
    s_m = 0.0
    if ai_ok:
        struct, _, s_m = _comp([
            (pr[0] if pr else None, .30, 'p'), (bs, .30, 'm'),
            (_map((gmn or 0) * 100, 10, 70), .20, 'm'),
            (_map((roic or 0) * 100, 5, 25), .20, 'm')])
        w = DEMAND_W.get(bm, DEMAND_W['_default'])
        dem, _, _ = _comp([(bl, w[0], 'm'), (rvm, w[1], 'm'),
                           (revs, w[2], 'm'), (conv_s, w[3], 'm')])
        ai, _, _ = _comp([(struct, .35, 'x'), (dem, .40, 'x'),
                          (eq, .25, 'x')])
        tier = [EXPO_S.get(q[1]) for q in ai_ths if EXPO_S.get(q[1])]
        directness = max(tier + [mdir or 0]) if (tier or mdir) else None

    # ---- event recovery — journaled evidence, never a score input ----
    ev = None
    bars = d['bars']
    if len(bars) >= 3:
        wed, thu, fri = bars[-3], bars[-2], bars[-1]
        drop = wed - thu
        if drop > 0:
            ev = {'pct_recovered': round((fri - thu) / drop, 2),
                  'thu_ret': round(thu / wed - 1, 3),
                  'fri_ret': round(fri / thu - 1, 3)}

    # ---- checklists ----
    rg_d = (f'{rg * 100:.0f}% {xstate}' if rg is not None
            else 'missing')
    health_chk = [
        _check('revenue growth >=15%', rg and rg >= 0.15, rg_d, .25,
               invalid=bad_rg),
        _check('margins stable/expanding', gms is not None and gms >= 0,
               f'gm {gmn * 100:.0f}% slope {gms * 100:+.1f}pp'
               if gmn is not None and gms is not None else 'missing',
               .20),
        _check('positive free cash flow', fcf is not None and fcf > 0,
               'BAD DATA: fcf_margin out of range' if bad_fcf else
               (f'fcf margin {fcf * 100:.0f}%'
                if fcf is not None else 'missing'), .20,
               invalid=bad_fcf),
        _check('balance sheet OK (nde<2)', nde is not None and nde < 2,
               f'net debt/ebitda {nde:.1f}'
               if nde is not None else 'missing', .15),
        _check('business strength >=60', bs is not None and bs >= 60,
               f'bs {bs:.0f}' if bs is not None else 'missing', .20),
    ]
    dem_chk = [
        _check('verified revenue growth >=25%',
               rg and rg >= 0.25 and xok,
               f'{rg * 100:.0f}% {xstate}' if rg else 'missing', .25),
        _check('committed-demand evidence (covr>=5%)', committed,
               f'covr {cov_ratio:.2f}x' if cov_ratio is not None
               else 'no RPO/backlog in XBRL', .30),
        _check('estimate revisions positive', er is not None and er > 0,
               f'{er * 100:+.1f}%' if er is not None else 'missing', .15),
        _check('revenue accelerating', ra is not None and ra > 0,
               f'accel {ra * 100:+.0f}pp' if ra is not None else 'missing',
               .10),
        _check('order language confirmed', ord_s is not None and ord_s >= 55,
               (t.get('orders_language') or 'no transcript'), .10),
        _check('conversion visibility', conv_s is not None,
               'crpo_share present' if conv_s is not None else 'missing',
               .10),
    ]
    pure = any(q[1] == 'pure' for q in ai_ths) or (mdir or 0) >= 80
    pure_d = (','.join(f'{q[0]}:{q[1]}' for q in ai_ths)
              or (f'module:{bm} (dir {mdir})' if mdir else 'no AI theme'))
    struct_chk = [
        _check('verified moat (bs>=70)', bs is not None and bs >= 70,
               f'bs {bs:.0f}' if bs is not None else 'missing', .30),
        _check('pricing power (gm>=40%)', gmn is not None and gmn >= 0.40,
               f'gm {gmn * 100:.0f}%' if gmn is not None else 'missing',
               .25),
        _check('capital efficient (roic>=15%)',
               roic is not None and roic >= 0.15,
               f'roic {roic * 100:.0f}%' if roic is not None else 'missing',
               .20),
        _check('low deployment sensitivity',
               deploy is not None and deploy < 40,
               f'deploy risk {deploy:.0f}' if deploy is not None
               else 'missing', .15),
        _check('AI-pure exposure', pure, pure_d, .10),
    ]

    flags = []
    for k, bad in (('rev_growth', bad_rg), ('fcf_margin', bad_fcf),
                   ('est_revision_pct', bad_er)):
        if bad:
            flags.append(f'bad_data:{k}')
    if verdict == 'contradicted':
        flags.append('xcheck_fail')
    elif xstate == 'unverifiable' and rg is not None:
        flags.append('xbrl_unverifiable')
    elif xstate == 'not_yet_checked' and rg is not None:
        flags.append('xbrl_not_checked')
    if cov_ratio and cov_ratio > 1.5:
        flags.append(f'cov_outlier:{cov_ratio:.1f}x')
    if r.get('recommendation') in NEG_STANCE and (dem or 0) >= 75:
        flags.append(f'stance_div:{r["recommendation"]}')
    if ai_ok and bl is None and conv_s is None:
        flags.append('no_committed_evidence')

    needs = (sorted((c for c in dem_chk
                     if not c['ok'] and not c['invalid']),
                    key=lambda c: -c['wt']) if ai_ok else [])
    meas = round((eq_m or 0) * .5 + (s_m or 0) * .5, 2)

    return {
        'symbol': sym, 'formula_version': FORMULA_VERSION,
        'business_model': bm, 'stance': r.get('recommendation'),
        'scores': {
            'company_health': round(health) if health is not None else None,
            'ai_opportunity': round(ai) if ai is not None else None,
            'tape_resilience': round(tape) if tape is not None else None,
            'structural': round(struct) if struct is not None else None,
            'demand_visibility': round(dem) if dem is not None else None,
            'earnings_quality': round(eq) if eq is not None else None,
            'deployment_risk': round(deploy) if deploy is not None else None,
            'ai_directness': directness,
        },
        'checks': {'health': health_chk, 'demand': dem_chk,
                   'structural': struct_chk},
        'flags': flags,
        'guidance': {'outlook': g_out,
                     'quality': (d.get('guide') or {}).get('quality')},
        'earnings_quality': {'quality': eq_s,
                             'flags': eq_row.get('flags') or [],
                             'legs': eq_row.get('legs')},
        'flow': {'footprint': fl.get('footprint'),
                 'streak': fl.get('streak'),
                 'acc_days': fl.get('acc_days'),
                 'dist_days': fl.get('dist_days'),
                 'today': fl.get('today')},
        'needs': [c['label'] for c in needs[:2]],
        'event': ev,
        'coverage': {'measured_share': meas,
                     'xcheck': xstate,
                     'committed_evidence': committed},
        'themes': [{'theme': q[0], 'exposure': q[1]} for q in ths],
    }


_SPY: list[float] = []


def _load_spy():
    global _SPY
    if not _SPY:
        _SPY = _spy_closes()
    return _SPY


# --- table + journal + alerts -------------------------------------------

def ensure_table() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS company_resilience_scores ("
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " formula_version INT NOT NULL, payload JSONB NOT NULL,"
        " ai_score NUMERIC, health_score NUMERIC, tape_score NUMERIC,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " PRIMARY KEY (symbol, as_of))")
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_fact_checks ("
        " id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL,"
        " field TEXT NOT NULL, verdict TEXT NOT NULL,"
        " evidence JSONB, checked_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    db.execute_update(
        "CREATE INDEX IF NOT EXISTS sfc_sym_field"
        " ON symbol_fact_checks (symbol, field, checked_at DESC)")


def _alert(sym: str, title: str, detail: dict, priority: int = 50) -> None:
    """Score-move alerts ride the existing alert_items journal —
    fingerprinted so the same delta doesn't alert twice."""
    from app.database import db
    try:
        db.execute_update(
            "INSERT INTO alert_items (symbol, event_type, direction,"
            " materiality, title, detail, fingerprint, source,"
            " source_timestamp, in_portfolio, in_watchlist, status,"
            " priority_score)"
            " VALUES (:s,'resilience','neutral','MEDIUM',:t,"
            " CAST(:de AS jsonb),:fp,'resilience_engine',now(),"
            " false,false,'new',:pr)"
            " ON CONFLICT (fingerprint) DO NOTHING",
            {"s": sym, "t": title,
             "de": json.dumps(detail, default=str),
             "fp": f"resil:{sym}:{date.today()}:{title[:40]}",
             "pr": priority})
    except Exception as exc:
        logger.debug('resilience alert %s: %s', sym, exc)


_BANDS = ((75, 'strong'), (55, 'solid'), (40, 'mixed'), (0, 'weak'))


def _band(score: Optional[float]) -> str:
    s = score if score is not None else 0
    for lo, name in _BANDS:
        if s >= lo:
            return name
    return 'weak'


def run(symbols: list[str], validate: bool = False) -> dict[str, Any]:
    """Weekly compute + journal + diff alerts. validate=True runs the
    slow XBRL cross-check pass first (nightly job's call)."""
    from app.database import db
    ensure_table()
    _load_spy()
    n = alerts = 0
    errors = []
    for sym in symbols:
        try:
            if validate:
                validate_facts(sym)
            card = compute(sym)
            sc = card['scores']
            prev = db.execute_query(
                "SELECT payload FROM company_resilience_scores"
                " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
                {"s": sym})
            db.execute_update(
                "INSERT INTO company_resilience_scores"
                " (symbol, as_of, formula_version, payload,"
                "  ai_score, health_score, tape_score)"
                " VALUES (:s,:d,:v,CAST(:p AS jsonb),:a,:h,:t)"
                " ON CONFLICT (symbol,as_of) DO UPDATE SET"
                " payload=EXCLUDED.payload,"
                " formula_version=EXCLUDED.formula_version,"
                " ai_score=EXCLUDED.ai_score,"
                " health_score=EXCLUDED.health_score,"
                " tape_score=EXCLUDED.tape_score",
                {"s": sym, "d": date.today(), "v": FORMULA_VERSION,
                 "p": json.dumps(card, default=str),
                 "a": sc['ai_opportunity'], "h": sc['company_health'],
                 "t": sc['tape_resilience']})
            n += 1
            if prev:
                po = prev[0].get('payload')
                if isinstance(po, str):
                    po = json.loads(po)
                psc = (po or {}).get('scores') or {}
                for k, label in (('ai_opportunity', 'AI opp'),
                                 ('company_health', 'health'),
                                 ('tape_resilience', 'tape')):
                    old, new = psc.get(k), sc.get(k)
                    if old is None or new is None:
                        continue
                    delta = new - old
                    if abs(delta) >= 10:
                        _alert(sym, f"{sym} {label} {old}->{new}",
                               {'score': k, 'delta': delta,
                                'flags': card['flags']})
                    elif _band(old) != _band(new):
                        _alert(sym, f"{sym} {label} band "
                               f"{_band(old)}->{_band(new)}",
                               {'score': k, 'delta': delta,
                                'flags': card['flags']})
                new_flags = set(card['flags']) - set(
                    (po or {}).get('flags') or [])
                if new_flags:
                    alerts += 1
                    _alert(sym, f"{sym} new flags: "
                           f"{', '.join(sorted(new_flags))}",
                           {'flags': sorted(new_flags),
                            'scores': sc})
        except Exception as exc:
            errors.append(f'{sym}: {exc}')
            if len(errors) >= 20:
                break
    return {'scored': n, 'alerts': alerts, 'errors': errors[:10],
            'as_of': str(date.today())}


def _tape_live(sym: str) -> dict | None:
    try:
        from app.signals.live_overlay import tape_live
        return tape_live(sym)
    except Exception:
        return None


def _swing_live(sym: str) -> dict | None:
    try:
        from app.signals.live_overlay import swing_live
        return swing_live(sym)
    except Exception:
        return None


def read_all() -> list[dict[str, Any]]:
    """Latest card per symbol — the screener/readiness read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, as_of, payload,"
            " ai_score, health_score, tape_score"
            " FROM company_resilience_scores ORDER BY symbol, as_of DESC")
        # prior-snapshot scores for delta columns
        prev = {r['symbol']: r.get('payload') for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, payload"
            " FROM company_resilience_scores"
            " WHERE as_of < (SELECT max(as_of)"
            "                FROM company_resilience_scores)"
            " ORDER BY symbol, as_of DESC")}
        # latest 5-min recovery eval per symbol — one query merged per
        # row; only the ai-infra watch scope has rows
        try:
            from app.signals import intraday_recovery as _ir
            rec_map = _ir.current()
        except Exception:
            rec_map = {}
        out = []
        for r in rows:
            p = r.get('payload')
            if isinstance(p, str):
                p = json.loads(p)
            sc = (p or {}).get('scores') or {}
            po = prev.get(r['symbol'])
            po = json.loads(po) if isinstance(po, str) else (po or {})
            psc = po.get('scores') or {}
            delta = {k: sc.get(k) - psc[k] for k in
                     ('ai_opportunity', 'company_health',
                      'tape_resilience', 'deployment_risk')
                     if sc.get(k) is not None
                     and psc.get(k) is not None}
            out.append({'symbol': r['symbol'], 'as_of': str(r['as_of']),
                        'scores': sc,
                        'flags': (p or {}).get('flags'),
                        'needs': (p or {}).get('needs'),
                        'checks': (p or {}).get('checks'),
                        'themes': (p or {}).get('themes'),
                        'business_model': (p or {}).get('business_model'),
                        'flow': (p or {}).get('flow'),
                        'delta': delta or None,
                        'tape_live': _tape_live(r['symbol']),
                        'swing_live': _swing_live(r['symbol']),
                        'recovery': rec_map.get(r['symbol'])})
        return out
    except Exception as e:
        logger.debug('resilience read_all: %s', e)
        return []


def read(sym: str) -> Optional[dict[str, Any]]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT payload FROM company_resilience_scores"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if not rows:
            return None
        p = rows[0].get('payload')
        return json.loads(p) if isinstance(p, str) else p
    except Exception:
        return None
