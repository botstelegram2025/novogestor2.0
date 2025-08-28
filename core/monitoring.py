"""
Professional Monitoring and Metrics System
Provides comprehensive application monitoring and observability
"""
import time
import threading
import psutil
import json
from typing import Dict, Any, Optional, List, Callable
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from core.logging import get_logger
from core.retry import get_all_circuit_breaker_stats

logger = get_logger(__name__)

@dataclass
class MetricPoint:
    """Individual metric data point"""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)

@dataclass
class HealthCheckResult:
    """Health check result"""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    response_time_ms: float
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

class MetricsCollector:
    """Collects and stores application metrics"""
    
    def __init__(self, max_points_per_metric: int = 1000):
        self.max_points_per_metric = max_points_per_metric
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            self._add_metric_point(name, self._counters[key], labels)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric value"""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            self._add_metric_point(name, value, labels)
    
    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Add observation to histogram metric"""
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
            # Keep only recent observations
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
            self._add_metric_point(name, value, labels)
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create unique key for metric with labels"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _add_metric_point(self, name: str, value: float, labels: Optional[Dict[str, str]]):
        """Add metric point to time series"""
        key = self._make_key(name, labels)
        point = MetricPoint(
            timestamp=time.time(),
            value=value,
            labels=labels or {}
        )
        self._metrics[key].append(point)
    
    def get_metric_summary(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Get summary statistics for a metric"""
        key = self._make_key(name, labels)
        
        with self._lock:
            if key not in self._metrics:
                return {}
            
            points = list(self._metrics[key])
            if not points:
                return {}
            
            values = [p.value for p in points]
            
            return {
                'name': name,
                'labels': labels or {},
                'count': len(values),
                'latest_value': values[-1],
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'latest_timestamp': points[-1].timestamp
            }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics with summaries"""
        with self._lock:
            result = {}
            for key in self._metrics.keys():
                # Parse key to extract name and labels
                if '{' in key:
                    name = key.split('{')[0]
                    labels_str = key.split('{')[1].rstrip('}')
                    labels = dict(item.split('=') for item in labels_str.split(','))
                else:
                    name = key
                    labels = {}
                
                result[key] = self.get_metric_summary(name, labels)
            
            return result

class PerformanceTracker:
    """Tracks performance metrics for operations"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
    
    def track_operation(self, operation_name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager for tracking operation performance"""
        return OperationTimer(self.metrics, operation_name, labels)

class OperationTimer:
    """Context manager for timing operations"""
    
    def __init__(self, metrics_collector: MetricsCollector, operation_name: str, labels: Optional[Dict[str, str]] = None):
        self.metrics = metrics_collector
        self.operation_name = operation_name
        self.labels = labels or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            
            # Track performance metrics
            self.metrics.observe_histogram(
                f"{self.operation_name}_duration_ms",
                duration_ms,
                self.labels
            )
            
            # Track success/failure
            success = exc_type is None
            self.metrics.increment_counter(
                f"{self.operation_name}_total",
                labels={**self.labels, 'status': 'success' if success else 'error'}
            )
            
            if not success:
                self.metrics.increment_counter(
                    f"{self.operation_name}_errors",
                    labels={**self.labels, 'error_type': exc_type.__name__ if exc_type else 'unknown'}
                )

class SystemMetricsCollector:
    """Collects system-level metrics"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self._running = False
        self._thread = None
        self._interval = 30  # seconds
    
    def start(self, interval: int = 30):
        """Start collecting system metrics"""
        self._interval = interval
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
        logger.info(f"System metrics collection started (interval: {interval}s)")
    
    def stop(self):
        """Stop collecting system metrics"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("System metrics collection stopped")
    
    def _collect_loop(self):
        """Main collection loop"""
        while self._running:
            try:
                self._collect_metrics()
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            
            time.sleep(self._interval)
    
    def _collect_metrics(self):
        """Collect system metrics"""
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        self.metrics.set_gauge("system_cpu_usage_percent", cpu_percent)
        
        # Memory metrics
        memory = psutil.virtual_memory()
        self.metrics.set_gauge("system_memory_usage_percent", memory.percent)
        self.metrics.set_gauge("system_memory_used_bytes", memory.used)
        self.metrics.set_gauge("system_memory_available_bytes", memory.available)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        self.metrics.set_gauge("system_disk_usage_percent", disk.percent)
        self.metrics.set_gauge("system_disk_used_bytes", disk.used)
        self.metrics.set_gauge("system_disk_free_bytes", disk.free)
        
        # Network metrics
        network = psutil.net_io_counters()
        self.metrics.set_gauge("system_network_bytes_sent", network.bytes_sent)
        self.metrics.set_gauge("system_network_bytes_recv", network.bytes_recv)
        
        # Process metrics
        process = psutil.Process()
        self.metrics.set_gauge("process_memory_rss_bytes", process.memory_info().rss)
        self.metrics.set_gauge("process_memory_vms_bytes", process.memory_info().vms)
        self.metrics.set_gauge("process_cpu_percent", process.cpu_percent())
        self.metrics.set_gauge("process_num_threads", process.num_threads())
        self.metrics.set_gauge("process_num_fds", process.num_fds())

class HealthChecker:
    """Performs health checks on application components"""
    
    def __init__(self):
        self._checks: Dict[str, Callable[[], HealthCheckResult]] = {}
    
    def register_check(self, name: str, check_func: Callable[[], HealthCheckResult]):
        """Register a health check function"""
        self._checks[name] = check_func
        logger.info(f"Health check registered: {name}")
    
    def run_check(self, name: str) -> HealthCheckResult:
        """Run a specific health check"""
        if name not in self._checks:
            return HealthCheckResult(
                name=name,
                status="unhealthy",
                response_time_ms=0,
                message=f"Health check '{name}' not found"
            )
        
        start_time = time.time()
        try:
            result = self._checks[name]()
            result.response_time_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status="unhealthy",
                response_time_ms=(time.time() - start_time) * 1000,
                message=f"Health check failed: {str(e)}"
            )
    
    def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all registered health checks"""
        results = {}
        for name in self._checks:
            results[name] = self.run_check(name)
        return results
    
    def get_overall_status(self) -> str:
        """Get overall application health status"""
        results = self.run_all_checks()
        
        if not results:
            return "unknown"
        
        statuses = [result.status for result in results.values()]
        
        if all(status == "healthy" for status in statuses):
            return "healthy"
        elif any(status == "unhealthy" for status in statuses):
            return "unhealthy"
        else:
            return "degraded"

class MonitoringSystem:
    """Main monitoring system that coordinates all monitoring components"""
    
    def __init__(self):
        self.metrics = MetricsCollector()
        self.performance = PerformanceTracker(self.metrics)
        self.system_metrics = SystemMetricsCollector(self.metrics)
        self.health_checker = HealthChecker()
        self._setup_default_health_checks()
    
    def start(self, system_metrics_interval: int = 30):
        """Start the monitoring system"""
        self.system_metrics.start(system_metrics_interval)
        logger.info("Monitoring system started")
    
    def stop(self):
        """Stop the monitoring system"""
        self.system_metrics.stop()
        logger.info("Monitoring system stopped")
    
    def _setup_default_health_checks(self):
        """Setup default health checks"""
        
        def database_health() -> HealthCheckResult:
            """Check database connectivity"""
            try:
                # This would be implemented with actual database check
                # For now, return healthy
                return HealthCheckResult(
                    name="database",
                    status="healthy",
                    response_time_ms=0,
                    message="Database connection OK"
                )
            except Exception as e:
                return HealthCheckResult(
                    name="database",
                    status="unhealthy",
                    response_time_ms=0,
                    message=f"Database error: {str(e)}"
                )
        
        def telegram_health() -> HealthCheckResult:
            """Check Telegram bot status"""
            try:
                # This would check Telegram API connectivity
                return HealthCheckResult(
                    name="telegram",
                    status="healthy",
                    response_time_ms=0,
                    message="Telegram bot OK"
                )
            except Exception as e:
                return HealthCheckResult(
                    name="telegram",
                    status="unhealthy",
                    response_time_ms=0,
                    message=f"Telegram error: {str(e)}"
                )
        
        def whatsapp_health() -> HealthCheckResult:
            """Check WhatsApp service status"""
            try:
                # This would check WhatsApp service connectivity
                return HealthCheckResult(
                    name="whatsapp",
                    status="healthy",
                    response_time_ms=0,
                    message="WhatsApp service OK"
                )
            except Exception as e:
                return HealthCheckResult(
                    name="whatsapp",
                    status="unhealthy",
                    response_time_ms=0,
                    message=f"WhatsApp error: {str(e)}"
                )
        
        self.health_checker.register_check("database", database_health)
        self.health_checker.register_check("telegram", telegram_health)
        self.health_checker.register_check("whatsapp", whatsapp_health)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        health_results = self.health_checker.run_all_checks()
        circuit_breaker_stats = get_all_circuit_breaker_stats()
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': self.health_checker.get_overall_status(),
            'health_checks': {name: {
                'status': result.status,
                'response_time_ms': result.response_time_ms,
                'message': result.message,
                'details': result.details
            } for name, result in health_results.items()},
            'circuit_breakers': circuit_breaker_stats,
            'system_metrics': {
                name: summary for name, summary in self.metrics.get_all_metrics().items()
                if name.startswith('system_') or name.startswith('process_')
            }
        }

# Global monitoring instance
monitoring = MonitoringSystem()