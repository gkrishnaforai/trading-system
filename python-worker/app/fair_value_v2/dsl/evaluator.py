from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import math


class DslError(Exception):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


Number = Union[int, float]
Expr = Any


@dataclass(frozen=True)
class EvalContext:
    scalars: Dict[str, Any]
    params: Dict[str, Any]
    locals: Dict[str, Any] = field(default_factory=dict)
    debug: bool = False
    trace: Optional[List[Dict[str, Any]]] = None


def _trace(ctx: EvalContext, record: Dict[str, Any]) -> None:
    if not ctx.debug:
        return
    if ctx.trace is None:
        return
    ctx.trace.append(record)


def _is_bad_number(v: Any) -> bool:
    try:
        f = float(v)
    except Exception:
        return True
    return math.isnan(f) or math.isinf(f)


def _to_float(v: Any, *, path: Optional[str] = None) -> float:
    if v is None:
        raise DslError("missing", "value is null", {"path": path})
    if _is_bad_number(v):
        raise DslError("invalid_number", "value is NaN/inf", {"path": path, "value": v})
    return float(v)


def _as_expr_list(node: Any) -> List[Any]:
    if isinstance(node, list):
        return node
    return [node]


def _eval_dcf_mega_cap_price(node: Any, ctx: EvalContext, path: str) -> float:
    if not isinstance(node, dict):
        raise DslError("invalid_ast", "dcf_mega_cap_price node must be a dict", {"path": path})

    fcf_ttm = _to_float(ctx.scalars.get("fcf_ttm"), path=f"{path}.fcf_ttm")
    shares_outstanding = _to_float(ctx.scalars.get("shares_outstanding"), path=f"{path}.shares_outstanding")
    total_debt = _to_float(ctx.scalars.get("total_debt"), path=f"{path}.total_debt")
    cash_and_equivalents = _to_float(ctx.scalars.get("cash_and_equivalents"), path=f"{path}.cash_and_equivalents")

    if fcf_ttm <= 0 or shares_outstanding <= 0:
        raise DslError("missing_data", "invalid inputs", {"path": path, "fcf_ttm": fcf_ttm, "shares_outstanding": shares_outstanding})

    wacc = _to_float(eval_expr(node.get("wacc"), ctx, path=f"{path}.wacc"), path=f"{path}.wacc")
    terminal_growth = _to_float(
        eval_expr(node.get("terminal_growth"), ctx, path=f"{path}.terminal_growth"), path=f"{path}.terminal_growth"
    )
    growth = _to_float(eval_expr(node.get("growth"), ctx, path=f"{path}.growth"), path=f"{path}.growth")
    growth_cap = _to_float(eval_expr(node.get("growth_cap"), ctx, path=f"{path}.growth_cap"), path=f"{path}.growth_cap")
    fade_years = _to_float(eval_expr(node.get("fade_years"), ctx, path=f"{path}.fade_years"), path=f"{path}.fade_years")
    explicit_years = int(
        _to_float(eval_expr(node.get("explicit_years"), ctx, path=f"{path}.explicit_years"), path=f"{path}.explicit_years")
    )
    terminal_value_cap_share_of_ev = _to_float(
        eval_expr(node.get("terminal_value_cap_share_of_ev"), ctx, path=f"{path}.terminal_value_cap_share_of_ev"),
        path=f"{path}.terminal_value_cap_share_of_ev",
    )

    if explicit_years != 10:
        raise DslError("invalid_assumption", "only explicit_years=10 is supported", {"path": path, "explicit_years": explicit_years})

    if wacc - terminal_growth <= 0:
        raise DslError(
            "invalid_assumption",
            "wacc must be > terminal_growth",
            {"path": path, "wacc": wacc, "terminal_growth": terminal_growth},
        )

    g0 = max(0.0, min(growth_cap, growth))
    one_plus_wacc = 1.0 + wacc
    fade_den = max(1.0, float(fade_years))
    g_step = (g0 - terminal_growth) / fade_den

    g6 = g0 - (g_step * 1.0)
    g7 = g0 - (g_step * 2.0)
    g8 = g0 - (g_step * 3.0)
    g9 = g0 - (g_step * 4.0)
    g10 = g0 - (g_step * 5.0)

    fcf_1 = fcf_ttm * math.pow(1.0 + g0, 1.0)
    fcf_2 = fcf_ttm * math.pow(1.0 + g0, 2.0)
    fcf_3 = fcf_ttm * math.pow(1.0 + g0, 3.0)
    fcf_4 = fcf_ttm * math.pow(1.0 + g0, 4.0)
    fcf_5 = fcf_ttm * math.pow(1.0 + g0, 5.0)

    fcf_6 = fcf_5 * (1.0 + g6)
    fcf_7 = fcf_6 * (1.0 + g7)
    fcf_8 = fcf_7 * (1.0 + g8)
    fcf_9 = fcf_8 * (1.0 + g9)
    fcf_10 = fcf_9 * (1.0 + g10)

    pv_1 = fcf_1 / math.pow(one_plus_wacc, 1.0)
    pv_2 = fcf_2 / math.pow(one_plus_wacc, 2.0)
    pv_3 = fcf_3 / math.pow(one_plus_wacc, 3.0)
    pv_4 = fcf_4 / math.pow(one_plus_wacc, 4.0)
    pv_5 = fcf_5 / math.pow(one_plus_wacc, 5.0)
    pv_6 = fcf_6 / math.pow(one_plus_wacc, 6.0)
    pv_7 = fcf_7 / math.pow(one_plus_wacc, 7.0)
    pv_8 = fcf_8 / math.pow(one_plus_wacc, 8.0)
    pv_9 = fcf_9 / math.pow(one_plus_wacc, 9.0)
    pv_10 = fcf_10 / math.pow(one_plus_wacc, 10.0)

    pv_fcf_1_10 = pv_1 + pv_2 + pv_3 + pv_4 + pv_5 + pv_6 + pv_7 + pv_8 + pv_9 + pv_10
    terminal_value = (fcf_10 * (1.0 + terminal_growth)) / (wacc - terminal_growth)
    pv_terminal = terminal_value / math.pow(one_plus_wacc, 10.0)
    ev = pv_fcf_1_10 + pv_terminal

    if ev <= 0:
        raise DslError("invalid_assumption", "ev must be > 0", {"path": path, "ev": ev})

    terminal_share_of_ev = pv_terminal / ev
    if terminal_share_of_ev > terminal_value_cap_share_of_ev:
        raise DslError(
            "invalid_assumption",
            "terminal_value_dominates",
            {
                "path": path,
                "terminal_share_of_ev": terminal_share_of_ev,
                "terminal_value_cap_share_of_ev": terminal_value_cap_share_of_ev,
            },
        )

    net_debt = total_debt - cash_and_equivalents
    equity_value = ev - net_debt
    fair_price = equity_value / shares_outstanding

    _trace(
        ctx,
        {
            "path": path,
            "op": "dcf_mega_cap_price",
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "growth": growth,
            "growth_cap": growth_cap,
            "fade_years": fade_years,
            "explicit_years": explicit_years,
            "terminal_share_of_ev": terminal_share_of_ev,
            "out": fair_price,
        },
    )
    return fair_price


