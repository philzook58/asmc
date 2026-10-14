"""Run existing semantic/oracle suites with scalarizable register words.

Small tool wrappers select the encoding for both driver and low-level workflows;
the assertions and negative examples stay identical to the flat-bank tests.
"""
import argparse
from pathlib import Path
import resource
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("challenges", "demo", "calls", "objects", "native", "switch", "riscv", "compose", "cbat")


def run(command, expected=0):
    process = subprocess.run([str(arg) for arg in command], text=True, capture_output=True, timeout=180)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\n{text}"
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asmc", type=Path)
    parser.add_argument("--suite", action="append", choices=SUITES)
    parser.add_argument("--object-solver", choices=("sat", "z3", "cvc5", "bitwuzla"), default="z3",
                        help="backend for object-mode driver checks (default: z3)")
    args = parser.parse_args()
    # Inherited by low-level CBMC invocations as well as the public driver.
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    real_tools = args.asmc.resolve().parent
    print(f"Register-word tests: existing backends; object-mode driver checks use {args.object_solver}", flush=True)
    with tempfile.TemporaryDirectory(prefix="asmc-scalar-") as directory:
        tmp = Path(directory)
        tools = tmp / "bin"
        tools.mkdir()
        for name in ("asmc", "goto-cc", "asmc-lift", "cbmc", "goto-instrument"):
            path = tools / name
            if name in ("asmc", "goto-cc"):
                flags = ["--scalar-registers"] if name == "asmc" else ["-DASMC_SCALAR_REGISTERS"]
                solver = ["--" + args.object_solver] if args.object_solver != "sat" else []
                local_solver = ROOT / ".venv/bin" / args.object_solver
                if solver and local_solver.is_file():
                    solver += ["--solver-path", str(local_solver)]
                path.write_text(f"#!{sys.executable}\nimport os, sys\n"
                                f"extra = {flags!r}\n"
                                "objects = '--memory' in sys.argv and sys.argv[sys.argv.index('--memory') + 1] == 'objects'\n"
                                "if objects and not any(x in sys.argv for x in ('--beautify', '--z3', '--cvc5', '--bitwuzla', '--external-sat-solver')):\n"
                                f"    extra += {solver if name != 'goto-cc' else []!r}\n"
                                f"os.execv({str(real_tools / name)!r}, [{str(real_tools / name)!r}, *sys.argv[1:], *extra])\n")
                path.chmod(0o755)
            else:
                path.symlink_to(real_tools / name)

        # Helper accesses cross storage blocks, including the final bank byte.
        harness = tmp / "bank.c"
        checks = []
        for offset in (0, 28, 60, 508, 760):
            checks += [f"asmc_set_reg(&s, {offset}, 8, value);",
                       f"assert(asmc_get_reg(&s, {offset}, 8) == value);",
                       f"asmc_set_reg(&s, {offset + 3}, 1, 0x5a);",
                       f"assert(asmc_get_reg(&s, {offset}, 8) == ((value & ~UINT64_C(0xff000000)) | UINT64_C(0x5a000000)));"]
        harness.write_text('#include "asmc_state.h"\n#include <assert.h>\n'
                           'void harness(void) { struct asmc_state s; uint64_t value;\n'
                           'assert(sizeof s.registers == ASMC_REGISTER_BYTES);\n' + "\n".join(checks) + '\n}\n')
        model = tmp / "bank.gb"
        run([tools / "goto-cc", "-I", ROOT / "include", ROOT / "runtime/runtime.c", harness, "-o", model])
        run([tools / "cbmc", model, "--function", "harness", "--unwind", "10", "--unwinding-assertions",
             "--bounds-check", "--pointer-check", "--validate-goto-model"])
        print("PASS blocked helper overlap and block/bank edges", flush=True)

        # Encoded C pointers can alias state storage. Register writes must remain
        # visible immediately to LOAD/STORE; caching a private bank would fail.
        source, elf = tmp / "alias.S", tmp / "alias.elf"
        source.write_text('.text\n.globl alias\n.type alias,@function\nalias:\n'
                          'movb $0x5a,(%rdi)\nmov %rdx,%rax\nret\n.size alias,.-alias\n'
                          '.section .note.GNU-stack,"",@progbits\n')
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,alias", source, "-o", elf])
        for layout in ("struct { unsigned long long block0[32], block1[32], block2[31]; } registers",
                       "struct { long long block0[32], block1[32], block2[32]; } registers",
                       "struct { unsigned block0[32], block1[32], block2[32]; } registers"):
            bad = tmp / "bad.c"
            bad.write_text(f"struct asmc_state {{ {layout}; }};\nvoid asmc_target(struct asmc_state *s) {{}}\n")
            run([tools / "goto-cc", "-c", bad, "-o", tmp / "bad.gb"])
            text = run([tools / "asmc-lift", elf, "--function", "alias", "--template", tmp / "bad.gb",
                        "-o", tmp / "bad-lift.gb"], 2)
            assert "template must have uint8_t registers" in text
            assert not (tmp / "bad-lift.gb").exists()
        print("PASS rejects malformed blocked templates", flush=True)
        harness.write_text('''#include "asmc_x86.h"
#include <assert.h>
void harness(void) {
  uint8_t stack[128]; struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter_objects(&s, stack, sizeof stack);
  asmc_set_reg(&s, ASMC_RDX, 8, 0);
  asmc_sysv_arg_ptr(&s, 0, &ASMC_REG_BYTE(&s, ASMC_RDX));
  asmc_target(&s);
  assert(asmc_sysv_result64(&s) == 0x5a);
  asmc_sysv_check(&s, &frame);
}
''')
        run([tools / "asmc", elf, "--function", "alias", "--harness", harness, "--memory", "objects",
             "--timeout", "90", "--memory-limit", "1024", "-o", tmp / "alias"])
        print("PASS C object aliases register bank", flush=True)

        for suite in args.suite or SUITES:
            command = [sys.executable, ROOT / "tests" / ("run.py" if suite == "challenges" else suite + ".py")]
            command += [tools / "asmc-lift", "--tools", tools] if suite == "challenges" else [tools / "asmc"]
            print("Register-word suite: " + suite, flush=True)
            subprocess.run([str(arg) for arg in command], check=True, timeout=600)


if __name__ == "__main__":
    main()
