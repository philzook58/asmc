"""Semantic checks for the benchmark generator and result classification."""
from pathlib import Path
import subprocess
import sys
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="asmc-scaling-test-") as temp:
    output = Path(temp) / "results"
    subprocess.run([sys.executable, ROOT / "benchmarks/scaling.py", Path(sys.argv[1]).resolve().parent,
                    "--smoke", "--solver", "sat", "--timeout", "30", "--output-dir", output], check=True, timeout=160)
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows[:4]] == ["PASS", "FAIL", "INCOMPLETE", "FAIL"]
    assert all(row["status"] == row["expected"] for row in rows)
    assert all(row["ssa_steps"] and row["rss_kib"] for row in rows)
    assert all(row["conversion_s"] is not None for row in rows)
    assert (output / "results.csv").is_file()
    assert json.loads((output / "manifest.json").read_text())["profile_validated"]["sat/plain"]
