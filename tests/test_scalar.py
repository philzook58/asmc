"""Register-word storage: overlapping accesses, malformed templates, and object aliases."""

import pytest
from support import ROOT, bounded_run as run

pytestmark = pytest.mark.slow


def test_register_bank_edges(scalar_asmc, tmp_path):
    tmp = tmp_path
    harness = tmp / "bank.c"
    checks = []
    for offset in (0, 28, 60, 508, 760):
        checks += [
            f"asmc_set_reg(&s, {offset}, 8, value);",
            f"assert(asmc_get_reg(&s, {offset}, 8) == value);",
            f"asmc_set_reg(&s, {offset + 3}, 1, 0x5a);",
            f"assert(asmc_get_reg(&s, {offset}, 8) == ((value & ~UINT64_C(0xff000000)) | UINT64_C(0x5a000000)));",
        ]
    harness.write_text(
        '#include "asmc_state.h"\n#include <assert.h>\n'
        "void harness(void) { struct asmc_state s; uint64_t value;\n"
        "assert(sizeof s.registers == ASMC_REGISTER_BYTES);\n" + "\n".join(checks) + "\n}\n"
    )
    model = tmp / "bank.gb"
    run(
        [
            scalar_asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            ROOT / "runtime/runtime.c",
            harness,
            "-o",
            model,
        ]
    )
    run(
        [
            scalar_asmc.parent / "cbmc",
            model,
            "--function",
            "harness",
            "--unwind",
            "10",
            "--unwinding-assertions",
            "--bounds-check",
            "--pointer-check",
            "--validate-goto-model",
        ]
    )


@pytest.fixture
def alias_elf(tmp_path):
    tmp = tmp_path
    source, elf = tmp / "alias.S", tmp / "alias.elf"
    source.write_text(
        ".text\n.globl alias\n.type alias,@function\nalias:\n"
        "movb $0x5a,(%rdi)\nmov %rdx,%rax\nret\n.size alias,.-alias\n"
        '.section .note.GNU-stack,"",@progbits\n'
    )
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,alias", source, "-o", elf])
    return elf


@pytest.mark.parametrize(
    "layout",
    (
        "struct { unsigned long long block0[32], block1[32], block2[31]; } registers",
        "struct { long long block0[32], block1[32], block2[32]; } registers",
        "struct { unsigned block0[32], block1[32], block2[32]; } registers",
    ),
    ids=["wrong-size", "signed-words", "wrong-word-width"],
)
def test_invalid_register_bank(scalar_asmc, alias_elf, tmp_path, layout):
    tmp = tmp_path
    elf = alias_elf
    bad = tmp / "bad.c"
    bad.write_text(
        f"struct asmc_state {{ {layout}; }};\nvoid asmc_target(struct asmc_state *s) {{}}\n"
    )
    run([scalar_asmc.parent / "goto-cc", "-c", bad, "-o", tmp / "bad.gb"])
    text = run(
        [
            scalar_asmc.parent / "asmc-lift",
            elf,
            "--function",
            "alias",
            "--template",
            tmp / "bad.gb",
            "-o",
            tmp / "bad-lift.gb",
        ],
        2,
    )
    assert "template must have uint8_t registers" in text
    assert not (tmp / "bad-lift.gb").exists()


def test_object_aliases_register_bank(scalar_asmc, alias_elf, tmp_path):
    tmp = tmp_path
    elf = alias_elf
    harness = tmp / "harness.c"
    harness.write_text("""#include "asmc_x86.h"
    #include <assert.h>
    void harness(void) {
      uint8_t stack[128]; struct asmc_state s;
      struct asmc_sysv_frame frame = asmc_sysv_setup_objects_model(&s, stack, sizeof stack);
      asmc_set_reg(&s, ASMC_RDX, 8, 0);
      asmc_sysv_arg_ptr(&s, 0, &ASMC_REG_BYTE(&s, ASMC_RDX));
      asmc_target(&s);
      assert(asmc_sysv_result64(&s) == 0x5a);
      asmc_sysv_check(&s, &frame);
    }
    """)
    run(
        [
            scalar_asmc,
            elf,
            "--function",
            "alias",
            "--harness",
            harness,
            "--memory",
            "objects",
            "--timeout",
            "90",
            "--memory-limit",
            "1024",
            "-o",
            tmp / "alias",
        ]
    )
