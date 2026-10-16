"""Small semantic controls for the standalone scaling benchmark."""

import json
import sys
import pytest
from support import ROOT, run

pytestmark = pytest.mark.fast


def test_scaling_controls(asmc, tmp_path):
    output = tmp_path / "results"
    run(
        [
            sys.executable,
            ROOT / "benchmarks/scaling.py",
            asmc.parent,
            "--smoke",
            "--solver",
            "sat",
            "--timeout",
            "30",
            "--output-dir",
            output,
        ],
        timeout=160,
    )
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows[:4]] == ["PASS", "FAIL", "INCOMPLETE", "FAIL"]
    assert all(row["status"] == row["expected"] for row in rows)
    assert all(row["ssa_steps"] and row["rss_kib"] for row in rows)
    assert all(row["conversion_s"] is not None for row in rows)
    assert (output / "results.csv").is_file()
    assert json.loads((output / "manifest.json").read_text())["profile_validated"]["sat/plain"]
