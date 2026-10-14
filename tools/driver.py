"""Compose the existing tools with an explicit or generated C harness."""
import argparse
from collections import deque
import os
from pathlib import Path
import re
import resource
import shlex
import signal
import subprocess
import sys
import tempfile
from demo import generate

ROOT = Path(__file__).resolve().parents[1]


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def print_counterexample(text, source_files, listing, full=False, first_only=False, demo=None):
    start = re.search(r"^Trace for .*:$", text, re.MULTILINE)
    if not start:
        return
    trace = text[start.start():]
    if full:
        print(trace, end="")
        return
    if first_only:
        # Invalid byte accesses often yield many follow-on properties. Preserve
        # all of them in the log, but lead with one actionable counterexample.
        first_line = trace.find("\n") + 1
        following = re.search(r"^Trace for .*:$", trace[first_line:], re.MULTILINE)
        if following:
            trace = trace[:first_line + following.start()]
    label = "first failing property; " if first_only else ""
    print("Counterexample (" + label + "harness/reference values; use --full-trace for machine steps):")
    instructions = listing.read_text().splitlines()
    recent = deque(maxlen=6)
    # Keep CBMC's state/value format, omitting helper and p-code temporaries.
    # Always retain violated properties, including failures inside the machine model.
    for block in re.split(r"\n\s*\n", trace):
        if block.startswith("Violated property:"):
            if recent:
                print("  Recent machine instructions:")
                for instruction in recent:
                    print("    " + instruction)
            recent.clear()
            print(block + "\n")
        elif block.startswith("Trace for "):
            recent.clear()
            print(block + "\n")
        elif block.startswith("State ") and "file " + str(listing) + " function " in block:
            location = re.search(r" line (\d+) thread", block.splitlines()[0])
            if location and 0 < int(location[1]) <= len(instructions):
                instruction = re.sub(r" pcode\[\d+\]", "", instructions[int(location[1])-1])
                instruction = re.sub(r" \([A-Z_]+\)$", "", instruction)
                if not recent or recent[-1] != instruction:
                    recent.append(instruction)
        elif block.startswith("State ") and any("file " + str(path) + " function " in block for path in source_files):
            lines = block.splitlines()
            if len(lines) >= 3 and "={" not in lines[2]:
                value = re.sub(r" \([01 ]+\)$", "", lines[2].strip())
                if ".preserved[" in value or ".stack_pointer=" in value or "=&" in value:
                    continue
                location = re.search(r"file (.*?) function .* line (\d+) thread", lines[0])
                if location:
                    if demo and Path(location[1]) == demo and not value.startswith(("in.", "out.")):
                        continue
                    print(f"  {Path(location[1]).name}:{location[2]}  {value[:240]}" + (" ..." if len(value) > 240 else ""))


