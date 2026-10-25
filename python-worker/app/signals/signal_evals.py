"""Signal contract evals — the regression net for the decision layer.

Every layer of the cockpit is deterministic + declarative: YAML specs
(pulse_action_rules / best_picks / leveraged_swings) drive `when:`
conditions through ONE interpreter (pulse_engine._cond). That design
is exactly what makes a contract suite feasible — and necessary: the
bugs that actually ship here are never math bugs, they're SILENT
CONTRACT DRIFT between layers:

  - an `except: pass` swallowing a dead import → a whole rank
    component drops out (the _SECTOR_TO_ETF bug, twice)
  - a row losing a field → downstream reads a default
    (atr_pct missing → flat stops for every call)
  - a checklist `any:` arm rescuing a state another engine excludes
    (knife + turning_up read 'ready')
  - an unknown-`when`-field returning vacuous-fail — or worse, a
    typo'd `_in` string becoming a literal singleton that never fires

Three layers, all offline (no DB — engines are pure over ctx):

  lint       every `when:` field exists in the engine's ctx
             vocabulary; every string `_in` value resolves in the
             spec's own `groups:`; every `rank_weights` component
             exists in _RANK_NORM; every `from app.* import` inside a
             try/except actually resolves.
  scenarios  signal_scenarios.yaml — ctx → expected verdict rows run
             through the REAL eval_use_case / _eval_section. Pins gate
             semantics so a 'fix' can't silently reopen a hole.
  invariants pure-function contracts: resilience bounds, rank
             normalization, fail-closed constants, missing-data
             semantics.

`run()` returns {ok, checks, failed} and logs one warning per
failure — the custodian's code-bug rule picks those up off the
journal. CLI: `python -m app.signals.signal_evals`.
"""
import ast
import logging
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_SIG = Path(__file__).resolve().parent
_APP = _SIG.parent
_SCENARIOS = _SIG / "signal_scenarios.yaml"

# keys added to the eval ctx after the ctx-builder's dict literal —
# declared, not derived, because they're computed joins (gates fire
# count, sleeve tag) not row columns.
_BP_CTX_EXTRAS = {"sleeve", "gates_fire", "gates_total"}

# same for the leveraged-swings ctx — evaluate() merges these onto
# the _taped() dict before legs evaluate.
_LEV_CTX_EXTRAS = {
    "soxx_above_8ema", "soxx_below_8ema", "soxx_close",
    "leaders_ratio", "bear_alerts", "catalyst_veto_at",
    "max_hold_bars", "targets_frac", "support_pct_disp",
    "support_window",
}

# _cond operators that aren't ctx fields.
_COND_OPS = {"any", "all", "flag", "not_flag", "any_missing",
             "tape_dir", "default"}

# ctx keys that exist but are legitimately absent from _normalize({})
# (computed in later stages / annotation outputs).
_PULSE_CTX_EXTRAS = {"extended_metrics", "blocking", "confidence",
                     "risk_flags", "hard_risk_active",
                     "risk_unverifiable", "ann", "notes",
                     "risk_pending"}

# Known-dead import paths — endpoints whose backing service was
# removed; the import failing is the CORRECT behavior (endpoint is
# dead, not silently degraded). Documented here so the lint keeps its
# teeth for NEW drift instead of crying wolf forever.
_IMPORT_ALLOWLIST = {
    "api/fundamentals_api.py": {"app.services.data_service"},
    "api/admin.py": {"app.utils.market_data_utils"},
    "services/data_refresh_scheduler.py":
        {"app.services.data_refresh_service"},
}


# ------------------------------------------------------------------
# when:-tree walking — every spec file, every dict key named `when`
# ------------------------------------------------------------------

def _walk_whens(node: Any, path: str = "") -> list[tuple[str, dict]]:
    """Yield (yaml-path, when-dict) for every `when:` in the doc —
    engine-agnostic so future sections are covered automatically."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if k == "when" and isinstance(v, dict):
                out.append((p, v))
            else:
                out.extend(_walk_whens(v, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_walk_whens(v, f"{path}[{i}]"))
    return out


def _field_refs(when: dict) -> tuple[set, set, set]:
    """(field names, string group refs, any_missing fields) a when
    block binds against — mirrors _cond's key dispatch exactly."""
    fields, group_refs, missing_fields = set(), set(), set()
    for k, v in (when or {}).items():
        if k in _COND_OPS:
            if k in ("any", "all"):
                for sub in v or []:
                    f, g, m = _field_refs(sub)
                    fields |= f
                    group_refs |= g
                    missing_fields |= m
            elif k == "any_missing":
                missing_fields |= set(v or [])
            continue
        base = k
        for suf in ("_not_in", "_in", "_gte", "_lte", "_gt", "_lt",
                    "_is_not", "_is"):
            if k.endswith(suf):
                base = k[:-len(suf)]
                if suf in ("_in", "_not_in") and isinstance(v, str):
                    group_refs.add(v)
                break
        fields.add(base)
    return fields, group_refs, missing_fields