def eval_expr(expr: Any, ctx: EvalContext, path: str = "$") -> Any:
    if expr is None:
        return None

    if isinstance(expr, (int, float)):
        return float(expr)

    if not isinstance(expr, dict):
        raise DslError("invalid_ast", f"expected dict AST node, got {type(expr)}")

    if "const" in expr:
        return expr["const"]

    if "var" in expr:
        key = str(expr["var"])
        if key in ctx.locals:
            val = ctx.locals.get(key)
            _trace(ctx, {"path": path, "op": "var", "key": key, "value": val, "scope": "local"})
            return val
        if key not in ctx.scalars:
            raise DslError("missing", f"missing scalar: {key}", {"path": path, "key": key})
        val = ctx.scalars.get(key)
        _trace(ctx, {"path": path, "op": "var", "key": key, "value": val})
        return val

    if "param" in expr:
        key = str(expr["param"])
        val = ctx.params.get(key)
        _trace(ctx, {"path": path, "op": "param", "key": key, "value": val})
        return val

    if "coalesce" in expr:
        for candidate in _as_expr_list(expr["coalesce"]):
            v = eval_expr(candidate, ctx, path=f"{path}.coalesce")
            if v is None:
                continue
            if isinstance(v, (int, float)) and _is_bad_number(v):
                continue
            _trace(ctx, {"path": path, "op": "coalesce", "value": v})
            return v
        return None

    if "dcf_mega_cap_price" in expr:
        return _eval_dcf_mega_cap_price(expr["dcf_mega_cap_price"], ctx, path=f"{path}.dcf_mega_cap_price")

    if "error" in expr:
        payload = expr["error"]
        if isinstance(payload, str):
            raise DslError("invalid_assumption", payload, {"path": path})
        if not isinstance(payload, dict):
            raise DslError("invalid_ast", "error payload must be a dict or string", {"path": path})

        code = str(payload.get("code") or "invalid_assumption")
        message = str(payload.get("message") or "error")
        details_node = payload.get("details")
        details: Dict[str, Any] = {"path": path}

        if details_node is not None:
            if not isinstance(details_node, dict):
                raise DslError("invalid_ast", "error.details must be a dict", {"path": path})
            for k, v_expr in details_node.items():
                details[str(k)] = eval_expr(v_expr, ctx, path=f"{path}.error.details.{k}")

        raise DslError(code, message, details)

    if "let" in expr:
        node = expr["let"] or {}
        bindings = node.get("bindings") or {}
        in_expr = node.get("in")
        if in_expr is None:
            raise DslError("invalid_ast", "let.in is required", {"path": path})

        scope: Dict[str, Any] = dict(ctx.locals or {})
        scoped_ctx = EvalContext(
            scalars=ctx.scalars,
            params=ctx.params,
            locals=scope,
            debug=ctx.debug,
            trace=ctx.trace,
        )

        if not isinstance(bindings, dict):
            raise DslError("invalid_ast", "let.bindings must be a dict", {"path": path})

        for k, v_expr in bindings.items():
            val = eval_expr(v_expr, scoped_ctx, path=f"{path}.let.bindings.{k}")
            scope[str(k)] = val
            _trace(ctx, {"path": path, "op": "let.bind", "key": str(k), "value": val})

        out = eval_expr(in_expr, scoped_ctx, path=f"{path}.let.in")
        _trace(ctx, {"path": path, "op": "let", "out": out, "keys": list(bindings.keys())})
        return out

    if "require" in expr:
        payload = expr["require"]
        v = eval_expr(payload.get("value"), ctx, path=f"{path}.require.value")
        if v is None or (isinstance(v, (int, float)) and _is_bad_number(v)):
            raise DslError(
                "missing_data",
                "required value missing",
                {"reason": payload.get("reason"), "path": path},
            )
        _trace(ctx, {"path": path, "op": "require", "value": v})
        return v

    if "add" in expr:
        a, b = _as_expr_list(expr["add"])[:2]
        av = _to_float(eval_expr(a, ctx, path=f"{path}.add.a"), path=f"{path}.add.a")
        bv = _to_float(eval_expr(b, ctx, path=f"{path}.add.b"), path=f"{path}.add.b")
        out = av + bv
        _trace(ctx, {"path": path, "op": "add", "a": av, "b": bv, "out": out})
        return out

    if "sub" in expr:
        a, b = _as_expr_list(expr["sub"])[:2]
        av = _to_float(eval_expr(a, ctx, path=f"{path}.sub.a"), path=f"{path}.sub.a")
        bv = _to_float(eval_expr(b, ctx, path=f"{path}.sub.b"), path=f"{path}.sub.b")
        out = av - bv
        _trace(ctx, {"path": path, "op": "sub", "a": av, "b": bv, "out": out})
        return out

    if "mul" in expr:
        parts = [eval_expr(p, ctx, path=f"{path}.mul") for p in _as_expr_list(expr["mul"])]
        out = 1.0
        for p in parts:
            out *= _to_float(p, path=f"{path}.mul")
        _trace(ctx, {"path": path, "op": "mul", "parts": parts, "out": out})
        return out

    if "div" in expr:
        a, b = _as_expr_list(expr["div"])[:2]
        denom = _to_float(eval_expr(b, ctx, path=f"{path}.div.b"), path=f"{path}.div.b")
        if denom == 0:
            raise DslError("invalid_assumption", "division by zero", {"path": path})
        num = _to_float(eval_expr(a, ctx, path=f"{path}.div.a"), path=f"{path}.div.a")
        out = num / denom
        _trace(ctx, {"path": path, "op": "div", "a": num, "b": denom, "out": out})
        return out

    if "min" in expr:
        a, b = _as_expr_list(expr["min"])[:2]
        out = min(
            _to_float(eval_expr(a, ctx, path=f"{path}.min.a"), path=f"{path}.min.a"),
            _to_float(eval_expr(b, ctx, path=f"{path}.min.b"), path=f"{path}.min.b"),
        )
        _trace(ctx, {"path": path, "op": "min", "a": a, "b": b, "out": out})
        return out

    if "max" in expr:
        a, b = _as_expr_list(expr["max"])[:2]
        out = max(
            _to_float(eval_expr(a, ctx, path=f"{path}.max.a"), path=f"{path}.max.a"),
            _to_float(eval_expr(b, ctx, path=f"{path}.max.b"), path=f"{path}.max.b"),
        )
        _trace(ctx, {"path": path, "op": "max", "a": a, "b": b, "out": out})
        return out

    if "clamp" in expr:
        node = expr["clamp"]
        v = _to_float(eval_expr(node.get("value"), ctx, path=f"{path}.clamp.value"), path=f"{path}.clamp.value")
        lo = _to_float(eval_expr(node.get("lo"), ctx, path=f"{path}.clamp.lo"), path=f"{path}.clamp.lo")
        hi = _to_float(eval_expr(node.get("hi"), ctx, path=f"{path}.clamp.hi"), path=f"{path}.clamp.hi")
        if lo > hi:
            lo, hi = hi, lo
        out = max(lo, min(hi, v))
        _trace(ctx, {"path": path, "op": "clamp", "value": v, "lo": lo, "hi": hi, "out": out})
        return out

    if "log" in expr:
        v = _to_float(eval_expr(expr["log"], ctx, path=f"{path}.log"), path=f"{path}.log")
        if v <= 0:
            raise DslError("invalid_assumption", "log input must be > 0", {"path": path, "value": v})
        out = math.log(v)
        _trace(ctx, {"path": path, "op": "log", "value": v, "out": out})
        return out

    if "pow" in expr:
        a, b = _as_expr_list(expr["pow"])[:2]
        base = _to_float(eval_expr(a, ctx, path=f"{path}.pow.a"), path=f"{path}.pow.a")
        exp = _to_float(eval_expr(b, ctx, path=f"{path}.pow.b"), path=f"{path}.pow.b")
        try:
            out = math.pow(base, exp)
        except Exception:
            raise DslError("invalid_assumption", "pow failed", {"path": path, "base": base, "exp": exp})
        _trace(ctx, {"path": path, "op": "pow", "base": base, "exp": exp, "out": out})
        return out

    if "gt" in expr:
        a, b = _as_expr_list(expr["gt"])[:2]
        out = _to_float(eval_expr(a, ctx, path=f"{path}.gt.a"), path=f"{path}.gt.a") > _to_float(
            eval_expr(b, ctx, path=f"{path}.gt.b"), path=f"{path}.gt.b"
        )
        _trace(ctx, {"path": path, "op": "gt", "a": a, "b": b, "out": out})
        return out

    if "gte" in expr:
        a, b = _as_expr_list(expr["gte"])[:2]
        out = _to_float(eval_expr(a, ctx, path=f"{path}.gte.a"), path=f"{path}.gte.a") >= _to_float(
            eval_expr(b, ctx, path=f"{path}.gte.b"), path=f"{path}.gte.b"
        )
        _trace(ctx, {"path": path, "op": "gte", "a": a, "b": b, "out": out})
        return out

    if "lt" in expr:
        a, b = _as_expr_list(expr["lt"])[:2]
        out = _to_float(eval_expr(a, ctx, path=f"{path}.lt.a"), path=f"{path}.lt.a") < _to_float(
            eval_expr(b, ctx, path=f"{path}.lt.b"), path=f"{path}.lt.b"
        )
        _trace(ctx, {"path": path, "op": "lt", "a": a, "b": b, "out": out})
        return out

    if "lte" in expr:
        a, b = _as_expr_list(expr["lte"])[:2]
        out = _to_float(eval_expr(a, ctx, path=f"{path}.lte.a"), path=f"{path}.lte.a") <= _to_float(
            eval_expr(b, ctx, path=f"{path}.lte.b"), path=f"{path}.lte.b"
        )
        _trace(ctx, {"path": path, "op": "lte", "a": a, "b": b, "out": out})
        return out

    if "eq" in expr:
        a, b = _as_expr_list(expr["eq"])[:2]
        out = eval_expr(a, ctx, path=f"{path}.eq.a") == eval_expr(b, ctx, path=f"{path}.eq.b")
        _trace(ctx, {"path": path, "op": "eq", "a": a, "b": b, "out": out})
        return out

    if "and" in expr:
        parts = [bool(eval_expr(p, ctx, path=f"{path}.and")) for p in _as_expr_list(expr["and"])]
        out = all(parts)
        _trace(ctx, {"path": path, "op": "and", "parts": parts, "out": out})
        return out

    if "or" in expr:
        parts = [bool(eval_expr(p, ctx, path=f"{path}.or")) for p in _as_expr_list(expr["or"])]
        out = any(parts)
        _trace(ctx, {"path": path, "op": "or", "parts": parts, "out": out})
        return out

    if "not" in expr:
        out = not bool(eval_expr(expr["not"], ctx, path=f"{path}.not"))
        _trace(ctx, {"path": path, "op": "not", "value": expr["not"], "out": out})
        return out

    if "if" in expr:
        payload = expr["if"]
        cond = bool(eval_expr(payload.get("cond"), ctx, path=f"{path}.if.cond"))
        out = eval_expr(payload.get("then" if cond else "else"), ctx, path=f"{path}.if")
        _trace(ctx, {"path": path, "op": "if", "cond": cond, "out": out})
        return out

    raise DslError("unsupported", f"unsupported AST node keys: {list(expr.keys())}")