def main(version):
    parser = argparse.ArgumentParser(
        prog="asmc",
        description="Lift an ELF function, link a C harness, and run CBMC.",
        epilog="Example: asmc build/demo/inc.elf --function inc "
               "--post 'out.rax == in.rdi + 1'")
    parser.add_argument("--version", action="version", version="ASMC " + version)
    parser.add_argument("elf", type=Path, help="linked x86-64 or RV32/RV64 ELF containing the function")
    parser.add_argument("--function", required=True, help="ELF symbol to lift")
    parser.add_argument("--target", default="asmc_target", help="name of the lifted GOTO function (default: asmc_target)")
    parser.add_argument("--callee", action="append", default=[], help="admit another ELF function for direct calls/tail calls; repeatable")
    parser.add_argument("--memory", choices=("ram", "objects"), default="ram",
                        help="data address scheme: numeric RAM or encoded CBMC object pointers (default: ram)")
    parser.add_argument("--rodata", action="store_true", help="map ELF .rodata sections as immutable machine memory")
    parser.add_argument("--indirect-target", action="append", default=[], help="allowed indirect-jump symbol/address inside admitted functions; repeatable")
    parser.add_argument("--dispatch", action="store_true",
                        help="join native branches in one dispatch loop; unwind counts basic blocks")
    parser.add_argument("--scalar-registers", action="store_true",
                        help="experimental: use scalarizable register words, preserving byte aliases")
    parser.add_argument("--harness", type=Path, help="C harness (default: generate a stack/ABI harness)")
    parser.add_argument("--pre", action="append", default=[],
                        help="C assumption over entry registers in.REG; repeatable; default harness only")
    parser.add_argument("--post", action="append", default=[],
                        help="C assertion over in.REG/out.REG; repeatable; default harness only")
    parser.add_argument("--stack-size", type=positive,
                        help="default harness stack capacity in bytes (default: 256, minimum: 16)")
    parser.add_argument("--reference", action="append", type=Path, default=[],
                        help="additional C source or GOTO object; repeat for multiple files")
    parser.add_argument("--entry", default="harness", help="C entry function (default: harness)")
    parser.add_argument("--unwind", type=positive, default=40, help="loop bound (default: 40)")
    parser.add_argument("--object-bits", type=positive, help="CBMC bits reserved for pointer object identifiers")
    parser.add_argument("--max-field-sensitivity-array-size", type=int,
                        help="CBMC array scalarization threshold (default: 64; 0 disables); try 768 for call dispatch")
    parser.add_argument("--unwindset", help="CBMC per-loop bounds, e.g. asmc_target.0:3")
    parser.add_argument("--full-trace", action="store_true", help="print all CBMC machine/helper steps on failure")
    inspection = parser.add_mutually_exclusive_group()
    inspection.add_argument("--show-loops", action="store_true", help="list loop IDs without checking")
    inspection.add_argument("--show-properties", action="store_true", help="list obligations without checking")
    for option, help_text in (("trace-hex", "display trace values in hexadecimal"),
                              ("compact-trace", "display a compact counterexample"),
                              ("beautify", "try to simplify counterexample values"),
                              ("slice-formula", "remove assignments unrelated to properties")):
        parser.add_argument("--" + option, action="store_true", help=help_text)
    solvers = parser.add_mutually_exclusive_group()
    solvers.add_argument("--z3", action="store_true", help="use CBMC's Z3 backend")
    solvers.add_argument("--cvc5", action="store_true", help="use CBMC's cvc5 backend")
    solvers.add_argument("--bitwuzla", action="store_true", help="use CBMC's Bitwuzla backend")
    solvers.add_argument("--external-sat-solver", type=Path, help="external SAT solver executable, e.g. kissat")
    parser.add_argument("--solver-path", type=Path,
                        help="SMT solver executable (otherwise found on PATH)")
    parser.add_argument("-I", dest="includes", action="append", type=Path, default=[])
    parser.add_argument("-D", dest="defines", action="append", default=[])
    parser.add_argument("-o", "--output-dir", type=Path,
                        help="empty output directory (default: a new directory under asmc-out)")
    parser.add_argument("--timeout", type=positive, default=300,
                        help="seconds allowed per tool (default: 300)")
    parser.add_argument("--memory-limit", type=positive,
                        help="address-space limit in MiB per tool/solver process")
    for option in ("end-address", "sla", "pspec"):
        parser.add_argument("--" + option, help="forwarded to the lifter")
    parser.add_argument("--lifter", type=Path,
                        default=Path(sys.argv[0]).resolve().with_name("asmc-lift"),
                        help="lifter executable (default: asmc-lift alongside this driver)")
    args = parser.parse_args()
    if args.harness and (args.pre or args.post or args.stack_size is not None):
        parser.error("--pre, --post, and --stack-size apply only to the default harness; omit --harness")
    if args.stack_size is not None and args.stack_size < 16:
        parser.error("--stack-size must be at least 16")
    if not args.harness and not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", args.entry):
        parser.error("--entry must be a C identifier for the default harness")
    if args.memory == "objects" and args.rodata:
        parser.error("--memory objects cannot be combined with --rodata; no ELF data fallback")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", args.target):
        parser.error("--target must be a C identifier")
    if args.solver_path and not (args.z3 or args.cvc5 or args.bitwuzla):
        parser.error("--solver-path requires --z3, --cvc5, or --bitwuzla")
    if args.max_field_sensitivity_array_size is not None and args.max_field_sensitivity_array_size < 0:
        parser.error("--max-field-sensitivity-array-size must be nonnegative")
    lifter = args.lifter.resolve()
    cc, cbmc = (lifter.parent / name for name in ("goto-cc", "cbmc"))
    for path in (args.elf, *([args.harness] if args.harness else []), *args.reference, lifter, cc, cbmc):
        if not path.is_file():
            parser.error(f"file not found: {path}; build the asmc-tools target first")

    if args.output_dir:
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            parser.error(f"output directory must be empty: {output}")
    else:
        parent = Path("asmc-out").resolve()
        parent.mkdir(exist_ok=True)
        prefix = re.sub(r"[^A-Za-z0-9_.-]", "_", args.function) + "-"
        output = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    print(f"Output: {output}", flush=True)

    def result(status, detail, code):
        message = f"{status}: {detail}"
        (output / "result.txt").write_text(message + "\n")
        print(message, flush=True)
        return code

    def resource_guidance(text):
        lines = text.splitlines()
        progress = [line for line in lines if line.startswith((
            "Starting Bounded", "Passing problem", "converting SSA", "Running "))]
        if progress:
            print("Last checker progress: " + progress[-1])
        print("Try smaller RAM and checked per-loop bounds, --slice-formula, or another solver (--bitwuzla/--z3/--cvc5).")
        print("For call/dispatch models, compare --scalar-registers with a field threshold covering the stack "
              "(e.g. --max-field-sensitivity-array-size 128), or 768 with the default register bank. "
              "For symbolic buffers, compare 0 with the default 64; measure these tradeoffs.")

    def run(stage, command):
        command = [str(arg) for arg in command]
        with (output / "commands.txt").open("a") as commands:
            commands.write(shlex.join(command) + "\n")
        log = output / (stage + ".log")
        print(f"{stage}: {log}", flush=True)
        with log.open("w") as stream:
            def limit_memory():
                limit = args.memory_limit * 1024**2
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True,
                                       preexec_fn=limit_memory if args.memory_limit else None)
            try:
                process.wait(timeout=args.timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                # Also stop descendants such as an external SMT solver.
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        text = log.read_text(errors="replace")
        for line in text.splitlines():
            if line.startswith("ASMC warning:"):
                print(line, flush=True)
        if stage != "cbmc" and process.returncode != 0:
            print("\n".join(text.splitlines()[-40:]), file=sys.stderr)
            raise RuntimeError(f"{stage} exited {process.returncode}; see {log}")
        return process.returncode, text

    try:
        seed, lifted, linked = (output / name for name in ("seed.gb", "lifted.gb", "check.gb"))
        compile_options = ["-I", ROOT / "include", "-DASMC_TARGET=" + args.target]
        if args.scalar_registers:
            compile_options.append("-DASMC_SCALAR_REGISTERS")
        if args.memory == "objects":
            compile_options.append("-DASMC_OBJECT_MEMORY")
        with args.elf.open("rb") as stream:
            header = stream.read(20)
        architecture, bits = None, None
        if len(header) == 20 and header[:4] == b"\x7fELF" and header[5] == 1:
            machine = int.from_bytes(header[18:20], "little")
            if machine == 243 and header[4] in (1, 2):
                architecture, bits = "riscv", 32 if header[4] == 1 else 64
            elif machine == 62 and header[4] == 2:
                architecture, bits = "x86", 64
        if architecture == "riscv":
            compile_options += ["-m" + str(bits), "-funsigned-char", "-DASMC_RISCV_XLEN=" + str(bits)]
        harness = args.harness.resolve() if args.harness else output / "demo.c"
        if not args.harness:
            if architecture is None:
                raise RuntimeError("default harness requires a little-endian x86-64 or RV32/RV64 ELF")
            harness.write_text(generate(architecture, bits, args.entry, args.stack_size or 256,
                                        args.pre, args.post))
            abi_name = "x86-64 SysV" if architecture == "x86" else f"RV{bits}"
            print(f"Harness: {harness} ({abi_name})", flush=True)
            if args.post:
                print(f"Checking: {len(args.post)} postcondition(s), safety and scalar ABI obligations.", flush=True)
            else:
                print("Checking: safety and scalar ABI obligations only (no --post).", flush=True)
        for include in args.includes:
            compile_options += ["-I", include.resolve()]
        compile_options += ["-D" + define for define in args.defines]
        run("seed", [cc, *compile_options, "-c", ROOT / "runtime/runtime.c", "-o", seed])
        lift_options = ["--memory", args.memory]
        if args.rodata:
            lift_options.append("--rodata")
        for target in args.indirect_target:
            lift_options += ["--indirect-target", target]
        if args.dispatch:
            lift_options.append("--dispatch")
        for callee in args.callee:
            lift_options += ["--callee", callee]
        for option in ("end-address", "sla", "pspec"):
            value = getattr(args, option.replace("-", "_"))
            if value is not None:
                lift_options += ["--" + option, value]
        run("lift", [lifter, args.elf.resolve(), "--function", args.function,
                     "--target", args.target, "--template", seed, "-o", lifted, *lift_options])
        run("link", [cc, *compile_options, lifted, harness,
                     *(path.resolve() for path in args.reference), "-o", linked])
        solver_options = []
        for name in ("z3", "cvc5", "bitwuzla"):
            if getattr(args, name):
                solver_options.append("--" + name)
        if args.external_sat_solver:
            solver_options += ["--external-sat-solver", args.external_sat_solver.resolve()]
        if args.solver_path:
            solver_options += ["--external-smt2-solver", args.solver_path.resolve()]
        if args.object_bits:
            solver_options += ["--object-bits", args.object_bits]
        if args.max_field_sensitivity_array_size is not None:
            solver_options += ["--max-field-sensitivity-array-size", args.max_field_sensitivity_array_size]
        if args.unwindset:
            solver_options += ["--unwindset", args.unwindset]
        for option in ("trace-hex", "compact-trace", "beautify", "slice-formula"):
            if getattr(args, option.replace("-", "_")):
                solver_options.append("--" + option)
        inspection = "--show-loops" if args.show_loops else "--show-properties" if args.show_properties else None
        if inspection:
            code, text = run("cbmc", [cbmc, linked, "--function", args.entry, inspection,
                                      "--unwinding-assertions", "--validate-goto-model"])
            print(text, end="")
            return result("INSPECT" if code == 0 else "ERROR",
                          "listing only; no verification performed" if code == 0 else
                          f"inspection exited {code}", 0 if code == 0 else 2)
        if args.memory == "objects":
            solver_options.append("--pointer-check")
        code, text = run("cbmc", [cbmc, linked, "--function", args.entry,
                                  "--unwind", args.unwind, *solver_options,
                                  "--unwinding-assertions", "--validate-goto-model", "--trace"])
        failures = re.findall(r"^\[([^\]\n]+)\] (.*): FAILURE$", text, re.MULTILINE)
        if code == 0 and "VERIFICATION SUCCESSFUL" in text and not failures:
            detail = "all checked properties passed with unwinding assertions"
            if not args.harness and not args.post:
                detail += "; safety/ABI only, no functional postcondition"
            return result("PASS", detail, 0)
        if code == 6 and "out of memory" in text.lower():
            resource_guidance(text)
            return result("INCOMPLETE", "checker exhausted memory; reduce RAM/bounds or try --z3; see cbmc.log", 11)
        if code == 10 and failures and "VERIFICATION FAILED" in text:
            missing = [prop.split(".no-body.", 1)[1] for prop, _ in failures if ".no-body." in prop]
            if missing:
                for name in missing:
                    print("Missing C definition: " + name)
                return result("ERROR", "link missing implementations with --reference FILE.c or FILE.gb; see cbmc.log", 2)
            # Classify using property IDs, not assertion descriptions supplied by users.
            unwinds = [bool(re.search(r"\.unwind\.\d+$|\.recursion$", prop))
                       for prop, _ in failures]
            brief_objects = args.memory == "objects" and not (args.full_trace or args.compact_trace)
            shown = failures[:5] if brief_objects else failures
            for prop, description in shown:
                print(f"  [{prop}] {description}")
                line = re.search(r"\bline (\d+)\b", description)
                if prop.startswith(args.target + ".") and line:
                    listing = Path(str(lifted) + ".asm").read_text().splitlines()
                    if 0 < int(line[1]) <= len(listing):
                        print("    Machine: " + listing[int(line[1])-1])
            if len(shown) < len(failures):
                print(f"  {len(failures) - len(shown)} more failed properties; see cbmc.log or --full-trace.")
            if args.memory == "objects" and any(
                    "invalid CBMC object" in description or "__CPROVER_r_ok" in description or
                    "__CPROVER_w_ok" in description for _, description in failures):
                print("Object mode requires encoded C pointers: check allocation lifetime, complete access bounds, "
                      "and pointer truncation. Fixed ELF data addresses are not mapped in this mode.")
                print("For setup, use the ABI's *_enter_objects stack helper and *_arg_ptr pointer arguments.")
            print_counterexample(text, [harness, *(path.resolve() for path in args.reference)],
                                 Path(str(lifted) + ".asm"), full=args.full_trace or args.compact_trace,
                                 first_only=brief_objects, demo=harness if not args.harness else None)
            print(f"Trace and details: {output / 'cbmc.log'}")
            if any(unwinds):
                loops = [prop.rsplit(".unwind.", 1) for prop, _ in failures if ".unwind." in prop]
                if loops:
                    print("Loop bounds apply to GOTO backedges, not necessarily source-loop iterations.")
                    print("Inspect with --show-loops; adjust --unwindset for " +
                          ", ".join(function + "." + number for function, number in loops) + ".")
                    if not args.dispatch:
                        print("For tangled native loops, try --dispatch with a basic-block bound.")
            if all(unwinds):
                return result("INCOMPLETE", "insufficient unwinding; increase the bound", 11)
            detail = "counterexample found"
            if any(unwinds):
                detail += "; unwinding is also insufficient"
            return result("FAIL", detail, 10)
        print("\n".join(text.splitlines()[-40:]), file=sys.stderr)
        return result("ERROR", f"unexpected checker result (exit {code}); see cbmc.log", 2)
    except subprocess.TimeoutExpired as error:
        status, code = ("INCOMPLETE", 11) if Path(error.cmd[0]) == cbmc else ("ERROR", 2)
        if code == 11:
            resource_guidance((output / "cbmc.log").read_text(errors="replace"))
        return result(status, f"tool timed out after {args.timeout}s; no verification result", code)
    except (OSError, RuntimeError) as error:
        return result("ERROR", str(error), 2)
    except KeyboardInterrupt:
        return result("INCOMPLETE", "interrupted; no verification result", 130)
