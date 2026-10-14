"""RV32/RV64 integer ABI, width, memory and rejection checks with real GCC."""
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/riscv"


def run(command, expected=0):
    result = subprocess.run([str(arg) for arg in command], capture_output=True,
                            text=True, timeout=120)
    text = result.stdout + result.stderr
    assert result.returncode == expected, f"{command}\nexit {result.returncode}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    lifter = asmc.with_name("asmc-lift")
    with tempfile.TemporaryDirectory(prefix="asmc-riscv-") as temp:
        tmp = Path(temp)

        def compile(bits, source, entry, name, opt="2", compressed=True):
            elf = tmp / (name + ".elf")
            run(["riscv64-unknown-elf-gcc", "-march=rv" + str(bits) + "im" + ("c" if compressed else ""),
                 "-mabi=" + ("ilp32" if bits == 32 else "lp64"), "-O" + opt,
                 "-DASMC_RISCV_XLEN=" + str(bits), "-fno-builtin", "-fno-stack-protector",
                 "-nostdlib", "-static", "-Wl,--no-relax,-e," + entry, source, "-o", elf])
            return elf

        def check(elf, function, case, name, expected=0, options=()):
            output = tmp / name
            text = run([asmc, elf, "--function", function, "--harness", EXAMPLES / "spec.c",
                        "--reference", EXAMPLES / "functions.c", "-DCASE=" + str(case),
                        "--unwind", "34", "--output-dir", output, "--timeout", "100", *options], expected)
            status = (output / "result.txt").read_text()
            assert status.startswith({0:"PASS:", 10:"FAIL:", 11:"INCOMPLETE:"}[expected]), text
            # Every successful lift must survive a validated serialization round-trip.
            run([asmc.parent / "goto-instrument", "--validate-goto-model", output / "lifted.gb",
                 output / "roundtrip.gb"])
            print("PASS " + name, flush=True)
            return output, text

        for bits in (32, 64):
            for opt, compressed in [("0", False), ("2", False), ("2", True)]:
                tag = f"rv{bits}-O{opt}" + ("c" if compressed else "")
                elf = compile(bits, EXAMPLES / "functions.c", "inc", tag, opt, compressed)
                for case, function in enumerate(("inc", "maximum", "shift", "multiply", "sum", "copy"), 1):
                    options = ["--unwindset", f"asmc_target.0:6,{function}.0:6"] if case >= 5 else []
                    if case == 4: options += ["--z3"]
                    check(elf, function, case, tag + "-" + function, options=options)
            elf = compile(bits, EXAMPLES / "instructions.S", "zero_test", f"rv{bits}-instructions")
            for function, case in [("zero_test", 1), ("argument32", 7), ("load32", 8), ("all_args", 11)]:
                seed, _ = check(elf, function, case, f"rv{bits}-" + function)
            obj = tmp / (f"rv{bits} object.o")
            run(["riscv64-unknown-elf-gcc", f"-march=rv{bits}imc",
                 "-mabi=" + ("ilp32" if bits == 32 else "lp64"), "-c",
                 EXAMPLES / "instructions.S", "-o", obj])
            text = run([lifter, obj, "--function", "zero_test", "--template", seed / "seed.gb",
                        "-o", tmp / "reject-object.gb"], 2)
            command = next(line.strip() for line in text.splitlines() if line.startswith("  riscv64-unknown-elf-ld "))
            run(shlex.split(command))
            run([lifter, obj.with_suffix(".elf"), "--function", "zero_test", "--template", seed / "seed.gb",
                 "-o", tmp / f"rv{bits}-linked.gb"])
            print(f"PASS rv{bits} relocatable suggestion", flush=True)
            for function in ("bad_return", "bad_saved", "bad_gp", "bad_tp", "bad_s11", "bad_sp"):
                # CASE=0 asks only the return and ABI obligations, not a functional result.
                _, text = check(elf, function, 0, f"rv{bits}-" + function, 10)
                assert "unexpected return address" in text or "asmc_riscv_check" in text, text
            if bits == 32:
                _, text = check(elf, "load32", 9, "rv32-address-wrap", 10)
                assert "RAM region wraps" in text or "memory access wraps" in text, text
                _, text = check(elf, "load32", 12, "rv32-access-wrap", 10)
                assert "memory access wraps" in text, text
            else:
                check(elf, "add_word", 10, "rv64-addiw")
            for function, opcode in [("divide", "INT_SDIV"), ("indirect", "BRANCHIND"), ("caller", "CALL")]:
                output = tmp / (f"rv{bits}-reject-" + function + ".gb")
                text = run([lifter, elf, "--function", function, "--template", seed / "seed.gb", "-o", output], 2)
                assert opcode in text and not output.exists(), text
                print(f"PASS rv{bits} rejects {function}", flush=True)
            # A corrupted implementation must differ from the unchanged C reference.
            bad = tmp / (f"rv{bits}-bad.c")
            bad.write_text((EXAMPLES / "functions.c").read_text().replace("return x + 1", "return x + 2"))
            bad_elf = compile(bits, bad, "inc", f"rv{bits}-bad")
            check(bad_elf, "inc", 1, f"rv{bits}-wrong-result", 10)
            sum_elf = compile(bits, EXAMPLES / "functions.c", "sum", f"rv{bits}-short")
            check(sum_elf, "sum", 5, f"rv{bits}-incomplete", 11,
                  ["--unwindset", "asmc_target.0:2,sum.0:6"])
            if bits == 32:
                wrong = tmp / "wrong-width.gb"
                run([asmc.parent / "goto-cc", "-m64", "-I", ROOT / "include", "-c",
                     ROOT / "runtime/runtime.c", "-o", wrong])
                text = run([lifter, elf, "--function", "zero_test", "--template", wrong,
                            "-o", tmp / "mismatch.gb"], 2)
                assert "pointer width" in text and not (tmp / "mismatch.gb").exists(), text
                print("PASS rejects mismatched template", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
