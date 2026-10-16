"""Native x86 execution is the oracle; flag gaps and corrupt observations fail."""

import platform
import random
import pytest
from support import ROOT, bounded_run as run, roundtrip

pytestmark = pytest.mark.fast


@pytest.fixture(scope="session")
def native_observations(tmp_path_factory):
    if platform.machine() != "x86_64":
        pytest.skip("native oracle requires x86-64")
    tmp = tmp_path_factory.mktemp("native")
    rng = random.Random(0xA5C)
    mask = (1 << 64) - 1
    inputs = [
        (0, 0),
        (mask, 1),
        (mask, mask),
        (127, 1),
        (255, 1),
        ((1 << 63) - 1, 1),
        (1 << 63, mask),
        (1, 63),
        (1, 64),
        (1, 65),
        (1, 255),
        (0x123456789ABCDEF0, 32),
    ]
    inputs += [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(12)]
    elf = tmp / "oracle.elf"
    run(
        [
            "gcc",
            "-static",
            "-no-pie",
            "-fcf-protection=none",
            ROOT / "tests/native.S",
            ROOT / "tests/native_runner.c",
            "-o",
            elf,
        ]
    )
    observed = run([elf], input="".join(f"{a} {b}\n" for a, b in inputs))
    outputs = [list(map(int, line.split())) for line in observed.splitlines()]
    assert len(outputs) == len(inputs) and all(len(row) == 7 for row in outputs)
    rows = [list(pair) + values for pair, values in zip(inputs, outputs)]
    return elf, rows


def write_harness(rows, harness):
    constants = ",\n".join("{" + ",".join(f"{n}ULL" for n in row) + "}" for row in rows)
    harness.write_text(
        """#include "asmc_x86.h"
#include <assert.h>
unsigned nondet_unsigned(void);
static const uint64_t observations[][9] = {
"""
        + constants
        + """};
void harness(void) {
  unsigned sample = nondet_unsigned();
  __CPROVER_assume(sample < sizeof observations / sizeof observations[0]);
  uint8_t ram[128] = {0};
  struct asmc_state s = {0};
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model(&s, ram, 0x1000, sizeof ram);
  asmc_sysv_arg64(&s, 0, observations[sample][0]);
  asmc_sysv_arg64(&s, 1, observations[sample][1]);
  asmc_sysv_arg64(&s, 2, 0x1000);
  asmc_target(&s);
  assert(asmc_sysv_result64(&s) == observations[sample][2]);
  for (unsigned i = 0; i < 6; ++i) {
    uint64_t mask = i == 1 ? 0x8c5 : UINT64_MAX;
#ifdef CHECK_AF
    mask = UINT64_MAX;
#endif
    assert((asmc_load(&s, 0x1000 + 8*i, 8) & mask) == (observations[sample][3+i] & mask));
  }
  for (unsigned i = 48; i < 64; ++i) assert(ram[i] == 0);
  asmc_sysv_check(&s, &frame);
}
"""
    )


@pytest.mark.parametrize(
    "variant,expected,options",
    [
        ("native", 0, []),
        ("known-auxiliary-carry-gap", 10, ["-DCHECK_AF"]),
        ("corrupt-observation", 10, []),
    ],
)
def test_native_oracle(asmc, native_observations, tmp_path, variant, expected, options):
    elf, original = native_observations
    rows = [row[:] for row in original]
    if variant == "corrupt-observation":
        rows[0][2] ^= 1
    harness = tmp_path / "harness.c"
    write_harness(rows, harness)
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
            "20",
            "--memory-limit",
            "2048",
            "--timeout",
            "110",
            "--output-dir",
            output,
            *options,
        ],
        expected,
    )
    roundtrip(asmc, output)
    assert ("PASS:" if expected == 0 else "FAIL:") in text
    if variant == "native":
        assert "ASMC warning: x86 AF" in text
