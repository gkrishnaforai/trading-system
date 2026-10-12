
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.observability.logging import get_logger
from app.services.investment_health_service import investment_health_service
from app.services.notification_service import ChannelType, NotificationMessage, notification_service


logger = get_logger("weekly_health_api")
router = APIRouter(tags=["weekly_health"])


class WeeklyHealthChangesResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WeeklyHealthEmailRequest(BaseModel):
    portfolio_id: str
    as_of_date: str
    recipient_email: str
    lookback_days: int = 14


@router.get("/latest", response_model=WeeklyHealthChangesResponse)
async def get_weekly_health_latest(portfolio_id: str, as_of_date: str, lookback_days: int = 14):
    try:
        latest_rows, prev_rows = investment_health_service.latest_and_previous(
            portfolio_id=portfolio_id,
            as_of_date_str=as_of_date,
            lookback_days=int(lookback_days or 14),
        )
        prev_by_symbol = {str(r.get("symbol") or "").strip().upper(): r for r in (prev_rows or [])}

        out = []
        for r in latest_rows or []:
            sym = str(r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            prev = prev_by_symbol.get(sym) or {}

            cur_score = r.get("overall_score")
            prev_score = prev.get("overall_score")
            delta = None
            try:
                if cur_score is not None and prev_score is not None:
                    delta = float(cur_score) - float(prev_score)
            except Exception:
                delta = None

            out.append(
                {
                    "symbol": sym,
                    "as_of_date": as_of_date,
                    "overall_score": cur_score,
                    "prev_overall_score": prev_score,
                    "delta": delta,
                    "action": r.get("action"),
                    "prev_action": prev.get("action"),
                    "fundamentals_score": r.get("fundamentals_score"),
                    "valuation_score": r.get("valuation_score"),
                    "industry_score": r.get("industry_score"),
                    "reasons": r.get("reasons"),
                    "inputs": r.get("inputs"),
                }
            )

        def _sort_key(x: Dict[str, Any]) -> float:
            try:
                v = x.get("overall_score")
                return float(v) if v is not None else -1.0
            except Exception:
                return -1.0

        out.sort(key=_sort_key, reverse=True)

        return WeeklyHealthChangesResponse(
            success=True,
            data={
                "portfolio_id": portfolio_id,
                "as_of_date": as_of_date,
                "rows": out,
                "count": len(out),
            },
        )
    except Exception as e:
        logger.error(f"weekly_health_latest_failed: {e}")
        return WeeklyHealthChangesResponse(success=False, error=str(e))


@router.get("/changes", response_model=WeeklyHealthChangesResponse)
async def get_weekly_health_changes(portfolio_id: str, as_of_date: str, lookback_days: int = 14):
    try:
        changes = investment_health_service.compute_changes(
            portfolio_id=portfolio_id,
            as_of_date_str=as_of_date,
            lookback_days=int(lookback_days or 14),
        )
        return WeeklyHealthChangesResponse(
            success=True,
            data={
                "portfolio_id": portfolio_id,
                "as_of_date": as_of_date,
                "changes": changes,
            },
        )
    except Exception as e:
        logger.error(f"weekly_health_changes_failed: {e}")
        return WeeklyHealthChangesResponse(success=False, error=str(e))


@router.post("/email", response_model=WeeklyHealthChangesResponse)
async def send_weekly_health_email(req: WeeklyHealthEmailRequest):
    try:
        changes = investment_health_service.compute_changes(
            portfolio_id=req.portfolio_id,
            as_of_date_str=req.as_of_date,
            lookback_days=int(req.lookback_days or 14),
        )

        subject = f"Weekly Investment Health Changes ({req.as_of_date})"

        rows = []
        for c in changes[:50]:
            sym = c.get("symbol")
            action = c.get("action")
            prev_action = c.get("prev_action")
            delta = c.get("delta")
            try:
                delta_s = f"{float(delta):+.1f}" if delta is not None else ""
            except Exception:
                delta_s = ""
            rows.append(f"<tr><td><b>{sym}</b></td><td>{prev_action} → {action}</td><td>{delta_s}</td></tr>")

        html_body = (
            "<h2>Weekly Investment Health Changes</h2>"
            f"<p>As of <b>{req.as_of_date}</b></p>"
            "<table border='1' style='border-collapse:collapse;width:100%'>"
            "<tr><th>Symbol</th><th>Action</th><th>Δ Score</th></tr>"
            + "".join(rows)
            + "</table>"
        )

        text_lines = [
            f"Weekly Investment Health Changes ({req.as_of_date})",
            "",
        ]
        for c in changes[:50]:
            sym = c.get("symbol")
            action = c.get("action")
            prev_action = c.get("prev_action")
            delta = c.get("delta")
            try:
                delta_s = f"{float(delta):+.1f}" if delta is not None else ""
            except Exception:
                delta_s = ""
            text_lines.append(f"- {sym}: {prev_action} -> {action} {delta_s}")
        text_body = "\n".join(text_lines).strip()

        msg = NotificationMessage(
            recipient=req.recipient_email,
            subject=subject,
            body=text_body,
            template_data={"html_override": html_body, "text_override": text_body},
            urgency_level="medium",
            channel_type=ChannelType.EMAIL,
        )

        channel = notification_service.channels.get(ChannelType.EMAIL)
        if channel is None:
            raise ValueError("email channel not configured")

        # EmailChannel renders its own template; we pass our content via template_data/body.
        await channel.send(msg)

        return WeeklyHealthChangesResponse(
            success=True,
            data={"sent": True, "recipient": req.recipient_email, "as_of_date": req.as_of_date, "changes_count": len(changes)},
        )
    except Exception as e:
        logger.error(f"weekly_health_email_failed: {e}")
        return WeeklyHealthChangesResponse(success=False, error=str(e))
