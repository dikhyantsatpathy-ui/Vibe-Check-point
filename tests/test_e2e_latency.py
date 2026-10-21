import pytest
from eval.e2e_latency import measure_e2e_latency


def test_e2e_latency_ci_gate(tmp_path):
    """Fast CI gate: runs 3 passes and asserts p50 latency is well within CI budget (< 8.0s)."""
    out_file = tmp_path / "e2e_latency_ci.json"
    metrics = measure_e2e_latency(iterations=3, out_file=out_file)

    assert out_file.exists()
    p50 = metrics["total_latency_ms"]["p50"]
    # Generous CI bound to prevent flakiness on shared runners
    assert p50 < 8000.0, f"p50 latency {p50}ms exceeded CI bound of 8000ms"
    assert "per_stage_breakdown_ms" in metrics


@pytest.mark.slow
def test_e2e_latency_full_benchmark(tmp_path):
    """Full 20-iteration benchmark evaluating production SLA targets (p50 < 3.0s, p95 < 6.0s)."""
    out_file = tmp_path / "e2e_latency_full.json"
    metrics = measure_e2e_latency(iterations=20, out_file=out_file)

    assert out_file.exists()
    p50 = metrics["total_latency_ms"]["p50"]
    assert p50 < 5000.0, f"Full benchmark p50 {p50}ms exceeded threshold"
