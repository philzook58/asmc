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

        def check_call_wrapper(architecture, elf, function, memory, expected=0):
            abi = "sysv" if architecture == "x86" else "riscv"
            arg = "asmc_sysv_arg64" if architecture == "x86" else "asmc_riscv_arg"
            result = "asmc_sysv_result64" if architecture == "x86" else "asmc_riscv_result"
            name = f"wrapper_{architecture}_{elf.stem}_{function}_{memory}"
            harness = tmp / (name + ".c")
            parameters = "&st, stack, sizeof stack" if memory == "objects" else "&st, stack, 0x1000, sizeof stack"
            harness.write_text(f'''#include "asmc_{architecture}.h"
void harness(void) {{
  uint8_t stack[256];
  struct asmc_state st;
  {arg}(&st, 0, 9);
  asmc_{abi}_call_{memory}_model({parameters});
  assert({result}(&st) == 10);
}}
''')
            text = run([asmc, elf, "--function", function, "--memory", memory,
                        "--harness", harness, "--target", "wrapper_target", "-o", tmp / name,
                        "--timeout", "60", "--memory-limit", "2048"], expected)
            if expected == 10:
                assert f"asmc_{abi}_check" in text, text
            print("PASS demo " + name, flush=True)

        elf = tmp / "x86.elf"
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,inc", ROOT / "tests/challenges.S", "-o", elf])
        post = ["--post", "outreg.rax == inreg.rdi + 1"]
        _, output = check("increment", elf, "inc", post)
        source = (output / "demo.c").read_text()
        assert "asmc_sysv_check(&st, &frame)" in source
        assert "uint8_t stack[256]" in source and "uint64_t rdi;" in source
        for memory in ("ram", "objects"):
            check_call_wrapper("x86", elf, "inc", memory)
            check_call_wrapper("x86", elf, "clobber_saved", memory, 10)
        text, _ = check("wrong_increment", elf, "inc_bad", [*post, "--beautify"], 10)
        assert "inreg.rdi=" in text and "outreg.rax=" in text and "post: outreg.rax == inreg.rdi + 1" in text
        assert "return_value_asmc_get_reg=" not in text and "Recent machine instructions:" in text
        check("wraparound", elf, "inc", ["--pre", "inreg.rdi == UINT64_MAX", "--pre", "inreg.rsi == 9",
                                          "--post", "outreg.rax == 0", "--post", "outreg.rsi == inreg.rsi"])
        check("zero_extension", elf, "alias_dword", ["--post", "outreg.rax == (uint32_t)inreg.rdi"])
        check("dword_aliases", elf, "alias_dword", ["--post", "outreg.eax == inreg.edi",
                                                    "--post", "outreg.rax == outreg.eax"])
        check("dword_wrap", elf, "inc", ["--pre", "inreg.edi == UINT32_MAX",
                                         "--post", "outreg.eax == inreg.edi + 1", "--post", "outreg.eax == 0"])
        text, _ = check("wrong_dword", elf, "inc_bad", ["--post", "outreg.eax == inreg.edi + 1"], 10)
        assert "inreg.edi=" in text and "outreg.eax=" in text
        assert "inreg.rdi=" not in text and "outreg.rax=" not in text and "inreg.al=" not in text
        assert text.count("outreg.eax == inreg.edi + 1") == 1
        text, _ = check("wrong_dword_full", elf, "inc_bad",
                        ["--post", "outreg.eax == inreg.edi + 1", "--full-trace"], 10)
        assert "inreg.rdi=" in text and "inreg.dil=" in text and "outreg.eax=" in text
        text, _ = check("multiple_posts", elf, "inc", ["--post", "outreg.rax == outreg.rdi + 1",
                        "--post", "outreg.rax == inreg.rax"], 10)
        assert "inreg.rax=" in text and "outreg.rax=" in text and "outreg.rdi=" in text
        assert "inreg.eax=" not in text and "inreg.r15=" not in text
        assert text.count("outreg.rax == inreg.rax") == 1
        text, _ = check("custom_entry_alias", elf, "inc_bad", ["--entry", "entry",
                        "--post", "outreg.eax == inreg.edi + 1"], 10)
        assert "inreg.edi=" in text and "inreg.rdi=" not in text
        check("byte_aliases", elf, "alias_byte", ["--post", "outreg.al == 0x34 && outreg.ah == 0x12",
              "--post", "outreg.ax == 0x1234", "--post", "(outreg.rax >> 16) == (inreg.rdi >> 16)"])
        check("word_aliases", elf, "alias_word", ["--post", "outreg.ax == 0x4321",
              "--post", "(outreg.rax >> 16) == (inreg.rdi >> 16)"])
        check("narrow_wrap", elf, "inc", ["--pre", "inreg.dil == UINT8_MAX && inreg.di == UINT16_MAX",
              "--post", "outreg.al == (uint8_t)(inreg.dil + 1)",
              "--post", "outreg.ax == (uint16_t)(inreg.di + 1)"])
        check("extended_aliases", elf, "inc", ["--pre", "inreg.r8 == UINT64_C(0x123456789abcdef0)",
              "--pre", "inreg.r15 == UINT64_C(0xfedcba9876543210)",
              "--pre", "inreg.rcx == 0xab12 && inreg.rdx == 0xcd34 && inreg.rbx == 0xef56",
              "--post", "outreg.r8d == 0x9abcdef0u && outreg.r8w == 0xdef0 && outreg.r8b == 0xf0",
              "--post", "outreg.r15d == 0x76543210u && outreg.r15w == 0x3210 && outreg.r15b == 0x10",
              "--post", "outreg.ch == 0xab && outreg.dh == 0xcd && outreg.bh == 0xef",
              "--post", "outreg.spl == (uint8_t)outreg.rsp && outreg.sp == (uint16_t)outreg.rsp"])
        check("signed_maximum", elf, "max_signed", ["--post",
              "(int64_t)outreg.rax == ((int64_t)inreg.rdi < (int64_t)inreg.rsi ? (int64_t)inreg.rsi : (int64_t)inreg.rdi)"])
        text, _ = check("safety_only", elf, "inc_bad")
        assert "safety/ABI only, no functional postcondition" in text
        check("callee_saved", elf, "clobber_saved", expected=10)
        text, _ = check("return_address", elf, "corrupt_return", expected=10)
        assert "clobbered stack return address" in text
        assert "Return destination: 0x0 (0)" in text and "Expected harness return sentinel:" in text
        text, _ = check("return_address_hex", elf, "corrupt_return", ["--trace-hex"], 10)
        assert "Return destination: 0x0 (0)" in text and "Expected harness return sentinel:" in text
        text, _ = check("unconstrained_pointer", elf, "read64", expected=10)
        assert "memory access" in text
        assert "inreg.rdi=" in text and "inreg.edi=" not in text
        check("bounded_pointer", elf, "read64", ["--pre", "inreg.rdi == 0x1000",
              "--post", "outreg.rax == asmc_load(&st, inreg.rdi, 8)"])
        check("object_stack", elf, "inc", [*post, "--memory", "objects"])
        text, _ = check("properties", elf, "inc", [*post, "--show-properties"])
        assert "post: outreg.rax == inreg.rdi + 1" in text and "INSPECT:" in text and "PASS:" not in text
        check("custom_names", elf, "inc", [*post, "--target", "lifted_inc", "--entry", "entry", "-DDEMO=1"])
        text, output = check("invalid_expression", elf, "inc", ["--post", "outreg.no_such_register == 1"], 2)
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
.globl red_zone
.type red_zone,@function
red_zone:
  movq $42,-8(%rsp)
  ret
