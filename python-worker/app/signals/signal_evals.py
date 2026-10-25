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


def _lint_job_targets() -> list[dict]:
    """Every _j_* job's asyncio.to_thread(target) must resolve — a
    renamed/missing callable surfaces as 'module has no attribute'
    at job time, silently dead on the scheduler (theme_rotation.run).
    Static resolution: function-local `from app.x import y` binds the
    name; to_thread(mod.fn) checks submodule file, to_thread(fn)
    checks the module binds it. Lambdas and non-app targets skip."""
    src = (_APP / "api" / "board_api.py").read_text()
    tree = ast.parse(src)
    bad = []

    def imports_of(fn) -> dict:
        """local name -> (module, imported_attr|None)."""
        out = {}
        scopes = [tree] + ([fn] if fn is not None else [])
        for scope in scopes:
            for node in ast.walk(scope):
                if isinstance(node, ast.ImportFrom) and \
                        (node.module or "").startswith("app."):
                    for a in node.names:
                        out.setdefault(a.asname or a.name,
                                       (node.module, a.name))
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.startswith("app."):
                            out.setdefault(
                                a.asname or a.name.split(".")[-1],
                                (a.name, None))
        return out

    def defines(module: str, attr: str) -> bool:
        f = _module_file(f"{module}.{attr}")          # submodule?
        if f is not None:
            return True
        f = _module_file(module)
        if f is None:
            return True                              # unresolvable —
        try:                                          # let imports lint
            return attr in _top_level_names(
                ast.parse(f.read_text()))
        except SyntaxError:
            return True

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                or not fn.name.startswith("_j_"):
            continue
        mods = imports_of(fn)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "to_thread" and node.args):
                continue
            tgt = node.args[0]
            if isinstance(tgt, ast.Attribute) and \
                    isinstance(tgt.value, ast.Name):
                entry = mods.get(tgt.value.id)
                if entry is None:
                    continue
                mod, attr = entry
                if attr is None:
                    base = mod                     # import app.x as n
                else:
                    cand = f"{mod}.{attr}"         # from x import y
                    if _module_file(cand) is not None:
                        base = cand                # y is a submodule
                    else:
                        # y is a bound object/function — the binding
                        # itself is lintable, its attributes aren't
                        if not defines(mod, attr):
                            bad.append(
                                f"{fn.name}: {mod}.{attr} unresolved")
                        continue
                try:
                    if tgt.attr not in _top_level_names(
                            ast.parse(_module_file(base).read_text())):
                        bad.append(f"{fn.name}: {base}.{tgt.attr} "
                                   "missing")
                except (SyntaxError, AttributeError):
                    pass
            elif isinstance(tgt, ast.Name):
                entry = mods.get(tgt.id)
                if entry and entry[1] is not None \
                        and not defines(entry[0], entry[1]):
                    bad.append(f"{fn.name}: {entry[0]}."
                               f"{entry[1]} missing")
    return [{"id": "lint.job_targets", "ok": not bad,
             "detail": bad or "all to_thread targets resolve"}]


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

