"""Skeptical review — the challenge step before any report ships.

Bounded LLM answering a FIXED question set against the journaled
evidence pack only. It produces findings, never scores — the
grounding contract is the same as the earnings narrative: every
material number must trace to the evidence or the finding is
dropped. 'No material weakness found' is a valid output only when
the evidence genuinely supports it — manufacturing doubt is as bad
as ignoring it.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_QUESTIONS = [
    "What evidence would disprove the thesis?",
    "Is AI actually driving growth — or acquisitions, pricing, "
    "market recovery?",
    "Defensible advantage or rented third-party capability?",
    "Can a larger competitor reproduce the product?",
    "Are customers renewing/expanding with measurable returns?",
    "Is dilution eroding per-share value?",
    "Do adjusted results mask weak cash economics?",
    "Is valuation already pricing the optimistic case?",
    "Strongest bear argument?",
    "Critical missing or contradictory data?",
]


def run(sym: str, evidence: dict) -> dict:
    """evidence = the journaled pack (scores ctx, quarters, products,
    commitments, thesis). Returns {findings: [{question, finding,
    severity, basis}], dropped: n} — advisory only."""
    from app.signals.earnings_watch import _grounded_narrative
    ev_text = json.dumps(evidence, default=str)[:12000]
    try:
        from litellm import completion
        from app.config import settings
        mdl = getattr(settings, "litellm_model", None) or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.1, max_tokens=1200, timeout=60,
            messages=[
                {"role": "system", "content":
                 "You are the skeptical reviewer on an equity "
                 "research team. Answer the fixed question set against "
                 "the supplied evidence ONLY — never invent figures; "
                 "every number must appear in the evidence. STRICT "
                 "JSON: {\"findings\": [{\"question\": one of the "
                 "listed questions verbatim, \"finding\": str, "
                 "\"severity\": \"material\"|\"minor\"|\"none\"}]}. "
                 "Only include findings that are REAL — severity "
                 "'none' means the question is answered cleanly; "
                 "do not manufacture doubt. Max 6 findings."},
                {"role": "user", "content":
                 f"Symbol: {sym}\nQuestions: "
                 f"{json.dumps(_QUESTIONS)}\nEvidence:\n{ev_text}"}])
        raw = json.loads(resp.choices[0].message.content or "{}")
        findings, dropped = [], 0
        for f in (raw.get("findings") or [])[:6]:
            txt = str(f.get("finding") or "")
            if not txt:
                continue
            if not _grounded_narrative(txt, ev_text):
                dropped += 1
                continue
            findings.append({
                "question": str(f.get("question") or "")[:160],
                "finding": txt[:400],
                "severity": f.get("severity")
                if f.get("severity") in ("material", "minor", "none")
                else "minor"})
        return {"findings": findings, "dropped": dropped}
    except Exception as exc:
        logger.debug("challenge %s: %s", sym, exc)
        return {"findings": [], "dropped": 0,
                "error": str(exc)[:120]}
