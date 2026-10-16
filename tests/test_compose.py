"""Named lifts and independent objects linked with ordinary C wrappers."""

import pytest
from support import ROOT, run

pytestmark = pytest.mark.slow
EXAMPLE = ROOT / "examples/compose"


@pytest.fixture(scope="session")
def composition(asmc, tmp_path_factory):
    directory = tmp_path_factory.mktemp("composition")
    elf, seed = directory / "functions.elf", directory / "seed.gb"
    run(
        [
            "gcc",
            "-nostdlib",
            "-no-pie",
            "-Wl,-e,machine_add_one",
            EXAMPLE / "functions.S",
            "-o",
            elf,
        ]
    )
    run(
        [
            asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            ROOT / "runtime/runtime.c",
            EXAMPLE / "entries.c",
            "-o",
            seed,
        ]
    )
    return elf, seed


def lift(asmc, source, function, target, template, output, expected=0):
    return run(
        [
            asmc.parent / "asmc-lift",
            source,
            "--function",
            function,
            "--target",
            target,
            "--template",
            template,
            "-o",
            output,
        ],
        expected,
    )


def verify(asmc, objects, output, expected=0):
    run(
        [
            asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            *objects,
            EXAMPLE / "wrappers.c",
            EXAMPLE / "harness.c",
            "-o",
            output,
        ]
    )
    text = run(
        [
            asmc.parent / "cbmc",
            output,
            "--function",
            "harness",
            "--unwind",
            "40",
            "--unwinding-assertions",
            "--validate-goto-model",
            "--trace",
        ],
        expected,
    )
    assert ("VERIFICATION SUCCESSFUL" if expected == 0 else "VERIFICATION FAILED") in text


def test_sequential_lifts(asmc, composition, tmp_path):
    elf, seed = composition
    first, both = tmp_path / "add.gb", tmp_path / "both.gb"
    lift(asmc, elf, "machine_add_one", "lifted_add_one", seed, first)
    lift(asmc, elf, "machine_sum", "lifted_sum", first, both)
    verify(asmc, [both], tmp_path / "check.gb")


def test_independent_objects(asmc, composition, tmp_path):
    elf, _ = composition
    objects = []
    for function, target in [("machine_add_one", "lifted_add_one"), ("machine_sum", "lifted_sum")]:
        source = tmp_path / (target + ".c")
        source.write_text(
            '#include "asmc_state.h"\nvoid ' + target + "(struct asmc_state *s) { (void)s; }\n"
        )
        stub, obj = tmp_path / (target + "-seed.gb"), tmp_path / (target + ".gb")
        run([asmc.parent / "goto-cc", "-I", ROOT / "include", "-c", source, "-o", stub])
        lift(asmc, elf, function, target, stub, obj)
        objects.append(obj)
    verify(asmc, [*objects, ROOT / "runtime/runtime.c"], tmp_path / "check.gb")


def test_named_driver_target(asmc, composition, tmp_path):
    text = run(
        [
            asmc,
            composition[0],
            "--function",
            "machine_add_one",
            "--target",
            "lifted_add_one",
            "--harness",
            EXAMPLE / "single.c",
            "--link-arg",
            EXAMPLE / "wrappers.c",
            "-o",
            tmp_path / "check",
        ]
    )
    assert "PASS: all checked properties" in text


@pytest.mark.parametrize(
    "before,after",
    [
        ("lea 1", "lea 2"),
        ("add $4", "add $8"),
        ("add (%rdi),%eax", "add (%rdi),%eax\n  movl $0,(%rdi)"),
    ],
    ids=["wrong-result", "wrong-stride", "unexpected-write"],
)
def test_composed_mutant(asmc, composition, tmp_path, before, after):
    source, elf = tmp_path / "bad.S", tmp_path / "bad.elf"
    original = (EXAMPLE / "functions.S").read_text()
    assert before in original
    source.write_text(original.replace(before, after))
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,machine_add_one", source, "-o", elf])
    first, both = tmp_path / "add.gb", tmp_path / "both.gb"
    lift(asmc, elf, "machine_add_one", "lifted_add_one", composition[1], first)
    lift(asmc, elf, "machine_sum", "lifted_sum", first, both)
    verify(asmc, [both], tmp_path / "check.gb", 10)


@pytest.mark.parametrize("bad_signature", [False, True], ids=["missing-target", "wrong-signature"])
def test_invalid_named_target(asmc, composition, tmp_path, bad_signature):
    elf, seed = composition
    if bad_signature:
        source, seed = tmp_path / "bad.c", tmp_path / "bad-seed.gb"
        source.write_text("int lifted_add_one(int x) { return x; }\n")
        run([asmc.parent / "goto-cc", "-c", source, "-o", seed])
    target = "lifted_add_one" if bad_signature else "missing"
    output = tmp_path / "bad.gb"
    text = lift(asmc, elf, "machine_add_one", target, seed, output, 2)
    assert (
        "incompatible lifted_add_one signature"
        if bad_signature
        else "template must define void missing"
    ) in text
    assert not output.exists()
