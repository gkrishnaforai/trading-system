"""Bounded LLM headline classification for alert triage.

Interpretation only — the classifier decides headline direction/kind for alert
ranking and display. It cannot set alert materiality above MODERATE, touch the
swing decision, or mutate any state. All failures fall back to the keyword
classifier in catalyst_intelligence.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal

from app.config import settings

logger = logging.getLogger(__name__)

try:
    from litellm import completion
    _LITELLM = True
except ImportError:
    completion = None
    _LITELLM = False


class HeadlineVerdict(BaseModel):
    title: str
    direction: Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"] = "NEUTRAL"
    event_kind: str = "other"  # earnings | analyst | contract | regulatory | macro | filler | other
    material: bool = False     # likely to move the stock over a swing horizon


class HeadlineClassifier:
    def __init__(self, *, model: str = "gpt-4o-mini"):
        self.model = model
        self.enabled = bool(
            _LITELLM and (
                getattr(settings, "openai_api_key", None)
                or getattr(settings, "anthropic_api_key", None)
                or getattr(settings, "litellm_proxy_url", None)
            )
        )

    def classify(self, symbol: str, titles: list[str]) -> Optional[list[HeadlineVerdict]]:
        """Return per-title verdicts, or None when LLM is unavailable/fails."""
        if not self.enabled or not titles:
            return None
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles[:10]))
        prompt = f"""Classify each news headline for {symbol} for a swing trader (days-to-weeks horizon).

For each headline return:
- direction: POSITIVE | NEGATIVE | NEUTRAL | MIXED — likely effect on the stock
- event_kind: earnings | analyst | contract | regulatory | macro | filler | other
  (filler = routine institutional share transactions, 13F disclosures, listicles)
- material: true only if plausibly price-moving over days, not trivia

Rules:
- "X Buys/Sells N Shares of Y" and 13F filings are filler, direction NEUTRAL.
- Do not infer facts beyond the headline text.
- Return JSON: {{"verdicts": [{{"index": <int>, "direction": ..., "event_kind": ..., "material": <bool>}}]}}

Headlines:
{numbered}
"""
        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You classify financial headlines for alert triage. You never make trading decisions. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 600,
                "response_format": {"type": "json_object"},
            }
            api_key = (getattr(settings, "openai_api_key", None)
                       or getattr(settings, "anthropic_api_key", None))
            if api_key:
                kwargs["api_key"] = api_key
            response = completion(**kwargs)
            raw = json.loads(response.choices[0].message.content)
        except Exception as exc:
            logger.warning("headline classification failed for %s: %s", symbol, exc)
            return None

        verdicts = []
        for v in (raw.get("verdicts") or []):
            try:
                idx = int(v.get("index", 0)) - 1
                if not (0 <= idx < len(titles)):
                    continue
                verdicts.append(HeadlineVerdict(
                    title=titles[idx],
                    direction=v.get("direction", "NEUTRAL"),
                    event_kind=str(v.get("event_kind", "other")),
                    material=bool(v.get("material")),
                ))
            except Exception:
                continue
        return verdicts or None
