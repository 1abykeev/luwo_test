"""Prometheus metrics: what to measure, and the small pieces that measure it.

Rules this file follows:
- Labels only take values from a small fixed set (a route template, a request type, a tool name).
  Never a user id, conversation id or free text: each new value would create a new time series.
- Durations are histograms, so Prometheus can compute p50/p95 (histogram_quantile) and rates."""

import time
import uuid

import psutil
import structlog
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from starlette.datastructures import MutableHeaders

registry = CollectorRegistry()

# seconds
SLOW_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 34, 55, 90)  # HTTP and the model: seconds
FAST_BUCKETS = (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)  # database and tools

http_requests_total = Counter(
    "luwo_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry
)
http_request_seconds = Histogram(
    "luwo_http_request_duration_seconds", "HTTP request duration", ["method", "route"],
    buckets=SLOW_BUCKETS, registry=registry,
)
http_in_flight = Gauge("luwo_http_requests_in_flight", "HTTP requests being handled right now", registry=registry)

agent_requests_total = Counter(
    "luwo_agent_requests_total", "Chat requests by type and outcome", ["request_type", "outcome"], registry=registry
)
agent_request_seconds = Histogram(
    "luwo_agent_request_duration_seconds", "Time to answer one chat request (all model calls and tools)",
    ["request_type"], buckets=SLOW_BUCKETS, registry=registry,
)
conversations_started_total = Counter(
    "luwo_conversations_started_total", "Conversations started", registry=registry
)

llm_calls_total = Counter("luwo_llm_calls_total", "Model calls by result", ["status"], registry=registry)
llm_call_seconds = Histogram(
    "luwo_llm_call_duration_seconds", "Duration of one model call", buckets=SLOW_BUCKETS, registry=registry
)
llm_tokens_total = Counter(
    "luwo_llm_tokens_total", "Model tokens by kind: input, output, cache_read, cache_write", ["kind"], registry=registry
)
request_tokens = Histogram(
    "luwo_request_tokens", "Model tokens (all kinds) used by one chat request",
    buckets=(250, 500, 1000, 2500, 5000, 10000, 20000, 50000), registry=registry,
)

tool_calls_total = Counter("luwo_tool_calls_total", "Tool calls by tool and result", ["tool", "result"], registry=registry)
tool_seconds = Histogram(
    "luwo_tool_duration_seconds", "Duration of one tool call", ["tool"], buckets=FAST_BUCKETS, registry=registry
)

db_query_seconds = Histogram(
    "luwo_db_query_duration_seconds", "Duration of one SQL statement", ["operation"],
    buckets=FAST_BUCKETS, registry=registry,
)


class ProcessCollector:
    """Memory and CPU of this process, read with psutil so it works on macOS too (the standard
    Prometheus process collector only reads /proc, which exists on Linux only)."""

    def __init__(self) -> None:
        self._process = psutil.Process()
        self._process.cpu_percent(interval=None)  # the first call only starts the measurement

    def collect(self):
        process = self._process
        with process.oneshot():
            yield GaugeMetricFamily(
                "luwo_process_resident_memory_bytes", "Memory held in RAM by this process", value=process.memory_info().rss
            )
            cpu = process.cpu_times()
            yield CounterMetricFamily(
                "luwo_process_cpu_seconds", "CPU time used by this process (user + system)", value=cpu.user + cpu.system
            )
            yield GaugeMetricFamily(
                "luwo_process_cpu_percent", "CPU use since the previous scrape, 100 = one full core",
                value=process.cpu_percent(interval=None),
            )
            yield GaugeMetricFamily("luwo_process_threads", "Threads in this process", value=process.num_threads())


registry.register(ProcessCollector())


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST


# ---- measuring database time: one hook on SQLAlchemy engines, so no repository needs to know ----

# ---- measuring every HTTP request ----

DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}  # served by FastAPI itself
IGNORED_ROUTES = {"/metrics", "/health"}  # monitoring probes should not drown the real traffic
log = structlog.get_logger("luwo.http")


class MetricsMiddleware:
    """A plain ASGI middleware (not Starlette's BaseHTTPMiddleware, which adds overhead per request):
    counts and times each request, gives it a request id, and writes one "http_request" log line."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()  # nothing from an earlier request may leak into this one
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status = 500
        # A probe is not "work": the request that reads /metrics would otherwise count itself and the gauge
        # could never show 0 while Prometheus is scraping.
        counted_in_flight = scope["path"] not in IGNORED_ROUTES
        if counted_in_flight:
            http_in_flight.inc()

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            if counted_in_flight:
                http_in_flight.dec()
            elapsed = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", None) or ("docs" if scope["path"] in DOC_PATHS else "unmatched")
            # (the label is the route template, never the raw URL)
            if route not in IGNORED_ROUTES:
                method = scope["method"]
                http_requests_total.labels(method, route, str(status)).inc()
                http_request_seconds.labels(method, route).observe(elapsed)
                level = log.error if status >= 500 else log.info
                level("http_request", method=method, route=route, status=status, duration_ms=round(elapsed * 1000, 1))
            structlog.contextvars.clear_contextvars()
