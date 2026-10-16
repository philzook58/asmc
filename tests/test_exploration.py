"""Upstream algorithms and handwritten implementations checked against C."""

import pytest
from support import ROOT, bounded_run as run, roundtrip

pytestmark = pytest.mark.slow
EXAMPLE = ROOT / "examples/exploration"


def compile(source, function, output, architecture="x86", compiler="gcc", optimization="2"):
    flags = ["-no-pie", "-fcf-protection=none"]
    if architecture != "x86":
        compiler = "riscv64-unknown-elf-gcc"
        flags = [
            "-march=" + architecture + "imc",
            "-mabi=" + ("ilp32" if architecture == "rv32" else "lp64"),
        ]
    flags += ["-O" + optimization, "-nostdlib", "-static", "-fno-builtin", "-fno-stack-protector"]
    flags += (
        ["-fno-vectorize", "-fno-slp-vectorize"]
        if compiler == "clang"
        else ["-fno-tree-vectorize", "-fno-tree-loop-distribute-patterns"]
    )
    run([compiler, *flags, "-Wl,-e," + function, source, "-o", output])
    return output


def check(asmc, elf, function, harness, output, options=(), expected=0, references=()):
    text = run(
        [
            asmc,
            elf,
            "--function",
            function,
            "--harness",
            EXAMPLE / harness,
            "--link-arg",
            EXAMPLE / "reference.c",
            "--unwind",
            "18",
            "--timeout",
            "55",
            "--memory-limit",
            "2048",
            "--output-dir",
            output,
            *[arg for source in references for arg in ("--link-arg", source)],
            *options,
        ],
        expected,
        timeout=70,
    )
    assert (
        (output / "result.txt")
        .read_text()
        .startswith({0: "PASS:", 10: "FAIL:", 11: "INCOMPLETE:"}[expected])
    )
    roundtrip(asmc, output)
    return text


def test_saturating_add(asmc, architecture, tmp_path):
    elf = compile(
        EXAMPLE / "aws-c-common/saturating.c",
        "saturating_add",
        tmp_path / "target.elf",
        architecture,
    )
    check(asmc, elf, "saturating_add", "scalar_spec.c", tmp_path / "check")


def test_lower_bound(asmc, architecture, tmp_path):
    elf = compile(
        EXAMPLE / "acsl-by-example/lower_bound.c",
        "lower_bound",
        tmp_path / "target.elf",
        architecture,
    )
    options = ["--dispatch", "--unwindset", "asmc_target.0:12,linear_lower_bound.0:5"]
    if architecture == "x86":
        # Split the byte register bank and RAM into fields. GCC 13's dispatch
        # model otherwise spends over 55s reducing symbolic array updates.
        options += ["--max-field-sensitivity-array-size", "768"]
    if architecture == "rv64":
        options += ["--scalar-registers", "--max-field-sensitivity-array-size", "128"]
    check(asmc, elf, "lower_bound", "search_spec.c", tmp_path / "check", options)


@pytest.mark.parametrize("compiler", ["gcc", "clang"])
@pytest.mark.parametrize(
    "stem,function,harness,options",
    [
        ("simdjson/swar.c", "parse_eight", "scalar_spec.c", ["-DDIGITS"]),
        ("rpn.c", "rpn", "rpn_spec.c", ["--unwindset", "asmc_target.0:6,rpn.0:6"]),
    ],
    ids=["eight-digits", "rpn"],
)
def test_compiled_algorithm(asmc, tmp_path, compiler, stem, function, harness, options):
    source = EXAMPLE / stem
    elf = compile(
        source,
        function,
        tmp_path / "target.elf",
        compiler=compiler,
        optimization="0" if function == "rpn" else "2",
    )
    check(asmc, elf, function, harness, tmp_path / "check", options, references=[source])


@pytest.mark.parametrize("architecture", ["rv64"], indirect=True)
def test_rv64_eight_digits(asmc, architecture, tmp_path):
    source = EXAMPLE / "simdjson/swar.c"
    elf = compile(source, "parse_eight", tmp_path / "target.elf", architecture)
    check(
        asmc,
        elf,
        "parse_eight",
        "scalar_spec.c",
        tmp_path / "check",
        ["-DDIGITS"],
        references=[source],
    )


@pytest.mark.parametrize(
    "source,function,harness,options,references",
    [
        (
            "scalar.S",
            "saturating_add_asm",
            "scalar_spec.c",
            ["--dispatch", "--unwindset", "asmc_target.0:4"],
            [],
        ),
        (
            "scalar.S",
            "parse_eight_asm",
            "scalar_spec.c",
            ["-DDIGITS"],
            [EXAMPLE / "simdjson/swar.c"],
        ),
        (
            "scalar.S",
            "parse_eight_asm",
            "scalar_spec.c",
            ["-DDIGITS", "-DDIGIT_CONTRACT"],
            [EXAMPLE / "simdjson/swar.c"],
        ),
        (
            "rpn.S",
            "rpn_asm",
            "rpn_spec.c",
            ["--unwindset", "asmc_target.0:6,rpn.0:6"],
            [EXAMPLE / "rpn.c"],
        ),
    ],
    ids=["saturating-add", "eight-digits", "four-digit-contract", "rpn"],
)
def test_handwritten_algorithm(asmc, tmp_path, source, function, harness, options, references):
    elf = compile(EXAMPLE / source, function, tmp_path / "target.elf")
    check(asmc, elf, function, harness, tmp_path / "check", options, references=references)


@pytest.mark.parametrize(
    "source,function,before,after,harness,options,references",
    [
        ("scalar.S", "saturating_add_asm", "jnc", "jc", "scalar_spec.c", [], []),
        (
            "scalar.S",
            "parse_eight_asm",
            "$2561",
            "$2562",
            "scalar_spec.c",
            ["-DDIGITS"],
            [EXAMPLE / "simdjson/swar.c"],
        ),
        (
            "rpn.S",
            "rpn_asm",
            "add %eax",
            "sub %eax",
            "rpn_spec.c",
            ["--unwindset", "asmc_target.0:6,rpn.0:6"],
            [EXAMPLE / "rpn.c"],
        ),
        (
            "acsl-by-example/lower_bound.c",
            "lower_bound",
            "a[middle] < v",
            "a[middle] <= v",
            "search_spec.c",
            ["--dispatch", "--unwindset", "asmc_target.0:12"],
            [],
        ),
    ],
    ids=["saturation", "digit-coefficient", "rpn-operator", "search-comparison"],
)
def test_algorithm_mutant(
    asmc, tmp_path, source, function, before, after, harness, options, references
):
    original = EXAMPLE / source
    bad = tmp_path / original.name
    assert before in original.read_text()
    bad.write_text(original.read_text().replace(before, after))
    elf = compile(bad, function, tmp_path / "target.elf")
    text = check(asmc, elf, function, harness, tmp_path / "check", options, 10, references)
    assert "Recent machine instructions:" in text


def test_insufficient_search_bound(asmc, tmp_path):
    elf = compile(EXAMPLE / "acsl-by-example/lower_bound.c", "lower_bound", tmp_path / "target.elf")
    text = check(
        asmc,
        elf,
        "lower_bound",
        "search_spec.c",
        tmp_path / "check",
        ["--dispatch", "--unwindset", "asmc_target.0:1"],
        11,
    )
    assert "asmc_target.unwind.0" in text and "Machine: 0x" in text and "--show-loops" in text
