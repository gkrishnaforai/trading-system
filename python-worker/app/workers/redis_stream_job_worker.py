import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import redis

from app.config import settings
from app.database import init_database, db
from app.observability.context import set_ingestion_run_id
from app.observability import audit
from app.observability.logging import get_logger
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType
from app.services.stock_grades.service import get_stock_grades_service


logger = get_logger("redis_stream_job_worker")


@dataclass
class DataLoadJobPayload:
    run_id: str
    portfolio_id: Optional[str]
    symbol: str
    data_types: List[str]
    force: bool
    attempt: int = 1
    max_attempts: int = 3


@dataclass
class PortfolioAnalysisJobPayload:
    run_id: str
    portfolio_id: Optional[str]
    symbol: str
    asset_type: str
    target_date: str
    attempt: int = 1
    max_attempts: int = 3


class RedisStreamWorker:
    def __init__(
        self,
        redis_url: str,
        stream_key: str = "ts:jobs",
        group: str = "python-workers",
        consumer: Optional[str] = None,
        block_ms: int = 5000,
        max_retries: int = 3,
        idle_retry_seconds: int = 2,
    ):
        self.redis_url = redis_url
        self.stream_key = stream_key
        self.group = group
        self.consumer = consumer or f"worker-{uuid.uuid4()}"
        self.block_ms = block_ms
        self.max_retries = max_retries
        self.idle_retry_seconds = idle_retry_seconds

        self.remaining_pref = "ts:run:remaining:"
        self.has_fail_pref = "ts:run:has_failures:"

        self.dlq_stream_key = os.getenv("JOB_DLQ_STREAM_KEY", "ts:jobs:dlq")

        self.stream_maxlen = int(os.getenv("JOB_STREAM_MAXLEN", "10000"))
        self.dlq_maxlen = int(os.getenv("JOB_DLQ_MAXLEN", "2000"))

        self.pending_min_idle_ms = int(os.getenv("JOB_PENDING_MIN_IDLE_MS", "60000"))
        self.pending_claim_batch = int(os.getenv("JOB_PENDING_CLAIM_BATCH", "10"))
        self.pending_claim_interval_seconds = int(os.getenv("JOB_PENDING_CLAIM_INTERVAL_SECONDS", "5"))
        self._last_claim_at = 0.0
        self._pending_claim_start_id = "0-0"

        self.fmp_rate_limit_calls = int(os.getenv("JOB_RATE_LIMIT_FMP_CALLS", "0"))
        self.fmp_rate_limit_window_seconds = float(os.getenv("JOB_RATE_LIMIT_FMP_WINDOW_SECONDS", "0"))

        self.job_done_ttl_seconds = int(os.getenv("JOB_DONE_TTL_SECONDS", str(7 * 24 * 3600)))
        self.job_lock_ttl_seconds = int(os.getenv("JOB_LOCK_TTL_SECONDS", str(30 * 60)))
        self.health_key = os.getenv("JOB_WORKER_HEALTH_KEY", "ts:jobs:worker:health")
        self._health_last_write_at = 0.0
        self.health_write_interval_seconds = int(os.getenv("JOB_WORKER_HEALTH_WRITE_INTERVAL_SECONDS", "10"))
        self._metric_reclaimed = 0
        self._metric_errors = 0
        self._metric_dlq = 0
        self._metric_claim_errors = 0
        self._last_claim_error_log_at = 0.0
        self.claim_error_log_interval_seconds = int(os.getenv("JOB_CLAIM_ERROR_LOG_INTERVAL_SECONDS", "30"))

        self._loop_error_count = 0
        self._last_loop_error_log_at = 0.0
        self.loop_error_log_interval_seconds = int(os.getenv("JOB_LOOP_ERROR_LOG_INTERVAL_SECONDS", "15"))

        self.r = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        self.refresh_manager = DataRefreshManager()

    def _recreate_redis_client(self):
        self.r = redis.Redis.from_url(
            self.redis_url,
            decode_responses=True,
            retry_on_timeout=True,
            health_check_interval=30,
        )

    def _wait_for_redis(self):
        backoff_s = 1.0
        while True:
            try:
                if self.r.ping():
                    return
            except Exception as e:
                now = time.time()
                if now - self._last_loop_error_log_at >= self.loop_error_log_interval_seconds:
                    self._last_loop_error_log_at = now
                    logger.warning(f"Redis not ready yet (url={self.redis_url}): {e}")
                try:
                    self._recreate_redis_client()
                except Exception:
                    pass

            time.sleep(backoff_s)
            backoff_s = min(30.0, backoff_s * 1.5)

    def ensure_group(self):
        try:
            self.r.xgroup_create(name=self.stream_key, groupname=self.group, id="0-0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                return
            raise

    def _xadd_trim(self, stream: str, fields: Dict[str, Any], maxlen: int):
        if maxlen > 0:
            return self.r.xadd(stream, fields, maxlen=maxlen, approximate=True)
        return self.r.xadd(stream, fields)

    def _rate_limit(self, provider: str):
        if provider != "fmp":
            return
        if self.fmp_rate_limit_calls <= 0 or self.fmp_rate_limit_window_seconds <= 0:
            return

        window = int(self.fmp_rate_limit_window_seconds)
        now = int(time.time())
        window_start = now - (now % window)
        key = f"ts:rl:{provider}:{window_start}"

        try:
            count = self.r.incr(key)
            if count == 1:
                self.r.expire(key, window)
            if count > self.fmp_rate_limit_calls:
                ttl = self.r.ttl(key)
                sleep_s = max(1.0, float(ttl) if ttl and ttl > 0 else float(window))
                time.sleep(sleep_s)
        except Exception:
            # Fail open: rate limiting should not break ingestion.
            return

    def _is_cancel_requested(self, run_id: str) -> bool:
        try:
            rows = db.execute_query(
                """
                SELECT COALESCE(metadata->>'cancel_requested_at','') AS canceled
                FROM data_ingestion_runs
                WHERE run_id = CAST(:run_id AS uuid)
                LIMIT 1
                """,
                {"run_id": run_id},
            )
            if not rows:
                return False
            return bool((rows[0].get("canceled") or "").strip())
        except Exception:
            return False

    def _parse_payload(self, raw: str) -> DataLoadJobPayload:
        d = json.loads(raw)
        return DataLoadJobPayload(
            run_id=d["run_id"],
            portfolio_id=d.get("portfolio_id"),
            symbol=d["symbol"],
            data_types=list(d.get("data_types") or []),
            force=bool(d.get("force")),
            attempt=int(d.get("attempt") or 1),
            max_attempts=int(d.get("max_attempts") or 3),
        )

    def _parse_analysis_payload(self, raw: str) -> PortfolioAnalysisJobPayload:
        d = json.loads(raw)
        return PortfolioAnalysisJobPayload(
            run_id=d["run_id"],
            portfolio_id=d.get("portfolio_id"),
            symbol=d["symbol"],
            asset_type=str(d.get("asset_type") or "stock"),
            target_date=str(d.get("target_date") or ""),
            attempt=int(d.get("attempt") or 1),
            max_attempts=int(d.get("max_attempts") or 3),
        )

    def _map_data_types(self, data_types: List[str]) -> List[DataType]:
        mapping = {dt.value: dt for dt in DataType}
        mapping["market_news"] = DataType.NEWS
        out: List[DataType] = []
        for dt in data_types:
            if dt in mapping:
                out.append(mapping[dt])
        return out

    def _is_grades_type(self, dt: str) -> bool:
        return dt in {"stock_grades", "analyst_ratings", "consensus_data", "price_targets"}

    def _run_refresh(self, payload: DataLoadJobPayload) -> Dict[str, Any]:
        sym = payload.symbol.strip().upper()
        dt = list(payload.data_types or [])

        main_types = [x for x in dt if not self._is_grades_type(x)]
        grades_requested = any(self._is_grades_type(x) for x in dt)

        results: Dict[str, Any] = {"symbol": sym, "data_types": dt, "main": None, "grades": None}

        if main_types:
            self._rate_limit("fmp")
            mapped = self._map_data_types(main_types)
            if mapped:
                refresh_mode_env = (os.getenv("JOB_REFRESH_MODE") or "on_demand").strip().lower()
                refresh_mode = RefreshMode.ON_DEMAND if refresh_mode_env == "on_demand" else RefreshMode.PERIODIC
                r = self.refresh_manager.refresh_data(
                    symbol=sym,
                    data_types=mapped,
                    mode=refresh_mode,
                    force=payload.force,
                )
                results["main"] = {
                    "total_requested": r.total_requested,
                    "total_successful": r.total_successful,
                    "total_failed": r.total_failed,
                    "total_skipped": r.total_skipped,
                }

        if grades_requested:
            self._rate_limit("fmp")
            grades_service = get_stock_grades_service()
            # service is async; run via event loop-free sync call using asyncio
            import asyncio

            async def _do():
                from app.services.data_sources.base import DataSourceType

                return await grades_service.refresh_symbol_data(
                    sym,
                    DataSourceType.FMP,
                    include_consensus=True,
                )

            results["grades"] = asyncio.run(_do())

        return results

    def _run_portfolio_analysis(self, payload: PortfolioAnalysisJobPayload) -> Dict[str, Any]:
        sym = payload.symbol.strip().upper()
        asset_type = (payload.asset_type or "stock").strip() or "stock"
        target_date = (payload.target_date or "").strip()
        if not target_date:
            target_date = time.strftime("%Y-%m-%d", time.gmtime())

        # Generate universal signal (python-worker internal call)
        import asyncio
        from app.api.universal_backtest_api import SignalRequest, get_universal_signal

        async def _do():
            req = SignalRequest(symbol=sym, date=target_date, asset_type=asset_type)
            return await get_universal_signal(req)

        resp = asyncio.run(_do())
        if not isinstance(resp, dict) or not resp.get("success"):
            raise RuntimeError(f"universal_signal_failed: {resp}")

        data = resp.get("data") or {}
        signal_block = data.get("signal") or {}
        signal_value = str(signal_block.get("signal") or "HOLD").strip().upper() or "HOLD"
        confidence = float(signal_block.get("confidence") or 0.0)
        reasoning = list(signal_block.get("reasoning") or [])
        metadata = dict(signal_block.get("metadata") or {})
        metadata["asset_type"] = asset_type
        metadata["target_date"] = target_date

        # Persist signal to stock_signals so operator/admin tooling can inspect recent signals
        from app.signal_engines.base import SignalResult, SignalType, EngineTier
        from app.repositories.signal_repository import SignalRepository

        try:
            st = SignalType(signal_value)
        except Exception:
            st = SignalType.HOLD

        result = SignalResult(
            engine_name="universal",
            engine_version="1.0.0",
            engine_tier=EngineTier.BASIC,
            symbol=sym,
            signal=st,
            confidence=confidence,
            position_size_pct=0.0,
            timeframe="swing",
            entry_price_range=None,
            stop_loss=None,
            take_profit=[],
            reasoning=reasoning,
            metadata=metadata,
        )
        SignalRepository.save_signal_result(result)

        # Emit universal event for downstream alerts/notifications (same pipeline as ratings alerts)
        try:
            from datetime import datetime
            from app.services.universal_alert_service_enhanced import UniversalEvent, EntityType
            from app.services.universal_alert_service_enhanced import universal_alert_service

            source_id = f"signal_generated:{sym}:{signal_value}:{target_date}:universal"
            event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"portfolio_analysis:{payload.run_id}:{source_id}"))
            event = UniversalEvent(
                event_id=event_id,
                event_type="signal_generated",
                entity_type=EntityType.STOCK,
                entity_id=sym,
                event_data={
                    "symbol": sym,
                    "signal": signal_value,
                    "confidence": confidence,
                    "engine": "universal",
                    "asset_type": asset_type,
                    "target_date": target_date,
                    "run_id": payload.run_id,
                },
                previous_data=None,
                event_timestamp=datetime.utcnow(),
                data_source="portfolio_analysis",
                source_id=source_id,
                confidence_score=min(1.0, max(0.0, confidence)),
                correlation_id=payload.run_id,
                tags=["portfolio_analysis"],
            )
            import asyncio

            async def _emit():
                return await universal_alert_service.event_repo.save_event(event)

            asyncio.run(_emit())
        except Exception:
            pass

        return {
            "symbol": sym,
            "asset_type": asset_type,
            "target_date": target_date,
            "signal": signal_value,
            "confidence": confidence,
        }

    def _maybe_reclaim_pending(self):
        now = time.time()
        if now - self._last_claim_at < self.pending_claim_interval_seconds:
            return
        self._last_claim_at = now

        try:
            # XAUTOCLAIM returns (next_start_id, [(msg_id, fields), ...], deleted)
            res = self.r.xautoclaim(
                name=self.stream_key,
                groupname=self.group,
                consumername=self.consumer,
                min_idle_time=self.pending_min_idle_ms,
                start_id=self._pending_claim_start_id,
                count=self.pending_claim_batch,
            )
        except Exception as e:
            self._metric_claim_errors += 1
            now2 = time.time()
            if now2-self._last_claim_error_log_at >= self.claim_error_log_interval_seconds:
                self._last_claim_error_log_at = now2
                logger.warning(f"XAUTOCLAIM failed (stream={self.stream_key} group={self.group} consumer={self.consumer}): {e}")
            return

        if not res or len(res) < 2:
            return

        try:
            next_start = res[0]
            if next_start:
                self._pending_claim_start_id = next_start
        except Exception:
            pass

        messages = res[1] or []
        for msg_id, fields in messages:
            self._metric_reclaimed += 1
            self._process_message(msg_id, fields, reclaimed=True)

        if messages:
            logger.info(f"Reclaimed {len(messages)} pending message(s) (stream={self.stream_key} group={self.group} consumer={self.consumer})")
            self._maybe_write_health()

    def _job_done_key(self, job_id: str) -> str:
        return f"ts:job:done:{job_id}"

    def _job_lock_key(self, job_id: str) -> str:
        return f"ts:job:lock:{job_id}"

    def _job_finalized_key(self, job_id: str) -> str:
        return f"ts:job:finalized:{job_id}"

    def _try_acquire_job_lock(self, job_id: str) -> bool:
        try:
            return bool(self.r.set(self._job_lock_key(job_id), self.consumer, nx=True, ex=self.job_lock_ttl_seconds))
        except Exception:
            return True

    def _release_job_lock(self, job_id: str):
        try:
            self.r.delete(self._job_lock_key(job_id))
        except Exception:
            return

    def _mark_job_done(self, job_id: str):
        try:
            self.r.set(self._job_done_key(job_id), "1", ex=self.job_done_ttl_seconds)
        except Exception:
            return

    def _is_job_done(self, job_id: str) -> bool:
        try:
            return self.r.get(self._job_done_key(job_id)) == "1"
        except Exception:
            return False

    def _finalize_once(self, run_id: str, job_id: str) -> int:
        key = self._job_finalized_key(job_id)
        try:
            if self.r.set(key, "1", nx=True, ex=24 * 3600):
                remaining = self._decrement_remaining(run_id)
                self._finish_run_if_done(run_id, remaining)
                return remaining
            return -1
        except Exception:
            return -1

    def _maybe_write_health(self):
        now = time.time()
        if now - self._health_last_write_at < self.health_write_interval_seconds:
            return
        self._health_last_write_at = now
        try:
            self.r.hset(
                self.health_key,
                mapping={
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "consumer": self.consumer,
                    "stream": self.stream_key,
                    "group": self.group,
                    "reclaimed": str(self._metric_reclaimed),
                    "errors": str(self._metric_errors),
                    "dlq": str(self._metric_dlq),
                    "claim_errors": str(self._metric_claim_errors),
                },
            )
            self.r.expire(self.health_key, 3600)
        except Exception:
            return

    def _send_to_dlq(self, payload: DataLoadJobPayload, job_id: Optional[str], error: str, msg_id: str):
        self._xadd_trim(
            self.dlq_stream_key,
            {
                "job_id": job_id or "",
                "source_msg_id": msg_id,
                "job_type": "portfolio_data_load",
                "payload": json.dumps(payload.__dict__),
                "error": (error or "")[:500],
                "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            self.dlq_maxlen,
        )

    def _send_analysis_to_dlq(self, payload: PortfolioAnalysisJobPayload, job_id: Optional[str], error: str, msg_id: str):
        self._xadd_trim(
            self.dlq_stream_key,
            {
                "job_id": job_id or "",
                "source_msg_id": msg_id,
                "job_type": "portfolio_analysis",
                "payload": json.dumps(payload.__dict__),
                "error": (error or "")[:500],
                "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            self.dlq_maxlen,
        )

    def _process_message(self, msg_id: str, fields: Dict[str, Any], reclaimed: bool = False):
        job_type = fields.get("job_type")
        raw_payload = fields.get("payload")
        if job_type not in {"portfolio_data_load", "portfolio_analysis"} or not raw_payload:
            self.r.xack(self.stream_key, self.group, msg_id)
            return

        is_analysis = job_type == "portfolio_analysis"
        if is_analysis:
            payload: Any = self._parse_analysis_payload(raw_payload)
        else:
            payload = self._parse_payload(raw_payload)

        run_uuid = uuid.UUID(payload.run_id)
        set_ingestion_run_id(run_uuid)

        job_id = str(fields.get("job_id") or "").strip()
        if job_id:
            if self._is_job_done(job_id):
                self.r.xack(self.stream_key, self.group, msg_id)
                return
            if not self._try_acquire_job_lock(job_id):
                # Another worker is likely processing the same logical job_id.
                # Keeping this entry pending leads to repeated re-delivery (PEL churn).
                # Industry standard behavior: ACK and defer by re-enqueueing.
                try:
                    self.r.xack(self.stream_key, self.group, msg_id)
                except Exception:
                    pass
                try:
                    self._xadd_trim(
                        self.stream_key,
                        {
                            "job_id": job_id,
                            "job_type": job_type,
                            "payload": raw_payload,
                            "enqueued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "deferred_reason": "lock_not_acquired",
                            "deferred_from_msg_id": msg_id,
                        },
                        self.stream_maxlen,
                    )
                except Exception:
                    pass
                return

        if self._is_cancel_requested(payload.run_id):
            audit.log_event(
                level="info",
                provider="worker",
                operation="job_canceled",
                symbol=payload.symbol,
                context={"job_id": fields.get("job_id"), "reclaimed": reclaimed},
            )
            self.r.xack(self.stream_key, self.group, msg_id)
            remaining = self._decrement_remaining(payload.run_id)
            self._finish_run_if_done(payload.run_id, remaining)
            return

        audit.log_event(
            level="info",
            provider="worker",
            operation="job_started",
            symbol=payload.symbol,
            context={
                "job_type": job_type,
                "data_types": getattr(payload, "data_types", None),
                "asset_type": getattr(payload, "asset_type", None),
                "target_date": getattr(payload, "target_date", None),
                "attempt": payload.attempt,
                "job_id": fields.get("job_id"),
                "reclaimed": reclaimed,
            },
        )

        start = time.time()
        try:
            if is_analysis:
                result = self._run_portfolio_analysis(payload)
            else:
                result = self._run_refresh(payload)
            dur_ms = int((time.time() - start) * 1000)
            audit.log_event(
                level="info",
                provider="worker",
                operation="job_finished",
                symbol=payload.symbol,
                duration_ms=dur_ms,
                context=self._to_jsonable({"job_type": job_type, "data_types": getattr(payload, "data_types", None), "job_id": fields.get("job_id"), "reclaimed": reclaimed, "result": result}),
            )
            self.r.xack(self.stream_key, self.group, msg_id)
            if job_id:
                self._mark_job_done(job_id)
                self._release_job_lock(job_id)
                self._finalize_once(payload.run_id, job_id)
            else:
                remaining = self._decrement_remaining(payload.run_id)
                self._finish_run_if_done(payload.run_id, remaining)
            self._maybe_write_health()
        except Exception as e:
            dur_ms = int((time.time() - start) * 1000)
            audit.log_event(
                level="error",
                provider="worker",
                operation="job_failed",
                symbol=payload.symbol,
                duration_ms=dur_ms,
                exception=e,
                context={
                    "job_type": job_type,
                    "data_types": getattr(payload, "data_types", None),
                    "asset_type": getattr(payload, "asset_type", None),
                    "target_date": getattr(payload, "target_date", None),
                    "attempt": payload.attempt,
                    "job_id": fields.get("job_id"),
                    "reclaimed": reclaimed,
                },
            )
            self._metric_errors += 1
            self._set_run_failed(payload.run_id)
            self.r.xack(self.stream_key, self.group, msg_id)

            if job_id:
                self._release_job_lock(job_id)

            # Retry or DLQ
            if payload.attempt >= payload.max_attempts:
                try:
                    if is_analysis:
                        self._send_analysis_to_dlq(payload, fields.get("job_id"), str(e), msg_id)
                    else:
                        self._send_to_dlq(payload, fields.get("job_id"), str(e), msg_id)
                    self._metric_dlq += 1
                except Exception:
                    pass
            else:
                if is_analysis:
                    self._requeue_analysis_with_backoff(payload, job_id or str(uuid.uuid4()), str(e))
                else:
                    self._requeue_with_backoff(payload, job_id or str(uuid.uuid4()), str(e))

            if job_id:
                self._finalize_once(payload.run_id, job_id)
            else:
                remaining = self._decrement_remaining(payload.run_id)
                self._finish_run_if_done(payload.run_id, remaining)
            self._maybe_write_health()

    def _to_jsonable(self, obj: Any) -> Any:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple, set)):
            return [self._to_jsonable(x) for x in obj]
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                try:
                    key = str(k)
                except Exception:
                    key = "<non_string_key>"
                out[key] = self._to_jsonable(v)
            return out
        to_dict = getattr(obj, "to_dict", None)
        if callable(to_dict):
            try:
                return self._to_jsonable(to_dict())
            except Exception:
                pass
        if hasattr(obj, "__dict__"):
            try:
                return self._to_jsonable(vars(obj))
            except Exception:
                pass
        try:
            return str(obj)
        except Exception:
            return "<unserializable>"

    def _decrement_remaining(self, run_id: str) -> int:
        key = self.remaining_pref + run_id
        try:
            n = self.r.decr(key)
            return int(n)
        except Exception:
            return -1

    def _set_run_failed(self, run_id: str):
        try:
            self.r.set(self.has_fail_pref + run_id, 1, ex=24 * 3600)
        except Exception:
            pass

    def _run_has_failures(self, run_id: str) -> bool:
        try:
            v = self.r.get(self.has_fail_pref + run_id)
            return v == "1"
        except Exception:
            return False

    def _finish_run_if_done(self, run_id: str, remaining: int):
        if remaining != 0:
            return
        status = "failed" if self._run_has_failures(run_id) else "success"
        try:
            audit.finish_run(uuid.UUID(run_id), status=status, metadata={"finished_by": "redis_stream_worker"})
        except Exception:
            # Fallback: best-effort direct update
            try:
                db.execute_update(
                    """
                    UPDATE data_ingestion_runs
                    SET finished_at = NOW(), status = :status
                    WHERE run_id = CAST(:run_id AS uuid)
                    """,
                    {"run_id": run_id, "status": status},
                )
            except Exception:
                pass

    def _requeue_with_backoff(self, payload: DataLoadJobPayload, job_id: str, last_error: str):
        if payload.attempt >= payload.max_attempts:
            return
        payload.attempt += 1
        raw = json.dumps(payload.__dict__)
        backoff = min(60, 2 ** (payload.attempt - 1))
        time.sleep(backoff)
        self._xadd_trim(
            self.stream_key,
            {
                "job_id": job_id,
                "job_type": "portfolio_data_load",
                "payload": raw,
                "enqueued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "requeued_from_error": last_error[:500],
            },
            self.stream_maxlen,
        )

    def _requeue_analysis_with_backoff(self, payload: PortfolioAnalysisJobPayload, job_id: str, last_error: str):
        if payload.attempt >= payload.max_attempts:
            return
        payload.attempt += 1
        raw = json.dumps(payload.__dict__)
        backoff = min(60, 2 ** (payload.attempt - 1))
        time.sleep(backoff)
        self._xadd_trim(
            self.stream_key,
            {
                "job_id": job_id,
                "job_type": "portfolio_analysis",
                "payload": raw,
                "enqueued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "requeued_from_error": last_error[:500],
            },
            self.stream_maxlen,
        )

    def run_forever(self):
        logger.info(f"Starting RedisStreamWorker consumer={self.consumer} group={self.group} stream={self.stream_key}")
        self.ensure_group()
        self._wait_for_redis()

        while True:
            try:
                self._maybe_reclaim_pending()
                self._maybe_write_health()
                resp = self.r.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer,
                    streams={self.stream_key: ">"},
                    count=1,
                    block=self.block_ms,
                )
                if not resp:
                    continue

                for _, messages in resp:
                    for msg_id, fields in messages:
                        self._process_message(msg_id, fields, reclaimed=False)

            except Exception as loop_err:
                self._loop_error_count += 1
                now = time.time()
                if now - self._last_loop_error_log_at >= self.loop_error_log_interval_seconds:
                    self._last_loop_error_log_at = now
                    logger.error(f"Worker loop error (count={self._loop_error_count}): {loop_err}")
                # Redis DNS resolution or transient connection failures can happen during container/network restarts.
                # Re-create the redis client to force a fresh DNS lookup and new TCP connection.
                try:
                    msg = str(loop_err)
                    if any(
                        s in msg
                        for s in [
                            "Name or service not known",
                            "Temporary failure in name resolution",
                            "Connection closed by server",
                            "Connection refused",
                            "ConnectionError",
                        ]
                    ):
                        self._recreate_redis_client()
                except Exception:
                    pass
                time.sleep(self.idle_retry_seconds)


def main():
    init_database()

    redis_url = os.getenv("REDIS_URL") or settings.redis_url
    stream_key = os.getenv("JOB_STREAM_KEY", "ts:jobs")
    group = os.getenv("JOB_STREAM_GROUP", "python-workers")
    consumer = os.getenv("JOB_STREAM_CONSUMER")

    w = RedisStreamWorker(redis_url=redis_url, stream_key=stream_key, group=group, consumer=consumer)
    w.run_forever()


if __name__ == "__main__":
    main()
