#!/usr/bin/env python3
"""Serial, bounded scaling experiments. Timings are observations, not test thresholds."""
import argparse
import csv
import json
import os
from pathlib import Path
import platform
import re
import resource
import shlex
import shutil
import signal
import subprocess
import time

from models import KINDS, Case, cases

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {"plain": [], "slice": ["--slice-formula"],
            "arrays-uf": ["--arrays-uf-always"],
            "fields-128": ["--max-field-sensitivity-array-size", "128"],
            "fields-1024": ["--max-field-sensitivity-array-size", "1024"],
            "fields-768": ["--max-field-sensitivity-array-size", "768"],
            "no-array-fields": ["--no-array-field-sensitivity"],
            "cache": ["--symex-cache-dereferences"],
            "paths": ["--paths", "dfs"], "refine-arrays": ["--refine-arrays"],
            "refine-arithmetic": ["--refine-arithmetic"],
            "no-sat-simplifier": ["--no-sat-preprocessor"],
            "reachability": ["--reachability-slice-fb"], "pre-inline": []}
SOLVER_FLAGS = {"sat": [], "z3": ["--z3"], "cvc5": ["--cvc5"],
                "bitwuzla": ["--bitwuzla"], "yices": ["--yices"], "kissat": []}


def execute(command, directory, label, timeout, memory_limit):
    """wait4 gives per-run usage, unlike cumulative RUSAGE_CHILDREN measurements."""
    command = [str(arg) for arg in command]
    with (directory / "commands.txt").open("a") as stream:
        stream.write(shlex.join(command) + "\n")
    started = time.monotonic()
    timed_out = False
    with (directory / (label + ".log")).open("w") as log:
        def limits():
            limit = memory_limit * 1024**2
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, preexec_fn=limits)
        try:
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    break
                if time.monotonic() - started >= timeout:
                    timed_out = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status, usage = os.wait4(process.pid, 0)
                    break
                time.sleep(0.005)
        except KeyboardInterrupt:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.wait4(process.pid, 0)
            process.returncode = -signal.SIGKILL
            raise
        process.returncode = os.waitstatus_to_exitcode(status)
    return {"exit": process.returncode, "wall_s": round(time.monotonic() - started, 6),
            "cpu_s": round(usage.ru_utime + usage.ru_stime, 6), "rss_kib": usage.ru_maxrss,
            "timeout": timed_out}


def measurements(text, process):
    stamps = []
    for line in text.splitlines():
        match = re.match(r"^(\d+\.\d+) (.*)", line)
        if match:
            stamps.append((float(match[1]), match[2]))
    clean = re.sub(r"^\d+\.\d+ ", "", text, flags=re.MULTILINE)
    failures = re.findall(r"^\[([^\]\n]+)\] (.*): FAILURE$", clean, re.MULTILINE)
    if process["timeout"]:
        status = "TIMEOUT"
    elif re.search(r"out of memory|std::bad_alloc|cannot allocate memory", clean, re.I):
        status = "OOM"
    elif process["exit"] == 0 and "VERIFICATION SUCCESSFUL" in clean and not failures:
        status = "PASS"
    elif process["exit"] == 10 and "VERIFICATION FAILED" in clean and failures:
        unwinds = [bool(re.search(r"\.unwind\.\d+$|\.recursion$", prop)) for prop, _ in failures]
        status = "INCOMPLETE" if all(unwinds) else "FAIL_WITH_UNWIND" if any(unwinds) else "FAIL"
    else:
        status = "ERROR"
    if "default solver will be used" in clean.lower():
        status = "ERROR"  # Do not silently label a fallback as the requested solver.

    def first(pattern):
        return next((stamp for stamp, message in stamps if re.search(pattern, message, re.I)), None)

    symex = first("Starting Bounded")
    conversion = first("Passing problem|converting SSA")
    solving = first("^Running (?!with)|Invoking SAT solver|Solving with")
    finished = first("Runtime decision procedure")
    progress = [message for _, message in stamps if re.match(
        r"Starting Bounded|Passing problem|converting SSA|Running (?!with)|Invoking SAT solver", message)]
    stats = {"status": status, "failures": [prop for prop, _ in failures],
             "last_stage": progress[-1] if progress else "startup"}
    for key, start, end in (("symex_s", symex, conversion), ("conversion_s", conversion, solving),
                            ("decision_s", solving, finished)):
        stats[key] = round(end - start, 6) if start is not None and end is not None else None
    for key, pattern in (("ssa_steps", r"size of program expression:\s*(\d+) steps"),
                         ("vccs", r"Generated (\d+) VCC"),
                         ("sat_variables", r"(\d+) variables, (\d+) clauses")):
        found = re.search(pattern, clean)
        stats[key] = int(found[1]) if found else None
        if key == "sat_variables":
            stats["sat_clauses"] = int(found[2]) if found else None
    calls = re.findall(r"Runtime Solver:\s*([\d.e+-]+)s", clean)
    stats["solver_call_s"] = sum(float(value) for value in calls) if calls else None
    return stats


