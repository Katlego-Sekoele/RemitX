"""summary.json + report.canvas.tsx + performance-report.html from Locust CSVs."""

import json
from pathlib import Path

from loadtest_summary import build_summary
from to_canvas import main, render_canvas, render_html

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "run"


def test_build_summary_splits_http_and_settle():
    summary = build_summary(FIXTURE)
    assert summary.profile_name == "fixture-sweep"
    assert summary.burn_p50_s == 8.61
    assert [c.name for c in summary.compute] == ["render-free", "api-1cpu"]
    by_name = {c.name: c for c in summary.compute}
    slow = by_name["render-free"]
    fast = by_name["api-1cpu"]
    p10_slow = next(p for p in slow.plateaus if p.users == 10)
    p10_fast = next(p for p in fast.plateaus if p.users == 10)
    assert p10_slow.http_median_ms is not None
    assert p10_fast.http_median_ms is not None
    assert p10_slow.http_median_ms > p10_fast.http_median_ms
    assert p10_slow.settle_e2e_rps > 0
    assert "CPU" in summary.bottleneck or "cpu" in summary.bottleneck.lower()


def test_to_canvas_writes_summary_and_canvas(tmp_path):
    # Copy fixture into tmp so we do not dirty the committed fixtures.
    import shutil

    run = tmp_path / "run"
    shutil.copytree(FIXTURE, run)
    assert main([str(run)]) == 0
    summary = json.loads((run / "summary.json").read_text())
    assert "compute" in summary
    assert "bottleneck" in summary
    assert summary["burn_p50_s"] == 8.61
    canvas = (run / "report.canvas.tsx").read_text()
    assert "Performance testing results" in canvas
    assert "API response times under concurrent use" in canvas
    assert "Requests processed per second" in canvas
    assert "Settlement: queue throughput" in canvas
    assert 'from "cursor/canvas"' in canvas or "from 'cursor/canvas'" in canvas
    assert "render-free" in canvas
    assert "api-1cpu" in canvas
    html = (run / "performance-report.html").read_text()
    assert "<!DOCTYPE html>" in html
    assert "Performance testing results" in html
    assert "report-data" in html
    assert "render-free" in html


def test_render_canvas_is_deterministic_enough():
    summary = build_summary(FIXTURE)
    text = render_canvas(summary)
    assert "Calibrated RLUSD burn" in text
    assert "HTTP-only median" in text
    html = render_html(summary)
    assert "lineChart" in html or "polyline" in html
    assert summary.profile_name in html
