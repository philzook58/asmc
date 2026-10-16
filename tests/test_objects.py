"""C object aliasing, pointer lifetime/bounds, and machine-address isolation."""

import pytest
from support import ROOT, bounded_run as run, roundtrip

pytestmark = pytest.mark.slow
EXAMPLE = ROOT / "examples/objects"


@pytest.fixture(scope="session")
def object_elves(machine, tmp_path_factory):
    compiler, flags, _ = machine
    directory = tmp_path_factory.mktemp("objects")
    binaries = {}
    for optimization in ("0", "2"):
        elf = directory / ("functions-O" + optimization + ".elf")
        run(
            [
                compiler,
                *flags,
                "-O" + optimization,
                "-nostdlib",
                "-static",
                "-fno-builtin",
                "-fno-stack-protector",
                "-Wl,-e,bump",
                EXAMPLE / "functions.c",
                "-o",
                elf,
            ]
        )
        binaries[optimization] = elf
    return binaries


def check(asmc, elf, function, case, output, expected=0, options=(), harness=EXAMPLE / "harness.c"):
    text = run(
        [
            asmc,
            elf,
            "--function",
            function,
            "--harness",
            harness,
            "--memory",
            "objects",
            "--unwind",
            "20",
            "--timeout",
            "80",
            "--memory-limit",
            "2048",
            f"-DCASE={case}",
            "--output-dir",
            output,
            *options,
        ],
        expected,
        timeout=90,
    )
    assert (output / "result.txt").read_text().startswith("PASS:" if expected == 0 else "FAIL:")
    if expected == 10 and case == 6:
        assert text.count("Trace for ") == 1 and "more failed properties" in text
    commands = (output / "commands.txt").read_text()
    assert "--pointer-check" in commands and "-DASMC_OBJECT_MEMORY" in commands
    roundtrip(asmc, output)
    return text


@pytest.mark.parametrize("optimization", ["0", "2"], ids=["O0", "O2"])
def test_spilled_pointer_call(asmc, object_elves, tmp_path, optimization):
    check(
        asmc,
        object_elves[optimization],
        "relay",
        1,
        tmp_path / "check",
        options=["--callee", "bump", "--unwindset", "asmc_target.0:4"],
    )


@pytest.mark.parametrize(
    "function,case,expected,options",
    [
        pytest.param("combine", 2, 0, [], id="alias"),
        pytest.param("next_word", 3, 0, [], id="pointer-result"),
        pytest.param("bump", 9, 0, [], id="C-global-argument"),
        pytest.param("bump", 1, 0, ["--object-bits", "12"], id="object-bits"),
        pytest.param("bump", 5, 10, [], id="allocation-too-small"),
        pytest.param("bump", 6, 10, [], id="use-after-free"),
        pytest.param("bump", 7, 10, [], id="null"),
        pytest.param("bump", 8, 10, [], id="cross-object-edge"),
        pytest.param("bump", 1, 10, ["-DSTACK_SIZE=16"], id="stack-too-small"),
        pytest.param("copy_bytes", 4, 0, [], id="copy"),
    ],
)
def test_object_contract(asmc, object_elves, tmp_path, function, case, expected, options):
    check(asmc, object_elves["0"], function, case, tmp_path / "check", expected, options)


@pytest.fixture(scope="session")
def fixed_elf(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fixed-address")
    elf, source = tmp / "fixed.elf", tmp / "fixed.S"
    source.write_text(""".text
    .globl fixed
    .type fixed,@function
    fixed:
      mov constant(%rip),%eax
      ret
    .size fixed,.-fixed
    .globl truncated
    .type truncated,@function
    truncated:
      mov %edi,%edi
      lea constant(%rip),%rax
      add %rax,%rdi
      mov (%rdi),%eax
      ret
    .size truncated,.-truncated
    .globl fixed_write
    .type fixed_write,@function
    fixed_write:
      movl $0,constant(%rip)
      ret
    .size fixed_write,.-fixed_write
    .section .rodata
    constant: .long 42
    .section .note.GNU-stack,"",@progbits
    """)
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,fixed", source, "-o", elf])
    return elf


@pytest.mark.parametrize(
    "function,diagnostic", [("fixed", "read"), ("truncated", "read"), ("fixed_write", "write")]
)
def test_fixed_elf_address_has_no_object_fallback(asmc, fixed_elf, tmp_path, function, diagnostic):
    text = check(asmc, fixed_elf, function, 1, tmp_path / "check", 10)
    assert "invalid CBMC object " + diagnostic in text
    if function == "fixed":
        assert "Machine: 0x" in text and "Fixed ELF data addresses are not mapped" in text


@pytest.mark.parametrize("objects", [False, True], ids=["ram-template", "object-template"])
def test_mismatched_memory_template(asmc, lifter, fixed_elf, tmp_path, objects):
    seed, output = tmp_path / "seed.gb", tmp_path / "mismatch.gb"
    run(
        [
            asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            "-c",
            ROOT / "runtime/runtime.c",
            *(["-DASMC_OBJECT_MEMORY"] if objects else []),
            "-o",
            seed,
        ]
    )
    text = run(
        [
            lifter,
            fixed_elf,
            "--function",
            "fixed",
            "--template",
            seed,
            "-o",
            output,
            "--memory",
            "ram" if objects else "objects",
        ],
        2,
    )
    assert "template runtime memory mode differs" in text and not output.exists()


@pytest.mark.parametrize("tool", ["driver", "lifter"])
def test_incompatible_address_schemes(asmc, lifter, fixed_elf, tmp_path, tool):
    if tool == "driver":
        command = [asmc, fixed_elf, "--function", "fixed", "--harness", EXAMPLE / "harness.c"]
    else:
        command = [
            lifter,
            fixed_elf,
            "--function",
            "fixed",
            "--template",
            tmp_path / "unused.gb",
            "-o",
            tmp_path / "out.gb",
        ]
    text = run([*command, "--memory", "objects", "--rodata"], 2)
    assert "cannot be combined" in text and not (tmp_path / "out.gb").exists()
