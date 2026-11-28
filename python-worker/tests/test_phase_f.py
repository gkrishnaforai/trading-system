"""Phase F — licensed cleanup: transcript_lang EDGAR pin, Finnhub
fallback removal, news-body trim."""
from __future__ import annotations

import pytest

from app.db_storage.repositories import _news_meta
from app.utils import data_mode as M


def test_news_meta_strips_body_keys():
    article = {"title": "Fed holds rates", "url": "https://x",
               "publishedDate": "2026-11-01", "site": "reuters",
               "text": "the full verbatim article body " * 50,
               "content": "more body", "body": "even more",
               "description": "a summary paragraph",
               "sentiment": 0.4, "tickers": ["AAPL"]}
    meta = _news_meta(article)
    assert "text" not in meta and "content" not in meta
    assert "body" not in meta and "description" not in meta
    assert meta["title"] == "Fed holds rates"
    assert meta["tickers"] == ["AAPL"]


def test_fallback_source_has_no_finnhub(monkeypatch):
    """The silent Finnhub substitution is gone — no fallback_source,
    no _use_fallback, no _fetch_finnhub_* methods."""
    from app.data_sources.fallback_source import FallbackDataSource
    fs = FallbackDataSource.__new__(FallbackDataSource)
    # construct without init (avoid client construction)
    fs.primary_source = object()
    assert not hasattr(fs, "fallback_source")
    assert not hasattr(fs, "_use_fallback")
    assert not hasattr(fs, "_fetch_finnhub_quote")


def test_transcript_docs_edgar_pinned_public(monkeypatch):
    """public_only → EDGAR 8-K docs only; the licensed transcript
    path never runs."""
    import app.signals.transcript_lang as T
    monkeypatch.setenv("MP_DATA_MODE", "public_only")
    called = {"fmp": 0}
    monkeypatch.setattr(T, "_fmp_transcript_docs",
                        lambda s, n: called.__setitem__("fmp", 1) or [])
    monkeypatch.setattr(T, "_recent_earnings_docs",
                        lambda s, n: [{"period": "2026Q3",
                                       "text": "x" * 3000}])
    docs = T._docs("NVDA", 2)
    assert called["fmp"] == 0                # licensed path untouched
    assert docs[0]["source"] == "sec_8k"


def test_transcript_docs_full_mode_augments(monkeypatch):
    """full mode → EDGAR pinned AND FMP transcripts augment."""
    import app.signals.transcript_lang as T
    monkeypatch.setenv("MP_DATA_MODE", "full")
    monkeypatch.setattr(T, "_fmp_transcript_docs",
                        lambda s, n: [{"period": "2026Q3",
                                       "text": "t" * 3000,
                                       "source": "fmp_transcript"}])
    monkeypatch.setattr(T, "_recent_earnings_docs",
                        lambda s, n: [{"period": "2026Q2",
                                       "text": "x" * 3000}])
    docs = T._docs("NVDA", 2)
    srcs = {d["source"] for d in docs}
    assert srcs == {"fmp_transcript", "sec_8k"}
