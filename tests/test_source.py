"""Assembly input, compiler configuration, lifting windows, and trace locations."""

import os
import shlex
import shutil
import sys
import pytest
from support import run

pytestmark = pytest.mark.fast
ANSWER = '.text\n.globl answer\n.type answer,@function\nanswer:\nmov $42,%rax\nret\n.size answer,.-answer\n.section .note.GNU-stack,"",@progbits\n'
UNSIZED = ANSWER.replace(".type answer,@function\n", "").replace(
    ".size answer,.-answer\n", "answer_end:\n"
)
CALL = '.text\n.globl answer, helper\nanswer:\nsub $8,%rsp\ncall helper\nadd $8,%rsp\nret\nhelper:\nmov $42,%rax\nret\n.section .note.GNU-stack,"",@progbits\n'


@pytest.fixture
def check(asmc, tmp_path):
    environment = dict(os.environ, CC="cc", CPPFLAGS="", CFLAGS="", LDFLAGS="")

    def invoke(
        source=ANSWER, post="outreg.rax == 42", expected=0, options=(), env=None, suffix=".s"
    ):
        path = tmp_path / ("program with 'quotes'" + suffix)
        path.write_text(source)
        output = tmp_path / "check"
        text = run(
            [asmc, path, "--function", "answer", "--post", post, "-o", output, *options],
            expected,
            env=environment if env is None else dict(environment, **env),
        )
        assert (output / "result.txt").read_text().strip() in text
        return text, output

    return invoke


@pytest.mark.parametrize("options", [[], ["--scalar-registers"]], ids=["bytes", "words"])
def test_assembly_input(check, options):
    text, output = check(options=options)
    assert "ELF: " + str(output / "target.elf") in text
    assert (output / "assemble.log").is_file() and (output / "target.elf").is_file()


def test_cc_argument_forwarding(check):
    _, output = check(options=["--cc-arg=-Wa,--fatal-warnings"])
    commands = [shlex.split(line) for line in (output / "commands.txt").read_text().splitlines()]
    assert "-Wa,--fatal-warnings" in commands[0]
    assert all("-Wa,--fatal-warnings" not in command for command in commands[1:])


def test_counterexample_instruction_locations(check):
    text, _ = check(post="outreg.rax == 43", expected=10)
    recent = text.split("Recent machine instructions:\n", 1)[1].split("Violated property:", 1)[0]
    assert recent.count("MOV RAX,0x2a") == 1 and recent.count("RET") == 1
    assert "outreg.rax=42" in text and "FAIL:" in text


def test_compiler_and_environment_quoting(check, tmp_path):
    compiler = tmp_path / "a compiler"
    compiler.write_text(
        f"#!{sys.executable}\nimport os, sys\nos.execvp('gcc', ['gcc', *sys.argv[1:]])\n"
    )
    compiler.chmod(0o755)
    source = "#ifndef RESULT\n#error CPPFLAGS missing\n#endif\n" + ANSWER.replace("$42", "$RESULT")
    _, output = check(
        source,
        suffix=".S",
        env={
            "CC": shlex.quote(str(compiler)) + " -v",
            "CPPFLAGS": "-DRESULT=42",
            "CFLAGS": "-g",
            "LDFLAGS": "-Wl,--build-id=none",
        },
    )
    command = shlex.split((output / "commands.txt").read_text().splitlines()[0])
    assert command[:2] == [str(compiler), "-v"]
    assert all(flag in command for flag in ("-DRESULT=42", "-g", "-Wl,--build-id=none"))
    assert command.index("-Wl,--build-id=none") > command.index(
        str(tmp_path / "program with 'quotes'.S")
    )


@pytest.mark.parametrize(
    "compiler", ["no-such-asmc-compiler", "", "'"], ids=["missing", "empty", "unmatched-quote"]
)
def test_invalid_compiler_configuration(check, compiler):
    text, output = check(expected=2, env={"CC": compiler})
    assert "ERROR:" in text and not (output / "cbmc.log").exists()