# ------------------------------------------------------------------
# ctx vocabularies — derived from the real ctx builders where the
# language allows, declared where it doesn't
# ------------------------------------------------------------------

def _pulse_vocab() -> set:
    from app.signals import pulse_engine
    c = pulse_engine._normalize({})
    c.setdefault("flags", [])
    c.setdefault("flags_known", False)
    vocab = set(c)
    try:
        vocab |= set(pulse_engine._stage0(dict(c)))
    except Exception:
        pass
    try:
        vocab |= set(pulse_engine._stage1(dict(c)))
    except Exception:
        pass
    return vocab | _PULSE_CTX_EXTRAS


def _func_node(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _largest_dict_keys(fn: ast.AST) -> set:
    """Keys of the largest all-string-literal dict in a function —
    the row/ctx dict is always the widest literal."""
    best: set = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys
                if isinstance(k, ast.Constant)
                and isinstance(k.value, str)}
        if len(keys) == len(node.keys) and len(keys) > len(best):
            best = keys
    return best


def _bp_vocab() -> set:
    import inspect
    from app.signals import best_picks
    fn = _func_node(ast.parse(inspect.getsource(best_picks)),
                    "_bulk_ctx")
    return (_largest_dict_keys(fn) | _BP_CTX_EXTRAS) if fn else set()


def _synth_bars(n: int = 320):
    """Deterministic flat-ish tape — enough bars for _taped's windows."""
    out = []
    d = date.today() - timedelta(days=int(n * 1.45))
    px = 100.0
    for i in range(n):
        px *= 1 + (0.002 if i % 3 else -0.001)
        out.append(SimpleNamespace(
            date=(d + timedelta(days=i)).isoformat(),
            timestamp=(d + timedelta(days=i)).isoformat(),
            close=px, high=px * 1.01, low=px * 0.99,
            open=px * 0.998, adj_close=px, volume=1_000_000))
    return out


def _lev_vocab() -> set:
    from app.signals import leveraged_swings as ls
    spec = ls._load()
    ctx = ls._taped(_synth_bars(int(spec["min_bars"]) + 60), spec)
    return (set(ctx) | _LEV_CTX_EXTRAS) if ctx else set(_LEV_CTX_EXTRAS)


# ------------------------------------------------------------------
# lint layer
# ------------------------------------------------------------------

def _plan_ctx_vocab() -> set:
    """trade_plans._ctx — the plan_status section binds the plan
    adapter's ctx, not the pulse row ctx."""
    import inspect
    from app.signals import trade_plans
    fn = _func_node(ast.parse(inspect.getsource(trade_plans)), "_ctx")
    return _largest_dict_keys(fn) if fn else set()


def _posture_ctx_vocab() -> set:
    """posture._ctx — the posture_rules section binds the regime-
    payload ctx (breadth/hedge features), not the pulse row ctx."""
    import inspect
    from app.signals import posture
    fn = _func_node(ast.parse(inspect.getsource(posture)), "_ctx")
    return _largest_dict_keys(fn) if fn else set()