def _apply_formula_bindings(formula: Dict[str, Any], ctx: EvalContext, *, path: str) -> EvalContext:
    bindings = (formula or {}).get("bindings")
    if not bindings:
        return ctx
    if not isinstance(bindings, dict):
        raise DslError("invalid_definition", "formula.bindings must be a dict", {"path": path})

    scope: Dict[str, Any] = dict(ctx.locals or {})
    scoped_ctx = EvalContext(
        scalars=ctx.scalars,
        params=ctx.params,
        locals=scope,
        debug=ctx.debug,
        trace=ctx.trace,
    )

    for k, v_expr in bindings.items():
        val = eval_expr(v_expr, scoped_ctx, path=f"{path}.bindings.{k}")
        scope[str(k)] = val
        _trace(ctx, {"path": path, "op": "formula.bind", "key": str(k), "value": val})

    return scoped_ctx


def evaluate_formula(formula: Dict[str, Any], scalars: Dict[str, Any], params: Dict[str, Any], debug: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ctx = EvalContext(scalars=scalars or {}, params=params or {}, locals={}, debug=debug, trace=[] if debug else None)
    ctx = _apply_formula_bindings(formula or {}, ctx, path="$")
    out: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}

    for key, expr in (formula or {}).items():
        v = eval_expr(expr, ctx, path=f"$.{key}")
        out[key] = v

    if debug:
        metrics["trace"] = ctx.trace

    return out, metrics


