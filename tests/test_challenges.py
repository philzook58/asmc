"""Instruction semantics, rejected inputs, and bounded upstream bignum checks."""

import re
import pytest
from support import ROOT, run


@pytest.fixture(scope="session")
def s2n_elf(tmp_path_factory):
    elf = tmp_path_factory.mktemp("s2n") / "functions.elf"
    run(
        [
            "gcc",
            "-nostdlib",
            "-no-pie",
            "-DNO_IBT=1",
            "-Wl,-e,word_max",
            "-I",
            ROOT / "tests/s2n-bignum/include",
            ROOT / "tests/s2n-bignum/word_max.S",
            ROOT / "tests/s2n-bignum/bignum_add.S",
            "-o",
            elf,
        ]
    )
    return elf


@pytest.fixture(scope="session")
def lifted_challenge(asmc, lifter, seed, x86_elf, s2n_elf, tmp_path_factory):
    directory = tmp_path_factory.mktemp("lifted-challenges")
    models = {}

    def lift(function):
        if function not in models:
            binary = s2n_elf if function in ("word_max", "bignum_add") else x86_elf
            model, checked = (
                directory / (function + ".gb"),
                directory / (function + "-roundtrip.gb"),
            )
            run([lifter, binary, "--function", function, "--template", seed, "-o", model])
            run([asmc.parent / "goto-instrument", "--validate-goto-model", model, checked])
            models[function] = checked
        return models[function]

    return lift


def link(asmc, model, case, output, defines=()):
    run(
        [
            asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            f"-DCASE={case}",
            *defines,
            model,
            ROOT / "tests/harness.c",
            ROOT / "tests/reference.c",
            "-o",
            output,
        ]
    )


@pytest.mark.fast
@pytest.mark.parametrize(
    "name,case,expected",
    [
        pytest.param("inc", 1, 0, id="inc"),
        pytest.param("alias_byte", 2, 0, id="alias_byte"),
        pytest.param("alias_word", 3, 0, id="alias_word"),
        pytest.param("alias_dword", 4, 0, id="alias_dword"),
        pytest.param("max_signed", 5, 0, id="max_signed"),
        pytest.param("max_signed_cmov", 5, 0, id="max_signed_cmov"),
        pytest.param("sext", 20, 0, id="sext"),
        pytest.param("zext", 21, 0, id="zext"),
        pytest.param("mulfull", 22, 0, id="mulfull"),
        pytest.param("max_unsigned", 6, 0, id="max_unsigned"),
        pytest.param("max_unsigned_cmov", 6, 0, id="max_unsigned_cmov"),
        pytest.param("swap", 7, 0, id="swap"),
        pytest.param("rotate", 8, 0, id="rotate"),
        pytest.param("add2", 9, 0, id="add2"),
        pytest.param("sub2", 10, 0, id="sub2"),
        pytest.param("copy", 11, 0, id="copy"),
        pytest.param("copy_rep", 11, 0, id="copy_rep"),
        pytest.param("search", 12, 0, id="search"),
        pytest.param("read64", 13, 0, id="read64"),
        pytest.param("word_max", 6, 0, id="word_max"),
        pytest.param("dead_unsupported", 1, 0, id="dead_unsupported"),
        pytest.param("inc_bad", 1, 10, id="inc_bad"),
        pytest.param("max_bad", 6, 10, id="max_bad"),
        pytest.param("add2_bad", 9, 10, id="add2_bad"),
        pytest.param("copy_bad", 11, 10, id="copy_bad"),
        pytest.param("copy_oob", 11, 10, id="copy_oob"),
        pytest.param("read64_oob", 14, 10, id="read64_oob"),
        pytest.param("read64_wrap", 15, 10, id="read64_wrap"),
        pytest.param("read64_region_wrap", 23, 10, id="read64_region_wrap"),
        pytest.param("corrupt_return", 16, 10, id="corrupt_return"),
        pytest.param("clobber_saved", 1, 10, id="clobber_saved"),
        pytest.param("copy_insufficient", 18, 10, id="copy_insufficient"),
    ],
)
def test_instruction_contract(asmc, lifted_challenge, tmp_path, name, case, expected):
    function = (
        "read64" if name.startswith("read64_") else "copy" if name == "copy_insufficient" else name
    )
    linked = tmp_path / "check.gb"
    link(
        asmc,
        lifted_challenge(function),
        case,
        linked,
        ["-DZERO_LENGTH"] if name == "copy_bad" else [],
    )
    options = ["--unwindset", "asmc_target.0:3"] if name == "copy_insufficient" else []
    if case == 22:
        options += ["--z3"]
    text = run(
        [
            asmc.parent / "cbmc",
            linked,
            "--function",
            "harness",
            "--unwind",
            "40",
            *options,
            "--unwinding-assertions",
            "--validate-goto-model",
            "--trace",
        ],
        expected,
    )
    assert ("VERIFICATION SUCCESSFUL" if expected == 0 else "VERIFICATION FAILED") in text
    failures = [line for line in text.splitlines() if line.rstrip().endswith(": FAILURE")]
    incomplete = bool(failures) and all("unwinding assertion" in line for line in failures)
    if name == "copy_insufficient":
        assert incomplete, failures
    elif name == "copy_bad":
        assert not incomplete and any("memory access outside RAM" in line for line in failures)
    elif name == "corrupt_return":
        assert "unexpected return address" in text


