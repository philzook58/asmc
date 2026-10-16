"""Driver behavior, including counterexamples and incomplete checks."""
import shlex
import shutil

import pytest

from support import ROOT, run

pytestmark = pytest.mark.fast
SPEC = ROOT / "examples/inc_spec.c"


@pytest.fixture
def check(asmc, x86_elf, tmp_path):
    def invoke(function, harness=SPEC, options=(), expected=0, *, elf=x86_elf):
        output = tmp_path / "check output"
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
        return text, output
    return invoke


@pytest.fixture
def missing_reference(tmp_path):
    source = tmp_path / "missing_reference.c"
    source.write_text("unsigned long missing_ref(unsigned long);\n" +
                      SPEC.read_text().replace("== x + 1", "== missing_ref(x)"))
    return source


def test_cli_help(asmc, lifter):
    driver_help = run([asmc, "--help"])
    lift_help = run([lifter, "--help"])
    assert "usage: asmc " in driver_help and "--harness" in driver_help
    assert "--template" not in driver_help
    assert "asmc-lift FILE.elf" in lift_help and "--template" in lift_help
    assert "--harness" not in lift_help
    assert "ASMC 0.1.0" in run([asmc, "--version"])
    assert "ASMC-lift 0.1.0" in run([lifter, "--version"])


def test_increment(check):
    text, output = check("inc", SPEC)
    assert "PASS: all checked properties" in text
    assert "VERIFICATION SUCCESSFUL" in (output / "cbmc.log").read_text()
    commands = [shlex.split(line) for line in (output / "commands.txt").read_text().splitlines()]
    assert "--beautify" not in commands[-1]


def test_explicit_lifter(check, lifter):
    text, _ = check("inc", SPEC, ["--lifter", lifter])
    assert "PASS:" in text


def test_rejects_old_subcommand(asmc, x86_elf):
    text = run([asmc, "check", x86_elf, "--function", "inc", "--harness", SPEC], 2)
    assert "unrecognized arguments" in text


def test_memory_limit(check):
    check("inc", SPEC, ["--memory-limit", "512"])


def test_counterexample(check):
    text, output = check("inc_bad", SPEC, expected=10)
    assert "--beautify" not in shlex.split((output / "commands.txt").read_text().splitlines()[-1])
    assert "FAIL: counterexample found" in text
    assert "Trace and details:" in text
    assert "Trace for harness.assertion.1:" in text and "Violated property:" in text
    assert "return_value_asmc_sysv_result64=" in text and "x=" in text
    assert "asmc_tmp_" not in text
    assert "Recent machine instructions:" in text and "0x" in text


def test_missing_c_definition(check, missing_reference):
    text, _ = check("inc", missing_reference, expected=2)
    assert "Missing C definition: missing_ref" in text and "--link-arg=FILE.c" in text


def test_argument_forwarding(check, missing_reference, tmp_path):
    reference = tmp_path / "reference with spaces.c"
    reference.write_text("unsigned long missing_ref(unsigned long x) { return x + 1; }\n")
    forwarded = tmp_path / "forwarded harness.c"
    forwarded.write_text('#if FORWARDED != 1\n#error missing forwarded define\n#endif\n' + missing_reference.read_text())
    _, output = check("inc", forwarded,
                      ["--link-arg=" + str(reference), "--goto-cc-arg=-DFORWARDED=1",
                       "--lift-arg=--dispatch", "--cbmc-arg=--verbosity", "--cbmc-arg=8"])
    commands = [shlex.split(line) for line in (output / "commands.txt").read_text().splitlines()]
    seed, lift, link, cbmc = commands
    assert all("-DFORWARDED=1" in command for command in (seed, link))
    assert all("-DFORWARDED=1" not in command for command in (lift, cbmc))
    assert str(reference) in link and all(str(reference) not in command for command in (seed, lift, cbmc))
    assert "--dispatch" in lift and all("--dispatch" not in command for command in (seed, link, cbmc))
    assert cbmc[-2:] == ["--verbosity", "8"]