def evaluate_fair_price(formula: Dict[str, Any], *, scalars: Dict[str, Any], params: Dict[str, Any], debug: bool = False) -> Tuple[Optional[float], Dict[str, Any]]:
    ctx = EvalContext(scalars=scalars or {}, params=params or {}, locals={}, debug=debug, trace=[] if debug else None)
    ctx = _apply_formula_bindings(formula or {}, ctx, path="$")
    metrics: Dict[str, Any] = {}

    fair_price_expr = formula.get("fair_price")
    if fair_price_expr is None:
        raise DslError("invalid_definition", "formula.fair_price is required")

    v = eval_expr(fair_price_expr, ctx, path="$.fair_price")
    if v is None:
        return None, {"reason": "missing_data"}
    fair_price = _to_float(v, path="$.fair_price")
    if debug:
        metrics["trace"] = ctx.trace
    return fair_price, metrics


def evaluate_scenarios(
    formula: Dict[str, Any], *, scalars: Dict[str, Any], params: Dict[str, Any], debug: bool = False
) -> Tuple[Dict[str, Optional[float]], Dict[str, Any]]:
    """Evaluate base + optional scenario fair prices.

    Scenario keys supported (optional):
    - bear_fair_price
    - bull_fair_price
    - explosive_fair_price
    """

    ctx = EvalContext(scalars=scalars or {}, params=params or {}, locals={}, debug=debug, trace=[] if debug else None)
    ctx = _apply_formula_bindings(formula or {}, ctx, path="$")
    metrics: Dict[str, Any] = {}

    out: Dict[str, Optional[float]] = {}

    # Base is required
    base_expr = formula.get("fair_price")
    if base_expr is None:
        raise DslError("invalid_definition", "formula.fair_price is required")

    base_v = eval_expr(base_expr, ctx, path="$.fair_price")
    out["base"] = None if base_v is None else _to_float(base_v, path="$.fair_price")

    for key, out_key in (
        ("bear_fair_price", "bear"),
        ("bull_fair_price", "bull"),
        ("explosive_fair_price", "explosive"),
    ):
        expr = formula.get(key)
        if expr is None:
            out[out_key] = None
            continue
        v = eval_expr(expr, ctx, path=f"$.{key}")
        out[out_key] = None if v is None else _to_float(v, path=f"$.{key}")

    if debug:
        metrics["trace"] = ctx.trace

    return out, metrics
