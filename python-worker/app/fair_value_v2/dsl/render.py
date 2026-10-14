"""Render a DSL formula AST as readable math with resolved values inline.

Used to surface "why this number" on the Fair Value Test page: each
scenario leg renders the actual arithmetic that produced it, e.g.

    base: (eps_ttm=2.08 × clamp((16 + (0.4 × g=10)), 8, 45)) = 33.28

Rendering never raises — an unresolvable leaf renders as `name=?` and a
broken node renders as `<?>` — a bad render must not kill a valuation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.fair_value_v2.dsl.evaluator import EvalContext, eval_expr


def _fmt(v: Any) -> str:
    if v is None:
        return "?"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        f = float(v)
        if abs(f) >= 1e6:
            return f"{f:.4g}"
        return f"{f:.4g}" if not f.is_integer() else str(int(f))
    return str(v)


def _val(expr: Any, ctx: EvalContext) -> Any:
    try:
        return eval_expr(expr, ctx, path="$.render")
    except Exception:
        return None


def _leaf(name: str, expr: Any, ctx: EvalContext) -> str:
    v = _val(expr, ctx)
    return f"{name}={_fmt(v)}"


def render_expr(expr: Any, ctx: EvalContext, depth: int = 0) -> str:
    if depth > 12:
        return "…"
    if expr is None:
        return "null"
    if isinstance(expr, (int, float)):
        return _fmt(expr)
    if not isinstance(expr, dict):
        return "<?>"

    r = lambda e: render_expr(e, ctx, depth + 1)  # noqa: E731

    if "const" in expr:
        return _fmt(expr["const"])

    if "var" in expr:
        key = str(expr["var"])
        if key in ctx.locals:
            return f"{key}={_fmt(ctx.locals.get(key))}"
        if key in ctx.scalars:
            return f"{key}={_fmt(ctx.scalars.get(key))}"
        return f"{key}=?"

    if "param" in expr:
        key = str(expr["param"])
        return f"{key}={_fmt(ctx.params.get(key))}"

    if "coalesce" in expr:
        cands = expr["coalesce"]
        if not isinstance(cands, list):
            cands = [cands]
        parts = [r(c) for c in cands]
        return "coalesce(" + " | ".join(parts) + ")"

    if "dcf_mega_cap_price" in expr:
        node = expr["dcf_mega_cap_price"] or {}
        bits = ", ".join(f"{k}={_fmt(_val(v, ctx))}" for k, v in node.items())
        return f"dcf_mega_cap({bits})"

    if "let" in expr:
        node = expr["let"] or {}
        bindings = node.get("bindings") or {}
        scope = dict(ctx.locals or {})
        scoped = EvalContext(scalars=ctx.scalars, params=ctx.params,
                             locals=scope)
        names = []
        for k, v_expr in (bindings.items() if isinstance(bindings, dict) else []):
            v = _val(v_expr, scoped)
            scope[str(k)] = v
            names.append(f"{k}={_fmt(v)}")
        inner = render_expr(node.get("in"), scoped, depth + 1)
        return f"let {'; '.join(names)} in {inner}"

    if "require" in expr:
        return r((expr["require"] or {}).get("value"))

    if "error" in expr:
        payload = expr["error"]
        code = payload.get("code") if isinstance(payload, dict) else payload
        return f"reject({code})"

    for op, sym in (("add", "+"), ("sub", "−"), ("gt", ">"),
                    ("gte", "≥"), ("lt", "<"), ("lte", "≤"), ("eq", "=")):
        if op in expr:
            a, b = (expr[op] if isinstance(expr[op], list)
                    else [expr[op]])[:2]
            return f"({r(a)} {sym} {r(b)})"

    if "mul" in expr:
        parts = expr["mul"] if isinstance(expr["mul"], list) else [expr["mul"]]
        return "(" + " × ".join(r(p) for p in parts) + ")"

    if "div" in expr:
        a, b = (expr["div"] if isinstance(expr["div"], list)
                else [expr["div"]])[:2]
        return f"({r(a)} ÷ {r(b)})"

    for op in ("min", "max"):
        if op in expr:
            a, b = (expr[op] if isinstance(expr[op], list)
                    else [expr[op]])[:2]
            return f"{op}({r(a)}, {r(b)})"

    if "clamp" in expr:
        node = expr["clamp"] or {}
        return (f"clamp({r(node.get('value'))}, "
                f"{r(node.get('lo'))}, {r(node.get('hi'))})")

    if "log" in expr:
        return f"ln({r(expr['log'])})"

    if "pow" in expr:
        a, b = (expr["pow"] if isinstance(expr["pow"], list)
                else [expr["pow"]])[:2]
        return f"({r(a)}^{r(b)})"

    if "and" in expr:
        parts = expr["and"] if isinstance(expr["and"], list) else [expr["and"]]
        return "(" + " AND ".join(r(p) for p in parts) + ")"

    if "or" in expr:
        parts = expr["or"] if isinstance(expr["or"], list) else [expr["or"]]
        return "(" + " OR ".join(r(p) for p in parts) + ")"

    if "not" in expr:
        return f"NOT({r(expr['not'])})"

    if "if" in expr:
        node = expr["if"] or {}
        cond = node.get("cond")
        taken = "then" if bool(_val(cond, ctx)) else "else"
        return (f"if({r(cond)}) → {taken}: "
                f"{r(node.get(taken))}")

    return "<?>"


_LEGS = (("fair_price", "base"), ("bear_fair_price", "bear"),
         ("bull_fair_price", "bull"), ("explosive_fair_price", "explosive"))


def render_scenarios(formula: Dict[str, Any], *, scalars: Dict[str, Any],
                     params: Dict[str, Any]) -> Dict[str, str]:
    """Render each scenario leg's formula with this run's resolved
    values — never raises; a broken render yields a placeholder."""
    ctx = EvalContext(scalars=scalars or {}, params=params or {},
                      locals={})
    # Bind formula.bindings defensively: a binding that can't evaluate
    # on absent inputs renders `name=?` instead of aborting the render.
    bindings = (formula or {}).get("bindings") or {}
    if isinstance(bindings, dict):
        scope: Dict[str, Any] = {}
        scoped = EvalContext(scalars=ctx.scalars, params=ctx.params,
                             locals=scope)
        for k, v_expr in bindings.items():
            scope[str(k)] = _val(v_expr, scoped)
        ctx = EvalContext(scalars=ctx.scalars, params=ctx.params,
                          locals=scope)
    out: Dict[str, str] = {}
    for key, leg in _LEGS:
        expr = (formula or {}).get(key)
        if expr is None:
            continue
        try:
            out[leg] = render_expr(expr, ctx)
        except Exception:
            out[leg] = "<render-error>"
    return out
