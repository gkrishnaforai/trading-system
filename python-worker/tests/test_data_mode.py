"""Phase E — MP_DATA_MODE kill-switch.

The contract: in public_only, every licensed provider call raises
LicensedDataBlocked — role-independent, logged at the gate. Public
sources pass. Mode reads the env per call (no settings staleness).
"""
from __future__ import annotations

import pytest

from app.utils import data_mode as M


@pytest.fixture
def full(monkeypatch):
    monkeypatch.setenv("MP_DATA_MODE", "full")


@pytest.fixture
def pub(monkeypatch):
    monkeypatch.setenv("MP_DATA_MODE", "public_only")


def test_default_is_full(monkeypatch):
    monkeypatch.delenv("MP_DATA_MODE", raising=False)
    assert M.data_mode() == "full"
    assert not M.public_only()


def test_public_only_flag(pub):
    assert M.data_mode() == "public_only"
    assert M.public_only()


def test_guard_blocks_licensed(pub):
    for src in ("fmp", "finnhub", "alphavantage", "yahoo", "massive",
                "unknown_vendor"):
        with pytest.raises(M.LicensedDataBlocked) as ei:
            M.guard_source(src, "test")
        assert ei.value.source == src


def test_guard_passes_public(pub):
    for src in ("sec_edgar", "fred", "bls", "sec"):
        M.guard_source(src, "test")          # no raise


def test_guard_is_noop_in_full_mode(full):
    M.guard_source("fmp", "test")            # no raise in full


def test_status_payload(pub):
    s = M.status()
    assert s["public_only"] is True
    assert "SEC EDGAR" in s["disclaimer"]
    assert "not investment" in s["disclaimer"]


def test_status_payload_full(full):
    s = M.status()
    assert s["public_only"] is False
    assert s["disclaimer"] is None


def test_provider_gates_fire(monkeypatch):
    """The gate is inside each client's request method — reaching it
    raises before any network call is attempted."""
    monkeypatch.setenv("MP_DATA_MODE", "public_only")

    from app.providers.finnhub.client import FinnhubClient
    c = FinnhubClient.__new__(FinnhubClient)
    c.config = type("C", (), {"api_key": "k", "max_retries": 1,
                            "base_url": "x", "timeout": 1})
    c.session = None
    c.rate_limiter = None
    with pytest.raises(M.LicensedDataBlocked):
        c._get("/x")

    from app.providers.alphavantage.client import AlphaVantageClient
    a = AlphaVantageClient.__new__(AlphaVantageClient)
    a.config = type("C", (), {"api_key": "k", "max_retries": 1,
                            "base_url": "x", "timeout": 1})
    a.session = None
    a.rate_limiter = None
    with pytest.raises(M.LicensedDataBlocked):
        a._make_request({})

    from app.providers.massive.client import (
        MassiveClient, MassiveClientConfig)
    with pytest.raises(M.LicensedDataBlocked):
        MassiveClient(MassiveClientConfig(api_key="k"))


def test_fmp_gate_fires(monkeypatch):
    monkeypatch.setenv("MP_DATA_MODE", "public_only")
    from app.providers.financial_modeling_prep.client import (
        EnhancedFMPClient)
    c = EnhancedFMPClient.__new__(EnhancedFMPClient)
    c.config = type("C", (), {"api_key": "k", "max_retries": 1,
                            "base_url": "x", "timeout": 1})
    c.session = None
    c.rate_limiter = type("R", (), {"acquire": lambda s: True})()
    with pytest.raises(M.LicensedDataBlocked):
        c._make_request("/profile")
