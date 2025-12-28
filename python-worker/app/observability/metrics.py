"""
Metrics collection
Industry standard: Prometheus-style metrics for observability
"""
import time
import logging
from typing import Dict, Any, Optional
from functools import wraps
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Simple metrics collector
    In production, integrate with Prometheus/StatsD
    """
    
    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = defaultdict(list)
        self._lock = Lock()
    
    def increment(self, metric_name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """
        Increment a counter metric
        
        Args:
            metric_name: Metric name (e.g., 'indicator_calculations_total')
            value: Increment value
            labels: Optional labels for metric
        """
        key = self._build_key(metric_name, labels)
        with self._lock:
            self._counters[key] += value
        logger.debug(f"Metric incremented: {key} = {self._counters[key]}")
    
    def set_gauge(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """
        Set a gauge metric
        
        Args:
            metric_name: Metric name (e.g., 'active_connections')
            value: Gauge value
            labels: Optional labels
        """
        key = self._build_key(metric_name, labels)
        with self._lock:
            self._gauges[key] = value
        logger.debug(f"Metric gauge set: {key} = {value}")
    
    def record_duration(self, metric_name: str, duration: float, labels: Optional[Dict[str, str]] = None):
        """
        Record a duration (histogram)
        
        Args:
            metric_name: Metric name (e.g., 'request_duration_seconds')
            duration: Duration in seconds
            labels: Optional labels
        """
        key = self._build_key(metric_name, labels)
        with self._lock:
            self._histograms[key].append(duration)
        logger.debug(f"Metric duration recorded: {key} = {duration}s")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all metrics (for health checks, monitoring)
        
        Returns:
            Dictionary with all metrics
        """
        with self._lock:
            return {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histograms': {
                    key: {
                        'count': len(values),
                        'sum': sum(values),
                        'avg': sum(values) / len(values) if values else 0,
                        'min': min(values) if values else 0,
                        'max': max(values) if values else 0,
                    }
                    for key, values in self._histograms.items()
                }
            }
    
    def _build_key(self, metric_name: str, labels: Optional[Dict[str, str]]) -> str:
        """Build metric key with labels"""
        if labels:
            label_str = ','.join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{metric_name}{{{label_str}}}"
        return metric_name


# Global metrics instance
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector"""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def track_duration(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """
    Decorator to track function execution duration
    
    Usage:
        @track_duration('indicator_calculation_seconds', {'symbol': 'AAPL'})
        def calculate_indicators(symbol):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                get_metrics().record_duration(metric_name, duration, labels)
        return wrapper
    return decorator

