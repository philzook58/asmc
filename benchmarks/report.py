"""Summarize saved runs; optionally plot with gnuplot (no Python dependencies)."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import shutil
import statistics
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows, rejected, manifests = [], [], []
    for run in args.runs:
        manifest = json.loads((run / "manifest.json").read_text())
        manifests.append(manifest)
        validated = manifest["profile_validated"]
        rejected += [f"{run.name}: {name}" for name, valid in validated.items() if not valid]
        for line in (run / "results.jsonl").read_text().splitlines():
            row = json.loads(line)
            if validated.get(row["solver"] + "/" + row["variant"], False) and not row["control"]:
                if row.get("scalar_registers", False):
                    row["variant"] += "+scalar-registers"
                row["limit_s"] = manifest["timeout_s"]
                rows.append(row)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["case"], row["solver"], row["variant"])].append(row)
    lines = ["# Scaling measurements", "", "Profiles that fail semantic controls are excluded from comparisons.",
             "Timeouts are censored observations, not completed verification times. Median times below use only PASS runs;",
             "the status counts expose all other repetitions. RSS on timeout may miss an unreaped external solver.", "",
             "| Case | Solver/profile | Status counts | Median PASS seconds | Largest reported RSS MiB |",
             "|---|---|---|---:|---:|"]
    for (case, solver, variant), samples in sorted(groups.items()):
        times = [row["wall_s"] for row in samples if row["status"] == "PASS"]
        elapsed = f"{statistics.median(times):.3f}" if times else "—"
        statuses = ", ".join(f"{count} {status}" for status, count in sorted(Counter(row["status"] for row in samples).items()))
        lines.append(f"| {case} | {solver}/{variant} | {statuses} | {elapsed} | {max(row['rss_kib'] for row in samples)/1024:.1f} |")
    lines += ["", "Rejected profiles:", "", *["- " + name for name in rejected]]
    if not rejected:
        lines += ["None."]
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    (output / "manifests.json").write_text(json.dumps(manifests, indent=2) + "\n")
    if not args.plot:
        return
    if not shutil.which("gnuplot"):
        raise SystemExit("gnuplot is required for --plot; summary.md was still written")

    # Each dataset has success values and a separate censored column; triangles
    # mark lower bounds. A timeout is never connected as if it were a PASS time.
    def series(name, selected, value="wall_s"):
        selected_rows = [row for row in rows if selected(row)]
        points = defaultdict(list)
        for row in selected_rows:
            x = row["bound"] if row["family"] == "call-bound" else row["size"]
            points[x].append(row)
        path = output / (name + ".dat")
        data = []
        for x, samples in sorted(points.items()):
            passed = [row[value] for row in samples if (row["status"] == "PASS" or value == "ssa_steps") and row.get(value) is not None]
            stopped = [row["limit_s"] if value == "wall_s" else row[value] for row in samples
                       if row["status"] == "TIMEOUT" and row.get(value) is not None]
            if value == "ssa_steps":
                stopped = []  # A recorded SSA count is exact even if solving timed out.
            if value == "rss_kib":
                passed = [number / 1024 for number in passed]
                stopped = [number / 1024 for number in stopped]
            exhausted = [row["rss_kib"] / 1024 for row in samples if row["status"] == "OOM"] if value == "rss_kib" else []
            data.append(f"{x} {statistics.median(passed) if passed else 'NaN'} {min(stopped) if stopped else 'NaN'} "
                        f"{min(exhausted) if exhausted else 'NaN'}")
        path.write_text("\n".join(data) + "\n")
        return path if data else None

    colors = ["#1565c0", "#e65100", "#2e7d32", "#8e24aa", "#795548"]
    solvers = ("sat", "z3", "cvc5", "bitwuzla", "kissat")
    quote = lambda value: json.dumps(str(value))

    def curves(items):
        parts = []
        for name, path, color in items:
            if path:
                parts += [f"{quote(path.name)} using 1:2 with linespoints lw 2 pt 7 lc rgb {quote(color)} title {quote(name)}",
                          f"{quote(path.name)} using 1:3 with points pt 9 ps 1.5 lc rgb {quote(color)} notitle",
                          f"{quote(path.name)} using 1:4 with points pt 4 ps 1.5 lc rgb {quote(color)} notitle"]
        return "plot " + ", ".join(parts) if parts else "plot NaN notitle"

    script = ["set terminal svg size 1200,900 enhanced font 'sans,13'", "set output 'scaling.svg'",
              "set multiplot layout 2,2 title 'ASMC scaling: triangles mark timeouts; squares mark OOM RSS observations'",
              "set grid", "set key top left", "set logscale x 2", "set logscale y 10", "set format y '%g'",
              "set xlabel 'Buffer bytes'", "set ylabel 'Wall seconds'", "set title 'Symbolic 8-byte store: numeric RAM, flat registers'"]
    items = []
    for solver, color in zip(solvers, colors):
        path = series("memory-" + solver, lambda row, solver=solver: row["family"] == "memory-write" and
                      row["memory"] == "ram" and not row["fixed_index"] and row["solver"] == solver and row["variant"] == "plain")
        items.append((solver, path, color))
    script.append(curves(items))
    script += ["set xlabel 'Conditional branches'", "set ylabel 'SSA steps'", "set title 'Direct branches vs PC dispatch: flat registers'"]
    items = []
    for dispatch, color in zip((False, True), colors):
        path = series("branches-" + str(dispatch), lambda row, dispatch=dispatch: row["family"] == "branches" and
                      row["solver"] == "sat" and row["variant"] == "plain" and row["dispatch"] == dispatch, "ssa_steps")
        items.append(("dispatch" if dispatch else "direct", path, color))
    script.append(curves(items))
    script += ["set xlabel 'Dispatch unwind bound (two actual calls)'", "set ylabel 'Peak reported RSS MiB'",
               "set title 'Loose bounds and register-array scalarization'"]
    items = []
    for variant, color in zip(("plain", "fields-768", "fields-1024", "plain+scalar-registers", "fields-128+scalar-registers"), colors):
        path = series("bounds-" + variant, lambda row, variant=variant: row["family"] == "call-bound" and
                      row["solver"] == "sat" and row["variant"] == variant, "rss_kib")
        items.append((variant, path, color))
    script.append(curves(items))
    script += ["set xlabel 'Admitted input/result bit width'", "set ylabel 'Wall seconds'",
               "set title 'Nonlinear modular arithmetic identity: flat registers'"]
    items = []
    for solver, color in zip(solvers, colors):
        path = series("multiply-" + solver, lambda row, solver=solver: row["family"] == "multiply" and
                      row["solver"] == solver and row["variant"] == "plain")
        items.append((solver, path, color))
    script += [curves(items), "unset multiplot"]
    (output / "plot.gnuplot").write_text("\n".join(script) + "\n")
    subprocess.run(["gnuplot", "plot.gnuplot"], cwd=output, check=True)
    png = ["set terminal pngcairo size 1200,900 font 'sans,13'", "set output 'scaling.png'", *script[2:]]
    (output / "plot-png.gnuplot").write_text("\n".join(png) + "\n")
    subprocess.run(["gnuplot", "plot-png.gnuplot"], cwd=output, check=True)


if __name__ == "__main__":
    main()