def _run_scenario_engine(sc: dict) -> dict:
    """One scenario → normalized {state, fields, checks}. Every engine
    is pure over a ctx — scenario rows ARE the ctx, no DB anywhere."""
    eng = sc.get("engine", "pulse")
    if eng == "pulse":
        from app.signals import pulse_engine
        row = dict(sc.get("row") or {})
        if "momentum_detail" in sc:
            row["momentum_detail"] = sc["momentum_detail"]
        res = pulse_engine.eval_use_case(row, sc["use_case"])
        return {"state": res["state"], "fields": res,
                "checks": res.get("rules") or []}
    if eng == "posture":
        from app.signals import posture as posture_mod
        res = posture_mod.evaluate(sc.get("stance"),
                                   sc.get("payload") or {})
        return {"state": res.get("posture"), "fields": res,
                "checks": []}
    if eng == "lev":
        from app.signals import leveraged_swings as ls
        spec = ls._load()
        res = ls._evaluate_etf(sc["etf"], spec["etfs"][sc["etf"]],
                               sc.get("ctx") or {})
        return {"state": res.get("state"), "fields": res,
                "checks": res.get("checklist") or []}
    if eng == "plan_status":
        from app.signals import trade_plans
        res = trade_plans._match(sc.get("ctx") or {})
        return {"state": res.get("status"), "fields": res,
                "checks": []}
    if eng == "best_picks":
        from app.signals import best_picks as bp
        spec = bp._load()
        res = bp._eval_section(spec[sc["sleeve"]],
                               sc.get("ctx") or {})
        state = ("gated" if res.get("gated")
                 else res.get("tier") or res.get("label"))
        return {"state": state, "fields": res,
                "checks": [{"ok": False, "line": res.get("reason")}
                           ] if res.get("gated") else []}
    if eng == "fed_path":
        from app.signals import fed_path
        res = fed_path.compute(sc.get("ctx") or {})
        lean = (res.get("path_3_6m") or {}).get("lean")
        nf = res.get("next_fomc") or {}
        return {"state": (res.get("path_1m") or {}).get("lean"),
                "fields": {**nf, "lean_3_6m": lean,
                           "expected_bps_3_6m":
                               (res.get("path_3_6m") or {})
                                   .get("expected_bps"),
                           "confidence": (res.get("data_quality") or {})
                               .get("confidence"),
                           "p_sum": sum(nf.get(k) or 0
                                        for k in ("p_hike", "p_hold",
                                                  "p_cut"))},
                "checks": []}
    raise ValueError(f"unknown engine '{eng}'")


def _scenarios() -> list[dict]:
    doc = yaml.safe_load(_SCENARIOS.read_text())
    out = []
    for sc in doc or []:
        try:
            res = _run_scenario_engine(sc)
            exp = sc.get("expect") or {}
            fails = []
            state = res["state"]
            if "state_in" in exp and state not in exp["state_in"]:
                fails.append(f"state {state} "
                             f"not in {exp['state_in']}")
            if "state_not_in" in exp and \
                    state in exp["state_not_in"]:
                fails.append(f"state {state} "
                             f"in {exp['state_not_in']}")
            for k, v in (exp.get("field_eq") or {}).items():
                if res["fields"].get(k) != v:
                    fails.append(f"{k}={res['fields'].get(k)!r} "
                                 f"≠ {v!r}")
            checks = res.get("checks") or []
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
                        "detail": fails or f"{state}"})
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

    def feat_adj_bounded():
        # learned feature adjustments are corrective-first: a rogue
        # weight can subtract at most 6, add at most 2 — and an
        # unfired feature always contributes zero (w injected → no DB)
        from app.signals.daily_board import _feat_adj
        cases = [
            (_feat_adj("screen_ready", True,
                       lambda k: {"adj": 50.0}), 2.0),
            (_feat_adj("screen_ready", True,
                       lambda k: {"adj": -50.0}), -6.0),
            (_feat_adj("screen_ready", True,
                       lambda k: -50.0), -6.0),
            (_feat_adj("screen_ready", True,
                       lambda k: None), 0.0),
            (_feat_adj("screen_ready", True,
                       lambda k: {"adj": "junk"}), 0.0),
            (_feat_adj("prior_good", False,
                       lambda k: {"adj": -50.0}), 0.0),
        ]
        bad = [f"{got}≠{want}" for got, want in cases if got != want]
        return not bad, bad or "bounded [-6,+2], unfired → 0"

    ck("resilience_bounds", resilience_bounds)
    ck("resilience_min_days", resilience_min_days)
    ck("defense_alone_not_resilient", defense_alone_not_resilient)
    ck("low_rs_pct_not_resilient", fragile_not_resilient_at_low_rs)
    ck("missing_field_fails", missing_is_not_clean)
    ck("unknown_key_fails", unknown_key_never_passes)
    ck("posture_fails_closed", posture_fails_closed)
    ck("rank_norm_bounds", rank_norm_bounds)
    ck("feat_adj_bounded", feat_adj_bounded)
    return out


