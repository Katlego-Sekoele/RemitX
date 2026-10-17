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
    assert "Calibrated UCTUSD burn" in text
    assert "HTTP-only median" in text
    html = render_html(summary)
    assert "lineChart" in html or "polyline" in html
    assert summary.profile_name in html


def test_every_report_says_where_its_burn_timings_were_measured():
    summary = build_summary(FIXTURE)
    assert summary.burn_calibrated_on == "XRP Ledger, pre-EVM"
    assert "(calibrated on XRP Ledger, pre-EVM)" in summary.bottleneck
    for report in (render_canvas(summary), render_html(summary)):
        assert '"burnCalibratedOn": "XRP Ledger, pre-EVM"' in report
        assert "(Testnet)" not in report
    assert "Calibrated UCTUSD burn p50 (${data.burnCalibratedOn})" in render_canvas(
        summary
    )
    assert "Calibrated UCTUSD burn p50 (${esc(data.burnCalibratedOn)})" in (
        render_html(summary)
    )


def test_a_run_from_before_calibrated_on_falls_back_to_testnet(tmp_path):
    import shutil

    run = tmp_path / "run"
    shutil.copytree(FIXTURE, run)
    profile = json.loads((run / "profile.json").read_text())
    del profile["burn"]["calibrated_on"]
    (run / "profile.json").write_text(json.dumps(profile))

    summary = build_summary(run)
    assert summary.burn_calibrated_on == "Testnet"
    assert "(calibrated on Testnet)" in summary.bottleneck
