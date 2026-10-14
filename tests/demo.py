"""Default C harness: widths, contracts, ABI, memory and honest bound failures."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(command, expected=0):
    process = subprocess.run([str(arg) for arg in command], capture_output=True,
                             text=True, timeout=90)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="asmc-demo-tests-") as temp:
        tmp = Path(temp)

        def check(name, elf, function, options=(), expected=0):
            output = tmp / name
            text = run([asmc, elf, "--function", function, "-o", output,
                        "--timeout", "60", "--memory-limit", "2048", *options], expected)
            assert (output / "demo.c").is_file(), text
            assert (output / "result.txt").read_text().strip() in text, text
            if expected != 2:
                run([asmc.parent / "goto-instrument", "--validate-goto-model",
                     output / "lifted.gb", output / "roundtrip.gb"])
            print("PASS demo " + name, flush=True)
            return text, output

        elf = tmp / "x86.elf"
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,inc", ROOT / "tests/challenges.S", "-o", elf])
        post = ["--post", "out.rax == in.rdi + 1"]
        _, output = check("increment", elf, "inc", post)
        source = (output / "demo.c").read_text()
        assert "asmc_sysv_check(&s, &frame)" in source
        assert "uint8_t stack[256]" in source and "uint64_t rdi;" in source
        text, _ = check("wrong_increment", elf, "inc_bad", [*post, "--beautify"], 10)
        assert "in.rdi=" in text and "out.rax=" in text and "post: out.rax == in.rdi + 1" in text
        assert "return_value_asmc_get_reg=" not in text and "Recent machine instructions:" in text
        check("wraparound", elf, "inc", ["--pre", "in.rdi == UINT64_MAX", "--pre", "in.rsi == 9",
                                          "--post", "out.rax == 0", "--post", "out.rsi == in.rsi"])
        check("zero_extension", elf, "alias_dword", ["--post", "out.rax == (uint32_t)in.rdi"])
        check("dword_aliases", elf, "alias_dword", ["--post", "out.eax == in.edi",
                                                    "--post", "out.rax == out.eax"])
        check("dword_wrap", elf, "inc", ["--pre", "in.edi == UINT32_MAX",
                                         "--post", "out.eax == in.edi + 1", "--post", "out.eax == 0"])
        text, _ = check("wrong_dword", elf, "inc_bad", ["--post", "out.eax == in.edi + 1"], 10)
        assert "in.edi=" in text and "out.eax=" in text
        check("byte_aliases", elf, "alias_byte", ["--post", "out.al == 0x34 && out.ah == 0x12",
              "--post", "out.ax == 0x1234", "--post", "(out.rax >> 16) == (in.rdi >> 16)"])
        check("word_aliases", elf, "alias_word", ["--post", "out.ax == 0x4321",
              "--post", "(out.rax >> 16) == (in.rdi >> 16)"])
        check("narrow_wrap", elf, "inc", ["--pre", "in.dil == UINT8_MAX && in.di == UINT16_MAX",
              "--post", "out.al == (uint8_t)(in.dil + 1)",
              "--post", "out.ax == (uint16_t)(in.di + 1)"])
        check("extended_aliases", elf, "inc", ["--pre", "in.r8 == UINT64_C(0x123456789abcdef0)",
              "--pre", "in.r15 == UINT64_C(0xfedcba9876543210)",
              "--pre", "in.rcx == 0xab12 && in.rdx == 0xcd34 && in.rbx == 0xef56",
              "--post", "out.r8d == 0x9abcdef0u && out.r8w == 0xdef0 && out.r8b == 0xf0",
              "--post", "out.r15d == 0x76543210u && out.r15w == 0x3210 && out.r15b == 0x10",
              "--post", "out.ch == 0xab && out.dh == 0xcd && out.bh == 0xef",
              "--post", "out.spl == (uint8_t)out.rsp && out.sp == (uint16_t)out.rsp"])
        check("signed_maximum", elf, "max_signed", ["--post",
              "(int64_t)out.rax == ((int64_t)in.rdi < (int64_t)in.rsi ? (int64_t)in.rsi : (int64_t)in.rdi)"])
        text, _ = check("safety_only", elf, "inc_bad")
        assert "safety/ABI only, no functional postcondition" in text
        check("callee_saved", elf, "clobber_saved", expected=10)
        text, _ = check("return_address", elf, "corrupt_return", expected=10)
        assert "unexpected return address" in text
        text, _ = check("unconstrained_pointer", elf, "read64", expected=10)
        assert "memory access" in text
        check("bounded_pointer", elf, "read64", ["--pre", "in.rdi == 0x1000",
              "--post", "out.rax == asmc_load(&s, in.rdi, 8)"])
        check("object_stack", elf, "inc", [*post, "--memory", "objects"])
        text, _ = check("properties", elf, "inc", [*post, "--show-properties"])
        assert "post: out.rax == in.rdi + 1" in text and "INSPECT:" in text and "PASS:" not in text
        check("custom_names", elf, "inc", [*post, "--target", "lifted_inc", "--entry", "entry", "-DDEMO=1"])
        text, output = check("invalid_expression", elf, "inc", ["--post", "out.no_such_register == 1"], 2)
        assert "ERROR:" in text and (output / "link.log").is_file() and not (output / "cbmc.log").exists()

        # The generated file can be used unchanged as an explicit harness.
        text = run([asmc, elf, "--function", "inc", "--harness", tmp / "increment/demo.c",
                    "-o", tmp / "reused", "--memory-limit", "2048"])
        assert "PASS:" in text and not (tmp / "reused/demo.c").exists()
        for option in (["--post", "1"], ["--pre", "1"], ["--stack-size", "256"]):
            text = run([asmc, elf, "--function", "inc", "--harness", tmp / "increment/demo.c", *option], 2)
            assert "default harness" in text
        text = run([asmc, elf, "--function", "inc", "--stack-size", "8"], 2)
        assert "at least 16" in text

        assembly = tmp / "stack_and_loop.S"
        assembly.write_text('''.text
.globl stack_use
.type stack_use,@function
stack_use:
  sub $512,%rsp
  movq $7,(%rsp)
  add $512,%rsp
  xor %eax,%eax
  ret
.size stack_use,.-stack_use
.globl countdown
.type countdown,@function
countdown:
  mov %rdi,%rax
  test %rax,%rax
  je 2f
1:dec %rax
  jne 1b
2:ret
.size countdown,.-countdown
.section .note.GNU-stack,"",@progbits
''')
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,stack_use", assembly, "-o", elf])
        check("small_stack", elf, "stack_use", expected=10)
        for memory in ("ram", "objects"):
            check("large_stack_" + memory, elf, "stack_use",
                  ["--stack-size", "1024", "--memory", memory, "--post", "out.rax == 0"])
        check("countdown", elf, "countdown", ["--pre", "in.rdi <= 4", "--post", "out.rax == 0"])
        text, _ = check("insufficient_bound", elf, "countdown",
                        ["--pre", "in.rdi == 4", "--post", "out.rax == 0", "--unwindset", "asmc_target.0:2"], 11)
        assert "INCOMPLETE:" in text and "PASS:" not in text

        # Unoptimized C exercises real call frames and stack spills in both modes.
        calls = tmp / "calls.c"
        calls.write_text('''#include <stdint.h>
#if WORD_BITS == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
__attribute__((noinline)) word helper(word x) { return x + 1; }
word caller(word x) { return helper(x); }
''')
        run(["gcc", "-O0", "-DWORD_BITS=64", "-nostdlib", "-no-pie", "-fno-stack-protector",
             "-Wl,-e,caller", calls, "-o", elf])
        for memory in ("ram", "objects"):
            check("compiled_calls_" + memory, elf, "caller",
                  ["--callee", "helper", "--unwindset", "asmc_target.0:4", "--memory", memory,
                   "--post", "out.rax == in.rdi + 1"])

        compiler = shutil.which("riscv64-unknown-elf-gcc")
        if not compiler:
            print("SKIP RV32/RV64: riscv64-unknown-elf-gcc not found", flush=True)
            return
        for bits in (32, 64):
            elf = tmp / f"rv{bits}.elf"
            run([compiler, f"-march=rv{bits}imc", "-mabi=" + ("ilp32" if bits == 32 else "lp64"),
                 "-nostdlib", "-static", "-Wl,--no-relax,-e,zero_test",
                 ROOT / "examples/riscv/instructions.S", "-o", elf])
            tag = f"rv{bits}_"
            post = ["--post", "out.a0 == in.a0 + 1"]
            _, output = check(tag + "increment", elf, "zero_test", post)
            assert f"uint{bits}_t a0;" in (output / "demo.c").read_text()
            check(tag + "wrong_result", elf, "zero_test", ["--post", "out.a0 == in.a0 + 2"], 10)
            check(tag + "wrap", elf, "zero_test", ["--pre", f"in.a0 == UINT{bits}_MAX",
                                                   "--post", "out.a0 == 0"])
            check(tag + "object_stack", elf, "zero_test", [*post, "--memory", "objects"])
            check(tag + "saved_register", elf, "bad_saved", expected=10)
            check(tag + "stack_pointer", elf, "bad_sp", expected=10)
            check(tag + "return_address", elf, "bad_return", expected=10)
            run([compiler, f"-march=rv{bits}imc", "-mabi=" + ("ilp32" if bits == 32 else "lp64"),
                 "-O0", f"-DWORD_BITS={bits}", "-nostdlib", "-static", "-Wl,-e,caller",
                 calls, "-o", elf])
            for memory in ("ram", "objects"):
                check(tag + "compiled_calls_" + memory, elf, "caller",
                      ["--callee", "helper", "--unwindset", "asmc_target.0:4", "--memory", memory, *post])


if __name__ == "__main__":
    main()
