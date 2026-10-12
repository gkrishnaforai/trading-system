from typing import Any, Dict

from app.observability.logging import get_logger
from app.services.macro_engine import MacroOrchestrator


logger = get_logger("macro_daily_job")


async def run_macro_daily_job(job_config: Dict[str, Any], execution: Any) -> Dict[str, Any]:
    """JobScheduler handler for daily macro recomputation."""
    try:
        orchestrator = MacroOrchestrator()
        res = orchestrator.run_daily()
        logger.info(
            f"Macro daily job result: ok={res.ok} snapshot_written={res.snapshot_written} updated_series={len(res.updated_series)}"
        )
        return {
            "records_processed": len(res.updated_series),
            "records_failed": 0,
            "alerts_generated": 0,
            "snapshot_written": res.snapshot_written,
        }
    except Exception as e:
        logger.error(f"Macro daily job failed: {e}")
        return {"records_processed": 0, "records_failed": 1, "alerts_generated": 0, "error": str(e)}