@pytest.mark.parametrize("correct", [True, False], ids=["correct", "wrong-result"])
def test_unsized_function(check, correct):
    text, _ = check(
        UNSIZED, post="outreg.rax == " + ("42" if correct else "43"), expected=0 if correct else 10
    )
    assert "ASMC lift range:" in text and ".text" in text


@pytest.mark.parametrize(
    "boundary,expected", [("exact", 0), ("below", 2), ("before-return", 2), ("padding", 0)]
)
def test_explicit_lifting_window(check, asmc, tmp_path, boundary, expected):
    # Obtain the linked address using the same assembler/linker, not a hardcoded base.
    assembly = tmp_path / "address.s"
    assembly.write_text(UNSIZED.replace(".globl answer", ".globl answer, answer_end"))
    run(
        [
            "cc",
            "-nostdlib",
            "-static",
            "-no-pie",
            "-Wl,-e,answer",
            assembly,
            "-o",
            tmp_path / "address.elf",
        ]
    )
    symbols = run(["nm", "-n", tmp_path / "address.elf"])
    end = int(
        next(line.split()[0] for line in symbols.splitlines() if line.endswith(" answer_end")), 16
    )
    address = {"exact": end, "below": 1, "before-return": end - 1, "padding": end + 1}[boundary]
    check(
        UNSIZED.replace("answer_end:", "answer_end:\nud2\nnop\nnop\nnop"),
        expected=expected,
        options=["--lift-end-address", hex(address)],
    )


def test_dead_padding_is_not_executed(check):
    _, output = check(UNSIZED.replace("answer_end:", "answer_end:\nud2\nnop\nnop\nnop"))
    listing = (output / "lifted.gb.asm").read_text()
    assert (
        "MOV RAX,0x2a" in listing
        and "RET" in listing
        and "UD2" not in listing
        and "NOP" not in listing
    )


@pytest.mark.parametrize("admitted", [False, True], ids=["section-edge", "admitted-helper"])
def test_executable_section_boundary(check, admitted):
    source = '.text\n.globl answer, helper\nanswer:\nmov $42,%rax\n.section .asmc_other,"ax",@progbits\nhelper:\nret\n.section .note.GNU-stack,"",@progbits\n'
    text, _ = check(
        source, expected=0 if admitted else 2, options=["--callee", "helper"] if admitted else []
    )
    if not admitted:
        assert "control flow leaves admitted lifting ranges at 0x" in text


def test_unsized_callee_windows(check):
    text, _ = check(
        CALL,
        options=[
            "--callee",
            "helper",
            "--unwindset",
            "asmc_target.0:4",
            "--max-field-sensitivity-array-size",
            "768",
        ],
    )
    assert text.count("ASMC lift range:") == 2


def test_symbol_size_overrides_section_fallback(check):
    source = CALL.replace("answer:\n", ".type answer,@function\nanswer:\n") + "\n.size answer,1\n"
    text, _ = check(source, expected=2)
    assert "instruction extends beyond the selected lifting window" in text


@pytest.mark.parametrize("bits", [32, 64], ids=["rv32", "rv64"])
@pytest.mark.parametrize("sized", [True, False], ids=["sized", "unsized"])
def test_riscv_source(check, bits, sized):
    if not shutil.which("riscv64-unknown-elf-gcc"):
        pytest.skip("RISC-V compiler is not installed")
    source = ANSWER.replace("mov $42,%rax", "li a0,42")
    if not sized:
        source = source.replace(".type answer,@function\n", "").replace(
            ".size answer,.-answer\n", ""
        )
    text, _ = check(
        source,
        post="outreg.a0 == 42",
        env={
            "CC": "riscv64-unknown-elf-gcc",
            "CFLAGS": f"-march=rv{bits}imc -mabi=" + ("ilp32" if bits == 32 else "lp64"),
        },
    )
    if not sized:
        assert "ASMC lift range:" in text
