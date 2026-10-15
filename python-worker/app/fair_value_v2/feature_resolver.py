from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from app.fair_value_v2 import currency as fv_ccy
from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore

logger = logging.getLogger(__name__)


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
        self._sym_currency_cache: Dict[str, Optional[str]] = {}

    def _symbol_reported_currency(self, symbol: str, as_of_ts: datetime) -> Optional[str]:
        """The currency the symbol's financial statements are reported
        in (TSM → TWD). Read once from the fmp_fundamentals snapshot;
        used to normalize unmarked money fields (key_metrics_ttm
        marketCap etc.) and statement rows alike."""
        cached = self._sym_currency_cache.get(symbol)
        if cached is not None:
            return cached or None
        ccy = None
        try:
            payload, _ts = self._store.get_snapshot_payload(
                symbol, as_of_ts, source="fmp_fundamentals")
            if isinstance(payload, dict):
                queue = [payload]
                while queue and ccy is None:
                    cur = queue.pop()
                    if isinstance(cur, dict):
                        rc = cur.get("reportedCurrency")
                        if rc:
                            ccy = str(rc).upper()
                            break
                        queue.extend(v for v in cur.values()
                                     if isinstance(v, (dict, list)))
                    elif isinstance(cur, list):
                        queue.extend(v for v in cur[:3]
                                     if isinstance(v, (dict, list)))
        except Exception:
            ccy = None
        self._sym_currency_cache[symbol] = ccy or ""
        return ccy

    @staticmethod
    def _row_currency(row: Any) -> Optional[str]:
        """Declared currency of a payload row — reportedCurrency on
        statement rows, currency on profile rows."""
        if not isinstance(row, dict):
            return None
        c = row.get("reportedCurrency") or row.get("currency")
        return str(c).upper() if c else None

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

    @staticmethod
    def _stale(d: Dict[str, Any], q: Dict[str, Any],
               as_of_ts: datetime) -> bool:
        """Reject a resolved source whose data is older than
        `max_age_days` relative to as_of. A 6-month-old key-metrics
        snapshot must not outrank a fresh fundamentals snapshot just
        because it sits first in the coalesce list."""
        max_age = d.get("max_age_days")
        if not max_age:
            return False
        raw_ts = q.get("generated_at") or q.get("timestamp")
        if not raw_ts:
            return False
        try:
            ts = datetime.fromisoformat(str(raw_ts))
        except Exception:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (as_of_ts - ts).days
        if age > float(max_age):
            q["stale_rejected"] = True
            q["age_days"] = age
            return True
        return False

    def _resolve_one(self, symbol: str, as_of_ts: datetime, name: str, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        # A store/source failure (schema drift, missing column, dead
        # connection) degrades to an unavailable source with explicit
        # quality metadata — coalesce falls through to the next source
        # instead of aborting the whole run.
        try:
            t = (d or {}).get("type")
            if t == "feature_ref":
                return self._resolve_feature_ref(symbol, as_of_ts, d)
            if t == "snapshot_json":
                v, s, q = self._resolve_snapshot_json(symbol, as_of_ts, d)
            elif t == "snapshot_json_path":
                v, s, q = self._resolve_snapshot_json_path(symbol, as_of_ts, d)
            elif t == "table_column":
                v, s, q = self._resolve_table_column(symbol, as_of_ts, d)
            elif t == "table_column_avg":
                v, s, q = self._resolve_table_column_avg(symbol, as_of_ts, d)
            elif t == "macro_column":
                v, s, q = self._resolve_macro_column(as_of_ts, d)
            elif t == "forward_estimate":
                v, s, q = self._resolve_forward_estimate(symbol, as_of_ts, d)
            elif t == "eps_estimate_series":
                v, s, q = self._resolve_eps_series(symbol, as_of_ts, d)
            elif t == "derived":
                return self._resolve_derived(symbol, as_of_ts, d)
            elif t == "coalesce":
                return self._resolve_coalesce(symbol, as_of_ts, d)
            else:
                return None, None, {"unsupported_type": t}
        except Exception as e:
            logger.warning("fv2 source error [%s] %s: %s", name, type(e).__name__, e)
            return None, None, {
                "source_error": True,
                "error_class": type(e).__name__,
                "error_detail": str(e)[:300],
            }

        if v is not None and self._stale(d, q, as_of_ts):
            return None, None, q
        return v, s, q

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

        # Foreign-lister normalization: statement/key-metric rows carry
        # reportedCurrency (e.g. TWD for TSM); scale money fields to USD.
        # Rows without a marker fall back to the symbol's reported
        # currency for known money keys (key_metrics_ttm marketCap).
        if v is not None:
            row_ccy = self._row_currency(root_obj)
            if row_ccy:
                v, fx_note = fv_ccy.scale(key_used, v, row_ccy, as_of=as_of_ts)
            else:
                v, fx_note = fv_ccy.scale(
                    key_used, v,
                    self._symbol_reported_currency(symbol, as_of_ts),
                    require_known=True, as_of=as_of_ts)
            if fx_note:
                q["fx"] = fx_note

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
        enc_cur: Optional[str] = None   # nearest enclosing row's reportedCurrency
        try:
            if not isinstance(path, list) or not path:
                q["invalid_path"] = True
                return None, None, q

            for seg in path:
                row_ccy = self._row_currency(cur)
                if row_ccy:
                    enc_cur = row_ccy
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

            # Foreign-lister normalization: leaf lives under a row whose
            # reportedCurrency is non-USD → scale money fields to USD.
            # No marker → symbol-level reported currency for known
            # money keys only.
            if v is not None:
                leaf_key = path[-1] if path and not isinstance(path[-1], int) else None
                if enc_cur:
                    v, fx_note = fv_ccy.scale(leaf_key, v, enc_cur, as_of=as_of_ts)
                else:
                    v, fx_note = fv_ccy.scale(
                        leaf_key, v,
                        self._symbol_reported_currency(symbol, as_of_ts),
                        require_known=True, as_of=as_of_ts)
                if fx_note:
                    q["fx"] = fx_note

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

        v, ts, row_ccy = self._store.get_table_scalar(
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
        if row_ccy:
            q["row_currency"] = row_ccy
        if v is not None:
            v, fx_note = fv_ccy.scale(column, v, row_ccy, as_of=as_of_ts)
            if fx_note:
                q["fx"] = fx_note
        if where and isinstance(where, dict):
            q["where"] = dict(where)

        src = f"{table}.{column}" if v is not None else None
        return v, src, q

    def _resolve_table_column_avg(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        table = str(d.get("table") or "")
        column = str(d.get("column") or "")
        as_of = str(d.get("as_of") or "")
        order_by = str(d.get("order_by") or as_of)
        rows = int(d.get("rows") or 8)

        allow = self._allow_table_columns.get(table) or {}
        allow_cols = set(allow.get("columns") or [])
        allow_asof = set(allow.get("as_of_columns") or [])
        if table not in self._allow_table_columns:
            return None, None, {"rejected": True, "reason": "table_not_allowed", "table": table}
        if column not in allow_cols:
            return None, None, {"rejected": True, "reason": "column_not_allowed", "table": table, "column": column}
        if as_of not in allow_asof:
            return None, None, {"rejected": True, "reason": "as_of_not_allowed", "table": table, "as_of": as_of}
        if order_by != as_of:
            return None, None, {"rejected": True, "reason": "order_by_must_equal_as_of", "order_by": order_by, "as_of": as_of}

        v, ts, row_ccy = self._store.get_table_column_avg(
            symbol=symbol, as_of_ts=as_of_ts, table=table, column=column,
            as_of_column=as_of, order_by_column=order_by, limit=rows)
        q: Dict[str, Any] = {
            "row_found": v is not None,
            "as_of_column": as_of,
            "rows": rows,
            "timestamp": str(ts) if ts is not None else None,
        }
        if row_ccy:
            q["row_currency"] = row_ccy
        if v is not None:
            v, fx_note = fv_ccy.scale(column, v, row_ccy, as_of=as_of_ts)
            if fx_note:
                q["fx"] = fx_note
        src = f"{table}.{column}~avg{rows}" if v is not None else None
        return v, src, q

    def _resolve_forward_estimate(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        column = str(d.get("column") or "revenue_estimate")
        try:
            v, ts, fy = self._store.get_forward_estimate(
                symbol, as_of_ts, column=column)
        except ValueError:
            return None, None, {"rejected": True,
                                "reason": "column_not_allowed",
                                "column": column}
        q: Dict[str, Any] = {
            "row_found": v is not None,
            "timestamp": str(ts) if ts is not None else None,
            "fiscal_year": fy,
        }
        src = (f"fundamental_estimate_snapshots.{column}[FY{fy}]"
               if v is not None else None)
        return v, src, q

    def _resolve_eps_series(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        field = str(d.get("field") or "start_eps")
        if field not in ("start_eps", "end_eps", "years", "analysts"):
            return None, None, {"rejected": True,
                                "reason": "field_not_allowed",
                                "field": field}
        s = self._store.get_eps_estimate_series(symbol, as_of_ts)
        v = (s or {}).get(field)
        cov = None
        if field == "analysts" and v is None:
            # coverage does not require a positive-EPS window — a
            # loss-maker can still be widely covered
            cov = self._store.get_estimate_coverage(symbol, as_of_ts)
            v = (cov or {}).get("analysts")
        window = (f"FY{s['start_fy']}-FY{s['end_fy']}"
                  if s else
                  (f"FY{cov['fiscal_year']}" if cov else None))
        q: Dict[str, Any] = {
            "row_found": s is not None or cov is not None,
            "timestamp": str((s or cov or {}).get("as_of") or "") or None,
            "window": window,
        }
        src = (f"fundamental_estimate_snapshots.eps_estimate[{window}]"
               if v is not None else None)
        return v, src, q

    def _resolve_coalesce(self, symbol: str, as_of_ts: datetime, d: Dict[str, Any]) -> Tuple[Any, Optional[str], Dict[str, Any]]:
        q: Dict[str, Any] = {}
        parts = d.get("sources") or []
        feat_max_age = d.get("max_age_days")
        for i, part in enumerate(parts):
            # feature-level max_age_days applies to every source that
            # doesn't set its own bound
            if feat_max_age and isinstance(part, dict) \
                    and "max_age_days" not in part:
                part = {**part, "max_age_days": feat_max_age}
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

        if name == "sales_to_capital":
            rev_def = (params or {}).get("revenue") or {}
            g_def = (params or {}).get("growth") or {}
            ri_def = (params or {}).get("reinvestment") or {}

            rev, rev_src, rev_q = self._resolve_one(symbol, as_of_ts, "derived.revenue", rev_def)
            g, g_src, g_q = self._resolve_one(symbol, as_of_ts, "derived.growth", g_def)
            ri, ri_src, ri_q = self._resolve_one(symbol, as_of_ts, "derived.reinvestment", ri_def)

            q: Dict[str, Any] = {
                "derived": name, "revenue": rev, "growth": g,
                "reinvestment": ri,
            }
            for k, v in (rev_q or {}).items():
                q[f"revenue.{k}"] = v
            for k, v in (g_q or {}).items():
                q[f"growth.{k}"] = v
            for k, v in (ri_q or {}).items():
                q[f"reinvestment.{k}"] = v

            if rev is None or g is None or ri is None:
                return None, None, q
            try:
                g_f, rev_f, ri_f = float(g), float(rev), float(ri)
                if rev_f <= 0 or g_f <= -1:
                    q["invalid_inputs"] = True
                    return None, None, q
                # realized Δrevenue from the YoY growth base
                delta_rev = rev_f * g_f / (1.0 + g_f)
                reinvest = abs(ri_f)
                if delta_rev <= 0 or reinvest <= 0:
                    q["no_measurable_reinvestment"] = True
                    return None, None, q
                scap = delta_rev / reinvest
                # sane band — a tiny capex base or a one-off print must
                # not produce a 40:1 turnover fantasy
                if not (0.1 <= scap <= 20.0):
                    q["out_of_band"] = round(scap, 4)
                    return None, None, q
            except Exception:
                q["derive_error"] = True
                return None, None, q

            src = (f"derived: Δrev/{ri_src}" if ri_src
                   else "derived: sales_to_capital")
            q["delta_revenue"] = round(delta_rev, 2)
            return scap, src, q

        return None, None, {"unsupported_derived": name}
