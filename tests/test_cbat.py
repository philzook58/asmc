"""Compare original/patched binaries, including broken patches and call effects."""

import shutil
import pytest
from support import ROOT, bounded_run as run

pytestmark = pytest.mark.slow
EXAMPLES = ROOT / "examples/cbat"
CASES = {
    "same_signs": (1, "same_signs"),
    "switch": (2, "process_status"),
    "pointer": (3, "deref"),
    "debruijn": (4, "rightmost_index_8"),
    "increment": (5, "increment"),
    "goto_fail": (6, "SSLVerifySignedServerKeyExchange"),
}
CALLEES = [
    "ReadyHash",
    "SSLHashSHA1_update",
    "SSLHashSHA1_final",
    "sslRawVerify",
    "cleanUp",
    "SSLFreeBuffer",
]


def compare(
    asmc,
    machine,
    architecture,
    tmp_path,
    name,
    opt,
    expected=0,
    mutation=None,
    record=False,
    fixed=False,
    tag="pair",
):
    if name == "increment" and architecture != "x86":
        pytest.skip("the increment fixture is specifically an x86 instruction reorder")
    compiler, machine_flags, width_flags = machine
    if architecture == "x86":
        machine_flags = [*machine_flags, "-mno-sse", "-mno-sse2"]
    c_flags = ["-I", ROOT / "include", "-I", EXAMPLES, *width_flags]
    case, function = CASES[name]
    tools = asmc.parent
    output = tmp_path / "comparison"
    output.mkdir()
    for notice in ("LICENSE", "SOURCES.md"):
        shutil.copyfile(EXAMPLES / notice, output / notice)

    def stage(label, command, code=0):
        return run(command, code, timeout=90, log=output / (label + ".log"))

    object_mode = case in (3, 6)
    options = [*c_flags, f"-DCASE={case}"]
    if object_mode:
        options += ["-DASMC_OBJECT_MEMORY"]
    if record:
        options += ["-DASMC_RECORD_CALLS"]
    if fixed:
        options += ["-DASMC_FIXED_SWITCH"]
    for side in ("original", "patched"):
        suffix = ".S" if case == 5 else ".c"
        source = EXAMPLES / f"{name}_{side}{suffix}"
        if side == "patched" and mutation:
            changed = output / source.name
            before, after = mutation
            text = source.read_text()
            assert before in text
            changed.write_text(text.replace(before, after))
            source = changed
        stage(
            "compile-" + side,
            [
                compiler,
                *machine_flags,
                "-O" + opt,
                "-fno-stack-protector",
                "-fno-tree-vectorize",
                "-fno-builtin",
                "-I",
                EXAMPLES,
                *(["-DASMC_RECORD_CALLS"] if record else []),
                "-nostdlib",
                "-static",
                "-Wl,-e," + function,
                source,
                "-o",
                output / (side + ".elf"),
            ],
        )
    stage(
        "seed",
        [
            tools / "goto-cc",
            *options,
            ROOT / "runtime/runtime.c",
            EXAMPLES / "entries.c",
            "-o",
            output / "seed.gb",
        ],
    )
    template = output / "seed.gb"
    for side in ("original", "patched"):
        model = output / (side + ".gb")
        lift = [
            tools / "asmc-lift",
            output / (side + ".elf"),
            "--function",
            function,
            "--target",
            side,
            "--template",
            template,
            "-o",
            model,
            "--memory",
            "objects" if object_mode else "ram",
        ]
        if case == 4:
            lift += ["--rodata"]
        if case == 6:
            lift += [item for callee in CALLEES for item in ("--callee", callee)]
        stage("lift-" + side, lift)
        stage(
            "roundtrip-" + side,
            [
                tools / "goto-instrument",
                "--validate-goto-model",
                model,
                output / (side + "-roundtrip.gb"),
            ],
        )
        template = model
    stage(
        "link",
        [tools / "goto-cc", *options, template, EXAMPLES / "harness.c", "-o", output / "check.gb"],
    )
    checker = [
        tools / "cbmc",
        output / "check.gb",
        "--function",
        "harness",
        "--unwind",
        "260",
        "--unwinding-assertions",
        "--validate-goto-model",
        "--trace",
    ]
    if object_mode:
        checker += ["--pointer-check"]
    if case == 6:
        checker += ["--unwindset", "original.0:10,patched.0:14"]
    text = stage("cbmc", checker, expected)
    assert ("VERIFICATION SUCCESSFUL" if expected == 0 else "VERIFICATION FAILED") in text
    assert not any(
        "unwind" in line and line.endswith("FAILURE") for line in text.splitlines()
    ), text[-4000:]
    if expected == 10:
        property_name = (
            "selected call effects agree"
            if record
            else (
                "pointed-to inputs unchanged"
                if tag == "unexpected_write"
                else "original and patched declared results agree"
            )
        )
        assert property_name + ": FAILURE" in text, text[-4000:]
    return text


@pytest.mark.parametrize(
    "name,optimization,expected",
    [
        pytest.param(
            name, optimization, 10 if name == "switch" else 0, id=name + "-O" + optimization
        )
        for name in CASES
        for optimization in (
            ["0"] if name == "increment" else ["2"] if name == "goto_fail" else ["0", "2"]
        )
    ],
)
def test_binary_pair(asmc, machine, architecture, tmp_path, name, optimization, expected):
    text = compare(asmc, machine, architecture, tmp_path, name, optimization, expected)
    if name == "switch":
        assert "status=0u" in text and "before=0" in text and "after=1" in text


@pytest.mark.parametrize(
    "name,variant,mutation",
    [
        ("same_signs", "broken", ("!((x ^ y) < 0)", "((x ^ y) < 0)")),
        ("pointer", "wrong_threshold", ("num_2 = 12", "num_2 = 13")),
        ("pointer", "unexpected_write", ("return 0;", "*num_1 = 0;\n    return 0;")),
        ("debruijn", "broken", ("return 7;", "return 6;")),
        ("increment", "broken", ("inc     %rdi", "add $2, %rdi")),
    ],
)
def test_patched_mutant(asmc, machine, architecture, tmp_path, name, variant, mutation):
    compare(asmc, machine, architecture, tmp_path, name, "0", 10, mutation, tag=variant)


def test_repaired_switch(asmc, machine, architecture, tmp_path):
    compare(
        asmc,
        machine,
        architecture,
        tmp_path,
        "switch",
        "0",
        mutation=("nav = true;", "nav = true;\n      break;"),
        fixed=True,
    )


def test_observed_call_effects(asmc, machine, architecture, tmp_path):
    text = compare(asmc, machine, architecture, tmp_path, "goto_fail", "2", 10, record=True)
    assert "selected call effects agree: FAILURE" in text
