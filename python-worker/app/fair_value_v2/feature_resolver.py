from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore


@dataclass(frozen=True)
class ResolvedScalar:
    value: Any
    source: Optional[str]


class FeatureResolver:
    def __init__(self, feature_store: PostgresPointInTimeFeatureStore, features_yaml_path: str):
        self._store = feature_store
        self._cfg = yaml.safe_load(Path(features_yaml_path).read_text())

        self._allow_table_columns = (self._cfg or {}).get("allow_table_columns") or {}
        self._allow_macro_columns = (self._cfg or {}).get("allow_macro_columns") or {}

    def resolve_scalars(self, symbol: str, as_of_ts: datetime, required_scalars: Any) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any]]:
        required = list(required_scalars or [])
        scalars: Dict[str, Any] = {}
        sources: Dict[str, str] = {}
        quality: Dict[str, Any] = {}

        feature_defs = (self._cfg or {}).get("features") or {}

        for name in required:
            d = feature_defs.get(name)
            if not d:
                scalars[name] = None
                quality[f"{name}.missing_definition"] = True
                continue

            v, s, q = self._resolve_one(symbol, as_of_ts, name, d)
            scalars[name] = v
            if s:
                sources[name] = s
            if q:
                quality.update({f"{name}.{k}": v for k, v in q.items()})

        return scalars, sources, quality

    def _resolve_one(self, symbol: str, as_of_ts: datetime, name: str, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        t = (d or {}).get("type")
        if t == "feature_ref":
            return self._resolve_feature_ref(symbol, as_of_ts, d)
        if t == "snapshot_json":
            return self._resolve_snapshot_json(symbol, as_of_ts, d)
        if t == "snapshot_json_path":
            return self._resolve_snapshot_json_path(symbol, as_of_ts, d)
        if t == "table_column":
            return self._resolve_table_column(symbol, as_of_ts, d)
        if t == "macro_column":
            return self._resolve_macro_column(as_of_ts, d)
        if t == "derived":
            return self._resolve_derived(symbol, as_of_ts, d)
        if t == "coalesce":
            return self._resolve_coalesce(symbol, as_of_ts, d)

        return None, None, {"unsupported_type": t}

    def _resolve_feature_ref(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        ref = str((d or {}).get("name") or "")
        feature_defs = (self._cfg or {}).get("features") or {}
        ref_def = feature_defs.get(ref)
        if not ref or not ref_def:
            return None, None, {"missing_ref": True, "ref": ref}
        v, src, q = self._resolve_one(symbol, as_of_ts, ref, ref_def)
        out_q: Dict[str, Any] = {"ref": ref}
        if q:
            out_q.update({f"ref.{k}": vv for k, vv in q.items()})
        return v, src, out_q

    def _resolve_macro_column(self, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        column = str(d.get("column") or "")
        as_of_column = str(d.get("as_of") or "data_date")

        allow_cols = set((self._allow_macro_columns or {}).get("columns") or [])
        allow_asof = set((self._allow_macro_columns or {}).get("as_of_columns") or [])
        if column not in allow_cols:
            return None, None, {"rejected": True, "reason": "column_not_allowed", "column": column}
        if as_of_column not in allow_asof:
            return None, None, {"rejected": True, "reason": "as_of_not_allowed", "as_of": as_of_column}

        v, ts = self._store.get_macro_scalar(as_of_ts=as_of_ts, column=column, as_of_column=as_of_column)
        q: Dict[str, Any] = {
            "row_found": v is not None,
            "as_of_column": as_of_column,
            "timestamp": str(ts) if ts is not None else None,
        }
        src = f"macro_market_data.{column}" if v is not None else None
        return v, src, q

    def _resolve_snapshot_json(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        source = d.get("source")
        json_root = d.get("json_root")
        keys = d.get("keys") or []

        metrics, generated_at = self._store.get_snapshot_payload(symbol, as_of_ts, source=str(source))
        q: Dict[str, Any] = {
            "source": str(source),
            "row_found": bool(metrics is not None),
            "generated_at": str(generated_at) if generated_at is not None else None,
            "candidate_keys": list(keys),
        }

        if metrics is None:
            return None, None, q

        root_obj = metrics
        if json_root:
            root_obj = (metrics or {}).get(str(json_root))
            q["root_found"] = bool(root_obj)

        # Some snapshot payloads store the json_root as a list (e.g. arrays of estimates).
        # For scalar feature extraction we use the first dict element when available.
        if isinstance(root_obj, list):
            q["root_is_list"] = True
            if root_obj and isinstance(root_obj[0], dict):
                root_obj = root_obj[0]
                q["root_list_first_dict"] = True

        try:
            if isinstance(root_obj, dict):
                q["available_keys_sample"] = list(root_obj.keys())[:60]
        except Exception:
            pass

        raw = None
        key_used = None
        for k in keys:
            if isinstance(root_obj, dict) and k in root_obj and root_obj.get(k) is not None:
                raw = root_obj.get(k)
                key_used = k
                break

        q["raw"] = raw
        q["key_used"] = key_used

        try:
            v = float(raw) if raw is not None else None
        except Exception:
            q["parse_error"] = True
            v = None

        src = None
        if key_used:
            src = f"stock_insights_snapshots.{source}.payload.{json_root}.{key_used}" if json_root else f"stock_insights_snapshots.{source}.payload.{key_used}"
        return v, src, q

    def _resolve_snapshot_json_path(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        source = d.get("source")
        path = d.get("path") or []

        metrics, generated_at = self._store.get_snapshot_payload(symbol, as_of_ts, source=str(source))
        q: Dict[str, Any] = {
            "source": str(source),
            "row_found": bool(metrics is not None),
            "generated_at": str(generated_at) if generated_at is not None else None,
            "path": list(path) if isinstance(path, list) else path,
        }
        if metrics is None:
            return None, None, q

        cur: Any = metrics
        try:
            if not isinstance(path, list) or not path:
                q["invalid_path"] = True
                return None, None, q

            for seg in path:
                if isinstance(seg, int):
                    if isinstance(cur, list) and 0 <= seg < len(cur):
                        cur = cur[seg]
                    else:
                        q["path_miss"] = True
                        return None, None, q
                else:
                    key = str(seg)
                    if isinstance(cur, dict) and key in cur:
                        cur = cur.get(key)
                    else:
                        q["path_miss"] = True
                        return None, None, q

            q["raw"] = cur
            try:
                v = float(cur) if cur is not None else None
            except Exception:
                q["parse_error"] = True
                v = None

            # Build a deterministic source string.
            src_path = ".".join([str(p) for p in path])
            src = f"stock_insights_snapshots.{source}.payload.{src_path}" if v is not None else None
            return v, src, q
        except Exception:
            q["path_error"] = True
            return None, None, q

    def _resolve_table_column(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        table = str(d.get("table") or "")
        column = str(d.get("column") or "")
        as_of = str(d.get("as_of") or "")
        order_by = str(d.get("order_by") or as_of)
        where_not_null = bool(d.get("where_not_null"))
        where = d.get("where") or {}

        allow = self._allow_table_columns.get(table) or {}
        allow_cols = set(allow.get("columns") or [])
        allow_asof = set(allow.get("as_of_columns") or [])
        if table not in self._allow_table_columns:
            return None, None, {"rejected": True, "reason": "table_not_allowed", "table": table}
        if column not in allow_cols:
            return None, None, {"rejected": True, "reason": "column_not_allowed", "table": table, "column": column}
        if where and isinstance(where, dict):
            for wk in where.keys():
                if str(wk) not in allow_cols:
                    return None, None, {
                        "rejected": True,
                        "reason": "where_column_not_allowed",
                        "table": table,
                        "column": str(wk),
                    }
        if as_of not in allow_asof:
            return None, None, {"rejected": True, "reason": "as_of_not_allowed", "table": table, "as_of": as_of}
        if order_by != as_of:
            return None, None, {"rejected": True, "reason": "order_by_must_equal_as_of", "order_by": order_by, "as_of": as_of}

        v, ts = self._store.get_table_scalar(
            symbol=symbol,
            as_of_ts=as_of_ts,
            table=table,
            column=column,
            as_of_column=as_of,
            order_by_column=order_by,
            where_not_null=where_not_null,
            where=where if isinstance(where, dict) else None,
        )

        q: Dict[str, Any] = {
            "row_found": v is not None,
            "as_of_column": as_of,
            "timestamp": str(ts) if ts is not None else None,
        }
        if where and isinstance(where, dict):
            q["where"] = dict(where)

        src = f"{table}.{column}" if v is not None else None
        return v, src, q

    def _resolve_coalesce(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        q: Dict[str, Any] = {}
        parts = d.get("sources") or []
        for i, part in enumerate(parts):
            v, src, qq = self._resolve_one(symbol, as_of_ts, f"coalesce[{i}]", part)
            q[f"part_{i}.value"] = v
            if qq:
                for k, vv in qq.items():
                    q[f"part_{i}.{k}"] = vv
            if v is not None:
                return v, src, {**q, "selected": i}
        return None, None, {**q, "selected": None}

    def _resolve_derived(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        name = str(d.get("name") or "")
        params = d.get("params") or {}

        if name == "price_div_pe":
            price_def = params.get("price") or {}
            pe_def = params.get("pe") or {}

            price, price_src, price_q = self._resolve_one(symbol, as_of_ts, "derived.price", price_def)
            pe, pe_src, pe_q = self._resolve_one(symbol, as_of_ts, "derived.pe", pe_def)

            q: Dict[str, Any] = {
                "derived": name,
                "price": price,
                "pe": pe,
            }
            for k, v in (price_q or {}).items():
                q[f"price.{k}"] = v
            for k, v in (pe_q or {}).items():
                q[f"pe.{k}"] = v

            if price is None or pe is None:
                return None, None, q
            try:
                pe_f = float(pe)
                if pe_f <= 0:
                    q["invalid_pe"] = True
                    return None, None, q
                v = float(price) / pe_f
            except Exception:
                q["derive_error"] = True
                return None, None, q

            src = f"derived: {price_src} / {pe_src}" if price_src and pe_src else "derived: price_div_pe"
            return v, src, q

        if name == "inv_earnings_yield":
            ey_def = (params or {}).get("earnings_yield") or {}
            ey, ey_src, ey_q = self._resolve_one(symbol, as_of_ts, "derived.earnings_yield", ey_def)

            q: Dict[str, Any] = {"derived": name, "earnings_yield": ey}
            for k, v in (ey_q or {}).items():
                q[f"earnings_yield.{k}"] = v

            if ey is None:
                return None, None, q
            try:
                ey_f = float(ey)
                if ey_f <= 0:
                    q["invalid_earnings_yield"] = True
                    return None, None, q
                pe = 1.0 / ey_f
            except Exception:
                q["derive_error"] = True
                return None, None, q

            src = f"derived: 1 / {ey_src}" if ey_src else "derived: inv_earnings_yield"
            return pe, src, q

        if name == "growth_from_eps_forward_and_eps_ttm":
            eps_f_def = (params or {}).get("eps_forward") or {}
            eps_ttm_def = (params or {}).get("eps_ttm") or {}

            eps_f, eps_f_src, eps_f_q = self._resolve_one(symbol, as_of_ts, "derived.eps_forward", eps_f_def)
            eps_ttm, eps_ttm_src, eps_ttm_q = self._resolve_one(symbol, as_of_ts, "derived.eps_ttm", eps_ttm_def)

            q: Dict[str, Any] = {
                "derived": name,
                "eps_forward": eps_f,
                "eps_ttm": eps_ttm,
            }
            for k, v in (eps_f_q or {}).items():
                q[f"eps_forward.{k}"] = v
            for k, v in (eps_ttm_q or {}).items():
                q[f"eps_ttm.{k}"] = v

            if eps_f is None or eps_ttm is None:
                return None, None, q

            try:
                eps_ttm_f = float(eps_ttm)
                if eps_ttm_f <= 0:
                    q["invalid_eps_ttm"] = True
                    return None, None, q
                g = (float(eps_f) / eps_ttm_f) - 1.0
            except Exception:
                q["derive_error"] = True
                return None, None, q

            src = (
                f"derived: ({eps_f_src} / {eps_ttm_src}) - 1" if eps_f_src and eps_ttm_src else "derived: growth_from_eps_forward_and_eps_ttm"
            )
            return g, src, q

        if name == "growth_pct_from_forward_growth":
            growth_def = (params or {}).get("growth") or {}
            g_raw, g_src, g_q = self._resolve_one(symbol, as_of_ts, "derived.forward_growth", growth_def)

            q: Dict[str, Any] = {
                "derived": name,
                "forward_growth_raw": g_raw,
            }
            for k, v in (g_q or {}).items():
                q[f"growth.{k}"] = v

            if g_raw is None:
                return None, None, q

            try:
                g_f = float(g_raw)
            except Exception:
                q["parse_error"] = True
                return None, None, q

            # Normalize growth to a 1Y percent value.
            # Inputs seen in the wild:
            # - fraction: 0.25 == 25%
            # - ratio: 1.25 == 125%
            # - percent: 25 == 25%
            # We interpret values in [0, 3] as fraction/ratio and scale by 100.
            # Values > 3 are interpreted as already being percent.
            # Negative growth is valid; infer unit based on absolute magnitude.
            if abs(g_f) <= 3.0:
                g_pct = 100.0 * g_f
                q["unit_inferred"] = "fraction_or_ratio"
            else:
                g_pct = g_f
                q["unit_inferred"] = "percent"

            src = f"derived: growth_pct({g_src})" if g_src else "derived: growth_pct_from_forward_growth"
            q["forward_growth_pct"] = g_pct
            return g_pct, src, q

        if name == "ratio":
            num_def = (params or {}).get("numerator") or {}
            den_def = (params or {}).get("denominator") or {}

            num, num_src, num_q = self._resolve_one(symbol, as_of_ts, "derived.numerator", num_def)
            den, den_src, den_q = self._resolve_one(symbol, as_of_ts, "derived.denominator", den_def)

            q: Dict[str, Any] = {"derived": name, "numerator": num, "denominator": den}
            for k, v in (num_q or {}).items():
                q[f"numerator.{k}"] = v
            for k, v in (den_q or {}).items():
                q[f"denominator.{k}"] = v

            if num is None or den is None:
                return None, None, q
            try:
                den_f = float(den)
                if den_f == 0:
                    q["invalid_denominator"] = True
                    return None, None, q
                v = float(num) / den_f
            except Exception:
                q["derive_error"] = True
                return None, None, q

            src = f"derived: {num_src} / {den_src}" if num_src and den_src else "derived: ratio"
            return v, src, q

        return None, None, {"unsupported_derived": name}