@pytest.mark.parametrize("mode", ["show-properties", "json-ui", "xml-ui"])
def test_forwarded_output_format(check, mode):
    text, _ = check("inc", options=["--cbmc-arg=--" + mode], expected=2)
    assert "no recognized verification result" in text and "PASS:" not in text


def test_full_trace(check):
    text, _ = check("inc_bad", SPEC, ["--full-trace"], 10)
    assert "asmc_tmp_" in text and "Violated property:" in text


def test_relocatable_link_suggestion(asmc, lifter, check, tmp_path):
    _, output = check("inc")
    # The suggestion must be runnable, including paths containing quotes and spaces.
    obj = tmp_path / "object with 'quotes'.o"
    run(["gcc", "-c", ROOT / "examples/inc.S", "-o", obj])
    text = run([lifter, obj, "--function", "inc", "--template", output / "seed.gb",
                "-o", tmp_path / "rejected.gb"], 2)
    assert "relocatable ELF (.o)" in text and "Link it first:" in text
    command = next(line.strip() for line in text.splitlines() if line.startswith("  ld "))
    run(shlex.split(command))
    run([lifter, obj.with_suffix(".elf"), "--function", "inc", "--template", output / "seed.gb",
         "-o", tmp_path / "linked.gb"])


def test_trace_options(check):
    text, output = check("inc_bad", SPEC,
                         ["--trace-hex", "--compact-trace", "--beautify", "--slice-formula"], 10)
    commands = (output / "commands.txt").read_text()
    for flag in ("--trace-hex", "--compact-trace", "--beautify", "--slice-formula"):
        assert flag in commands


def test_sliced_increment(check):
    text, _ = check("inc", SPEC, ["--slice-formula"])
    assert "PASS: all checked properties" in text


@pytest.mark.parametrize("threshold", [0, 1024])
def test_array_field_threshold(check, threshold):
    text, output = check("inc", options=["--max-field-sensitivity-array-size", str(threshold)])
    assert "--max-field-sensitivity-array-size " + str(threshold) in (output / "commands.txt").read_text()


@pytest.mark.parametrize("solver", ["bitwuzla", "kissat"])
@pytest.mark.parametrize("function,expected", [("inc", 0), ("inc_bad", 10)], ids=["correct", "mutant"])
def test_solver_positive_and_negative(check, solver, function, expected):
    executable = shutil.which(solver)
    if not executable:
        pytest.skip(f"{solver} is not installed")
    options = ["--external-sat-solver", executable] if solver == "kissat" else ["--bitwuzla", "--solver-path", executable]
    text, _ = check(function, options=options, expected=expected)
    if expected == 10:
        assert "Violated property:" in text


def test_rejects_negative_array_threshold(asmc, x86_elf):
    text = run([asmc, x86_elf, "--function", "inc", "--max-field-sensitivity-array-size", "-1"], 2)
    assert "must be nonnegative" in text


def test_insufficient_loop_bound(check):
    copy_options = ["--link-arg", ROOT / "tests/reference.c", "-DCASE=18",
                    "--unwindset", "asmc_target.0:3"]
    text, _ = check("copy", ROOT / "tests/harness.c", copy_options, 11)
    assert "INCOMPLETE: insufficient unwinding" in text and "PASS:" not in text
    assert "Machine: 0x" in text and "--show-loops" in text


def test_bounded_copy(check):
    text, _ = check("copy", ROOT / "tests/harness.c",
                    ["--link-arg", ROOT / "tests/reference.c", "-DCASE=11"])
    assert "PASS: all checked properties" in text