# ------------------------------------------------------------------
# LLM judge — bounded interpretation on top of the deterministic net
#
# The cockpit's own rule applies here too: the LLM INTERPRETS, the
# deterministic layer DECIDES. Concretely:
#   * judge() produces ADVISORY findings — line-fidelity review and
#     scenario-coverage gaps the lint can't express. Never a gate.
#   * run_fix() is a closed propose-verify loop: for each failing
#     check the judge gets a context pack and proposes a minimal
#     patch; a patch is applied only if the FULL suite re-runs at
#     least as green — and reverted otherwise. The judge can never
#     patch signal_evals.py itself (it cannot weaken its own net),
#     and patches to spec/scenario files are flagged needs_review
#     because those files are policy, not mechanics.
# ------------------------------------------------------------------

_LLM_MODEL_ENV = "SIGNAL_EVAL_LLM"
_PROTECTED = {Path(__file__).resolve().name}   # the verifier itself
_POLICY_FILES = {"signal_scenarios.yaml", "pulse_action_rules.yaml",
                 "best_picks.yaml", "leveraged_swings.yaml"}


def _llm():
    """Judge transport — litellm + a configured key, else None.
    The suite skips judge work cleanly with no key; a missing judge
    is never a failure (deterministic checks always run)."""
    try:
        from litellm import completion  # noqa: F401
    except ImportError:
        return None
    import os
    if not (os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("LITELLM_PROXY_URL")):
        return None
    model = os.getenv(_LLM_MODEL_ENV, "gpt-4o-mini")

    def call(system: str, user: str) -> str:
        r = completion(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0)
        return r.choices[0].message.content
    return call


def _json_out(text: str):
    """LLM → parsed JSON object/array, tolerant of code fences."""
    import json as _json
    import re as _re
    m = _re.search(r"```(?:json)?\s*(.*?)```", text, _re.S)
    raw = m.group(1) if m else text
    return _json.loads(raw.strip())


def _judge_line_fidelity(call) -> list[dict]:
    """Does each checklist `line` honestly describe its `when:`?
    The deterministic lint checks fields EXIST; it can't check the
    prose matches the math — a line claiming 'defends the tape' over
    a {rsi_gt: 50} condition misleads the human making the call.
    Advisory: findings land in detail, the check fails only when the
    judge marks a line materially WRONG (not merely unclear)."""
    items = []
    for path in (_SIG / "pulse_action_rules.yaml",
                 _SIG / "leveraged_swings.yaml"):
        spec = yaml.safe_load(path.read_text())
        for p, when in _walk_whens(spec):
            parent = p.rsplit(".", 1)[0]
            # find the sibling `line` — walk the spec to the parent
            node = spec
            for part in parent.replace("[", ".").replace("]", "") \
                              .split("."):
                if not part:
                    continue
                node = node[int(part)] if isinstance(node, list) \
                    else node.get(part) or {}
            line = node.get("line") or node.get("why")
            if line:
                items.append({"path": f"{path.name}:{p}",
                              "when": when, "line": line})
    if not items:
        return [{"id": "judge.line_fidelity", "ok": True,
                 "detail": "no line-bearing conditions"}]
    user = (
        "Each entry is a trading-system checklist condition (`when`) "
        "and the prose `line` shown to a human deciding whether to "
        "act. For each, say whether the line FAITHFULLY describes "
        "the condition. Reply JSON: [{\"path\": ..., \"verdict\": "
        "\"ok\"|\"unclear\"|\"wrong\", \"issue\": \"why (if not ok)\"}]\n\n"
        + yaml.dump(items[:60], default_flow_style=False))
    verdicts = _json_out(call(
        "You audit whether UI text honestly describes trading "
        "conditions. Be strict about material misdescription, "
        "lenient about brevity. Reply JSON only.", user))
    wrong = {v["path"]: v.get("issue") for v in verdicts
             if isinstance(v, dict) and v.get("verdict") == "wrong"}
    unclear = {v["path"]: v.get("issue") for v in verdicts
               if isinstance(v, dict) and v.get("verdict") == "unclear"}
    return [{"id": "judge.line_fidelity", "ok": not wrong,
             "advisory": True,
             "detail": {"wrong": wrong, "unclear": unclear}
             if (wrong or unclear) else f"{len(items)} lines audited"}]


