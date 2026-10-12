"""One reusable explanation layer for every canonical agent result."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

from .models import TradingExplanation

logger = logging.getLogger(__name__)

try:
    from litellm import completion
    LITELLM_AVAILABLE = True
except ImportError:
    completion = None
    LITELLM_AVAILABLE = False


class TradingExplanationService:
    """Explain validated results without changing deterministic decisions."""

    def __init__(self, *, use_llm: bool = True, model: str = "gpt-4o-mini"):
        self.use_llm = use_llm
        self.model = model
        self.enabled = bool(
            use_llm and LITELLM_AVAILABLE and (
                getattr(settings, "openai_api_key", None)
                or getattr(settings, "anthropic_api_key", None)
                or getattr(settings, "litellm_proxy_url", None)
            )
        )

    def explain(self, agent: str, result: dict[str, Any]) -> TradingExplanation:
        fixed_action = self._fixed_action(result)
        fallback = self._fallback(agent, result, fixed_action)
        if not self.enabled:
            return fallback
        try:
            explanation = self._llm_explain(agent, result, fixed_action)
            return self._validate(explanation, fallback, fixed_action, result)
        except Exception as exc:
            logger.warning("Trading explanation fallback for %s: %s", agent, exc)
            return fallback

    def _llm_explain(self, agent: str, result: dict[str, Any], fixed_action: str) -> dict[str, Any]:
        payload = json.dumps(result, default=str)[:30000]
        prompt = f"""Explain this deterministic trading analysis for a human trader.
Analysis component: {agent}
Fixed action from deterministic policy: {fixed_action}

The deterministic trading system is the analytical authority. You are not the
analytical agent and you are not allowed to make, revise, or authorize the
trading decision. You are an explanation layer for a human trader.

Rules:
- Treat the fixed action as architecturally immutable.
- Do not return or generate an action field.
- Distinguish deterministic facts from your interpretation.
- Never infer missing values, probabilities, catalysts, or conclusions.
- Clearly state missing, stale, or unavailable data.
- Do not provide broker instructions or execution commands.
- Return JSON with keys: headline, action_summary, why, changes_since_previous,
  risks, next_confirmation, data_gaps, catalyst_summary, catalyst_direction,
  positive_catalysts, negative_catalysts.
- why, changes_since_previous, risks, next_confirmation, data_gaps,
  positive_catalysts, and negative_catalysts must be arrays of strings where applicable.
- Catalyst direction must be grounded in the deterministic catalyst evidence.

Deterministic result:
{payload}
"""
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a conservative explanation layer for a deterministic trading system. The deterministic system decides; you explain validated facts and uncertainties for a human trader. You are not the analytical agent and must never change or author the fixed action."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        api_key = getattr(settings, "openai_api_key", None) or getattr(settings, "anthropic_api_key", None)
        if api_key:
            kwargs["api_key"] = api_key
        response = completion(**kwargs)
        content = response.choices[0].message.content
        return json.loads(content)

    def _validate(self, raw: dict[str, Any], fallback: TradingExplanation, fixed_action: str, result: dict[str, Any] | None = None) -> TradingExplanation:
        allowed = {"headline", "action_summary", "why", "changes_since_previous", "risks", "next_confirmation", "data_gaps", "catalyst_direction", "catalyst_summary", "positive_catalysts", "negative_catalysts"}
        clean = {key: raw.get(key) for key in allowed if key in raw}
        clean["agent"] = fallback.agent
        clean["symbol"] = fallback.symbol
        clean["action"] = fixed_action
        clean["source"] = "llm_validated"
        clean["model"] = self.model
        explanation = TradingExplanation.model_validate(clean)
        if explanation.action != fixed_action:
            raise ValueError("LLM attempted to change deterministic action")

        # Deterministic catalyst facts override contradictory narrative gaps.
        result = result or {}
        catalyst = result.get("catalyst", {}) if isinstance(result.get("catalyst"), dict) else {}
        has_catalyst = bool(
            catalyst.get("news_count", 0)
            or catalyst.get("recent_earnings_count", 0)
            or catalyst.get("catalyst_type") not in {None, "", "NONE"}
            or catalyst.get("materiality") in {"MODERATE", "HIGH", "EXTREME"}
        )
        if has_catalyst:
            explanation.data_gaps = [
                gap for gap in explanation.data_gaps
                if "no recent" not in gap.lower()
                and "no significant" not in gap.lower()
                and "no catalyst" not in gap.lower()
            ]
            if not explanation.catalyst_direction:
                explanation.catalyst_direction = str(
                    catalyst.get("catalyst_direction", catalyst.get("direction", "UNKNOWN"))
                )
            if not explanation.catalyst_summary:
                explanation.catalyst_summary = (
                    f"{catalyst.get('materiality', 'UNKNOWN')} "
                    f"{catalyst.get('catalyst_type', 'catalyst')} evidence; "
                    f"reaction={catalyst.get('reaction_state', 'UNKNOWN')}"
                )
        return explanation

    @staticmethod
    def _fixed_action(result: dict[str, Any]) -> str:
        if isinstance(result.get("decision"), dict):
            return str(result["decision"].get("action") or "REVIEW").upper()
        if isinstance(result.get("actions"), list):
            return "PORTFOLIO_REVIEW"
        if isinstance(result.get("regime"), dict):
            return "MARKET_CONTEXT"
        return "REVIEW"

    @staticmethod
    def _fallback(agent: str, result: dict[str, Any], action: str) -> TradingExplanation:
        decision = result.get("decision", {}) if isinstance(result.get("decision"), dict) else {}
        opportunity = result.get("opportunity", {}) if isinstance(result.get("opportunity"), dict) else {}
        symbol = opportunity.get("symbol") or result.get("symbol")
        reasons = decision.get("reasons") or result.get("reasons") or []
        vetoes = decision.get("vetoes") or result.get("blocking_reasons") or []
        setup = opportunity.get("setup", {})
        gaps = []
        fundamentals = opportunity.get("fundamentals", {})
        catalyst = opportunity.get("catalyst", {}) if isinstance(opportunity, dict) else {}
        recent_news = [item for item in catalyst.get("recent_news", []) if isinstance(item, dict)]
        positive_headlines = [str(item.get("title")) for item in recent_news if item.get("title") and item.get("headline_direction") == "POSITIVE"]
        negative_headlines = [str(item.get("title")) for item in recent_news if item.get("title") and item.get("headline_direction") == "NEGATIVE"]
        if fundamentals.get("data_quality") in {"partial", "insufficient"}:
            gaps.append("fundamental coverage is incomplete")
        if not result.get("snapshot") and agent == "market_regime":
            gaps.append("market snapshot unavailable")
        if vetoes:
            summary = f"The deterministic policy produced {action} because safety or setup constraints remain."
        else:
            summary = f"The deterministic analysis produced {action}; review the evidence before acting."
        return TradingExplanation(
            agent=agent,
            symbol=symbol,
            action=action,
            headline=f"{action}: {symbol or agent}",
            action_summary=summary,
            why=[str(item) for item in reasons[:8]],
            risks=[str(item) for item in vetoes[:8]],
            next_confirmation=["Re-run after current data and event state change"],
            data_gaps=gaps,
            catalyst_direction=catalyst.get("catalyst_direction", catalyst.get("direction")),
            catalyst_summary=(
                f"{catalyst.get('materiality', 'LOW')} {catalyst.get('catalyst_type', 'NONE')} catalyst; "
                f"reaction={catalyst.get('reaction_state', 'UNKNOWN')}"
                if catalyst else None
            ),
            positive_catalysts=positive_headlines,
            negative_catalysts=negative_headlines,
        )