@pytest.mark.slow
@pytest.mark.parametrize("p", range(3))
@pytest.mark.parametrize("m", range(3))
@pytest.mark.parametrize("n", range(3))
def test_bignum_add(asmc, lifted_challenge, tmp_path, p, m, n):
    # All 27 length triples retain arbitrary 64-bit input limbs.
    linked = tmp_path / "check.gb"
    link(
        asmc,
        lifted_challenge("bignum_add"),
        19,
        linked,
        [f"-DINPUT_P={p}", f"-DINPUT_M={m}", f"-DINPUT_N={n}"],
    )
    listing = run([asmc.parent / "goto-instrument", "--show-loops", linked])
    loops = re.findall(r"Loop (asmc_target\.\d+):", listing)
    assert loops, "expected loops in the upstream bignum routine"
    text = run(
        [
            asmc.parent / "cbmc",
            linked,
            "--function",
            "harness",
            "--unwind",
            "40",
            "--unwindset",
            ",".join(loop + ":4" for loop in loops),
            "--max-field-sensitivity-array-size",
            "768",
            "--unwinding-assertions",
            "--validate-goto-model",
            "--trace",
        ]
    )
    assert "VERIFICATION SUCCESSFUL" in text


@pytest.mark.fast
@pytest.mark.parametrize(
    "function,diagnostic",
    [
        ("unsupported_div", "INT_DIV"),
        ("unsupported_simd", "register"),
        ("unsupported_call", "CALL"),
        ("unsupported_indirect", "BRANCHIND"),
        ("unsupported_tls", "segment"),
        ("outside_function", "range"),
        ("truncated", "extends"),
    ],
)
def test_rejected_instruction(lifter, seed, x86_elf, tmp_path, function, diagnostic):
    output = tmp_path / "rejected.gb"
    text = run([lifter, x86_elf, "--function", function, "--template", seed, "-o", output], 2)
    assert diagnostic in text and not output.exists()


@pytest.mark.fast
def test_elf_and_explicit_range(lifter, seed, x86_elf, tmp_path):
    obj = tmp_path / "object.o"
    run(["gcc", "-c", ROOT / "tests/challenges.S", "-o", obj])
    text = run([lifter, obj, "--function", "inc", "--template", seed, "-o", tmp_path / "obj.gb"], 2)
    assert "relocatable ELF (.o)" in text and "Link it first:" in text
    symbols = run(["nm", x86_elf])
    end = next(
        line.split()[0] for line in symbols.splitlines() if line.endswith(" missing_size_end")
    )
    model = tmp_path / "inferred.gb"
    text = run([lifter, x86_elf, "--function", "missing_size", "--template", seed, "-o", model])
    assert "ASMC lift range:" in text and ".text" in text
    assert "MOV RAX,RDI" in (tmp_path / "inferred.gb.asm").read_text()
    assert "RET" in (tmp_path / "inferred.gb.asm").read_text()
    run(
        [
            lifter,
            x86_elf,
            "--function",
            "missing_size",
            "--lift-end-address",
            "0x" + end,
            "--template",
            seed,
            "-o",
            tmp_path / "explicit.gb",
        ]
    )


@pytest.mark.fast
@pytest.mark.parametrize(
    "source",
    ["void asmc_target(int *s) {}", "void other(void) {}"],
    ids=["wrong-signature", "missing-target"],
)
def test_incompatible_template(asmc, lifter, x86_elf, tmp_path, source):
    cfile, model = tmp_path / "bad.c", tmp_path / "bad.gb"
    cfile.write_text(source)
    run([asmc.parent / "goto-cc", "-c", cfile, "-o", model])
    text = run(
        [lifter, x86_elf, "--function", "inc", "--template", model, "-o", tmp_path / "out.gb"], 2
    )
    assert "template" in text


@pytest.mark.fast
@pytest.mark.parametrize("compiler", ["gcc", "clang"])
@pytest.mark.parametrize("optimization", ["0", "2"], ids=["O0", "O2"])
def test_compiled_kernel(asmc, lifter, seed, tmp_path, compiler, optimization):
    elf, model, checked = (tmp_path / name for name in ("kernel.elf", "kernel.gb", "check.gb"))
    run(
        [
            compiler,
            "-O" + optimization,
            "-nostdlib",
            "-no-pie",
            "-fno-stack-protector",
            "-Wl,-e,kernel",
            ROOT / "tests/kernel.c",
            "-o",
            elf,
        ]
    )
    run([lifter, elf, "--function", "kernel", "--template", seed, "-o", model])
    link(asmc, model, 17, checked)
    run(
        [
            asmc.parent / "cbmc",
            checked,
            "--function",
            "harness",
            "--unwind",
            "40",
            "--unwinding-assertions",
            "--validate-goto-model",
        ]
    )
