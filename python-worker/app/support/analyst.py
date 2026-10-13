"""Research agent — bounded root-cause analysis for escalated incidents.

Deterministic first: pattern-match the error evidence to a known cause
catalog. When an LLM key is configured, escalate to a bounded
interpretation pass (logs in → structured diagnosis out; the agent can
propose, never act). Auto-patching production code stays behind a
human approval gate by design — the output is a plan, not a commit.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.database import db
from app.observability.logging import get_logger
from .log_buffer import tail, signature_patterns

logger = get_logger("custodian_analyst")

# error-pattern → (root cause, fix steps, confidence, fix_type)
#   fix_type: infra = ops/config fix, code = needs a dev ticket,
#             enhancement = capability gap worth a ticket
_RULES = [
    (r"AmbiguousParameter|inconsistent types deduced",
     "psycopg can't infer the type of a parameter reused in CASE/literal "
     "context (varchar column + reused :param).",
     "Cast the reused parameter explicitly, e.g. CAST(:status AS text), "
     "in the failing query — same fix applied earlier in "
     "notification_service / universal_alert_service_enhanced.",
     "high", "code"),
    (r"401|unauthorized|invalid api key|forbidden",
     "Provider credential rejected — expired/typo'd key or wrong env "
     "name for that code path.",
     "Compare the env key the code reads vs what's configured; re-paste "
     "into Coolify without quotes/whitespace; restart the worker.",
     "high", "infra"),
    (r"No module named|ModuleNotFoundError",
     "Missing Python dependency in the worker image.",
     "Add the package to python-worker requirements and rebuild — or "
     "the import is from an optional provider that should be guarded.",
     "high", "code"),
    (r"connection refused|could not connect|Name or service not known",
     "DB/service unreachable — container down, wrong host:port, or "
     "PgBouncer pool wedged.",
     "docker ps the db containers; check DATABASE_URL host/port; "
     "restart pgbouncer if pool is saturated.",
     "high", "infra"),
    (r"Killed|OOM|MemoryError|exit code 137",
     "Process OOM-killed — job exceeded container memory limit.",
     "Raise the service memory limit in compose or reduce the job's "
     "batch size; check for an unbounded query/buffer.",
     "high", "infra"),
    (r"timeout|timed out|ReadTimeout",
     "Upstream call timing out — provider slow/down or query too heavy.",
     "Check provider status; if the query is the timeout, add an index "
     "or narrow the window; the custodian retry may self-heal if "
     "transient.",
     "medium", "infra"),
    (r"migration.*fail|relation .* does not exist|column .* does not exist",
     "Schema drift — code expects a column/table migrations haven't "
     "applied (or a migration failed earlier).",
     "Check job_runs/logs for the failed migration statement; run the "
     "migration manually, then re-run the job.",
     "high", "code"),
    (r"semicolon|unterminated|syntax error.*sql",
     "Migration splitter broke on a semicolon inside a SQL comment — "
     "the Go migration runner splits naively on ';'.",
     "Remove the semicolon from the comment in the migration file and "
     "redeploy.",
     "high", "code"),
    (r"duplicate key|violates unique constraint",
     "Data conflict on insert — upstream re-send or a dedupe rule "
     "changed.",
     "Inspect the conflicting key; if benign, make the insert "
     "idempotent (ON CONFLICT); if systemic, fix the upstream source.",
     "medium", "code"),
    (r"key.*not configured|no api key|missing.*key|not provided",
     "Required API key/env unset for that code path.",
     "Set the key in Coolify env for the worker service; some plugins "
     "read their own config dict — check the code path's env name.",
     "high", "infra"),
]


def _rule_analysis(sig: str, lines: List[str]) -> Optional[Dict[str, Any]]:
    evidence = "\n".join(lines)
    for rx, cause, fix, conf, fix_type in _RULES:
        if re.search(rx, evidence, re.I):
            hits = [l for l in lines if re.search(rx, l, re.I)]
            return {"source": "rules", "root_cause": cause,
                    "proposed_fix": fix, "confidence": conf,
                    "fix_type": fix_type,
                    "evidence": hits[:6]}
    return None


def _llm_analysis(sig: str, incident: dict, lines: List[str],
                  code: Optional[Dict[str, Any]] = None
                  ) -> Optional[Dict[str, Any]]:
    try:
        from litellm import completion
    except ImportError:
        return None
    from app.config import settings
    if not (settings.openai_api_key or settings.anthropic_api_key
            or getattr(settings, "litellm_proxy_url", None)):
        return None
    prompt = f"""You are a reliability engineer diagnosing a production
incident in a trading-data pipeline (FastAPI worker, Postgres, cron jobs,
market-data providers).

