"""Turn two snapshots of GET /metrics (taken before and after a load test) into the numbers for the README.

    curl -s http://127.0.0.1:8001/metrics > before.txt
    ... run the load test ...
    curl -s http://127.0.0.1:8001/metrics > after.txt
    python loadtest/metrics_report.py before.txt after.txt <seconds the test ran>

Percentiles are estimated from histogram buckets the same way Prometheus does (linear inside a bucket),
so they are as exact as the bucket edges allow."""

import sys
from collections import defaultdict

from prometheus_client.parser import text_string_to_metric_families


def load(path: str) -> dict[tuple[str, tuple], float]:
    values: dict[tuple[str, tuple], float] = {}
    with open(path) as handle:
        text = handle.read()
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            values[(sample.name, tuple(sorted(sample.labels.items())))] = sample.value
    return values


def delta(before: dict, after: dict) -> dict:
    return {key: value - before.get(key, 0.0) for key, value in after.items()}


def total(values: dict, name: str, **labels: str) -> float:
    return sum(v for (n, lab), v in values.items() if n == name and all(dict(lab).get(k) == x for k, x in labels.items()))


def quantile(values: dict, metric: str, q: float) -> float | None:
    """q-quantile (0..1) of a histogram, all label sets together."""
    buckets: dict[float, float] = defaultdict(float)
    for (name, labels), value in values.items():
        if name == f"{metric}_bucket":
            edge = dict(labels)["le"]
            buckets[float("inf") if edge == "+Inf" else float(edge)] += value
    edges = sorted(buckets)
    if not edges or buckets[edges[-1]] <= 0:
        return None
    target = q * buckets[edges[-1]]
    previous_edge, previous_count = 0.0, 0.0
    for edge in edges:
        count = buckets[edge]
        if count >= target:
            if edge == float("inf"):
                return previous_edge
            if count == previous_count:
                return edge
            return previous_edge + (edge - previous_edge) * (target - previous_count) / (count - previous_count)
        previous_edge, previous_count = edge, count
    return None


def ms(seconds: float | None) -> str:
    return "n/a" if seconds is None else f"{seconds * 1000:.0f} ms"


def main(before_path: str, after_path: str, seconds: float) -> None:
    d = delta(load(before_path), load(after_path))
    chat_total = total(d, "luwo_http_requests_total", route="/chat")
    chat_5xx = sum(v for (n, lab), v in d.items() if n == "luwo_http_requests_total" and dict(lab).get("route") == "/chat" and dict(lab).get("status", "").startswith("5"))
    agent_count = total(d, "luwo_agent_requests_total")
    agent_errors = total(d, "luwo_agent_requests_total", outcome="error")
    statements = total(d, "luwo_db_query_duration_seconds_count")
    print(f"test length            : {seconds:.0f} s")
    print(f"/chat requests         : {chat_total:.0f}  ({chat_total / seconds:.1f} per second)")
    print(f"/chat 5xx              : {chat_5xx:.0f}")
    print(f"agent requests         : {agent_count:.0f}, outcome=error: {agent_errors:.0f}")
    print(f"agent latency          : p50 {ms(quantile(d, 'luwo_agent_request_duration_seconds', 0.5))}, p95 {ms(quantile(d, 'luwo_agent_request_duration_seconds', 0.95))}")
    print(f"HTTP /chat latency     : p50 {ms(quantile({k: v for k, v in d.items() if dict(k[1]).get('route') in (None, '/chat')}, 'luwo_http_request_duration_seconds', 0.5))}, p95 {ms(quantile({k: v for k, v in d.items() if dict(k[1]).get('route') in (None, '/chat')}, 'luwo_http_request_duration_seconds', 0.95))}")
    print(f"model call latency     : p50 {ms(quantile(d, 'luwo_llm_call_duration_seconds', 0.5))}, p95 {ms(quantile(d, 'luwo_llm_call_duration_seconds', 0.95))}")
    print(f"tool call latency      : p50 {ms(quantile(d, 'luwo_tool_duration_seconds', 0.5))}, p95 {ms(quantile(d, 'luwo_tool_duration_seconds', 0.95))}")
    print(f"DB statement latency   : p50 {ms(quantile(d, 'luwo_db_query_duration_seconds', 0.5))}, p95 {ms(quantile(d, 'luwo_db_query_duration_seconds', 0.95))}")
    if agent_count:
        print(f"DB statements / request: {statements / agent_count:.1f}  ({statements / seconds:.0f} per second)")
    tokens = {kind: total(d, "luwo_llm_tokens_total", kind=kind) for kind in ("input", "output", "cache_read", "cache_write")}
    if agent_count:
        print("tokens / request       : " + ", ".join(f"{k} {v / agent_count:.0f}" for k, v in tokens.items()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]))
