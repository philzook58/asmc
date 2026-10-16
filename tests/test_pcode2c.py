"""C references and ABI regressions adapted from the pcode2c examples."""

import pytest
from support import ROOT, run

pytestmark = pytest.mark.slow
EXAMPLES = ROOT / "examples/pcode2c"


def compile(source, function, output, compiler="gcc", optimization="0"):
    run(
        [
            compiler,
            "-O" + optimization,
            "-nostdlib",
            "-no-pie",
            "-fno-stack-protector",
            "-fcf-protection=none",
            "-fno-tree-vectorize",
            "-fno-optimize-sibling-calls",
            "-Wl,-e," + function,
            source,
            "-o",
            output,
        ]
    )
    return output


def check(asmc, elf, function, harness, output, reference=None, options=(), expected=0):
    command = [
        asmc,
        elf,
        "--function",
        function,
        "--harness",
        harness,
        "--output-dir",
        output,
        "--timeout",
        "90",
        *options,
    ]
    if reference:
        command += ["--link-arg", reference]
    text = run(command, expected, timeout=100)
    assert (
        (output / "result.txt")
        .read_text()
        .startswith({0: "PASS:", 10: "FAIL:", 11: "INCOMPLETE:"}[expected])
    )
    return text


@pytest.fixture(scope="session", params=["gcc", "clang"])
def compiler(request):
    return request.param


@pytest.fixture(scope="session", params=["0", "2"], ids=["O0", "O2"])
def optimization(request):
    return request.param


@pytest.mark.parametrize(
    "stem,function", [("min", "mymin"), ("factorial", "fact"), ("equal", "equal")]
)
def test_compiled_c_reference(asmc, tmp_path, compiler, optimization, stem, function):
    source = EXAMPLES / (stem + ".c")
    elf = compile(source, function, tmp_path / "target.elf", compiler, optimization)
    options = ["--unwindset", "asmc_target.0:10,equal.0:10"] if stem == "equal" else []
    check(asmc, elf, function, EXAMPLES / (stem + "_spec.c"), tmp_path / "check", source, options)


@pytest.fixture(scope="session")
def cmpxchg(tmp_path_factory):
    return compile(
        EXAMPLES / "cmpxchg.S",
        "compare_exchange",
        tmp_path_factory.mktemp("cmpxchg") / "target.elf",
    )


def test_compare_exchange(asmc, cmpxchg, tmp_path):
    check(asmc, cmpxchg, "compare_exchange", EXAMPLES / "cmpxchg_spec.c", tmp_path / "check")


@pytest.mark.parametrize(
    "stem,function,before,after",
    [
        ("min", "mymin", "x < y", "x > y"),
        ("factorial", "fact", "result * x", "result + x"),
        ("equal", "equal", "a[i] != b[i]", "a[i] == b[i]"),
    ],
)
def test_compiled_mutant(asmc, tmp_path, stem, function, before, after):
    original, source = EXAMPLES / (stem + ".c"), tmp_path / "bad.c"
    assert before in original.read_text()
    source.write_text(original.read_text().replace(before, after))
    elf = compile(source, function, tmp_path / "bad.elf")
    options = ["--unwindset", "asmc_target.0:10,equal.0:10"] if stem == "equal" else []
    check(
        asmc,
        elf,
        function,
        EXAMPLES / (stem + "_spec.c"),
        tmp_path / "check",
        original,
        options,
        10,
    )


@pytest.mark.parametrize(
    "instruction",
    ["mov $0,%rbx\n  ret", "ret $8", "std\n  ret"],
    ids=["callee-saved-register", "stack-cleanup", "direction-flag"],
)
def test_abi_mutant(asmc, tmp_path, instruction):
    source = tmp_path / "bad.S"
    source.write_text(
        (EXAMPLES / "cmpxchg.S").read_text().replace("\n  ret\n", "\n  " + instruction + "\n")
    )
    elf = compile(source, "compare_exchange", tmp_path / "bad.elf")
    text = check(
        asmc, elf, "compare_exchange", EXAMPLES / "cmpxchg_spec.c", tmp_path / "check", expected=10
    )
    assert "asmc_sysv_check" in text


@pytest.mark.parametrize(
    "value,expected", [(0, 0), (1, 0), (2, 10)], ids=["false", "true", "invalid-bool"]
)
def test_boolean_result_bits(asmc, tmp_path, value, expected):
    harness, source = tmp_path / "harness.c", tmp_path / "result.S"
    harness.write_text("""#include "asmc_x86.h"
#include <assert.h>
void harness(void) {
  uint8_t ram[256]; struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model_at(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  asmc_target(&s);
  assert(asmc_sysv_result_bool(&s) == EXPECTED_BOOL);
  asmc_sysv_check(&s, &frame);
}
""")
    source.write_text(
        ".text\n.globl result\n.type result,@function\nresult:\n"
        f'movabs $0xfedcba987654320{value},%rax\nret\n.size result,.-result\n.section .note.GNU-stack,"",@progbits\n'
    )
    elf = compile(source, "result", tmp_path / "target.elf")
    check(
        asmc,
        elf,
        "result",
        harness,
        tmp_path / "check",
        options=["-DEXPECTED_BOOL=" + str(value != 0).lower()],
        expected=expected,
    )


def test_incomplete_array_comparison(asmc, tmp_path):
    source = EXAMPLES / "equal.c"
    elf = compile(source, "equal", tmp_path / "target.elf")
    check(
        asmc,
        elf,
        "equal",
        EXAMPLES / "equal_spec.c",
        tmp_path / "check",
        source,
        ["--unwindset", "asmc_target.0:3,equal.0:10"],
        11,
    )


def test_recursive_factorial(asmc, tmp_path):
    elf = compile(EXAMPLES / "fact_recursive.c", "fact_recursive", tmp_path / "target.elf")
    harness = tmp_path / "harness.c"
    harness.write_text((EXAMPLES / "factorial_spec.c").read_text().replace("x <= 12", "x <= 3"))
    check(
        asmc,
        elf,
        "fact_recursive",
        harness,
        tmp_path / "check",
        EXAMPLES / "factorial.c",
        ["--unwindset", "asmc_target.0:8", "--memory-limit", "2048"],
    )


def test_unsupported_division(lifter, seed, tmp_path):
    elf = compile(EXAMPLES / "unsupported.c", "is_prime", tmp_path / "target.elf")
    model = tmp_path / "rejected.gb"
    text = run([lifter, elf, "--function", "is_prime", "--template", seed, "-o", model], 2)
    assert "INT_SDIV" in text and not model.exists()
