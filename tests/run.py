"""End-to-end tests use the same freshly built CBMC toolchain as ASMC."""
import argparse
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, expected=0, timeout=120):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    if result.returncode != expected:
        raise AssertionError(f"{args}\nexit {result.returncode}, expected {expected}\n"
                             f"{result.stdout[-10000:]}\n{result.stderr[-10000:]}")
    return result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("lifter", type=Path)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--only", help="Run one function")
    parser.add_argument("--solver", choices=("auto", "sat", "z3", "cvc5"), default="auto",
                        help="auto uses Z3 for multiplication/bignum and SAT otherwise")
    args = parser.parse_args()
    lifter = args.lifter.resolve()
    cc, cbmc, instrument = (args.tools.resolve() / name for name in ("goto-cc", "cbmc", "goto-instrument"))
    print(run([lifter, "--version"]).strip(), flush=True)
    with tempfile.TemporaryDirectory(prefix="asmc-tests-") as temp:
        tmp = Path(temp)
        seed, elf = tmp / "seed.gb", tmp / "challenges.elf"
        run([cc, "-I", ROOT / "include", "-c", ROOT / "runtime/runtime.c", "-o", seed])
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,inc", ROOT / "tests/challenges.S", "-o", elf])
        s2n = tmp / "s2n.elf"
        run(["gcc", "-nostdlib", "-no-pie", "-DNO_IBT=1", "-Wl,-e,word_max",
             "-I", ROOT / "tests/s2n-bignum/include", ROOT / "tests/s2n-bignum/word_max.S",
             ROOT / "tests/s2n-bignum/bignum_add.S", "-o", s2n])
        cases = [
            ("inc", 1, 0), ("alias_byte", 2, 0), ("alias_word", 3, 0),
            ("alias_dword", 4, 0), ("max_signed", 5, 0), ("max_signed_cmov", 5, 0),
            ("sext", 20, 0), ("zext", 21, 0), ("mulfull", 22, 0),
            ("max_unsigned", 6, 0), ("max_unsigned_cmov", 6, 0), ("swap", 7, 0),
            ("rotate", 8, 0), ("add2", 9, 0), ("sub2", 10, 0),
            ("copy", 11, 0), ("copy_rep", 11, 0), ("search", 12, 0), ("read64", 13, 0),
            ("word_max", 6, 0),
            ("dead_unsupported", 1, 0),
            ("inc_bad", 1, 10), ("max_bad", 6, 10), ("add2_bad", 9, 10),
            ("copy_bad", 11, 10), ("copy_oob", 11, 10),
            ("read64_oob", 14, 10), ("read64_wrap", 15, 10),
            ("read64_region_wrap", 23, 10),
            ("corrupt_return", 16, 10), ("clobber_saved", 1, 10),
            ("copy_insufficient", 18, 10),
        ]
        # Partition the bounded length domain, retaining arbitrary 64-bit
        # limbs in every case. This covers exactly the same 27 length triples
        # without burdening the SAT solver with symbolic buffer indices.
        cases += [(f"bignum_add_{p}_{m}_{n}", 19, 0)
                  for p in range(3) for m in range(3) for n in range(3)]
        for name, case, expected in cases:
            if args.only and args.only != name and not name.startswith(args.only + "_"):
                continue
            start = time.monotonic()
            function = "read64" if name.startswith("read64_") else "copy" if name == "copy_insufficient" else name
            if name.startswith("bignum_add_"):
                function = "bignum_add"
            lifted, linked = tmp / f"{name}.gb", tmp / f"{name}-check.gb"
            binary = s2n if function in {"word_max", "bignum_add"} else elf
            run([lifter, binary, "--function", function, "--template", seed, "-o", lifted])
            # Read, validate, and write the GOTO object again before linking.
            roundtrip = tmp / f"{name}-roundtrip.gb"
            run([instrument, "--validate-goto-model", lifted, roundtrip])
            extra = ["-DZERO_LENGTH"] if name == "copy_bad" else []
            if function == "bignum_add":
                p, m, n = name.split("_")[-3:]
                extra += [f"-DINPUT_P={p}", f"-DINPUT_M={m}", f"-DINPUT_N={n}"]
            run([cc, "-I", ROOT / "include", f"-DCASE={case}", *extra,
                 roundtrip, ROOT / "tests/harness.c", ROOT / "tests/reference.c", "-o", linked])
            unwind = ["--unwindset", "asmc_target.0:3"] if name == "copy_insufficient" else []
            if case == 19:
                loops = re.findall(r"Loop (asmc_target\.\d+):", run([instrument, "--show-loops", linked]))
                assert loops, "expected loops in the upstream bignum routine"
                unwind = ["--unwindset", ",".join(loop + ":4" for loop in loops)]
            selected = "z3" if args.solver == "auto" and case in {19, 22} else args.solver
            solver = ["--" + selected] if selected in {"z3", "cvc5"} else []
            output = run([cbmc, linked, "--function", "harness", "--unwind", "40", *unwind,
                          *solver, "--unwinding-assertions", "--validate-goto-model", "--trace"], expected=expected)
            if expected == 0:
                assert "VERIFICATION SUCCESSFUL" in output
            else:
                assert "VERIFICATION FAILED" in output
                if name == "copy_insufficient":
                    assert "unwinding assertion" in output
                if name == "corrupt_return":
                    assert "unexpected return address" in output
            failures = [line for line in output.splitlines() if line.rstrip().endswith(": FAILURE")]
            incomplete = bool(failures) and all("unwinding assertion" in line for line in failures)
            status = "verified" if expected == 0 else "incomplete bound detected" if incomplete else "bug detected"
            if name == "copy_insufficient":
                assert incomplete, failures
            if name == "copy_bad":
                assert not incomplete and any("memory access outside RAM" in line for line in failures), failures
            print(f"PASS {name}: {status} "
                  f"({time.monotonic()-start:.1f}s)", flush=True)

        if not args.only:
            for name, diagnostic in [
                ("unsupported_div", "INT_DIV"), ("unsupported_simd", "register"),
                ("unsupported_call", "CALL"), ("unsupported_indirect", "BRANCHIND"),
                ("unsupported_tls", "segment"), ("outside_function", "range"),
                ("truncated", "extends"), ("missing_size", "no size")
            ]:
                out = tmp / "rejected.gb"
                output = run([lifter, elf, "--function", name, "--template", seed, "-o", out], expected=2)
                assert diagnostic in output, output
                assert not out.exists()
                print(f"PASS rejects {name}", flush=True)
            obj = tmp / "object.o"
            run(["gcc", "-c", ROOT / "tests/challenges.S", "-o", obj])
            output = run([lifter, obj, "--function", "inc", "--template", seed, "-o", tmp / "obj.gb"], expected=2)
            assert "relocatable ELF (.o)" in output and "Link it first:" in output
            symbols = run(["nm", elf])
            end = next(line.split()[0] for line in symbols.splitlines() if line.endswith(" missing_size_end"))
            run([lifter, elf, "--function", "missing_size", "--end-address", "0x" + end,
                 "--template", seed, "-o", tmp / "explicit.gb"])
            print("PASS ELF input and explicit range checks", flush=True)
            for source in ["void asmc_target(int *s) {}", "void other(void) {}"]:
                cfile, bad = tmp / "bad-template.c", tmp / "bad-template.gb"
                cfile.write_text(source)
                run([cc, "-c", cfile, "-o", bad])
                output = run([lifter, elf, "--function", "inc", "--template", bad,
                              "-o", tmp / "bad-output.gb"], expected=2)
                assert "template" in output
            print("PASS rejects incompatible runtime templates", flush=True)
            for compiler in ("gcc", "clang"):
                for opt in ("0", "2"):
                    kernel = tmp / f"{compiler}-O{opt}.elf"
                    run([compiler, f"-O{opt}", "-nostdlib", "-no-pie", "-fno-stack-protector",
                         "-Wl,-e,kernel", ROOT / "tests/kernel.c", "-o", kernel])
                    lifted, linked = tmp / "kernel.gb", tmp / "kernel-check.gb"
                    run([lifter, kernel, "--function", "kernel", "--template", seed, "-o", lifted])
                    run([cc, "-I", ROOT / "include", "-DCASE=17", lifted,
                         ROOT / "tests/harness.c", ROOT / "tests/reference.c", "-o", linked])
                    run([cbmc, linked, "--function", "harness", "--unwind", "40",
                         "--unwinding-assertions", "--validate-goto-model"])
                    print(f"PASS compiled kernel {compiler} -O{opt}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
