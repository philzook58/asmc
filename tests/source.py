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

    def check(name, property="out.rax == 42", expected=0, options=(), environment=env):
        output = tmp / name
        text = run([asmc, source, "--function", "answer", "--post", property,
                    "-o", output, *options], expected, environment)
        assert (output / "result.txt").read_text().strip() in text
        return text, output

    text, output = check("source")
    assert "ELF: " + str(output / "target.elf") in text
    assert (output / "assemble.log").is_file() and (output / "target.elf").is_file()
    text, output = check("wrong", "out.rax == 43", 10)
    recent = text.split("Recent machine instructions:\n", 1)[1].split("Violated property:", 1)[0]
    assert recent.count("MOV RAX,0x2a") == 1 and recent.count("RET") == 1, recent
    assert "out.rax=42" in text and "FAIL:" in text
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

    # Size-free assembly needs an exclusive end address from the linked ELF.
    source = tmp / "unsized.s"
    source.write_text('.text\n.globl answer, answer_end\nanswer:\nmov $42,%rax\nret\nanswer_end:\n'
                      '.section .note.GNU-stack,"",@progbits\n')
    text, output = check("missing_size", expected=2)
    assert "exclusive linked virtual address, not a byte count" in text and "nm -n " in text
    symbols = run(["nm", "-n", output / "target.elf"])
    end = next(line.split()[0] for line in symbols.splitlines() if line.endswith(" answer_end"))
    check("end", options=["--end-address", "0x" + end])
    check("bad_end", expected=2, options=["--end-address", "1"])
    print("PASS end-label address and invalid range", flush=True)

    if shutil.which("riscv64-unknown-elf-gcc"):
        for bits in (32, 64):
            source = tmp / ("rv" + str(bits) + ".s")
            source.write_text('.text\n.globl answer\n.type answer,@function\nanswer:\n'
                              'li a0,42\nret\n.size answer,.-answer\n')
            riscv = dict(env, CC="riscv64-unknown-elf-gcc",
                         CFLAGS=f"-march=rv{bits}imc -mabi=" + ("ilp32" if bits == 32 else "lp64"))
            check("rv" + str(bits), "out.a0 == 42", environment=riscv)
        print("PASS RV32/RV64 assembly input through CC", flush=True)
