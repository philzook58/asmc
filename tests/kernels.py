"""Real compiler and assembly checks for the explanatory kernel examples."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/kernels"


def run(command, expected=0):
    process = subprocess.run([str(arg) for arg in command], capture_output=True,
                             text=True, timeout=120)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="asmc-kernels-") as temp:
        tmp = Path(temp)

        def check(source, function, harness, name, compiler="gcc", options=(), expected=0):
            elf, output = tmp / (name + ".elf"), tmp / name
            run([compiler, "-O2", "-nostdlib", "-no-pie", "-fno-stack-protector",
                 "-fcf-protection=none", "-fno-tree-vectorize", "-Wl,-e," + function,
                 source, "-o", elf])
            text = run([asmc, elf, "--function", function, "--harness", harness,
                        "--reference", EXAMPLES / "kernels.c", "--unwind", "66",
                        "--output-dir", output, "--timeout", "100", *options], expected)
            assert (output / "result.txt").read_text().startswith("PASS:" if expected == 0 else "FAIL:"), text
            print("PASS " + name, flush=True)

        for compiler in ("gcc", "clang"):
            for function, harness, options in [
                ("count_bits", "scalar_spec.c", []),
                ("choose", "scalar_spec.c", ["-DSELECT"]),
                ("sum_words", "memory_spec.c", ["--unwindset", "asmc_target.0:6,sum_words.0:6"]),
                ("swap_words", "memory_spec.c", ["-DSWAP"]),
            ]:
                check(EXAMPLES / "kernels.c", function, EXAMPLES / harness,
                      function + "-" + compiler, compiler, options)

        for function, options in [("count_bits_fast", []), ("choose_fast", ["-DSELECT"])]:
            check(EXAMPLES / "optimized.S", function, EXAMPLES / "scalar_spec.c", function,
                  options=options)

        # Incorrect optimized instruction and arithmetic/memory mutations must fail.
        bad_asm = tmp / "bad.S"
        bad_asm.write_text((EXAMPLES / "optimized.S").read_text().replace("cmovne", "cmove"))
        check(bad_asm, "choose_fast", EXAMPLES / "scalar_spec.c", "choose_bad",
              options=["-DSELECT"], expected=10)
        for function, before, after, options in [
            ("count_bits", "i < 64", "i < 63", []),
            ("sum_words", "sum += data[i]", "sum ^= data[i]",
             ["--unwindset", "asmc_target.0:6,sum_words.0:6"]),
            ("swap_words", "*b = old_a", "*b = old_b", ["-DSWAP"]),
        ]:
            bad = tmp / (function + "_bad.c")
            bad.write_text((EXAMPLES / "kernels.c").read_text().replace(before, after))
            harness = "scalar_spec.c" if function == "count_bits" else "memory_spec.c"
            check(bad, function, EXAMPLES / harness, function + "_bad", options=options, expected=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
