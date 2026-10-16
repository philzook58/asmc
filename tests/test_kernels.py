"""Compiled and hand-optimized kernels compared with C, including mutations."""

import pytest
from support import ROOT, run

pytestmark = pytest.mark.slow
EXAMPLES = ROOT / "examples/kernels"


def check(asmc, source, function, harness, output, compiler="gcc", options=(), expected=0):
    elf = output.with_suffix(".elf")
    run(
        [
            compiler,
            "-O2",
            "-nostdlib",
            "-no-pie",
            "-fno-stack-protector",
            "-fcf-protection=none",
            "-fno-tree-vectorize",
            "-Wl,-e," + function,
            source,
            "-o",
            elf,
        ]
    )
    text = run(
        [
            asmc,
            elf,
            "--function",
            function,
            "--harness",
            EXAMPLES / harness,
            "--link-arg",
            EXAMPLES / "kernels.c",
            "--unwind",
            "66",
            "--timeout",
            "100",
            "--output-dir",
            output,
            *options,
        ],
        expected,
    )
    assert (
        (output / "result.txt").read_text().startswith("PASS:" if expected == 0 else "FAIL:")
    ), text


@pytest.mark.parametrize("compiler", ["gcc", "clang"])
@pytest.mark.parametrize(
    "function,harness,options",
    [
        ("count_bits", "scalar_spec.c", []),
        ("choose", "scalar_spec.c", ["-DSELECT"]),
        ("sum_words", "memory_spec.c", ["--unwindset", "asmc_target.0:6,sum_words.0:6"]),
        ("swap_words", "memory_spec.c", ["-DSWAP"]),
    ],
    ids=["count-bits", "choose", "sum", "swap"],
)
def test_compiled_kernel(asmc, tmp_path, compiler, function, harness, options):
    check(asmc, EXAMPLES / "kernels.c", function, harness, tmp_path / "check", compiler, options)


@pytest.mark.parametrize(
    "function,options", [("count_bits_fast", []), ("choose_fast", ["-DSELECT"])]
)
def test_optimized_assembly(asmc, tmp_path, function, options):
    check(
        asmc,
        EXAMPLES / "optimized.S",
        function,
        "scalar_spec.c",
        tmp_path / "check",
        options=options,
    )


@pytest.mark.parametrize(
    "source,function,before,after,harness,options",
    [
        ("optimized.S", "choose_fast", "cmovne", "cmove", "scalar_spec.c", ["-DSELECT"]),
        ("kernels.c", "count_bits", "i < 64", "i < 63", "scalar_spec.c", []),
        (
            "kernels.c",
            "sum_words",
            "sum += data[i]",
            "sum ^= data[i]",
            "memory_spec.c",
            ["--unwindset", "asmc_target.0:6,sum_words.0:6"],
        ),
        ("kernels.c", "swap_words", "*b = old_a", "*b = old_b", "memory_spec.c", ["-DSWAP"]),
    ],
    ids=["wrong-condition", "missing-bit", "wrong-sum", "wrong-store"],
)
def test_kernel_mutant(asmc, tmp_path, source, function, before, after, harness, options):
    original = (EXAMPLES / source).read_text()
    assert before in original
    bad = tmp_path / source
    bad.write_text(original.replace(before, after))
    check(asmc, bad, function, harness, tmp_path / "check", options=options, expected=10)
