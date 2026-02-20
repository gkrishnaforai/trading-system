"""
Ingestion Profiles (DRY orchestration)
Defines reusable ingestion profiles that can be triggered by Go API runs.
Each profile accepts a run_id and emits change events to universal_events.
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.data_management.refresh_manager import DataRefreshManager, RefreshMode
from app.data_management.refresh_strategy import DataType
from app.database import db
from app.observability.event_emitter import EventEmitter

logger = logging.getLogger(__name__)

# Registry of named profiles
INGESTION_PROFILES: Dict[str, "IngestionProfile"] = {}

class IngestionProfile:
    """A reusable ingestion profile that can be triggered with a run_id."""
    def __init__(
        self,
        name: str,
        data_types: List[DataType],
        window_days: int = 7,
        default_symbols: Optional[List[str]] = None,
    ):
        self.name = name
        self.data_types = data_types
        self.window_days = window_days
        self.default_symbols = default_symbols or []
        self.refresh_manager = DataRefreshManager()
        self.event_emitter = EventEmitter()

    def execute(self, run_id: str, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute the profile for given symbols under the provided run_id.
        Emits change events to universal_events.
        Returns a summary dict.
        """
        target_symbols = symbols or self.default_symbols
        if not target_symbols:
            raise ValueError(f"No symbols provided for profile {self.name}")

        logger.info(f"[{run_id}] Executing profile {self.name} for symbols: {target_symbols}")
        start = datetime.utcnow()

        results = []
        for symbol in target_symbols:
            try:
                # Run refresh for this symbol
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=self.data_types,
                    mode=RefreshMode.ON_DEMAND,
                    force=False,
                )
                results.append({"symbol": symbol, "status": result.status.name, "details": result.to_dict()})

                # Emit change events for each data type that changed
                for dt, dt_result in result.data_type_results.items():
                    if dt_result.status == "success":
                        # Detect change vs prior snapshot (simplified: always emit for now)
                        self.event_emitter.emit_change_event(
                            entity_type="stock",
                            entity_id=symbol,
                            event_type=self._event_type_for_data_type(dt),
                            event_data={"data_type": dt.value, "run_id": run_id},
                            previous_data=None,  # TODO: fetch prior snapshot if needed
                        )
            except Exception as e:
                logger.error(f"[{run_id}] Error processing {symbol}: {e}")
                results.append({"symbol": symbol, "status": "error", "error": str(e)})

        duration = (datetime.utcnow() - start).total_seconds()
        summary = {
            "run_id": run_id,
            "profile_name": self.name,
            "symbols": target_symbols,
            "window_days": self.window_days,
            "started_at": start.isoformat(),
            "duration_seconds": duration,
            "results": results,
        }
        logger.info(f"[{run_id}] Profile {self.name} completed in {duration:.2f}s")
        return summary

    def _event_type_for_data_type(self, dt: DataType) -> str:
        """Map DataType to universal event type."""
        mapping = {
            DataType.FUNDAMENTALS: "fundamentals_update",
            DataType.NEWS: "news_spike",
            DataType.STOCK_GRADES: "grade_change",
            DataType.CONSENSUS_DATA: "consensus_update",
            DataType.PRICE_CURRENT: "price_update",
            DataType.PRICE_INTRADAY_5M: "price_update",
        }
        return mapping.get(dt, "data_update")

def register_profile(profile: IngestionProfile):
    """Register a profile in the global registry."""
    if profile.name in INGESTION_PROFILES:
        raise ValueError(f"Profile {profile.name} already registered")
    INGESTION_PROFILES[profile.name] = profile
    logger.info(f"Registered ingestion profile: {profile.name}")

def get_profile(name: str) -> IngestionProfile:
    """Get a profile by name."""
    profile = INGESTION_PROFILES.get(name)
    if not profile:
        raise ValueError(f"Unknown ingestion profile: {name}")
    return profile

# ----------------------------------------------------------------------
# Define concrete profiles
# ----------------------------------------------------------------------
register_profile(IngestionProfile(
    name="monthly_portfolio_refresh_v1",
    data_types=[
        DataType.FUNDAMENTALS,
        DataType.NEWS,
        DataType.STOCK_GRADES,
        DataType.CONSENSUS_DATA,
        DataType.PRICE_CURRENT,
    ],
    window_days=30,
))

register_profile(IngestionProfile(
    name="daily_news_grades_v1",
    data_types=[DataType.NEWS, DataType.STOCK_GRADES],
    window_days=7,
))

register_profile(IngestionProfile(
    name="prices_live_v1",
    data_types=[DataType.PRICE_INTRADAY_5M],
    window_days=1,
))
