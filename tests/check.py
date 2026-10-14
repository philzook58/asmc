"""Exercise the public check command with real tools and explicit harnesses."""
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]


def run(command, expected=0):
    process = subprocess.run([str(arg) for arg in command], capture_output=True,
                             text=True, timeout=120)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    lifter = asmc.with_name("asmc-lift")
    driver_help = run([asmc, "--help"])
    lift_help = run([lifter, "--help"])
    assert "usage: asmc " in driver_help and "--harness" in driver_help
    assert "--template" not in driver_help
    assert "asmc-lift FILE.elf" in lift_help and "--template" in lift_help
    assert "--harness" not in lift_help
    assert "ASMC 0.1.0" in run([asmc, "--version"])
    assert "ASMC-lift 0.1.0" in run([lifter, "--version"])
    with tempfile.TemporaryDirectory(prefix="asmc-check-tests-") as temp:
        tmp = Path(temp)
        elf = tmp / "functions with spaces.elf"
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,inc", ROOT / "tests/challenges.S", "-o", elf])

        def check(name, function, harness, options=(), expected=0):
            output = tmp / (name + " output")
            text = run([asmc, elf, "--function", function, "--harness", harness,
                        "--output-dir", output, *options], expected)
            assert (output / "commands.txt").is_file(), text
            assert (output / "result.txt").read_text().strip() in text, text
            if expected != 2:
                for filename in ("seed.gb", "lifted.gb", "lifted.gb.asm", "check.gb",
                                 "seed.log", "lift.log", "link.log", "cbmc.log"):
                    assert (output / filename).is_file(), filename
                commands = (output / "commands.txt").read_text()
                assert "--unwinding-assertions" in commands
                assert "--validate-goto-model" in commands
            print(f"PASS check {name}", flush=True)
            return text, output

        text, output = check("increment", "inc", ROOT / "examples/inc_spec.c")
        assert "PASS: all checked properties" in text
        assert "VERIFICATION SUCCESSFUL" in (output / "cbmc.log").read_text()
        text, _ = check("explicit_lifter", "inc", ROOT / "examples/inc_spec.c", ["--lifter", lifter])
        assert "PASS:" in text
        text = run([asmc, "check", elf, "--function", "inc", "--harness", ROOT / "examples/inc_spec.c"], 2)
        assert "unrecognized arguments" in text
        check("memory_limit", "inc", ROOT / "examples/inc_spec.c", ["--memory-limit", "512"])
        text, _ = check("counterexample", "inc_bad", ROOT / "examples/inc_spec.c", expected=10)
        assert "FAIL: counterexample found" in text
        assert "Trace and details:" in text
        assert "Trace for harness.assertion.1:" in text and "Violated property:" in text
        assert "return_value_asmc_sysv_result64=" in text and "x=" in text
        assert "asmc_tmp_" not in text
        assert "Recent machine instructions:" in text and "0x" in text
        missing = tmp / "missing_reference.c"
        missing.write_text("unsigned long missing_ref(unsigned long);\n" +
                           (ROOT / "examples/inc_spec.c").read_text().replace("== x + 1", "== missing_ref(x)"))
        text, _ = check("missing_reference", "inc", missing, expected=2)
        assert "Missing C definition: missing_ref" in text and "--reference FILE.c" in text
        text, _ = check("full_trace", "inc_bad", ROOT / "examples/inc_spec.c", ["--full-trace"], 10)
        assert "asmc_tmp_" in text and "Violated property:" in text

        # The diagnostic supplies a runnable, shell-quoted link command for an .o.
        obj = tmp / "object with 'quotes'.o"
        run(["gcc", "-c", ROOT / "examples/inc.S", "-o", obj])
        text = run([lifter, obj, "--function", "inc", "--template", output / "seed.gb",
                    "-o", tmp / "rejected.gb"], 2)
        assert "relocatable ELF (.o)" in text and "Link it first:" in text
        command = next(line.strip() for line in text.splitlines() if line.startswith("  ld "))
        run(shlex.split(command))
        run([lifter, obj.with_suffix(".elf"), "--function", "inc", "--template", output / "seed.gb",
             "-o", tmp / "linked.gb"])
        print("PASS check relocatable suggestion", flush=True)
        text, output = check("trace_options", "inc_bad", ROOT / "examples/inc_spec.c",
                             ["--trace-hex", "--compact-trace", "--beautify", "--slice-formula"], 10)
        commands = (output / "commands.txt").read_text()
        for flag in ("--trace-hex", "--compact-trace", "--beautify", "--slice-formula"):
            assert flag in commands
        text, _ = check("sliced_increment", "inc", ROOT / "examples/inc_spec.c", ["--slice-formula"])
        assert "PASS: all checked properties" in text
        for threshold in (0, 1024):
            text, output = check("array_fields_" + str(threshold), "inc", ROOT / "examples/inc_spec.c",
                                 ["--max-field-sensitivity-array-size", str(threshold)])
            assert "--max-field-sensitivity-array-size " + str(threshold) in (output / "commands.txt").read_text()
        for name, flag in (("bitwuzla", "--bitwuzla"), ("kissat", "--external-sat-solver")):
            solver = shutil.which(name)
            if solver:
                options = [flag, solver] if name == "kissat" else [flag, "--solver-path", solver]
                check(name + "_pass", "inc", ROOT / "examples/inc_spec.c", options)
                text, _ = check(name + "_counterexample", "inc_bad", ROOT / "examples/inc_spec.c", options, 10)
                assert "Violated property:" in text
        text = run([asmc, elf, "--function", "inc", "--max-field-sensitivity-array-size", "-1"], 2)
        assert "must be nonnegative" in text

        copy_options = ["--reference", ROOT / "tests/reference.c", "-DCASE=18",
                        "--unwindset", "asmc_target.0:3"]
        text, _ = check("insufficient", "copy", ROOT / "tests/harness.c", copy_options, 11)
        assert "INCOMPLETE: insufficient unwinding" in text and "PASS:" not in text
        assert "Machine: 0x" in text and "--show-loops" in text
        text, _ = check("copy", "copy", ROOT / "tests/harness.c",
                        ["--reference", ROOT / "tests/reference.c", "-DCASE=11"])
        assert "PASS: all checked properties" in text
        for flag, expected_listing in [("--show-loops", "asmc_target.0"),
                                       ("--show-properties", "Property ")]:
            text, output = check(flag[2:], "copy", ROOT / "tests/harness.c",
                                 ["--reference", ROOT / "tests/reference.c", "-DCASE=11", flag])
            assert expected_listing in text, text
            assert "INSPECT: listing only; no verification performed" in text
            assert "PASS:" not in text and "VERIFICATION SUCCESSFUL" not in text


        # Exercise all six argument registers through actual memory-writing assembly.
        assembly = tmp / "arguments.S"
        assembly.write_text(".text\n.globl args_store\n.type args_store,@function\nargs_store:\n"
                            "mov %rsi,0(%rdi)\nmov %rdx,8(%rdi)\nmov %rcx,16(%rdi)\n"
                            "mov %r8,24(%rdi)\nmov %r9,32(%rdi)\nmov %r9,%rax\nret\n"
                            '.size args_store,.-args_store\n.section .note.GNU-stack,"",@progbits\n')
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,args_store", assembly, "-o", elf])
        argument_harness = tmp / "arguments.c"
        argument_harness.write_text('''#include "asmc_x86.h"
#include <assert.h>
uint64_t nondet_u64(void);
void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  s.ram = ram; s.ram_base = 0x1000; s.ram_size = sizeof(ram);
  asmc_assume_flags(&s); asmc_setup_stack(&s, 0x10c8);
  uint64_t values[5];
  asmc_sysv_arg64(&s, 0, s.ram_base);
  for (unsigned i = 0; i < 5; ++i) {
    values[i] = nondet_u64();
    asmc_sysv_arg64(&s, i + 1, values[i]);
  }
  asmc_target(&s);
  for (unsigned i = 0; i < 5; ++i)
    assert(asmc_load(&s, s.ram_base + 8 * i, 8) == values[i]);
  assert(asmc_sysv_result64(&s) == values[4]);
  assert(asmc_get_reg(&s, ASMC_RSP, 8) == 0x10d0);
}
''')
        check("sysv_arguments", "args_store", argument_harness)
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,inc", ROOT / "tests/challenges.S", "-o", elf])

        headers = tmp / "headers with spaces"
        headers.mkdir()
        (headers / "expected.h").write_text("#define EXPECTED_INCREMENT INCREMENT\n")
        harness = tmp / "custom harness.c"
        harness.write_text('#include "expected.h"\n' +
                           (ROOT / "examples/inc_spec.c").read_text()
                           .replace("void harness(void)", "void entry(void)")
                           .replace("== x + 1", "== x + EXPECTED_INCREMENT"))
        check("entry_and_options", "inc", harness,
              ["--entry", "entry", "-I", headers, "-DINCREMENT=1"])

        text, output = check("missing_symbol", "no_such_function", ROOT / "examples/inc_spec.c",
                             expected=2)
        assert "ERROR:" in text and "PASS:" not in text
        assert not (output / "check.gb").exists()
        harness.write_text("this is invalid C;\n")
        text, output = check("compile_error", "inc", harness, expected=2)
        assert "ERROR:" in text and "PASS:" not in text
        assert (output / "link.log").is_file() and not (output / "cbmc.log").exists()

        # A declaration's comment must not make an ordinary failure look like unwinding.
        harness.write_text((ROOT / "examples/inc_spec.c").read_text()
                           .replace("assert(asmc_sysv_result64(&s) == x + 1);",
                                    '__CPROVER_assert(0, "unwinding assertion");'))
        text, _ = check("assertion_description", "inc", harness, expected=10)
        assert "FAIL: counterexample found" in text and "INCOMPLETE:" not in text

        harness.write_text("unsigned long nondet_u64(void);\nvoid harness(void) {\n"
                           "while (nondet_u64()) {}\n}\n")
        text, _ = check("timeout", "inc", harness, ["--timeout", "1", "--unwind", "1000000"], 11)
        assert "INCOMPLETE: tool timed out" in text and "PASS:" not in text
        assert "Last checker progress:" in text and "--slice-formula" in text
        text, _ = check("memory_exhausted", "inc", harness,
                        ["--memory-limit", "128", "--timeout", "15", "--unwind", "1000000"], 11)
        assert "INCOMPLETE: checker exhausted memory" in text and "PASS:" not in text

        text = run([asmc, elf, "--function", "inc", "--harness",
                    ROOT / "examples/inc_spec.c", "--output-dir", tmp / "increment output"], 2)
        assert "must be empty" in text
        print("PASS check preserves existing output", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
