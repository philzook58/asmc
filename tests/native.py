"""Compare an actual x86 executable with its lifted model, using recorded inputs.

This checks finite executions, not equivalence for arbitrary inputs. The same
ELF runs natively and supplies the bytes lifted by ASMC. No p-code evaluator
is involved in constructing the expected outputs.
"""
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(command, expected=0, **kwargs):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True,
                            timeout=120, **kwargs)
    text = result.stdout + result.stderr
    assert result.returncode == expected, f"{command}\n{text}"
    return text


def main():
    if platform.machine() != "x86_64":
        print("SKIP: native oracle requires x86-64")
        return 0
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    asmc = Path(sys.argv[1]).resolve()
    rng = random.Random(0xA5C)
    mask = (1 << 64) - 1
    inputs = [(0, 0), (mask, 1), (mask, mask), (127, 1), (255, 1),
              ((1 << 63) - 1, 1), (1 << 63, mask), (1, 63), (1, 64),
              (1, 65), (1, 255), (0x123456789ABCDEF0, 32)]
    inputs += [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(12)]
    with tempfile.TemporaryDirectory(prefix="asmc-native-") as directory:
        tmp = Path(directory)
        elf = tmp / "oracle.elf"
        run(["gcc", "-static", "-no-pie", "-fcf-protection=none", ROOT / "tests/native.S",
             ROOT / "tests/native_runner.c", "-o", elf])
        observed = run([elf], input="".join(f"{a} {b}\n" for a, b in inputs))
        outputs = [list(map(int, line.split())) for line in observed.splitlines()]
        assert len(outputs) == len(inputs) and all(len(row) == 7 for row in outputs)
        rows = [list(pair) + values for pair, values in zip(inputs, outputs)]
        harness = tmp / "harness.c"

        def write_harness(rows):
            constants = ",\n".join("{" + ",".join(f"{n}ULL" for n in row) + "}" for row in rows)
            harness.write_text('''#include "asmc_x86.h"
#include <assert.h>
unsigned nondet_unsigned(void);
static const uint64_t observations[][9] = {
''' + constants + '''};
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
''')

        def check(name, expected=0, options=()):
            text = run([asmc, elf, "--function", "probe", "--callee", "probe_helper",
                        "--harness", harness, "--unwind", "20", "--memory-limit", "2048",
                        "--timeout", "110", "--output-dir", tmp / name, *options], expected)
            run([asmc.parent / "goto-instrument", "--validate-goto-model",
                 tmp / name / "lifted.gb", tmp / name / "roundtrip.gb"])
            return text

        write_harness(rows)
        text = check("native")
        assert "PASS:" in text and "ASMC warning: x86 AF" in text
        print(f"PASS {len(rows)} native executions: flags, aliases, shifts, memory and calls", flush=True)
        # SLEIGH explicitly leaves AF unimplemented. Keep the observed mismatch
        # visible rather than claiming all six architectural flags agree.
        assert "FAIL:" in check("known-auxiliary-carry-gap", 10, ["-DCHECK_AF"])
        print("PASS detects known SLEIGH auxiliary-carry mismatch", flush=True)
        # Check that the oracle assertions actually detect a disagreement.
        rows[0][2] ^= 1
        write_harness(rows)
        assert "FAIL:" in check("corrupt-observation", 10)
        print("PASS corrupted native observation is rejected", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