def _judge_coverage(call) -> list[dict]:
    """Scenario-coverage gaps — the judge sees the gate vocabulary
    plus existing pins and proposes what's missing. Always advisory:
    proposals land in detail for a human to turn into scenarios."""
    doc = yaml.safe_load(_SCENARIOS.read_text())
    have = [s["id"] for s in doc or []]
    spec = yaml.safe_load((_SIG / "pulse_action_rules.yaml")
                          .read_text())
    ucs = list((spec.get("use_cases") or {}).keys())
    user = (
        "A trading system's gate semantics are pinned by behavioral "
        "scenarios. Existing scenario ids: "
        f"{have}. Use-cases with checklists: {ucs}. Engines covered: "
        "pulse readiness, posture, leveraged ETF legs, plan status, "
        "best-picks gates. What HIGH-VALUE scenario is still unpinned "
        "— a gate hole, a missing-data edge, an ordering regression? "
        "Reply JSON: [{\"id\": ..., \"engine\": ..., \"why\": ..., "
        "\"risk_if_unpinned\": ...}] — max 5, highest value first.")
    props = _json_out(call(
        "You find coverage gaps in a trading system's behavioral "
        "test suite. Propose scenarios a regression would slip "
        "through. Reply JSON only.", user))
    return [{"id": "judge.scenario_coverage", "ok": True,
             "advisory": True,
             "detail": props or "no gaps proposed"}]


def judge() -> list[dict]:
    """Advisory findings — never counted in the pass/fail gate."""
    call = _llm()
    if call is None:
        return [{"id": "judge.available", "ok": True,
                 "advisory": True,
                 "detail": "no LLM key — judge checks skipped; "
                           "set SIGNAL_EVAL_LLM + a provider key"}]
    findings = []
    for fn in (_judge_line_fidelity, _judge_coverage):
        try:
            findings.extend(fn(call))
        except Exception as exc:
            findings.append({"id": f"judge.{fn.__name__}",
                             "ok": True, "advisory": True,
                             "detail": f"judge error: {exc}"})
    return findings


# ------------------------------------------------------------------
# run_fix — the closed propose→verify→revert loop
# ------------------------------------------------------------------

def _context_pack(check: dict) -> dict:
    """What the judge sees for a failing check — the check plus the
    smallest artifact set that could hold the bug."""
    pack = {"failing_check": check}
    if check["id"].startswith("scenario."):
        sid = check["id"].split(".", 1)[1]
        doc = yaml.safe_load(_SCENARIOS.read_text())
        pack["scenario"] = next((s for s in doc or []
                                 if s.get("id") == sid), None)
        pack["note"] = ("Decide whether the ENGINE is wrong (fix "
                        "the engine/spec) or the SCENARIO is wrong "
                        "(fix the scenario). Scenario edits are "
                        "policy — flagged for human review.")
    if check["id"].startswith("lint."):
        pack["note"] = ("Field/group/import/row-schema drift — the "
                        "fix is almost always in the referenced "
                        "source file, not the lint.")
    return pack


def _propose_fix(call, check: dict) -> Optional[dict]:
    pack = _context_pack(check)
    user = (
        "A contract check in a trading system's eval suite failed.\n\n"
        + yaml.dump(pack, default_flow_style=False)
        + "\nPropose a MINIMAL patch as JSON: {\"file\": "
          "\"app/... relative to python-worker\", \"old\": \"exact "
          "text to replace (must appear verbatim)\", \"new\": "
          "\"replacement\", \"rationale\": \"...\", \"confidence\": "
          "0-1}. If no safe minimal patch exists, reply "
          "{\"patch\": null, \"why\": \"...\"}.")
    try:
        p = _json_out(call(
            "You repair failing contract checks in a trading "
            "system. Propose minimal, exact-match patches. Never "
            "weaken a check to make it pass. Reply JSON only.",
            user))
        return p if isinstance(p, dict) and p.get("file") else None
    except Exception:
        return None