def _lint_when_fields() -> list[dict]:
    """Every `when:` field must exist in its engine's ctx vocabulary —
    an unknown field is a silent never-fire (or vacuous-fail).
    plan_status binds the trade-plan adapter ctx and posture_rules
    the regime-payload ctx — per-section vocabularies."""
    pulse_vocab = _pulse_vocab()
    specs = [
        ("pulse", _SIG / "pulse_action_rules.yaml", pulse_vocab),
        ("plan_status", _SIG / "pulse_action_rules.yaml",
         _plan_ctx_vocab()),
        ("posture", _SIG / "pulse_action_rules.yaml",
         _posture_ctx_vocab()),
        ("best_picks", _SIG / "best_picks.yaml", _bp_vocab()),
        ("lev_swings", _SIG / "leveraged_swings.yaml", _lev_vocab()),
    ]
    checks = []
    for name, path, vocab in specs:
        spec = yaml.safe_load(path.read_text())
        groups = set((spec.get("groups") or {}).keys())
        bad_fields, bad_groups = {}, {}
        for p, when in _walk_whens(spec):
            # section-vocab split inside the shared pulse file
            in_plan = p.startswith("plan_status")
            in_post = p.startswith("posture_rules")
            if name == "pulse" and (in_plan or in_post):
                continue
            if name == "plan_status" and not in_plan:
                continue
            if name == "posture" and not in_post:
                continue
            fields, grefs, mfields = _field_refs(when)
            for f in fields | mfields:
                if f not in vocab:
                    bad_fields.setdefault(f, []).append(p)
            for g in grefs:
                # a string `_in` value that's not a declared group
                # degrades to literal-membership — the typo that
                # silently never fires. Bare strings are only clean
                # when the spec has no groups: (lev uses literals).
                if groups and g not in groups:
                    bad_groups.setdefault(g, []).append(p)
        checks.append({"id": f"lint.{name}.fields",
                       "ok": not bad_fields,
                       "detail": bad_fields or
                                 f"{len(vocab)} ctx keys checked"})
        checks.append({"id": f"lint.{name}.groups",
                       "ok": not bad_groups,
                       "detail": bad_groups or "ok"})
    return checks


def _lint_rank_components() -> list[dict]:
    """Every `k:` under rank_weights must have a _RANK_NORM row — a
    typo'd component silently drops its weight (rescale absorbs it)."""
    from app.signals import pulse_engine
    spec = pulse_engine._load()
    out = []
    for uc, blk in (spec.get("rank_weights") or {}).items():
        if uc not in (spec.get("use_cases") or {}):
            out.append({"id": f"lint.rank.{uc}.exists", "ok": False,
                        "detail": "rank_weights for unknown use_case"})
            continue
        missing = [w.get("k") for w in (blk or {}).get("weights", [])
                   if isinstance(w, dict)
                   and w.get("k") not in pulse_engine._RANK_NORM]
        out.append({"id": f"lint.rank.{uc}.components",
                    "ok": not missing,
                    "detail": missing or "ok"})
    return out


def _module_file(module: str) -> Optional[Path]:
    """app.x.y → app/x/y.py or app/x/y/__init__.py — static resolve."""
    rel = Path(*module.split(".")[1:])
    for cand in (rel.with_suffix(".py"), rel / "__init__.py"):
        p = _APP / cand
        if p.is_file():
            return p
    return None


def _top_level_names(tree: ast.AST) -> set:
    """Names a module binds at top level — defs, classes, assigns,
    and re-exported `from x import y` names."""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and \
                isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {a.asname or a.name.split(".")[0]
                      for a in node.names}
        elif isinstance(node, ast.Try):
            names |= _top_level_names(
                ast.Module(body=node.body, type_ignores=[]))
    return names


def _lint_internal_imports() -> list[dict]:
    """`from app.X import name` inside try/except must resolve — the
    except:pass idiom makes a dead import a silent feature-drop (the
    _SECTOR_TO_ETF bug class). Resolved STATICALLY: a module file that
    can't be found, or a name the module no longer binds at top level,
    means the guarded code path is dead code pretending to run.
    External optionals (yfinance et al.) aren't app.* — untouched."""
    bad = {}
    for py in _APP.rglob("*.py"):
        if py == Path(__file__).resolve():
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        targets = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for sub in ast.walk(ast.Module(
                    body=node.body + node.finalbody,
                    type_ignores=[])):
                if isinstance(sub, ast.ImportFrom) and \
                        (sub.module or "").startswith("app."):
                    targets.append(sub)
        for t in targets:
            rel = str(py.relative_to(_APP))
            if t.module in _IMPORT_ALLOWLIST.get(rel, set()):
                continue
            f = _module_file(t.module)
            if f is None:
                bad.setdefault(rel, []).append(
                    f"module {t.module} not found")
                continue
            try:
                names = _top_level_names(ast.parse(f.read_text()))
            except SyntaxError:
                continue
            for a in t.names:
                # `from app.pkg import sub` may be a submodule file
                if a.name not in names and _module_file(
                        f"{t.module}.{a.name}") is None:
                    bad.setdefault(
                        str(py.relative_to(_APP)), []).append(
                        f"{t.module}.{a.name} no longer bound")
    return [{"id": "lint.internal_imports", "ok": not bad,
             "detail": bad or "ok"}]