.size red_zone,.-red_zone
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
        for memory in ("ram", "objects"):
            check("red_zone_" + memory, elf, "red_zone", ["--memory", memory,
                  "--post", "asmc_load(&st, inreg.rsp - 8, 8) == 42"])
            check("past_stack_" + memory, elf, "red_zone", ["--memory", memory,
                  "--post", "asmc_load(&st, outreg.rsp, 1) == 42"], 10)
        check("small_stack", elf, "stack_use", expected=10)
        for memory in ("ram", "objects"):
            check("large_stack_" + memory, elf, "stack_use",
                  ["--stack-size", "1024", "--memory", memory, "--post", "outreg.rax == 0"])
        check("countdown", elf, "countdown", ["--pre", "inreg.rdi <= 4", "--post", "outreg.rax == 0"])
        text, _ = check("insufficient_bound", elf, "countdown",
                        ["--pre", "inreg.rdi == 4", "--post", "outreg.rax == 0", "--unwindset", "asmc_target.0:2"], 11)
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
                   "--post", "outreg.rax == inreg.rdi + 1"])

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
            for memory in ("ram", "objects"):
                check_call_wrapper("riscv", elf, "zero_test", memory)
                check_call_wrapper("riscv", elf, "bad_saved", memory, 10)
            post = ["--post", "outreg.a0 == inreg.a0 + 1"]
            _, output = check(tag + "increment", elf, "zero_test", post)
            assert f"uint{bits}_t a0;" in (output / "demo.c").read_text()
            check(tag + "wrong_result", elf, "zero_test", ["--post", "outreg.a0 == inreg.a0 + 2"], 10)
            check(tag + "wrap", elf, "zero_test", ["--pre", f"inreg.a0 == UINT{bits}_MAX",
                                                   "--post", "outreg.a0 == 0"])
            check(tag + "object_stack", elf, "zero_test", [*post, "--memory", "objects"])
            check(tag + "saved_register", elf, "bad_saved", expected=10)
            check(tag + "stack_pointer", elf, "bad_sp", expected=10)
            text, _ = check(tag + "return_address", elf, "bad_return", expected=10)
            assert "clobbered RA register" in text
            assert "Return destination:" in text and "Expected harness return sentinel:" in text
            run([compiler, f"-march=rv{bits}imc", "-mabi=" + ("ilp32" if bits == 32 else "lp64"),
                 "-O0", f"-DWORD_BITS={bits}", "-nostdlib", "-static", "-Wl,-e,caller",
                 calls, "-o", elf])
            for memory in ("ram", "objects"):
                check(tag + "compiled_calls_" + memory, elf, "caller",
                      ["--callee", "helper", "--unwindset", "asmc_target.0:4", "--memory", memory, *post])


if __name__ == "__main__":
    main()