@pytest.mark.parametrize("flag,expected_listing", [("--show-loops", "asmc_target.0"), ("--show-properties", "Property ")])
def test_inspection(check, flag, expected_listing):
    text, _ = check("copy", ROOT / "tests/harness.c",
                    ["--link-arg", ROOT / "tests/reference.c", "-DCASE=11", flag])
    assert expected_listing in text
    assert "INSPECT: listing only; no verification performed" in text
    assert "PASS:" not in text and "VERIFICATION SUCCESSFUL" not in text


def test_all_sysv_arguments(check, tmp_path):
    x86_elf = tmp_path / "arguments.elf"
    # Exercise all six argument registers through actual memory-writing assembly.
    assembly = tmp_path / "arguments.S"
    assembly.write_text(".text\n.globl args_store\n.type args_store,@function\nargs_store:\n"
                        "mov %rsi,0(%rdi)\nmov %rdx,8(%rdi)\nmov %rcx,16(%rdi)\n"
                        "mov %r8,24(%rdi)\nmov %r9,32(%rdi)\nmov %r9,%rax\nret\n"
                        '.size args_store,.-args_store\n.section .note.GNU-stack,"",@progbits\n')
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,args_store", assembly, "-o", x86_elf])
    argument_harness = tmp_path / "arguments.c"
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
    check("args_store", argument_harness, elf=x86_elf)


def test_entry_and_preprocessor_options(check, tmp_path):
    headers = tmp_path / "headers with spaces"
    headers.mkdir()
    (headers / "expected.h").write_text("#define EXPECTED_INCREMENT INCREMENT\n")
    harness = tmp_path / "custom harness.c"
    harness.write_text('#include "expected.h"\n' +
                       SPEC.read_text()
                       .replace("void harness(void)", "void entry(void)")
                       .replace("== x + 1", "== x + EXPECTED_INCREMENT"))
    check("inc", harness,
          ["--entry", "entry", "-I", headers, "-DINCREMENT=1"])


def test_missing_symbol(check):
    text, output = check("no_such_function", SPEC,
                         expected=2)
    assert "ERROR:" in text and "PASS:" not in text
    assert not (output / "check.gb").exists()


def test_invalid_c_harness(check, tmp_path):
    harness = tmp_path / "invalid.c"
    harness.write_text("this is invalid C;\n")
    text, output = check("inc", harness, expected=2)
    assert "ERROR:" in text and "PASS:" not in text
    assert (output / "link.log").is_file() and not (output / "cbmc.log").exists()


def test_assertion_description_is_not_an_unwinding_failure(check, tmp_path):
    harness = tmp_path / "misleading_description.c"
    # A declaration's comment must not make an ordinary failure look like unwinding.
    harness.write_text(SPEC.read_text()
                       .replace("assert(asmc_sysv_result64(&s) == x + 1);",
                                '__CPROVER_assert(0, "unwinding assertion");'))
    text, _ = check("inc", harness, expected=10)
    assert "FAIL: counterexample found" in text and "INCOMPLETE:" not in text


@pytest.mark.parametrize("options,diagnostic", [
    (["--timeout", "1", "--unwind", "1000000"], "INCOMPLETE: tool timed out"),
    (["--memory-limit", "128", "--timeout", "15", "--unwind", "1000000"], "INCOMPLETE: checker exhausted memory"),
], ids=["timeout", "out-of-memory"])
def test_resource_exhaustion(check, tmp_path, options, diagnostic):
    harness = tmp_path / "unbounded.c"
    harness.write_text("unsigned long nondet_u64(void);\nvoid harness(void) {\n"
                       "while (nondet_u64()) {}\n}\n")
    text, _ = check("inc", harness, options, 11)
    assert diagnostic in text and "PASS:" not in text
    assert "Last checker progress:" in text and "--slice-formula" in text


def test_preserves_existing_output(asmc, x86_elf, check, tmp_path):
    _, output = check("inc")
    text = run([asmc, x86_elf, "--function", "inc", "--harness",
                SPEC, "--output-dir", output], 2)
    assert "must be empty" in text
