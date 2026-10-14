"""FV v2 unit contract — pct vs decimal must be declared, not assumed.

Catches the silent 100x class: a feature named *_pct_* must be unit
`percent`; methods' growth params must bind to the unit they expect.
"""
import os
import yaml

BASE = os.path.join(os.path.dirname(__file__), "..",
                    "app", "fair_value_v2", "methods")
FEATS = yaml.safe_load(open(os.path.join(BASE, "features.yaml")))
UNITS = FEATS.get("units") or {}
DEFS = os.path.join(BASE, "definitions")


def _features():
    return FEATS.get("features") or {}


def test_every_scalar_feature_declares_unit():
    missing = [k for k in _features() if k not in UNITS]
    assert not missing, f"features without declared unit: {missing}"


def test_percent_features_carry_pct_marker():
    for name, unit in UNITS.items():
        if unit == "percent":
            assert "_pct" in name or name in {
                "tnx_yield", "irx_yield", "yield_curve_spread"}, (
                f"{name} is percent-scaled but has no _pct marker — "
                "a decimal consumer will read it 100x too large")
        if "_pct" in name:
            assert unit == "percent", (
                f"{name} says _pct but declared {unit}")


def test_method_scalar_refs_all_have_units():
    """Every scalar a method may consume must resolve to a declared unit."""
    bad = []
    for fn in os.listdir(DEFS):
        if not fn.endswith(".yaml"):
            continue
        d = yaml.safe_load(open(os.path.join(DEFS, fn)))
        req = (d.get("requires") or {})
        for s in (req.get("scalars") or []) + (req.get("optional_scalars") or []):
            if s not in UNITS:
                bad.append(f"{fn}:{s}")
    assert not bad, f"method scalars without units: {bad}"


def test_growth_unit_consumption_is_consistent():
    """peg_* methods' pe_per_g / peg_target params price percentage
    points — they must consume a percent feature, not the decimal
    forward_growth."""
    for fn in os.listdir(DEFS):
        if not fn.endswith(".yaml"):
            continue
        d = yaml.safe_load(open(os.path.join(DEFS, fn)))
        key = d.get("method_key", "")
        req = (d.get("requires") or {})
        scalars = (req.get("scalars") or []) + (req.get("optional_scalars") or [])
        if key.startswith("peg") and "pe_cap" in (d.get("params") or {}):
            assert "forward_growth_pct_1y" in scalars or \
                "eps_est_start" in scalars, (
                    f"{key}: PEG params need a percent-scale growth input")


def test_table_column_avg_source_shape():
    """The new aggregate source must declare rows + a date as-of."""
    for name, fdef in _features().items():
        for src in (fdef.get("sources") or []):
            if src.get("type") == "table_column_avg":
                assert src.get("rows"), f"{name}: table_column_avg missing rows"
                assert src.get("as_of"), f"{name}: table_column_avg missing as_of"