def _lint_row_schemas() -> list[dict]:
    """Fields a downstream engine reads off a shared row must be
    produced upstream — atr_pct off the board row, rs_* off the
    overlay. AST-extract the emitted dict literals (file-level —
    importing app.api pulls optional deps the eval box may lack)."""
    out = []
    board_src = (_APP / "signals" / "daily_board.py").read_text()
    fn = _func_node(ast.parse(board_src), "_accumulate_scores")
    if fn is None:
        return [{"id": "lint.board_row.fields", "ok": False,
                 "detail": "_accumulate_scores not found in "
                           "daily_board.py — renamed?"}]
    row_keys = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and \
                isinstance(node.func, ast.Attribute) and \
                node.func.attr == "append" and node.args and \
                isinstance(node.args[0], ast.Dict):
            row_keys |= {k.value for k in node.args[0].keys
                         if isinstance(k, ast.Constant)
                         and isinstance(k.value, str)}
    required = {"symbol", "score", "atr_pct", "dip_phase",
                "swing", "momentum", "why", "fund_state",
                "entry_status", "levels"}
    missing = sorted(required - row_keys)
    out.append({"id": "lint.board_row.fields", "ok": not missing,
                "detail": (f"missing {missing}" if missing
                           else f"{len(row_keys)} keys emitted")})
    return out


# ------------------------------------------------------------------
# scenario layer — declarative ctx → expected verdict, through the
# real engines
# ------------------------------------------------------------------

def _scenarios() -> list[dict]:
    from app.signals import pulse_engine
    doc = yaml.safe_load(_SCENARIOS.read_text())
    out = []
    for sc in doc or []:
        try:
            row = dict(sc.get("row") or {})
            if "momentum_detail" in sc:
                row["momentum_detail"] = sc["momentum_detail"]
            res = pulse_engine.eval_use_case(row, sc["use_case"])
            exp = sc.get("expect") or {}
            fails = []
            if "state_in" in exp and \
                    res["state"] not in exp["state_in"]:
                fails.append(f"state {res['state']} "
                             f"not in {exp['state_in']}")
            if "state_not_in" in exp and \
                    res["state"] in exp["state_not_in"]:
                fails.append(f"state {res['state']} "
                             f"in {exp['state_not_in']}")
            checks = res.get("rules") or []
            for frag in exp.get("must_pass", []):
                if not any(frag in (c.get("line") or "")
                           and c.get("ok") for c in checks):
                    fails.append(f"no passing check ~ '{frag}'")
            for frag in exp.get("must_fail", []):
                if not any(frag in (c.get("line") or "")
                           and not c.get("ok") for c in checks):
                    fails.append(f"no failing check ~ '{frag}'")
            out.append({"id": f"scenario.{sc['id']}",
                        "ok": not fails,
                        "detail": fails or
                                  f"{res['state']} "
                                  f"{res.get('score')}/{res.get('of')}"})
        except Exception as exc:
            out.append({"id": f"scenario.{sc.get('id')}",
                        "ok": False,
                        "detail": f"engine error: {exc}"})
    return out


# ------------------------------------------------------------------
# invariants — pure-function contracts
# ------------------------------------------------------------------

def _mk_books(closes: dict[str, list[float]]):
    """symbol → bars book, same-date series for _resilience windows."""
    books = {}
    for sym, cs in closes.items():
        d = date.today() - timedelta(days=int(len(cs) * 1.45))
        books[sym] = [SimpleNamespace(
            date=(d + timedelta(days=i)).isoformat(),
            timestamp=(d + timedelta(days=i)).isoformat(),
            close=c, high=c, low=c, open=c, adj_close=c,
            volume=1) for i, c in enumerate(cs)]
    return books


