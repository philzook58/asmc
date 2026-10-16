"""Compiler-to-C checks and ABI regressions adapted from pcode2c examples."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/pcode2c"


def run(command, expected=0):
    result = subprocess.run([str(arg) for arg in command], capture_output=True,
                            text=True, timeout=100)
    text = result.stdout + result.stderr
    assert result.returncode == expected, f"{command}\nexit {result.returncode}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    lifter = asmc.with_name("asmc-lift")
    with tempfile.TemporaryDirectory(prefix="asmc-pcode2c-") as temp:
        tmp = Path(temp)

        def compile(source, function, name, compiler="gcc", opt="0"):
            elf = tmp / (name + ".elf")
            run([compiler, "-O" + opt, "-nostdlib", "-no-pie", "-fno-stack-protector",
                 "-fcf-protection=none", "-fno-tree-vectorize", "-fno-optimize-sibling-calls",
                 "-Wl,-e," + function, source, "-o", elf])
            return elf

        def check(elf, function, name, harness, reference=None, options=(), expected=0):
            output = tmp / name
            command = [asmc, elf, "--function", function, "--harness", harness,
                       "--output-dir", output, "--timeout", "90", *options]
            if reference:
                command += ["--reference", reference]
            text = run(command, expected)
            status = (output / "result.txt").read_text().strip()
            assert status.startswith({0: "PASS:", 10: "FAIL:", 11: "INCOMPLETE:"}[expected]), text
            print(f"PASS {name}: {status}", flush=True)
            return text

        cases = [("min", "mymin"), ("factorial", "fact"), ("equal", "equal")]
        binaries = {}
        for compiler in ("gcc", "clang"):
            for opt in ("0", "2"):
                for stem, function in cases:
                    name = f"{stem}-{compiler}-O{opt}"
                    source = EXAMPLES / (stem + ".c")
                    elf = compile(source, function, name, compiler, opt)
                    binaries[stem, compiler, opt] = elf
                    options = ["--unwindset", "asmc_target.0:10,equal.0:10"] if stem == "equal" else []
                    check(elf, function, name, EXAMPLES / (stem + "_spec.c"), source, options)

        assembly = EXAMPLES / "cmpxchg.S"
        cmp_elf = compile(assembly, "compare_exchange", "cmpxchg")
        cmp_spec = EXAMPLES / "cmpxchg_spec.c"
        check(cmp_elf, "compare_exchange", "cmpxchg", cmp_spec)

        # The compiled implementation is wrong; the linked C reference stays unchanged.
        mutations = [
            ("min", "mymin", "x < y", "x > y"),
            ("factorial", "fact", "result * x", "result + x"),
            ("equal", "equal", "a[i] != b[i]", "a[i] == b[i]"),
        ]
        for stem, function, before, after in mutations:
            source = tmp / (stem + "_bad.c")
            original = EXAMPLES / (stem + ".c")
            assert before in original.read_text()
            source.write_text(original.read_text().replace(before, after))
            elf = compile(source, function, stem + "_bad")
            options = ["--unwindset", "asmc_target.0:10,equal.0:10"] if stem == "equal" else []
            check(elf, function, stem + "_bad", EXAMPLES / (stem + "_spec.c"),
                  original, options, 10)

        for name, instruction in [("saved_register", "mov $0,%rbx\n  ret"),
                                  ("stack_cleanup", "ret $8"), ("direction_flag", "std\n  ret")]:
            source = tmp / (name + ".S")
            source.write_text(assembly.read_text().replace("\n  ret\n", "\n  " + instruction + "\n"))
            elf = compile(source, "compare_exchange", name)
            text = check(elf, "compare_exchange", name, cmp_spec, expected=10)
            assert "asmc_sysv_check" in text, text

        # Only AL carries a _Bool result; dirty higher bits are deliberately retained.
        bool_spec = tmp / "bool_spec.c"
        bool_spec.write_text('''#include "asmc_x86.h"
#include <assert.h>
void harness(void) {
  uint8_t ram[256]; struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model_at(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  asmc_target(&s);
  assert(asmc_sysv_result_bool(&s) == EXPECTED_BOOL);
  asmc_sysv_check(&s, &frame);
}
''')
        for value, expected in [(0, 0), (1, 0), (2, 10)]:
            name = "bool_low_byte_" + str(value)
            source = tmp / (name + ".S")
            source.write_text(".text\n.globl result\n.type result,@function\nresult:\n"
                              f"movabs $0xfedcba987654320{value},%rax\nret\n"
                              '.size result,.-result\n.section .note.GNU-stack,"",@progbits\n')
            elf = compile(source, "result", name)
            check(elf, "result", name, bool_spec,
                  options=["-DEXPECTED_BOOL=" + str(value != 0).lower()], expected=expected)

        check(binaries["equal", "gcc", "0"], "equal", "equal_insufficient",
              EXAMPLES / "equal_spec.c", EXAMPLES / "equal.c",
              ["--unwindset", "asmc_target.0:3,equal.0:10"], 11)

        elf = compile(EXAMPLES / "fact_recursive.c", "fact_recursive", "fact_recursive")
        recursive_spec = tmp / "recursive_spec.c"
        recursive_spec.write_text((EXAMPLES / "factorial_spec.c").read_text().replace("x <= 12", "x <= 3"))
        check(elf, "fact_recursive", "recursive_factorial", recursive_spec,
              EXAMPLES / "factorial.c", ["--unwindset", "asmc_target.0:8", "--memory-limit", "2048"])
        elf = compile(EXAMPLES / "unsupported.c", "is_prime", "unsupported")
        text = run([lifter, elf, "--function", "is_prime", "--template", tmp / "cmpxchg/seed.gb",
                    "-o", tmp / "is_prime.gb"], 2)
        assert "INT_SDIV" in text, text
        assert not (tmp / "is_prime.gb").exists()
        print("PASS rejects is_prime: INT_SDIV", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
