from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.database import db
from app.fair_value_v2.feature_resolver import FeatureResolver
from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore
from app.fair_value_v2.methods.registry import MethodRegistry
from app.fair_value_v2.regime_router import RegimeRouter
from app.fair_value_v2.router import CategoryRouter


@dataclass(frozen=True)
class CoverageRow:
    symbol: str
    category: str
    regime: str
    method_keys: List[str]
    missing_features: Dict[str, List[str]]
    classification_missing: bool


def generate_coverage_report(
    *,
    symbols: List[str],
    as_of_ts: Optional[datetime] = None,
) -> List[CoverageRow]:
    ts = as_of_ts or datetime.now(timezone.utc)

    store = PostgresPointInTimeFeatureStore()
    resolver = FeatureResolver(feature_store=store, features_yaml_path="app/fair_value_v2/methods/features.yaml")

    methods_dir = "app/fair_value_v2/methods"
    category_router = CategoryRouter(
        category_router_path=f"{methods_dir}/category_router.yaml",
        category_methods_path=f"{methods_dir}/category_methods.yaml",
    )
    regime_router = RegimeRouter(
        regime_router_path=f"{methods_dir}/regime_router.yaml",
        regime_methods_path=f"{methods_dir}/regime_methods.yaml",
    )
    registry = MethodRegistry.load_from_dir(f"{methods_dir}/definitions")

    rows: List[CoverageRow] = []

    # Scalars used for regime selection (must match runner’s list).
    regime_scalars = [
        "eps_ttm",
        "eps_forward",
        "market_cap",
        "revenue_growth_ttm",
        "forward_growth_pct_1y",
        "operating_margin_ttm",
    ]

    for sym in symbols:
        sector, industry = store.get_company_classification(sym)
        classification_missing = not (sector or "") and not (industry or "")
        company_name, description = store.get_company_profile_text(sym)

        override_category, _ = store.get_category_override(sym)
        if override_category:
            category = str(override_category)
        else:
            category, _ = category_router.route(symbol=sym, sector=sector, industry=industry, company_name=company_name, description=description)

        scalars, _, _ = resolver.resolve_scalars(sym, ts, regime_scalars)
        regime_name, method_weights = regime_router.route(category=category, sector=sector, industry=industry, scalars=scalars)
        regime = f"{category}:{regime_name}"

        missing_by_method: Dict[str, List[str]] = {}
        method_keys: List[str] = []

        for mw in method_weights:
            method_keys.append(mw.method_key)
            try:
                mdef = registry.get(mw.method_key)
            except Exception:
                missing_by_method[mw.method_key] = ["method_definition_missing"]
                continue

            required = list((mdef.requires or {}).get("scalars") or [])
            if not required:
                continue
            f, _, _ = resolver.resolve_scalars(sym, ts, required)
            missing = [k for k in required if f.get(k) is None]

            if missing:
                missing_by_method[mw.method_key] = missing

        rows.append(
            CoverageRow(
                symbol=sym,
                category=category,
                regime=regime,
                method_keys=method_keys,
                missing_features=missing_by_method,
                classification_missing=classification_missing,
            )
        )

    return rows


def _fetch_recent_symbols(limit: int = 200) -> List[str]:
    with db.get_session() as s:
        rows = s.execute(
            text(
                """
                SELECT stock_symbol
                FROM stock_insights_snapshots
                GROUP BY stock_symbol
                ORDER BY MAX(generated_at) DESC
                LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        ).fetchall()
    return [r[0] for r in rows if r and r[0]]


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Fair Value V2 coverage report")
    p.add_argument("--symbols", type=str, default="", help="Comma-separated symbols")
    p.add_argument("--limit", type=int, default=200, help="If --symbols not provided, scan recent symbols")
    p.add_argument(
        "--show-ok",
        action="store_true",
        help="Print a line for symbols with no missing required features (default prints only missing)",
    )
    p.add_argument(
        "--show-methods",
        action="store_true",
        help="Include method list in per-symbol output",
    )
    args = p.parse_args()

    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = _fetch_recent_symbols(limit=args.limit)

    rep = generate_coverage_report(symbols=symbols)

    by_category: Dict[str, List[CoverageRow]] = defaultdict(list)
    for r in rep:
        by_category[r.category].append(r)

    for cat in sorted(by_category.keys()):
        print(f"\n== {cat} ==")
        for r in by_category[cat]:
            missing_any = bool(r.missing_features)
            if not missing_any and not args.show_ok:
                continue

            methods_part = f"  methods={r.method_keys}" if args.show_methods else ""
            status_part = "MISSING" if missing_any else "OK"
            cls_part = "  CLASSIFICATION_MISSING" if r.classification_missing else ""
            print(f"{r.symbol}  {r.regime}  {status_part}{cls_part}{methods_part}")
            if missing_any:
                for mk, miss in r.missing_features.items():
                    print(f"  - {mk}: missing {miss}")


if __name__ == "__main__":
    main()