def solver_profiles(names, overrides, tools):
    profiles, missing = {}, []
    for name in names:
        if name == "sat":
            executable = tools / "cbmc"
        else:
            executable_name = "yices-smt2" if name == "yices" else name
            local = ROOT / ".venv/bin" / executable_name
            executable = overrides.get(name) or (local if local.is_file() else shutil.which(executable_name))
        if not executable:
            missing.append(name)
            continue
        executable = Path(executable).absolute()
        if not executable.is_file():
            raise RuntimeError(f"solver executable not found: {executable}")
        version = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=10)
        lines = (version.stdout + version.stderr).splitlines()
        flags = list(SOLVER_FLAGS[name])
        if name == "kissat":
            flags += ["--external-sat-solver", str(executable)]
        elif name != "sat":
            flags += ["--external-smt2-solver", str(executable)]
        profiles[name] = {"path": str(executable), "version": lines[0] if lines else "unknown", "flags": flags}
    return profiles, missing


def build(case, directory, tools, timeout, memory_limit):
    directory.mkdir()
    (directory / "target.S").write_text(case.assembly())
    (directory / "objects.h").write_text(case.objects_header() if case.family == "objects" else "")
    flags = ["-I", ROOT / "include", "-I", directory, *case.defines()]
    stages = [
        ("compile", ["gcc", "-nostdlib", "-no-pie", "-Wl,-e,target", directory / "target.S", "-o", directory / "target.elf"]),
        ("seed", [tools / "goto-cc", *flags, "-c", ROOT / "runtime/runtime.c", "-o", directory / "seed.gb"]),
        ("lift", [tools / "asmc-lift", directory / "target.elf", "--function", "target", "--template", directory / "seed.gb",
                  "--memory", case.memory, "-o", directory / "lifted.gb"]),
        ("roundtrip", [tools / "goto-instrument", "--validate-goto-model", directory / "lifted.gb", directory / "roundtrip.gb"]),
        ("link", [tools / "goto-cc", *flags, directory / "lifted.gb", ROOT / "benchmarks/harness.c", "-o", directory / "check.gb"])]
    if case.family in ("calls", "call-bound"):
        stages[2][1].extend(["--callee", "helper"])
    if case.dispatch:
        stages[2][1].append("--dispatch")
    costs = {}
    for label, command in stages:
        costs[label] = execute(command, directory, label, timeout, memory_limit)
        if costs[label]["exit"] != 0 or costs[label]["timeout"]:
            raise RuntimeError(f"model construction failed: {directory / (label + '.log')}")
    (directory / "model.json").write_text(json.dumps({**case.__dict__, "bound": case.bound, "build": costs}, indent=2) + "\n")
    return costs


