"""GNU assembly input, compiler overrides, end addresses and real trace steps."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def run(command, expected=0, env=None):
    process = subprocess.run([str(arg) for arg in command], text=True,
                             capture_output=True, timeout=90, env=env)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\n{text}"
    return text


asmc = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="asmc-source-") as directory:
    tmp = Path(directory)
    source = tmp / "program with 'quotes'.s"
    source.write_text('''.text
.globl answer
.type answer,@function
answer:
  mov $42,%rax
  ret
.size answer,.-answer
.section .note.GNU-stack,"",@progbits
''')
    # Make the native compiler configuration deterministic for these tests.
    env = dict(os.environ, CC="cc", CPPFLAGS="", CFLAGS="", LDFLAGS="")

    def check(name, property="outreg.rax == 42", expected=0, options=(), environment=env):
        output = tmp / name
        text = run([asmc, source, "--function", "answer", "--post", property,
                    "-o", output, *options], expected, environment)
        assert (output / "result.txt").read_text().strip() in text
        return text, output

    text, output = check("source")
    assert "ELF: " + str(output / "target.elf") in text
    assert (output / "assemble.log").is_file() and (output / "target.elf").is_file()
    text, output = check("wrong", "outreg.rax == 43", 10)
    recent = text.split("Recent machine instructions:\n", 1)[1].split("Violated property:", 1)[0]
    assert recent.count("MOV RAX,0x2a") == 1 and recent.count("RET") == 1, recent
    assert "outreg.rax=42" in text and "FAIL:" in text
    check("scalar", options=["--scalar-registers"])
    print("PASS source input, counterexample, scalar layout and trace locations", flush=True)

    # CC is a command plus optional arguments, parsed without a shell.
    compiler = tmp / "a compiler"
    compiler.write_text(f"#!{sys.executable}\nimport os, sys\nos.execvp('gcc', ['gcc', *sys.argv[1:]])\n")
    compiler.chmod(0o755)
    source = source.with_suffix(".S")
    source.write_text('''#ifndef RESULT
#error CPPFLAGS missing
#endif
.text
.globl answer
.type answer,@function
answer:
  mov $RESULT,%rax
  ret
.size answer,.-answer
.section .note.GNU-stack,"",@progbits
''')
    overrides = dict(env, CC=shlex.quote(str(compiler)) + " -v", CPPFLAGS="-DRESULT=42",
                     CFLAGS="-g", LDFLAGS="-Wl,--build-id=none")
    _, output = check("compiler", environment=overrides)
    command = shlex.split((output / "commands.txt").read_text().splitlines()[0])
    assert command[:2] == [str(compiler), "-v"]
    assert all(flag in command for flag in ("-DRESULT=42", "-g", "-Wl,--build-id=none"))
    assert command.index("-Wl,--build-id=none") > command.index(str(source))
    for name, cc in (("missing", "no-such-asmc-compiler"), ("empty", ""), ("quoted", "'")):
        text, output = check(name, expected=2, environment=dict(env, CC=cc))
        assert "ERROR:" in text and not (output / "cbmc.log").exists()
    print("PASS .S preprocessing, compiler/env quoting and failures", flush=True)

    # Unsized functions infer a lifting window; an explicit end overrides it.
    source = tmp / "unsized.s"
    source.write_text('.text\n.globl answer, answer_end\nanswer:\nmov $42,%rax\nret\nanswer_end:\n'
                      '.section .note.GNU-stack,"",@progbits\n')
    text, output = check("missing_size")
    assert "ASMC lift range:" in text and ".text" in text
    check("unsized_wrong", "outreg.rax == 43", 10)
    symbols = run(["nm", "-n", output / "target.elf"])
    end = next(line.split()[0] for line in symbols.splitlines() if line.endswith(" answer_end"))
    check("end", options=["--lift-end-address", "0x" + end])
    check("bad_end", expected=2, options=["--lift-end-address", "1"])
    check("excludes_return", expected=2, options=["--lift-end-address", hex(int(end, 16) - 1)])
    # Padding broadens the available window, without executing past RET.
    source.write_text(source.read_text().replace('answer_end:', 'answer_end:\nud2\nnop\nnop\nnop'))
    _, output = check("padding")
    listing = (output / "lifted.gb.asm").read_text()
    assert "MOV RAX,0x2a" in listing and "RET" in listing and "UD2" not in listing and "NOP" not in listing
    check("loose_end", options=["--lift-end-address", hex(int(end, 16) + 1)])
    print("PASS inferred/explicit ranges, dead padding and excluded return", flush=True)

    # Section end is the fallback, even when another executable section shares
    # the same LOAD segment. Leaving it cannot silently end the check.
    source.write_text('.text\n.globl answer, helper\nanswer:\nmov $42,%rax\n'
                      '.section .asmc_other,"ax",@progbits\nhelper:\nret\n'
                      '.section .note.GNU-stack,"",@progbits\n')
    text, _ = check("section_edge", expected=2)
    assert "control flow leaves admitted lifting ranges at 0x" in text
    check("section_helper", options=["--callee", "helper"])
    # Same-section unsized callees must not overlap the caller's window.
    source.write_text('.text\n.globl answer, helper\nanswer:\nsub $8,%rsp\ncall helper\n'
                      'add $8,%rsp\nret\nhelper:\nmov $42,%rax\nret\n'
                      '.section .note.GNU-stack,"",@progbits\n')
    text, _ = check("unsized_call", options=["--callee", "helper", "--unwindset", "asmc_target.0:4",
                                           "--max-field-sensitivity-array-size", "768"])
    assert text.count("ASMC lift range:") == 2
    # Metadata still wins: adjacent bytes cannot repair a truncated .size.
    source.write_text(source.read_text().replace('answer:\n', '.type answer,@function\nanswer:\n') +
                      '\n.size answer,1\n')
    text, _ = check("size_wins", expected=2)
    assert "instruction extends beyond the selected lifting window" in text
    print("PASS section bounds, multiple unsized functions and symbol-size priority", flush=True)

    if shutil.which("riscv64-unknown-elf-gcc"):
        for bits in (32, 64):
            source = tmp / ("rv" + str(bits) + ".s")
            source.write_text('.text\n.globl answer\n.type answer,@function\nanswer:\n'
                              'li a0,42\nret\n.size answer,.-answer\n')
            riscv = dict(env, CC="riscv64-unknown-elf-gcc",
                         CFLAGS=f"-march=rv{bits}imc -mabi=" + ("ilp32" if bits == 32 else "lp64"))
            check("rv" + str(bits), "outreg.a0 == 42", environment=riscv)
            source.write_text(source.read_text().replace('.type answer,@function\n', '')
                              .replace('.size answer,.-answer\n', ''))
            text, _ = check("rv" + str(bits) + "-unsized", "outreg.a0 == 42", environment=riscv)
            assert "ASMC lift range:" in text
        print("PASS RV32/RV64 assembly input through CC", flush=True)
