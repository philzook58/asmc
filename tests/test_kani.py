"""Rust/Kani and native assembly equivalence, with wrong-result and aliasing controls."""

import os
import shutil
import pytest
from support import ROOT, bounded_run as run

pytestmark = pytest.mark.slow
EXAMPLES = ROOT / "examples/kani"


@pytest.fixture(scope="session")
def rust_programs(lifter, tmp_path_factory):
    kani, rustc = shutil.which("kani"), shutil.which("rustc")
    if not kani or not rustc or os.uname().machine != "x86_64":
        pytest.skip("Kani, rustc and an x86-64 host are required")
    tmp = tmp_path_factory.mktemp("rust")

    def stage(name, command):
        return run(command, timeout=90, log=tmp / (name + ".log"))

    stage("kani-version", [kani, "--version"])
    stage("rustc-version", [rustc, "--version"])
    # Copy first: Kani's retained artifacts must not be written in examples/.
    source = tmp / "equivalence.rs"
    shutil.copyfile(EXAMPLES / "equivalence.rs", source)
    native_object, native_elf = tmp / "native.o", tmp / "native.elf"
    stage(
        "rustc",
        [
            rustc,
            "--edition",
            "2021",
            "--crate-type",
            "lib",
            "--emit",
            "obj",
            "-C",
            "opt-level=1",
            "-C",
            "panic=abort",
            source,
            "-o",
            native_object,
        ],
    )
    stage(
        "native-link",
        [
            "cc",
            "-nostdlib",
            "-static",
            "-no-pie",
            "-Wl,-e,add_one",
            native_object,
            "-o",
            native_elf,
        ],
    )
    assembly = tmp / "increment.elf"
    stage(
        "assembly-link",
        [
            "cc",
            "-nostdlib",
            "-static",
            "-no-pie",
            "-Wl,-e,inc",
            ROOT / "examples/inc.S",
            "-o",
            assembly,
        ],
    )
    cc = lifter.parent / "goto-cc"
    c_options = ["-I", ROOT / "include", "-DASMC_OBJECT_MEMORY"]
    seed = tmp / "seed.gb"
    stage("seed", [cc, *c_options, "-c", ROOT / "runtime/runtime.c", "-o", seed])
    return kani, source, assembly, native_elf, seed


@pytest.mark.parametrize(
    "kind,function,harness,expected",
    [
        pytest.param("assembly", "inc", "scalar_equivalence", 0, id="hand-assembly"),
        pytest.param("rust", "add_one", "scalar_equivalence", 0, id="compiled-rust"),
        pytest.param("rust", "add_two", "scalar_equivalence", 1, id="wrong-increment"),
        pytest.param("rust", "swap_words", "swap_equivalence", 0, id="pointer-swap"),
        pytest.param("rust", "swap_xor", "swap_equivalence", 1, id="aliasing-mutant"),
    ],
)
def test_rust_equivalence(lifter, rust_programs, tmp_path, kind, function, harness, expected):
    kani, original_source, assembly, native, seed = rust_programs
    source = tmp_path / "equivalence.rs"
    shutil.copyfile(original_source, source)
    elf = assembly if kind == "assembly" else native
    model, bridge = tmp_path / "lifted.gb", tmp_path / "bridge.gb"

    def stage(name, command, code=0):
        return run(command, code, timeout=90, log=tmp_path / (name + ".log"))

    stage(
        "lift",
        [
            lifter,
            elf,
            "--function",
            function,
            "--template",
            seed,
            "--memory",
            "objects",
            "-o",
            model,
        ],
    )
    stage(
        "validate",
        [
            lifter.parent / "goto-instrument",
            "--validate-goto-model",
            model,
            tmp_path / "roundtrip.gb",
        ],
    )
    defines = ["-DSWAP"] if harness == "swap_equivalence" else []
    stage(
        "bridge",
        [
            lifter.parent / "goto-cc",
            "-I",
            ROOT / "include",
            "-DASMC_OBJECT_MEMORY",
            *defines,
            model,
            EXAMPLES / "bridge.c",
            "-o",
            bridge,
        ],
    )
    text = stage(
        "kani",
        [
            kani,
            source,
            "-Z",
            "c-ffi",
            "--c-lib",
            bridge,
            "--harness",
            "proofs::" + harness,
            "--keep-temps",
            "--unwind",
            "40",
            "--output-format",
            "terse",
        ],
        expected,
    )
    assert "VERIFICATION:- " + ("FAILED" if expected else "SUCCESSFUL") in text
    if expected:
        assert "Failed Checks: assertion failed:" in text and "in proofs::" + harness in text
