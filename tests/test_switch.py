"""Relative jump tables, explicit targets, immutable ELF data, and access edges."""

import struct
import pytest
from support import ROOT, bounded_run as run, roundtrip

pytestmark = pytest.mark.slow
EXAMPLE = ROOT / "examples/switch"


@pytest.fixture(scope="session")
def jump_table(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("switch")
    elf, data = tmp / "switch.elf", tmp / "rodata.bin"
    run(
        [
            "gcc",
            "-O2",
            "-nostdlib",
            "-static",
            "-no-pie",
            "-fcf-protection=none",
            "-fno-reorder-blocks-and-partition",
            "-Wl,-e,choose",
            EXAMPLE / "switch.c",
            "-o",
            elf,
        ]
    )
    sections = run(["objdump", "-h", elf])
    line = next(line for line in sections.splitlines() if ".rodata" in line)
    size, base = (int(x, 16) for x in line.split()[2:4])
    assert size == 32, "compiler changed fixture table layout"
    run(["objcopy", "--dump-section", f".rodata={data}", elf])
    targets = [hex(base + offset) for offset in struct.unpack("<8i", data.read_bytes())]
    return elf, base, targets


@pytest.mark.parametrize(
    "variant,expected,diagnostic",
    [
        ("complete", 0, "PASS:"),
        ("symbol-target", 0, "PASS:"),
        ("missing-targets", 2, "--indirect-target"),
        ("omitted-case", 10, "indirect jump outside supplied targets"),
        ("missing-rodata", 10, "memory access outside RAM"),
        ("overlap", 10, "RAM overlaps immutable ELF .rodata"),
    ],
)
def test_jump_table(asmc, jump_table, tmp_path, variant, expected, diagnostic):
    elf, base, targets = jump_table
    if variant == "symbol-target":
        targets = targets + ["choose"]
    elif variant == "missing-targets":
        targets = []
    elif variant == "omitted-case":
        targets = targets[1:]
    harness = EXAMPLE / "harness.c"
    if variant == "overlap":
        harness = tmp_path / "overlap.c"
        harness.write_text((EXAMPLE / "harness.c").read_text().replace("0x1000", hex(base)))
    output = tmp_path / "check"
    text = run(
        [
            asmc,
            elf,
            "--function",
            "choose",
            "--harness",
            harness,
            "--link-arg",
            EXAMPLE / "switch.c",
            "--unwind",
            "20",
            "--unwindset",
            "asmc_target.0:3",
            "--timeout",
            "80",
            "--memory-limit",
            "2048",
            "--output-dir",
            output,
            *([] if variant == "missing-rodata" else ["--rodata"]),
            *[arg for target in targets for arg in ("--indirect-target", target)],
        ],
        expected,
        timeout=90,
    )
    assert diagnostic in text
    if expected != 2:
        roundtrip(asmc, output)


@pytest.fixture(scope="session")
def readonly_elf(tmp_path_factory):
    elf = tmp_path_factory.mktemp("readonly") / "readonly.elf"
    run(
        [
            "gcc",
            "-nostdlib",
            "-static",
            "-no-pie",
            "-Wl,-e,read32",
            ROOT / "tests/readonly.S",
            "-o",
            elf,
        ]
    )
    symbols = run(["nm", elf])
    base = int(
        next(line.split()[0] for line in symbols.splitlines() if line.endswith(" constant_bytes")),
        16,
    )
    return elf, base


@pytest.mark.parametrize(
    "function,offset,value,expected,ram",
    [
        pytest.param("read32", 4, 0x88776655, 0, False, id="read-end"),
        pytest.param("read64", 0, 0x8877665544332211, 0, False, id="read-full"),
        pytest.param("read64", 0x1000, 0, 0, True, id="read-ram"),
        pytest.param("read32", 5, 0, 10, False, id="cross-end"),
        pytest.param("read64", -1, 0, 10, False, id="cross-start"),
        pytest.param("read32", (1 << 64) - 2, 0, 10, True, id="wrap"),
        pytest.param("write32", 0, 0, 10, False, id="write-readonly"),
    ],
)
def test_readonly_access(asmc, readonly_elf, tmp_path, function, offset, value, expected, ram):
    elf, base = readonly_elf
    address = offset if ram else base + offset
    harness = tmp_path / "harness.c"
    harness.write_text(
        """#include "asmc_x86.h"
    #include <assert.h>
    void harness(void) {
      uint8_t ram[128] = {0};
      struct asmc_state s;
      struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model(&s, ram, 0x1000, sizeof ram);
      asmc_sysv_arg64(&s, 0, """
        + str(address)
        + """ULL);
      asmc_target(&s);
      assert(asmc_sysv_result64(&s) == """
        + str(value)
        + """ULL);
      asmc_sysv_check(&s, &frame);
    }
    """
    )
    output = tmp_path / "check"
    text = run(
        [
            asmc,
            elf,
            "--function",
            function,
            "--harness",
            harness,
            "--rodata",
            "--memory-limit",
            "2048",
            "--timeout",
            "80",
            "--output-dir",
            output,
        ],
        expected,
        timeout=90,
    )
    assert ("PASS:" if expected == 0 else "FAIL:") in text
    roundtrip(asmc, output)
