"""Tutorial contracts, aliasing, stack separation, and frame-condition mutations."""

import os
import pytest
from support import ROOT, run, roundtrip

pytestmark = pytest.mark.slow
EXAMPLES = ROOT / "examples/tutorial"


@pytest.fixture(scope="session")
def tutorial_binaries(tmp_path_factory):
    directory = tmp_path_factory.mktemp("tutorial")
    binaries = {}
    for kind, source, entry in [
        ("assembly", "instructions.S", "answer"),
        ("compiled", "functions.c", "swap"),
    ]:
        elf = directory / (kind + ".elf")
        run(
            [
                "gcc",
                "-O0",
                "-fno-stack-protector",
                "-fcf-protection=none",
                "-nostdlib",
                "-static",
                "-no-pie",
                "-Wl,-e," + entry,
                EXAMPLES / source,
                "-o",
                elf,
            ]
        )
        binaries[kind] = elf
    return binaries


@pytest.mark.parametrize(
    "name,function,options,expected,diagnostic,kind",
    [
        pytest.param(
            "constant", "answer", ["--post", "outreg.rax == 42"], 0, None, "assembly", id="constant"
        ),
        pytest.param(
            "constant_wrong",
            "answer",
            ["--post", "outreg.rax == 43"],
            10,
            "post:",
            "assembly",
            id="constant_wrong",
        ),
        pytest.param(
            "increment",
            "increment",
            ["--post", "outreg.rax == outreg.rdi + 1"],
            0,
            None,
            "assembly",
            id="increment",
        ),
        pytest.param(
            "increment_wrap",
            "increment",
            ["--pre", "inreg.rdi == UINT64_MAX", "--post", "outreg.rax == 0"],
            0,
            None,
            "assembly",
            id="increment_wrap",
        ),
        pytest.param(
            "increment_wrong_snapshot",
            "increment",
            ["--post", "outreg.rax == outreg.rdi + 1", "--post", "outreg.rax == inreg.rax"],
            10,
            "post: outreg.rax == inreg.rax",
            "assembly",
            id="increment_wrong_snapshot",
        ),
        pytest.param(
            "minimum",
            "minimum",
            ["--post", "outreg.rax == (inreg.rdi < inreg.rsi ? inreg.rdi : inreg.rsi)"],
            0,
            None,
            "assembly",
            id="minimum",
        ),
        pytest.param(
            "minimum_not_maximum",
            "minimum",
            ["--post", "outreg.rax == (inreg.rdi > inreg.rsi ? inreg.rdi : inreg.rsi)"],
            10,
            "post:",
            "assembly",
            id="minimum_not_maximum",
        ),
        pytest.param(
            "minimum_not_signed",
            "minimum",
            [
                "--pre",
                "inreg.rdi == UINT64_MAX && inreg.rsi == 0",
                "--post",
                "(int64_t)outreg.rax == -1",
            ],
            10,
            "post:",
            "assembly",
            id="minimum_not_signed",
        ),
        pytest.param(
            "scratch_ram",
            "stack_scratch",
            ["--memory", "ram", "--post", "asmc_load(&st, inreg.rsp - 8, 8) == 42"],
            0,
            None,
            "assembly",
            id="scratch_ram",
        ),
        pytest.param(
            "scratch_wrong_snapshot_ram",
            "stack_scratch",
            ["--memory", "ram", "--post", "asmc_load(&st, outreg.rsp - 8, 8) == 42"],
            10,
            "post:",
            "assembly",
            id="scratch_wrong_snapshot_ram",
        ),
        pytest.param(
            "corrupt_return_ram",
            "corrupt_return",
            ["--memory", "ram"],
            10,
            "Return destination: 0x2a (42)",
            "assembly",
            id="corrupt_return_ram",
        ),
        pytest.param(
            "scratch_objects",
            "stack_scratch",
            ["--memory", "objects", "--post", "asmc_load(&st, inreg.rsp - 8, 8) == 42"],
            0,
            None,
            "assembly",
            id="scratch_objects",
        ),
        pytest.param(
            "scratch_wrong_snapshot_objects",
            "stack_scratch",
            ["--memory", "objects", "--post", "asmc_load(&st, outreg.rsp - 8, 8) == 42"],
            10,
            "post:",
            "assembly",
            id="scratch_wrong_snapshot_objects",
        ),
        pytest.param(
            "corrupt_return_objects",
            "corrupt_return",
            ["--memory", "objects"],
            10,
            "Return destination: 0x2a (42)",
            "assembly",
            id="corrupt_return_objects",
        ),
        pytest.param(
            "compiled_add42",
            "add42",
            ["--post", "outreg.eax == inreg.edi + 42"],
            0,
            None,
            "compiled",
            id="compiled_add42",
        ),
        pytest.param(
            "compiled_add42_wrap",
            "add42",
            ["--pre", "inreg.edi == UINT32_MAX", "--post", "outreg.eax == 41 && outreg.rax == 41"],
            0,
            None,
            "compiled",
            id="compiled_add42_wrap",
        ),
        pytest.param(
            "compiled_add42_bad64",
            "add42",
            ["--pre", "inreg.rdi == UINT32_MAX", "--post", "outreg.rax == inreg.rdi + 42"],
            10,
            "post:",
            "compiled",
            id="compiled_add42_bad64",
        ),
        pytest.param(
            "swap_missing_lower_bound",
            "swap_spills",
            ["--pre", "inreg.rdi <= inreg.rsp - 64", "--pre", "inreg.rsi <= inreg.rsp - 64"],
            10,
            "memory address below RAM base",
            "assembly",
            id="swap_missing_lower_bound",
        ),
        pytest.param(
            "swap_saved_pointer_alias",
            "swap_spills",
            [
                "--pre",
                "inreg.rdi == inreg.rsp - 40",
                "--pre",
                "inreg.rsi == st.ram_base",
                "--pre",
                "asmc_load(&st, inreg.rsi, 4) == inreg.rsp",
            ],
            10,
            "unexpected return address",
            "assembly",
            id="swap_saved_pointer_alias",
        ),
        pytest.param(
            "swap_separated_region",
            "swap_spills",
            [
                "--pre",
                "inreg.rdi >= st.ram_base && inreg.rdi <= st.ram_base + 124",
                "--pre",
                "inreg.rsi >= st.ram_base && inreg.rsi <= st.ram_base + 124",
            ],
            0,
            "safety/ABI only, no functional postcondition",
            "assembly",
            id="swap_separated_region",
        ),
        pytest.param(
            "swap_final_equality_is_wrong",
            "swap_spills",
            [
                "--pre",
                "inreg.rdi >= st.ram_base && inreg.rdi <= st.ram_base + 124",
                "--pre",
                "inreg.rsi >= st.ram_base && inreg.rsi <= st.ram_base + 124",
                "--post",
                "asmc_load(&st, inreg.rdi, 4) == asmc_load(&st, inreg.rsi, 4)",
            ],
            10,
            "post:",
            "assembly",
            id="swap_final_equality_is_wrong",
        ),
        pytest.param(
            "swap_both_alias_cases",
            "swap",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c"],
            0,
            None,
            "compiled",
            id="swap_both_alias_cases",
        ),
        pytest.param(
            "swap_distinct",
            "swap",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DALIAS_CASE=0"],
            0,
            None,
            "compiled",
            id="swap_distinct",
        ),
        pytest.param(
            "swap_same_object",
            "swap",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DALIAS_CASE=1"],
            0,
            None,
            "compiled",
            id="swap_same_object",
        ),
        pytest.param(
            "swap_manual_abi",
            "swap",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DMANUAL_ABI"],
            0,
            None,
            "compiled",
            id="swap_manual_abi",
        ),
        pytest.param(
            "swap_array",
            "swap",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_array.c"],
            0,
            None,
            "compiled",
            id="swap_array",
        ),
        pytest.param(
            "swap_bad_distinct",
            "swap_bad",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DALIAS_CASE=0"],
            10,
            "swap second value",
            "compiled",
            id="swap_bad_distinct",
        ),
        pytest.param(
            "swap_bad_hidden_by_alias",
            "swap_bad",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DALIAS_CASE=1"],
            0,
            None,
            "compiled",
            id="swap_bad_hidden_by_alias",
        ),
        pytest.param(
            "xor_distinct_only",
            "swap_xor",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DALIAS_CASE=0"],
            0,
            None,
            "compiled",
            id="xor_distinct_only",
        ),
        pytest.param(
            "xor_same_object",
            "swap_xor",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c", "-DALIAS_CASE=1"],
            10,
            "swap first value",
            "compiled",
            id="xor_same_object",
        ),
        pytest.param(
            "xor_both_alias_cases",
            "swap_xor",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c"],
            10,
            "swap first value",
            "compiled",
            id="xor_both_alias_cases",
        ),
        pytest.param(
            "xor_array",
            "swap_xor",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_array.c"],
            10,
            "swap first value",
            "compiled",
            id="xor_array",
        ),
        pytest.param(
            "swap_frame_violation",
            "swap_extra",
            ["--memory", "objects", "--harness", EXAMPLES / "swap_array.c", "-DFIXED_INDICES"],
            10,
            "swap unchanged element",
            "compiled",
            id="swap_frame_violation",
        ),
        pytest.param(
            "objects_harness_in_ram_mode",
            "swap",
            ["--harness", EXAMPLES / "swap_objects.c"],
            2,
            "ERROR:",
            "compiled",
            id="objects_harness_in_ram_mode",
        ),
    ],
)
def test_tutorial_contract(
    asmc, tutorial_binaries, tmp_path, name, function, options, expected, diagnostic, kind
):
    output = tmp_path / "check"
    environment = dict(os.environ, CC="cc", CPPFLAGS="", CFLAGS="", LDFLAGS="")
    text = run(
        [
            asmc,
            tutorial_binaries[kind],
            "--function",
            function,
            *options,
            "-o",
            output,
            "--timeout",
            "60",
            "--memory-limit",
            "2048",
        ],
        expected,
        timeout=75,
        env=environment,
    )
    assert (output / "result.txt").read_text().strip() in text
    if diagnostic:
        assert diagnostic in text
    if expected != 2:
        roundtrip(asmc, output)
    if name == "swap_frame_violation":
        assert "swap first value" not in text and "swap second value" not in text