def write_results(output, rows, manifest):
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if rows:
        with (output / "results.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tools", type=Path, help="directory containing built ASMC/CBMC tools")
    parser.add_argument("--output-dir", type=Path, required=True, help="empty directory for models, raw logs, JSONL and CSV")
    parser.add_argument("--family", action="append", choices=KINDS)
    parser.add_argument("--size", action="append", type=int, help="override family sizes; repeatable")
    parser.add_argument("--solver", action="append", choices=SOLVER_FLAGS)
    parser.add_argument("--solver-path", action="append", default=[], help="NAME=/path/to/executable; repeatable")
    parser.add_argument("--variant", action="append", choices=VARIANTS)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10, help="seconds per checker run (default: 10)")
    parser.add_argument("--memory-limit", type=int, default=1024, help="MiB address-space cap per process (default: 1024)")
    parser.add_argument("--smoke", action="store_true", help="controls plus two tiny semantic checks; no performance thresholds")
    args = parser.parse_args()
    if args.repetitions < 1 or args.timeout <= 0 or args.memory_limit < 128:
        parser.error("positive repetitions/timeout and at least 128 MiB required")
    chosen = cases(args.family or list(KINDS), args.size, args.smoke)
    for case in chosen:
        if case.size < 1 or case.size > 4096 or (case.family.startswith("memory-") and case.size < 16):
            parser.error("sizes must be 1..4096; memory buffers must be at least 16 bytes")
        if (case.family == "multiply" and case.size > 64) or (case.family == "branches" and case.size > 16):
            parser.error("multiply width must be <=64; branch count <=16")
    output, tools = args.output_dir.resolve(), args.tools.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("output directory must be empty")
    overrides = {}
    for override in args.solver_path:
        name, separator, path = override.partition("=")
        if not separator or name not in SOLVER_FLAGS or name == "sat":
            parser.error("--solver-path expects NAME=/path for an external solver")
        overrides[name] = Path(path)
    solvers, missing = solver_profiles(args.solver or ["sat", "z3", "cvc5", "bitwuzla"], overrides, tools)
    variants = args.variant or ["plain"]
    cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")), platform.processor())
    manifest = {"host": platform.platform(), "cpu": cpu, "tools": str(tools),
                "solvers": solvers, "missing_solvers": missing, "variants": variants,
                "timeout_s": args.timeout, "memory_limit_mib": args.memory_limit,
                "repetitions": args.repetitions, "profile_validated": {}}
    rows, valid = [], {(name, variant): True for name in solvers for variant in variants}
    for index, case in enumerate(chosen):
        directory = output / case.name
        costs = build(case, directory, tools, max(30, args.timeout), args.memory_limit)
        for variant in variants:
            model = directory / "check.gb"
            pre_s = 0
            if variant == "pre-inline":
                model = directory / "inline.gb"
                cost = execute([tools / "goto-instrument", "--inline", "--validate-goto-model", directory / "check.gb", model],
                               directory, "inline", max(30, args.timeout), args.memory_limit)
                if cost["exit"] != 0 or cost["timeout"]:
                    raise RuntimeError(f"inline failed: {directory}")
                pre_s = cost["wall_s"]
            for name, solver in solvers.items():
                profile = (name, variant)
                if index >= 4 and not valid[profile]:
                    continue
                for repetition in range(args.repetitions):
                    label = f"{name}-{variant}-{repetition}"
                    helper_bound = max(16, case.size + 1) if case.family == "branches" else 16
                    checker = [tools / "cbmc", model, "--function", "harness", "--unwind", str(helper_bound),
                               "--unwinding-assertions", "--validate-goto-model", "--trace", "--verbosity", "9", "--timestamp", "monotonic",
                               *solver["flags"], *VARIANTS[variant]]
                    if case.bound is not None:
                        checker += ["--unwindset", f"asmc_target.0:{case.bound}"]
                    process = execute(checker, directory, label, args.timeout, args.memory_limit)
                    stats = measurements((directory / (label + ".log")).read_text(errors="replace"), process)
                    expected = "FAIL" if case.bad or case.bad_pointer else "INCOMPLETE" if case.short_bound else "PASS"
                    if index < 4 and (stats["status"] != expected or
                                     (case.bad and "harness.assertion.1" not in stats["failures"]) or
                                     (case.bad_pointer and not any(prop.startswith("asmc_target.asmc.") for prop in stats["failures"]))):
                        valid[profile] = False
                    row = {"case": case.name, "family": case.family, "size": case.size,
                           "memory": case.memory, "dispatch": case.dispatch, "fixed_index": case.fixed_index,
                           "bound": case.bound, "control": index < 4, "expected": expected,
                           "solver": name, "variant": variant, "repetition": repetition,
                           "model_bytes": model.stat().st_size, "build_s": sum(c["wall_s"] for c in costs.values()),
                           "preprocess_s": pre_s, **process, **stats}
                    rows.append(row)
                    with (output / "results.jsonl").open("a") as stream:
                        stream.write(json.dumps(row) + "\n")
                    manifest["profile_validated"] = {"/".join(key): value for key, value in valid.items()}
                    write_results(output, rows, manifest)
                    print(f"{case.name} {label}: {stats['status']} {process['wall_s']:.3f}s {process['rss_kib']/1024:.1f}MiB", flush=True)
    print("Results: " + str(output), flush=True)
    if not solvers or not all(valid.values()):
        raise SystemExit("one or more profiles failed semantic controls; see manifest.json")
    if args.smoke and any(row["status"] != row["expected"] for row in rows):
        raise SystemExit("smoke semantic check failed")


if __name__ == "__main__":
    main()
