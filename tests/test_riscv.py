"""RV32/RV64 ABI, widths, memory, mutations, and rejected operations."""

import shlex
import pytest
from support import ROOT, run, roundtrip

pytestmark = [
    pytest.mark.slow,
    pytest.mark.parametrize("architecture", ["rv32", "rv64"], indirect=True),
]
EXAMPLES = ROOT / "examples/riscv"


@pytest.fixture(
    scope="session",
    params=[("0", False), ("2", False), ("2", True)],
    ids=["O0", "O2", "O2-compressed"],
)
def compiled_riscv(request, architecture, tmp_path_factory):
    optimization, compressed = request.param
    bits = int(architecture[2:])
    elf = tmp_path_factory.mktemp("riscv") / "functions.elf"
    run(
        [
            "riscv64-unknown-elf-gcc",
            f"-march=rv{bits}im" + ("c" if compressed else ""),
            "-mabi=" + ("ilp32" if bits == 32 else "lp64"),
            "-O" + optimization,
            f"-DASMC_RISCV_XLEN={bits}",
            "-fno-builtin",
            "-fno-stack-protector",
            "-nostdlib",
            "-static",
            "-Wl,--no-relax,-e,inc",
            EXAMPLES / "functions.c",
            "-o",
            elf,
        ]
    )
    return elf


def check(asmc, elf, function, case, output, expected=0, options=()):
    text = run(
        [
            asmc,
            elf,
            "--function",
            function,
            "--harness",
            EXAMPLES / "spec.c",
            "--link-arg",
            EXAMPLES / "functions.c",
            f"-DCASE={case}",
            "--unwind",
            "34",
            "--output-dir",
            output,
            "--timeout",
            "100",
            *options,
        ],
        expected,
    )
    assert (
        (output / "result.txt")
        .read_text()
        .startswith({0: "PASS:", 10: "FAIL:", 11: "INCOMPLETE:"}[expected])
    )
    roundtrip(asmc, output)
    return text


@pytest.mark.parametrize(
    "case,function", list(enumerate(("inc", "maximum", "shift", "multiply", "sum", "copy"), 1))
)
def test_compiled_reference(asmc, compiled_riscv, tmp_path, case, function):
    options = ["--unwindset", f"asmc_target.0:6,{function}.0:6"] if case >= 5 else []
    if case == 4:
        options += ["--z3"]
    check(asmc, compiled_riscv, function, case, tmp_path / "check", options=options)


@pytest.mark.parametrize(
    "function,case", [("zero_test", 1), ("argument32", 7), ("load32", 8), ("all_args", 11)]
)
def test_integer_abi(asmc, instructions, tmp_path, function, case):
    check(asmc, instructions, function, case, tmp_path / "check")


def test_relocatable_link_suggestion(lifter, machine_seed, architecture, tmp_path):
    obj = tmp_path / "object with spaces.o"
    run(
        [
            "riscv64-unknown-elf-gcc",
            "-march=" + architecture + "imc",
            "-mabi=" + ("ilp32" if architecture == "rv32" else "lp64"),
            "-c",
            EXAMPLES / "instructions.S",
            "-o",
            obj,
        ]
    )
    text = run(
        [
            lifter,
            obj,
            "--function",
            "zero_test",
            "--template",
            machine_seed,
            "-o",
            tmp_path / "reject.gb",
        ],
        2,
    )
    command = next(
        line.strip() for line in text.splitlines() if line.startswith("  riscv64-unknown-elf-ld ")
    )
    run(shlex.split(command))
    run(
        [
            lifter,
            obj.with_suffix(".elf"),
            "--function",
            "zero_test",
            "--template",
            machine_seed,
            "-o",
            tmp_path / "linked.gb",
        ]
    )


@pytest.mark.parametrize(
    "function", ["bad_return", "bad_saved", "bad_gp", "bad_tp", "bad_s11", "bad_sp"]
)
def test_abi_violation(asmc, instructions, tmp_path, function):
    text = check(asmc, instructions, function, 0, tmp_path / "check", 10)
    assert "unexpected return address" in text or "asmc_riscv_check" in text


@pytest.mark.parametrize("case,diagnostic", [(9, "RAM region wraps"), (12, "memory access wraps")])
def test_rv32_address_wrap(asmc, instructions, architecture, tmp_path, case, diagnostic):
    if architecture != "rv32":
        pytest.skip("32-bit address-wrap regression")
    text = check(asmc, instructions, "load32", case, tmp_path / "check", 10)
    assert diagnostic in text or "memory access wraps" in text


def test_rv64_addiw(asmc, instructions, architecture, tmp_path):
    if architecture != "rv64":
        pytest.skip("RV64 word instruction")
    check(asmc, instructions, "add_word", 10, tmp_path / "check")


@pytest.mark.parametrize(
    "function,opcode", [("divide", "INT_SDIV"), ("indirect", "BRANCHIND"), ("caller", "CALL")]
)
def test_unsupported_operation(lifter, machine_seed, instructions, tmp_path, function, opcode):
    output = tmp_path / "rejected.gb"
    text = run(
        [lifter, instructions, "--function", function, "--template", machine_seed, "-o", output], 2
    )
    assert opcode in text and not output.exists()


def test_wrong_result(asmc, machine, architecture, tmp_path):
    source, elf = tmp_path / "bad.c", tmp_path / "bad.elf"
    source.write_text(
        (EXAMPLES / "functions.c").read_text().replace("return x + 1", "return x + 2")
    )
    run(
        [
            machine[0],
            *machine[1],
            f"-DASMC_RISCV_XLEN={architecture[2:]}",
            "-O2",
            "-fno-builtin",
            "-fno-stack-protector",
            "-nostdlib",
            "-static",
            "-Wl,--no-relax,-e,inc",
            source,
            "-o",
            elf,
        ]
    )
    check(asmc, elf, "inc", 1, tmp_path / "check", 10)


def test_insufficient_sum_bound(asmc, machine, architecture, tmp_path):
    elf = tmp_path / "sum.elf"
    run(
        [
            machine[0],
            *machine[1],
            f"-DASMC_RISCV_XLEN={architecture[2:]}",
            "-O2",
            "-fno-builtin",
            "-fno-stack-protector",
            "-nostdlib",
            "-static",
            "-Wl,--no-relax,-e,sum",
            EXAMPLES / "functions.c",
            "-o",
            elf,
        ]
    )
    check(asmc, elf, "sum", 5, tmp_path / "check", 11, ["--unwindset", "asmc_target.0:2,sum.0:6"])


def test_wrong_template_pointer_width(asmc, lifter, architecture, instructions, tmp_path):
    if architecture != "rv32":
        pytest.skip("64-bit template for a 32-bit ELF")
    seed = tmp_path / "wrong.gb"
    run(
        [
            asmc.parent / "goto-cc",
            "-m64",
            "-I",
            ROOT / "include",
            "-c",
            ROOT / "runtime/runtime.c",
            "-o",
            seed,
        ]
    )
    output = tmp_path / "mismatch.gb"
    text = run(
        [lifter, instructions, "--function", "zero_test", "--template", seed, "-o", output], 2
    )
    assert "pointer width" in text and not output.exists()
