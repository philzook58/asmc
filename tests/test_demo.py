"""Generated harness contracts: passing examples, mutations, and ABI failures."""
import pytest

from support import run

pytestmark = pytest.mark.slow
INC_POST = ["--post", "outreg.rax == inreg.rdi + 1"]


@pytest.fixture
def check(asmc, tmp_path):
    def invoke(elf, function, options=(), expected=0):
        output = tmp_path / "check"
        text = run([asmc, elf, "--function", function, "-o", output,
                    "--timeout", "60", "--memory-limit", "2048", *options], expected, timeout=90)
        assert (output / "demo.c").is_file(), text
        assert (output / "result.txt").read_text().strip() in text, text
        if expected != 2:
            run([asmc.parent / "goto-instrument", "--validate-goto-model",
                 output / "lifted.gb", output / "roundtrip.gb"])
        return text, output
    return invoke


@pytest.fixture(scope="session")
def saved_elf(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("saved")
    saved_assembly = tmp_path / "saved.S"
    saved_assembly.write_text('''.text
    .globl clobber_r12, restore_r12
    .type clobber_r12,@function
    clobber_r12:
      mov $42,%r12
      ret
    .size clobber_r12,.-clobber_r12
    .type restore_r12,@function
    restore_r12:
      push %r12
      mov $42,%r12
      pop %r12
      ret
    .size restore_r12,.-restore_r12
    ''')
    saved_elf = tmp_path / "saved.elf"
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,clobber_r12", saved_assembly, "-o", saved_elf])
    return saved_elf


@pytest.fixture(scope="session")
def stack_elf(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("stack")
    elf = tmp_path / "stack.elf"
    assembly = tmp_path / "stack_and_loop.S"
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
    return elf


def test_increment(check, x86_elf):
    _, output = check(x86_elf, "inc", INC_POST)
    source = (output / "demo.c").read_text()
    assert "asmc_sysv_check(&st, &frame)" in source
    assert "uint8_t stack[256]" in source and "uint64_t rdi;" in source


def test_wrong_increment(check, x86_elf):
    text, _ = check(x86_elf, "inc_bad", [*INC_POST, "--beautify"], 10)
    assert "inreg.rdi=" in text and "outreg.rax=" in text and "post: outreg.rax == inreg.rdi + 1" in text
    assert "return_value_asmc_get_reg=" not in text and "Recent machine instructions:" in text


def test_wraparound(check, x86_elf):
    check(x86_elf, "inc", ["--pre", "inreg.rdi == UINT64_MAX", "--pre", "inreg.rsi == 9",
                                      "--post", "outreg.rax == 0", "--post", "outreg.rsi == inreg.rsi"])


def test_zero_extension(check, x86_elf):
    check(x86_elf, "alias_dword", ["--post", "outreg.rax == (uint32_t)inreg.rdi"])


def test_dword_aliases(check, x86_elf):
    check(x86_elf, "alias_dword", ["--post", "outreg.eax == inreg.edi",
                                                "--post", "outreg.rax == outreg.eax"])


def test_dword_wrap(check, x86_elf):
    check(x86_elf, "inc", ["--pre", "inreg.edi == UINT32_MAX",
                                     "--post", "outreg.eax == inreg.edi + 1", "--post", "outreg.eax == 0"])


def test_wrong_dword(check, x86_elf):
    text, _ = check(x86_elf, "inc_bad", ["--post", "outreg.eax == inreg.edi + 1"], 10)
    assert "inreg.edi=" in text and "outreg.eax=" in text
    assert "inreg.rdi=" not in text and "outreg.rax=" not in text and "inreg.al=" not in text
    assert text.count("outreg.eax == inreg.edi + 1") == 1


def test_wrong_dword_full_trace(check, x86_elf):
    text, _ = check(x86_elf, "inc_bad",
                    ["--post", "outreg.eax == inreg.edi + 1", "--full-trace"], 10)
    assert "inreg.rdi=" in text and "inreg.dil=" in text and "outreg.eax=" in text


def test_multiple_posts(check, x86_elf):
    text, _ = check(x86_elf, "inc", ["--post", "outreg.rax == outreg.rdi + 1",
                    "--post", "outreg.rax == inreg.rax"], 10)
    assert "inreg.rax=" in text and "outreg.rax=" in text and "outreg.rdi=" in text
    assert "inreg.eax=" not in text and "inreg.r15=" not in text
    assert text.count("outreg.rax == inreg.rax") == 1


def test_custom_entry_alias(check, x86_elf):
    text, _ = check(x86_elf, "inc_bad", ["--entry", "entry",
                    "--post", "outreg.eax == inreg.edi + 1"], 10)
    assert "inreg.edi=" in text and "inreg.rdi=" not in text


def test_byte_aliases(check, x86_elf):
    check(x86_elf, "alias_byte", ["--post", "outreg.al == 0x34 && outreg.ah == 0x12",
          "--post", "outreg.ax == 0x1234", "--post", "(outreg.rax >> 16) == (inreg.rdi >> 16)"])


def test_word_aliases(check, x86_elf):
    check(x86_elf, "alias_word", ["--post", "outreg.ax == 0x4321",
          "--post", "(outreg.rax >> 16) == (inreg.rdi >> 16)"])


def test_narrow_wrap(check, x86_elf):
    check(x86_elf, "inc", ["--pre", "inreg.dil == UINT8_MAX && inreg.di == UINT16_MAX",
          "--post", "outreg.al == (uint8_t)(inreg.dil + 1)",
          "--post", "outreg.ax == (uint16_t)(inreg.di + 1)"])


def test_extended_aliases(check, x86_elf):
    check(x86_elf, "inc", ["--pre", "inreg.r8 == UINT64_C(0x123456789abcdef0)",
          "--pre", "inreg.r15 == UINT64_C(0xfedcba9876543210)",
          "--pre", "inreg.rcx == 0xab12 && inreg.rdx == 0xcd34 && inreg.rbx == 0xef56",
          "--post", "outreg.r8d == 0x9abcdef0u && outreg.r8w == 0xdef0 && outreg.r8b == 0xf0",
          "--post", "outreg.r15d == 0x76543210u && outreg.r15w == 0x3210 && outreg.r15b == 0x10",
          "--post", "outreg.ch == 0xab && outreg.dh == 0xcd && outreg.bh == 0xef",
          "--post", "outreg.spl == (uint8_t)outreg.rsp && outreg.sp == (uint16_t)outreg.rsp"])


def test_signed_maximum(check, x86_elf):
    check(x86_elf, "max_signed", ["--post",
          "(int64_t)outreg.rax == ((int64_t)inreg.rdi < (int64_t)inreg.rsi ? (int64_t)inreg.rsi : (int64_t)inreg.rdi)"])


def test_safety_only(check, x86_elf):
    text, _ = check(x86_elf, "inc_bad")
    assert "safety/ABI only, no functional postcondition" in text


def test_callee_saved_rbx(check, x86_elf):
    text, _ = check(x86_elf, "clobber_saved", expected=10)
    assert "ABI violation: callee-saved register RBX was not restored" in text


def test_unconstrained_pointer(check, x86_elf):
    text, _ = check(x86_elf, "read64", expected=10)
    assert "memory access" in text
    assert "inreg.rdi=" in text and "inreg.edi=" not in text


def test_bounded_pointer(check, x86_elf):
    check(x86_elf, "read64", ["--pre", "inreg.rdi == 0x1000",
          "--post", "outreg.rax == asmc_load(&st, inreg.rdi, 8)"])


def test_object_stack(check, x86_elf):
    check(x86_elf, "inc", [*INC_POST, "--memory", "objects"])


def test_properties(check, x86_elf):
    text, _ = check(x86_elf, "inc", [*INC_POST, "--show-properties"])
    assert "post: outreg.rax == inreg.rdi + 1" in text and "INSPECT:" in text and "PASS:" not in text


def test_custom_names(check, x86_elf):
    check(x86_elf, "inc", [*INC_POST, "--target", "lifted_inc", "--entry", "entry", "-DDEMO=1"])


def test_invalid_expression(check, x86_elf):
    text, output = check(x86_elf, "inc", ["--post", "outreg.no_such_register == 1"], 2)
    assert "ERROR:" in text and (output / "link.log").is_file() and not (output / "cbmc.log").exists()


@pytest.mark.parametrize("function,expected", [("clobber_r12", 10), ("restore_r12", 0)], ids=["clobbered", "restored"])
def test_callee_saved_r12(check, saved_elf, function, expected):
    text, _ = check(saved_elf, function, expected=expected)
    if expected == 10:
        assert "ABI violation: callee-saved register R12 was not restored" in text


@pytest.mark.parametrize("options", [[], ["--trace-hex"]], ids=["decimal", "hex"])
def test_return_address(check, x86_elf, options):
    text, _ = check(x86_elf, "corrupt_return", options, 10)
    assert "clobbered stack return address" in text
    assert "Return destination: 0x0 (0)" in text and "Expected harness return sentinel:" in text


def test_reuse_generated_harness(asmc, check, x86_elf, tmp_path):
    _, output = check(x86_elf, "inc", INC_POST)
    # The generated file can be used unchanged as an explicit harness.
    text = run([asmc, x86_elf, "--function", "inc", "--harness", output / "demo.c",
                "-o", tmp_path / "reused", "--memory-limit", "2048"])
    assert "PASS:" in text and not (tmp_path / "reused/demo.c").exists()


@pytest.mark.parametrize("option", [["--post", "1"], ["--pre", "1"], ["--stack-size", "256"]], ids=["post", "pre", "stack-size"])
def test_rejects_default_only_options_with_harness(asmc, check, x86_elf, option):
    _, output = check(x86_elf, "inc", INC_POST)
    text = run([asmc, x86_elf, "--function", "inc", "--harness", output / "demo.c", *option], 2)
    assert "default harness" in text


def test_rejects_tiny_stack(asmc, x86_elf):
    text = run([asmc, x86_elf, "--function", "inc", "--stack-size", "8"], 2)
    assert "at least 16" in text


@pytest.mark.parametrize("memory", ["ram", "objects"])
@pytest.mark.parametrize("valid_address", [True, False], ids=["valid", "past-stack"])
def test_red_zone(check, stack_elf, memory, valid_address):
    post = "asmc_load(&st, inreg.rsp - 8, 8) == 42" if valid_address else "asmc_load(&st, outreg.rsp, 1) == 42"
    check(stack_elf, "red_zone", ["--memory", memory, "--post", post], 0 if valid_address else 10)


@pytest.mark.parametrize("memory", ["ram", "objects"])
@pytest.mark.parametrize("large", [False, True], ids=["too-small", "sufficient"])
def test_stack_capacity(check, stack_elf, memory, large):
    options = ["--memory", memory]
    if large:
        options += ["--stack-size", "1024", "--post", "outreg.rax == 0"]
    check(stack_elf, "stack_use", options, 0 if large else 10)


def test_bounded_loop(check, stack_elf):
    check(stack_elf, "countdown", ["--pre", "inreg.rdi <= 4", "--post", "outreg.rax == 0"])


def test_insufficient_loop_bound(check, stack_elf):
    text, _ = check(stack_elf, "countdown",
                    ["--pre", "inreg.rdi == 4", "--post", "outreg.rax == 0", "--unwindset", "asmc_target.0:2"], 11)
    assert "INCOMPLETE:" in text and "PASS:" not in text


@pytest.fixture(scope="session")
def caller_elf(architecture, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("caller-" + architecture)
    source = tmp / "calls.c"
    word_type = "uint32_t" if architecture == "rv32" else "uint64_t"
    source.write_text(f"#include <stdint.h>\ntypedef {word_type} word;\n"
                      "__attribute__((noinline)) word helper(word x) { return x + 1; }\n"
                      "word caller(word x) { return helper(x); }\n")
    elf = tmp / "calls.elf"
    compiler, flags = "gcc", ["-no-pie", "-fno-stack-protector"]
    if architecture != "x86":
        bits = int(architecture[2:])
        compiler = "riscv64-unknown-elf-gcc"
        flags = [f"-march=rv{bits}imc", "-mabi=" + ("ilp32" if bits == 32 else "lp64")]
    run([compiler, *flags, "-O0", "-nostdlib", "-static", "-Wl,-e,caller", source, "-o", elf])
    return elf


@pytest.mark.parametrize("memory", ["ram", "objects"])
def test_compiled_calls(check, caller_elf, architecture, memory):
    post = "outreg.rax == inreg.rdi + 1" if architecture == "x86" else "outreg.a0 == inreg.a0 + 1"
    check(caller_elf, "caller", ["--callee", "helper", "--unwindset", "asmc_target.0:4",
                                          "--memory", memory, "--post", post])


@pytest.mark.parametrize("memory", ["ram", "objects"])
@pytest.mark.parametrize("bad", [False, True], ids=["preserved", "clobbered"])
def test_call_wrapper_checks_abi(asmc, instructions, architecture, tmp_path, memory, bad):
    x86 = architecture == "x86"
    abi = "sysv" if x86 else "riscv"
    arg = "asmc_sysv_arg64" if x86 else "asmc_riscv_arg"
    result = "asmc_sysv_result64" if x86 else "asmc_riscv_result"
    parameters = "&st, stack, sizeof stack" if memory == "objects" else "&st, stack, 0x1000, sizeof stack"
    harness = tmp_path / "wrapper.c"
    harness.write_text(f'''#include "asmc_{'x86' if x86 else 'riscv'}.h"
void harness(void) {{
  uint8_t stack[256];
  struct asmc_state st;
  {arg}(&st, 0, 9);
  asmc_{abi}_call_{memory}_model({parameters});
  assert({result}(&st) == 10);
}}
''')
    function = ("clobber_saved" if bad else "inc") if x86 else ("bad_saved" if bad else "zero_test")
    text = run([asmc, instructions, "--function", function, "--memory", memory,
                "--harness", harness, "--target", "wrapper_target", "-o", tmp_path / "check",
                "--timeout", "60", "--memory-limit", "2048"], 10 if bad else 0)
    if bad:
        assert f"asmc_{abi}_check" in text


@pytest.mark.parametrize("architecture", ["rv32", "rv64"], indirect=True)
@pytest.mark.parametrize("function,options,expected,diagnostics", [
    pytest.param("zero_test", ["--post", "outreg.a0 == inreg.a0 + 1"], 0, [], id="increment"),
    pytest.param("zero_test", ["--post", "outreg.a0 == inreg.a0 + 2"], 10, [], id="wrong-result"),
    pytest.param("zero_test", ["--pre", "inreg.a0 == UINT{bits}_MAX", "--post", "outreg.a0 == 0"],
                 0, [], id="wrap"),
    pytest.param("zero_test", ["--post", "outreg.a0 == inreg.a0 + 1", "--memory", "objects"],
                 0, [], id="object-stack"),
    pytest.param("bad_saved", [], 10, ["ABI violation: callee-saved register s0 (x8) was not restored"],
                 id="saved-register"),
    pytest.param("bad_sp", [], 10, ["ABI violation: stack pointer sp (x2) was not restored"],
                 id="stack-pointer"),
    pytest.param("bad_return", [], 10, ["clobbered RA register", "Return destination:",
                                       "Expected harness return sentinel:"], id="return-address"),
])
def test_riscv_contract(check, instructions, architecture, function, options, expected, diagnostics):
    bits = int(architecture[2:])
    options = [option.format(bits=bits) for option in options]
    text, output = check(instructions, function, options, expected)
    assert f"uint{bits}_t a0;" in (output / "demo.c").read_text()
    for diagnostic in diagnostics:
        assert diagnostic in text
