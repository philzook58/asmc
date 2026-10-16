"""Compare the lifted ELF with independent QEMU execution, on RV32 and RV64."""

import random
import shutil

import pytest

from support import ROOT, bounded_run as run, roundtrip

pytestmark = pytest.mark.slow


@pytest.fixture(scope="session", params=[32, 64], ids=["rv32", "rv64"])
def qemu_observations(request, tmp_path_factory):
    bits = request.param
    compiler = shutil.which("riscv64-unknown-elf-gcc")
    qemu = shutil.which(f"qemu-riscv{bits}")
    if not compiler or not qemu:
        pytest.skip(f"RISC-V compiler and qemu-riscv{bits} are required")
    directory = tmp_path_factory.mktemp(f"qemu-rv{bits}")
    elf = directory / "oracle.elf"
    run(
        [
            compiler,
            f"-march=rv{bits}imc",
            "-mabi=" + ("ilp32" if bits == 32 else "lp64"),
            "-O2",
            "-ffreestanding",
            "-fno-stack-protector",
            "-nostdlib",
            "-static",
            "-Wl,--no-relax,-e,_start",
            ROOT / "tests/riscv_native.S",
            ROOT / "tests/riscv_native_runner.c",
            "-o",
            elf,
        ]
    )
    mask, high = (1 << bits) - 1, 1 << (bits - 1)
    inputs = [
        (0, 0),
        (mask, 1),
        (mask, mask),
        (high - 1, 1),
        (high, mask),
        (127, 1),
        (255, 1),
        (1, bits - 1),
        (1, bits),
        (1, bits + 1),
        (mask, 255),
        (high, bits - 1),
    ]
    rng = random.Random(0xA5C)
    inputs += [(rng.getrandbits(bits), rng.getrandbits(bits)) for _ in range(12)]
    records = "".join(f"{a:0{bits//4}x}{b:0{bits//4}x}\n" for a, b in inputs)
    # RV32 QEMU reserves a 4 GiB guest address space; this is virtual memory,
    # so the ordinary 2 GiB tool limit cannot be applied to the emulator.
    text = run([qemu, elf], input=records, log=directory / "qemu.log", memory_gib=None)
    observed = [[int(value, 16) for value in line.split()] for line in text.splitlines()]
    assert len(observed) == len(inputs) and all(len(row) == 7 for row in observed)
    return elf, [list(pair) + row for pair, row in zip(inputs, observed)]


@pytest.mark.parametrize("corrupt", [None, 2, 3], ids=["qemu", "corrupt-return", "corrupt-memory"])
def test_qemu_oracle(asmc, qemu_observations, tmp_path, corrupt):
    elf, original = qemu_observations
    rows = [row[:] for row in original]
    if corrupt is not None:
        rows[0][corrupt] ^= 1
    constants = ",\n".join("{" + ",".join(f"{n}ULL" for n in row) + "}" for row in rows)
    harness = tmp_path / "harness.c"
    harness.write_text(
        """#include "asmc_riscv.h"
unsigned nondet_unsigned(void);
static const uint64_t observations[][9] = {
"""
        + constants
        + """};
void harness(void) {
  unsigned sample = nondet_unsigned();
  __CPROVER_assume(sample < sizeof observations / sizeof observations[0]);
  uint8_t ram[128] = {0};
  struct asmc_state st;
  struct asmc_riscv_frame frame = asmc_riscv_setup_ram_model(&st, ram, 0x1000, sizeof ram);
  asmc_riscv_arg(&st, 0, observations[sample][0]);
  asmc_riscv_arg(&st, 1, observations[sample][1]);
  asmc_riscv_arg(&st, 2, 0x1000);
  asmc_target(&st);
  __CPROVER_assert(asmc_riscv_result(&st) == observations[sample][2], "QEMU return value");
  for (unsigned i = 0; i < 6; ++i)
    __CPROVER_assert(asmc_load(&st, 0x1000 + i*ASMC_RV_BYTES, ASMC_RV_BYTES)
                     == observations[sample][3+i], "QEMU memory output");
  for (unsigned i = 6*ASMC_RV_BYTES; i < 112; ++i) assert(ram[i] == 0);
  asmc_riscv_check(&st, &frame);
}
"""
    )
    output = tmp_path / "check"
    text = run(
        [
            asmc,
            elf,
            "--function",
            "probe",
            "--callee",
            "probe_helper",
            "--harness",
            harness,
            "--unwind",
            "114",
            "--unwindset",
            "asmc_target.0:4",
            "--timeout",
            "90",
            "--memory-limit",
            "2048",
            "--output-dir",
            output,
        ],
        10 if corrupt else 0,
    )
    assert ("FAIL:" if corrupt else "PASS:") in text
    if corrupt:
        assert ("QEMU return value" if corrupt == 2 else "QEMU memory output") in text
        assert "INCOMPLETE:" not in text
    roundtrip(asmc, output)