def _apply_patch(patch: dict) -> tuple[bool, Optional[str]]:
    """Exact-match apply within app/ — the same contract as the edit
    tool: old text must appear exactly once. Refuses protected and
    out-of-tree paths."""
    name = (patch.get("file") or "").strip()
    if not name or name in _PROTECTED or ".." in name:
        return False, "refused path"
    target = (_APP / name).resolve()
    if not str(target).startswith(str(_APP.resolve())) or \
            not target.is_file():
        return False, f"no such file under app/: {name}"
    src = target.read_text()
    old, new = patch.get("old"), patch.get("new")
    if old is None or new is None or src.count(old) != 1:
        return False, "old not unique/absent"
    target.write_text(src.replace(old, new, 1))
    return True, None


def run_fix(max_attempts: int = 6, dry: bool = False) -> dict:
    """Propose → apply → re-run → keep-if-green. The loop 'until all
    issues are fixed' the user asked for — bounded by attempts and
    by the rule that a patch can never make the suite less green."""
    history, applied = [], []
    res = run()
    call = _llm()
    for _ in range(max_attempts):
        failed = [c for c in res["checks"] if not c["ok"]]
        if not failed:
            break
        if call is None:
            history.append({"note": "no LLM key — propose step "
                                    "skipped; deterministic fixes "
                                    "still possible by hand"})
            break
        improved = False
        for f in failed:
            patch = _propose_fix(call, f)
            if not patch:
                history.append({"check": f["id"],
                                "patch": None})
                continue
            patch["needs_review"] = Path(
                patch.get("file") or "").name in _POLICY_FILES
            if dry:
                history.append({"check": f["id"],
                                "proposed": patch})
                continue
            ok, why = _apply_patch(patch)
            if not ok:
                history.append({"check": f["id"],
                                "patch": patch.get("file"),
                                "rejected": why})
                continue
            res2 = run()
            if len(res2["failed"]) <= len(res["failed"]) and \
                    any(c["id"] == f["id"] and c["ok"]
                        for c in res2["checks"]):
                applied.append({"check": f["id"],
                                "patch": patch.get("file"),
                                "needs_review":
                                    patch["needs_review"]})
                res = res2
                improved = True
            else:
                # revert — suite got worse or the target didn't pass
                _apply_patch({"file": patch["file"],
                              "old": patch["new"],
                              "new": patch["old"]})
                history.append({"check": f["id"],
                                "patch": patch.get("file"),
                                "reverted": "suite not greener"})
        if not improved and not dry:
            break
    return {"ok": res["ok"], "applied": applied,
            "history": history, "final": res["failed"]}


# ------------------------------------------------------------------
# runner
# ------------------------------------------------------------------

def run(with_judge: bool = False) -> dict:
    checks = (_lint_when_fields() + _lint_rank_components()
              + _lint_internal_imports() + _lint_row_schemas()
              + _lint_job_targets()
              + _scenarios() + _invariants())
    failed = [c for c in checks if not c["ok"]]
    for c in failed:
        logger.warning("signal_eval FAIL %s — %s",
                       c["id"], c["detail"])
    out = {"ok": not failed,
           "passed": len(checks) - len(failed),
           "total": len(checks),
           "failed": [{"id": c["id"], "detail": c["detail"]}
                      for c in failed],
           "checks": checks}
    if with_judge:
        findings = judge()
        out["judge"] = findings
        # advisory findings log as warnings but never gate the suite
        for f_ in findings:
            if not f_["ok"]:
                logger.warning("signal_eval JUDGE %s — %s",
                               f_["id"], f_["detail"])
    return out


def main():
    import argparse
    import json as _json
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", action="store_true",
                    help="run advisory LLM-judge checks too")
    ap.add_argument("--fix", action="store_true",
                    help="propose→verify loop on failing checks")
    ap.add_argument("--fix-dry", action="store_true",
                    help="print proposed patches without applying")
    args = ap.parse_args()
    if args.fix or args.fix_dry:
        res = run_fix(dry=args.fix_dry)
        print(_json.dumps(res, indent=2, default=str))
        if not res["ok"]:
            sys.exit(1)
        return
    res = run(with_judge=args.judge)
    print(_json.dumps(
        {k: v for k, v in res.items() if k != "checks"},
        indent=2, default=str))
    if not res["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
