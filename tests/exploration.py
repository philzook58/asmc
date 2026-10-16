"""Upstream algorithms, native assembly, C contracts, and deliberate mutations."""
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/exploration"


def run(command, expected=0):
    process = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=70)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text}"
    return text


def main():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    asmc = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="asmc-exploration-") as directory:
        tmp = Path(directory)

        def compile(source, function, tag, arch="x86", compiler="gcc", opt="2"):
            elf = tmp / (tag + ".elf")
            flags = ["-no-pie", "-fcf-protection=none"] if arch == "x86" else [
                "-march=" + arch + "imc", "-mabi=" + ("ilp32" if arch == "rv32" else "lp64")]
            cc = compiler if arch == "x86" else "riscv64-unknown-elf-gcc"
            flags += ["-O" + opt, "-nostdlib", "-static", "-fno-builtin", "-fno-stack-protector"]
            if cc != "clang": flags += ["-fno-tree-vectorize", "-fno-tree-loop-distribute-patterns"]
            else: flags += ["-fno-vectorize", "-fno-slp-vectorize"]
            run([cc, *flags, "-Wl,-e," + function, source, "-o", elf])
            return elf

        def check(elf, function, harness, name, options=(), expected=0, references=()):
            output = tmp / name
            text = run([asmc, elf, "--function", function, "--harness", EXAMPLE / harness,
                        "--reference", EXAMPLE / "reference.c", "--unwind", "18", "--timeout", "55",
                        "--memory-limit", "2048", "--output-dir", output,
                        *[item for source in references for item in ("--reference", source)], *options], expected)
            assert (output / "result.txt").read_text().startswith({0:"PASS:", 10:"FAIL:", 11:"INCOMPLETE:"}[expected])
            run([asmc.parent / "goto-instrument", "--validate-goto-model", output / "lifted.gb", output / "roundtrip.gb"])
            print("PASS " + name, flush=True)
            return text

        architectures = ["x86"]
        if shutil.which("riscv64-unknown-elf-gcc"): architectures += ["rv32", "rv64"]
        for arch in architectures:
            source = EXAMPLE / "aws-c-common/saturating.c"
            elf = compile(source, "saturating_add", "sat-" + arch, arch)
            check(elf, "saturating_add", "scalar_spec.c", "sat-" + arch)
            source = EXAMPLE / "acsl-by-example/lower_bound.c"
            elf = compile(source, "lower_bound", "search-" + arch, arch)
            options = ["--dispatch", "--unwindset", "asmc_target.0:12,linear_lower_bound.0:5"]
            # Scalarize the RV64 register bank and 128-byte RAM to avoid a
            # costly array encoding, keeping all inputs and bounds unchanged.
            if arch == "rv64":
                options += ["--scalar-registers", "--max-field-sensitivity-array-size", "128"]
            check(elf, "lower_bound", "search_spec.c", "search-" + arch, options)
            if arch == "rv64":
                source = EXAMPLE / "simdjson/swar.c"
                elf = compile(source, "parse_eight", "swar-rv64", arch)
                check(elf, "parse_eight", "scalar_spec.c", "swar-rv64", ["-DDIGITS"], references=[source])

        for compiler in ("gcc", "clang"):
            source = EXAMPLE / "simdjson/swar.c"
            elf = compile(source, "parse_eight", "swar-" + compiler, compiler=compiler)
            check(elf, "parse_eight", "scalar_spec.c", "swar-" + compiler,
                  ["-DDIGITS"], references=[source])
            source = EXAMPLE / "rpn.c"
            elf = compile(source, "rpn", "rpn-" + compiler, compiler=compiler, opt="0")
            check(elf, "rpn", "rpn_spec.c", "rpn-" + compiler,
                  ["--unwindset", "asmc_target.0:6,rpn.0:6"], references=[source])

        asm = compile(EXAMPLE / "scalar.S", "saturating_add_asm", "scalar-asm")
        check(asm, "saturating_add_asm", "scalar_spec.c", "sat-asm", ["--dispatch", "--unwindset", "asmc_target.0:4"])
        check(asm, "parse_eight_asm", "scalar_spec.c", "swar-asm", ["-DDIGITS"],
              references=[EXAMPLE / "simdjson/swar.c"])
        check(asm, "parse_eight_asm", "scalar_spec.c", "swar-four-digit-contract",
              ["-DDIGITS", "-DDIGIT_CONTRACT"], references=[EXAMPLE / "simdjson/swar.c"])
        rpn = compile(EXAMPLE / "rpn.S", "rpn_asm", "rpn-asm")
        check(rpn, "rpn_asm", "rpn_spec.c", "rpn-asm", ["--unwindset", "asmc_target.0:6,rpn.0:6"],
              references=[EXAMPLE / "rpn.c"])

        for name, source, function, before, after, harness, options, refs in [
            ("sat-bad", EXAMPLE / "scalar.S", "saturating_add_asm", "jnc", "jc", "scalar_spec.c", [], []),
            ("swar-bad", EXAMPLE / "scalar.S", "parse_eight_asm", "$2561", "$2562", "scalar_spec.c", ["-DDIGITS"], [EXAMPLE / "simdjson/swar.c"]),
            ("rpn-bad", EXAMPLE / "rpn.S", "rpn_asm", "add %eax", "sub %eax", "rpn_spec.c", ["--unwindset", "asmc_target.0:6,rpn.0:6"], [EXAMPLE / "rpn.c"]),
            ("search-bad", EXAMPLE / "acsl-by-example/lower_bound.c", "lower_bound", "a[middle] < v", "a[middle] <= v", "search_spec.c", ["--dispatch", "--unwindset", "asmc_target.0:12"], []),
        ]:
            bad = tmp / (name + source.suffix)
            assert before in source.read_text()
            bad.write_text(source.read_text().replace(before, after))
            elf = compile(bad, function, name)
            text = check(elf, function, harness, name, options, 10, refs)
            assert "Recent machine instructions:" in text

        source = EXAMPLE / "acsl-by-example/lower_bound.c"
        elf = compile(source, "lower_bound", "search-bound")
        text = check(elf, "lower_bound", "search_spec.c", "search-incomplete",
                     ["--dispatch", "--unwindset", "asmc_target.0:1"], 11)
        assert "asmc_target.unwind.0" in text and "Machine: 0x" in text and "--show-loops" in text

    return 0


if __name__ == "__main__":
    sys.exit(main())