def _invariants() -> list[dict]:
    out = []

    def ck(cid, fn):
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"error: {exc}"
        out.append({"id": f"invariant.{cid}", "ok": ok,
                    "detail": detail})

    def resilience_bounds():
        from app.signals.relative_strength import (
            _daily_rets, _resilience)
        # flat market → no qualifying days → all null, never zeros
        flat = [100.0] * 70
        books = _mk_books({"A": flat, "SPY": flat})
        res = _resilience(_daily_rets(books["A"]),
                          _daily_rets(books["SPY"]))
        ok = res["down_cap"] is None and res["up_cap"] is None
        return ok, f"flat tape → down_cap {res['down_cap']}"

    def resilience_min_days():
        from app.signals.relative_strength import (
            _MIN_RED, _daily_rets, _resilience)
        # fewer than _MIN_RED red days → null, not a small-sample %
        spy = [100.0]
        for i in range(1, 70):
            spy.append(spy[-1] * (0.95 if i in (10, 30, 50)
                                  else 1.001))   # 3 red days
        assert sum(1 for i in range(1, 70)
                   if spy[i] / spy[i - 1] - 1 <= -0.004) < _MIN_RED
        books = _mk_books({"A": spy, "SPY": spy})
        res = _resilience(_daily_rets(books["A"]),
                          _daily_rets(books["SPY"]))
        ok = res["down_cap"] is None
        return ok, f"{res['down_n']} red days → null"

    def defense_alone_not_resilient():
        from app.signals.relative_strength import _quality_bucket
        # 100% defense, negative rebound → never 'resilient'
        q = _quality_bucket(80, {"down_cap": 1.0, "up_cap": 0.3,
                                 "rebound_x": -0.005})
        return q != "resilient", f"defense-only → {q}"

    def fragile_not_resilient_at_low_rs():
        from app.signals.relative_strength import _quality_bucket
        # great behavior at terrible RS pct → not resilient
        q = _quality_bucket(20, {"down_cap": 0.8, "up_cap": 0.7,
                                 "rebound_x": 0.015})
        return q != "resilient", f"rs_pct 20 → {q}"

    def missing_is_not_clean():
        # _cond contract: a missing field fails the check, never
        # passes silently (the missing≠clean rule)
        from app.signals.pulse_engine import _cond
        miss = []
        ok = _cond({"rsi": None}, {"rsi_gte": 0}, miss)
        return (not ok) and miss == ["rsi"], f"miss={miss}"

    def unknown_key_never_passes():
        from app.signals.pulse_engine import _cond
        miss = []
        ok = _cond({"rsi": 50}, {"rsi_typo_gte": 10}, miss)
        return not ok and any(m.startswith("unknown:")
                              or "rsi_typo" in m for m in miss), \
            f"miss={miss}"

    def posture_fails_closed():
        from app.signals import posture
        p = posture.NO_SNAPSHOT
        return (p["new_longs"] is False and p["shorts"] is False
                and p["hedge_on"] is False), f"{p['posture']}"

    def rank_norm_bounds():
        # normalizers take the full normalized ctx — build the real
        # one so a component reading a key _normalize doesn't emit
        # surfaces as a failure here (the missing-key bug class)
        from app.signals.pulse_engine import _RANK_NORM, _normalize
        base = _normalize({})
        bad = []
        for k, fn in _RANK_NORM.items():
            for v in (None, 0.0, -50.0, 200.0):
                try:
                    s = fn(dict(base, **{k: v}))
                except KeyError as e:
                    bad.append(f"{k} reads non-ctx key {e}")
                    continue
                except Exception:
                    continue   # type-mismatch values: tolerated
                if s is not None and not (0 <= s <= 100):
                    bad.append(f"{k}({v})={s}")
        return not bad, bad or f"{len(_RANK_NORM)} components bounded"

    ck("resilience_bounds", resilience_bounds)
    ck("resilience_min_days", resilience_min_days)
    ck("defense_alone_not_resilient", defense_alone_not_resilient)
    ck("low_rs_pct_not_resilient", fragile_not_resilient_at_low_rs)
    ck("missing_field_fails", missing_is_not_clean)
    ck("unknown_key_fails", unknown_key_never_passes)
    ck("posture_fails_closed", posture_fails_closed)
    ck("rank_norm_bounds", rank_norm_bounds)
    return out


# ------------------------------------------------------------------
# runner
# ------------------------------------------------------------------

def run() -> dict:
    checks = (_lint_when_fields() + _lint_rank_components()
              + _lint_internal_imports() + _lint_row_schemas()
              + _scenarios() + _invariants())
    failed = [c for c in checks if not c["ok"]]
    for c in failed:
        logger.warning("signal_eval FAIL %s — %s",
                       c["id"], c["detail"])
    return {"ok": not failed,
            "passed": len(checks) - len(failed),
            "total": len(checks),
            "failed": [{"id": c["id"], "detail": c["detail"]}
                       for c in failed],
            "checks": checks}


def main():
    import json as _json
    import sys
    res = run()
    print(_json.dumps(
        {k: v for k, v in res.items() if k != "checks"},
        indent=2, default=str))
    if not res["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
