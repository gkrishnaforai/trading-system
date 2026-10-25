"""pytest entry for the signal contract evals — every lint/scenario/
invariant check becomes a test case so CI fails per-contract, not as
one blob. Run: `pytest test_signal_evals.py -v` or the standalone
CLI `python -m app.signals.signal_evals`."""
import pytest

from app.signals import signal_evals

_RESULTS = signal_evals.run()


@pytest.mark.parametrize("check", _RESULTS["checks"],
                         ids=[c["id"] for c in _RESULTS["checks"]])
def test_signal_contract(check):
    assert check["ok"], f"{check['id']}: {check['detail']}"