Incident signature: {sig}
Diagnosis (deterministic): {incident.get('diagnosis')}
Remediation tried: {incident.get('remediation')} ({incident.get('attempts')} attempts)
Sensor detail: {json.dumps(incident.get('detail') or {})[:1200]}

Recent related log lines:
{chr(10).join(lines[:15]) or '(none captured)'}

Handler source ({code['file'] + ' :: ' + code['name'] if code else 'not resolved'}):
{code['source'][:2400] if code else ''}

Classify the fix: "infra" = config/keys/restart/ops action a human can
do now; "code" = needs a developer ticket (the fix is a code change —
never auto-apply, propose as a ticket); "enhancement" = capability gap
worth a feature ticket.

Return ONLY compact JSON:
{{"root_cause": "...", "confidence": "high|medium|low",
  "fix_type": "infra|code|enhancement",
  "proposed_fix": "numbered steps",
  "patch": "unified diff or code snippet if fix_type=code, else null",
  "ticket": {{"title": "one-line JIRA-style title",
             "description": "problem + evidence + acceptance criteria"}},
  "verify": "how to confirm the fix worked"}}"""
    try:
        resp = completion(
            model=getattr(settings, "llm_model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=600)
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        out = json.loads(m.group(0))
        out["source"] = "llm"
        out["evidence"] = lines[:6]
        return out
    except Exception as e:
        logger.warning(f"llm analysis failed for {sig}: {e}")
        return None


def _code_context(signature: str) -> Optional[Dict[str, Any]]:
    """Resolve the signature to source — the dev-agent half of the
    analyst. job:X → the registered handler; stale:X → its refresh
    job; scan:alerts → the scan entrypoint."""
    import inspect
    job_map = {"stale:momentum": "momentum",
               "stale:fundamental": "fund-flags",
               "stale:flywheel": "flywheel"}
    name = None
    fn = None
    if signature.startswith("job:"):
        name = signature.split(":")[1]
    elif signature in job_map:
        name = job_map[signature]
    if name:
        try:
            from app.api.board_api import JOBS
            spec = JOBS.get(name)
            fn = spec[1] if spec else None
        except Exception:
            fn = None
    elif signature.startswith("scan:"):
        try:
            from app.alerts.service import run_scan_job
            fn = run_scan_job
        except Exception:
            fn = None
    if not fn:
        return None
    try:
        return {"file": inspect.getsourcefile(fn),
                "name": getattr(fn, "__name__", str(fn)),
                "source": inspect.getsource(fn)[:3000]}
    except (TypeError, OSError):
        return None


def analyze(signature: str) -> Dict[str, Any]:
    """Full analysis: incident row + log tail + handler source →
    rules → LLM fallback."""
    rows = db.execute_query(
        "SELECT * FROM custodian_incidents WHERE signature=:s",
        {"s": signature})
    if not rows:
        return {"error": "incident not found", "signature": signature}
    inc = rows[0]
    lines = tail(signature_patterns(signature), n=15)
    code = _code_context(signature)
    base = {"signature": signature, "log_tail": lines,
            "detail": inc.get("detail"),
            "status": inc.get("status"),
            "attempts": inc.get("attempts"),
            "code_context": code}
    out = _rule_analysis(signature, lines) \
        or _llm_analysis(signature, inc, lines, code) \
        or {"source": "none",
            "root_cause": "No matching error pattern and LLM analysis "
                          "unavailable (no OPENAI_API_KEY / "
                          "ANTHROPIC_API_KEY configured).",
            "proposed_fix": "Read the captured log tail above and the "
                            "incident's manual_steps runbook.",
            "confidence": "low", "fix_type": "infra",
            "evidence": lines[:6]}
    # ticket drafts are for code/enhancement work — never auto-filed
    if out.get("fix_type") in ("code", "enhancement") \
            and not out.get("ticket"):
        cc = code or {}
        out["ticket"] = {
            "title": f"[{signature}] {out.get('root_cause', '')[:80]}",
            "description": (
                f"Incident: {signature}\n\n"
                f"Root cause: {out.get('root_cause')}\n\n"
                f"Proposed fix: {out.get('proposed_fix')}\n\n"
                f"Handler: {cc.get('file', '—')} :: {cc.get('name', '—')}\n\n"
                "Evidence:\n" + "\n".join(lines[:8]))}
    base.update(out)
    # journal the analysis on the incident for the page + postmortems
    try:
        db.execute_update(
            "UPDATE custodian_incidents SET detail = detail || "
            "CAST(:a AS jsonb) WHERE signature=:s",
            {"s": signature, "a": json.dumps(
                {"analysis": {k: out.get(k) for k in
                              ("source", "root_cause", "confidence")}})})
    except Exception:
        pass
    return base
