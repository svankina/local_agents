import csv
import importlib.util
import json
from pathlib import Path


def load_metrics_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "compute_run_metrics.py"
    spec = importlib.util.spec_from_file_location("compute_run_metrics", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compute_run_metrics_synthetic_fixture(tmp_path):
    rows = [
        {"ts": "2026-06-12T00:00:00+00:00", "monotonic_s": "0", "power_w": "100", "gpu_util_pct": "0", "vram_used_mib": "42", "temp_c": "40", "cpu_util_pct": "10", "ram_used_gib": "8"},
        {"ts": "2026-06-12T00:00:01+00:00", "monotonic_s": "1", "power_w": "200", "gpu_util_pct": "80", "vram_used_mib": "1000", "temp_c": "50", "cpu_util_pct": "20", "ram_used_gib": "9"},
        {"ts": "2026-06-12T00:00:02+00:00", "monotonic_s": "2", "power_w": "100", "gpu_util_pct": "10", "vram_used_mib": "900", "temp_c": "48", "cpu_util_pct": "30", "ram_used_gib": "10"},
    ]
    with (tmp_path / "telemetry.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    response = {
        "ts": "2026-06-12T00:00:01+00:00",
        "type": "response",
        "body": {
            "_client_wall_s": 1.0,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "timings": {
                "prompt_n": 100,
                "predicted_n": 50,
                "prompt_ms": 200,
                "predicted_ms": 500,
                "prompt_per_second": 500,
                "predicted_per_second": 100,
            },
        },
    }
    (tmp_path / "transcript.jsonl").write_text(json.dumps(response) + "\n")
    events = [
        {"ts": "2026-06-12T00:00:01+00:00", "event": "tool_start", "id": "gate"},
        {"ts": "2026-06-12T00:00:01.250000+00:00", "event": "tool_end", "id": "gate"},
    ]
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    module = load_metrics_module()
    metrics = module.compute(tmp_path)

    assert metrics["wall_clock_seconds"] == 2.0
    assert round(metrics["energy"]["gpu_wh"], 6) == round((150 + 150) / 3600, 6)
    assert metrics["time_accounting"]["t_prefill"] == 0.2
    assert metrics["time_accounting"]["t_generating"] == 0.5
    assert round(metrics["time_accounting"]["t_api_wait"], 6) == 0.3
    assert metrics["time_accounting"]["t_tool_exec"] == 0.25
    assert metrics["time_accounting"]["sanity_ok"] is True
    assert metrics["peak_throughput"]["max_decode_tps_single"]["value"] == 100
    assert metrics["peak_throughput"]["max_prefill_tps"]["value"] == 500
    assert metrics["peak_throughput"]["max_aggregate_tps_1s"]["value"] == 50
