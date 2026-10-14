"""A compiled relative jump table, explicit targets, and immutable ELF data."""
from pathlib import Path
import resource
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/switch"


def run(command, expected=0):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True, timeout=90)
    text = result.stdout + result.stderr
    assert result.returncode == expected, f"{command}\nexit {result.returncode}\n{text}"
    return text


def main():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    asmc = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="asmc-switch-") as directory:
        tmp = Path(directory)
        elf, data = tmp / "switch.elf", tmp / "rodata.bin"
        run(["gcc", "-O2", "-nostdlib", "-static", "-no-pie", "-fcf-protection=none",
             "-fno-reorder-blocks-and-partition", "-Wl,-e,choose", EXAMPLE / "switch.c", "-o", elf])
        # This fixture deliberately has one table of eight signed offsets from
        # the .rodata base. Extracting it is test-specific, not target inference.
        sections = run(["objdump", "-h", elf])
        line = next(line for line in sections.splitlines() if ".rodata" in line)
        size, base = (int(x, 16) for x in line.split()[2:4])
        assert size == 32, "compiler changed fixture table layout"
        run(["objcopy", "--dump-section", f".rodata={data}", elf])
        targets = [hex(base + offset) for offset in struct.unpack("<8i", data.read_bytes())]

        def check(name, targets=targets, rodata=True, harness=EXAMPLE / "harness.c", expected=0):
            text = run([asmc, elf, "--function", "choose", "--harness", harness,
                        "--reference", EXAMPLE / "switch.c", "--unwind", "20",
                        "--unwindset", "asmc_target.0:3", "--timeout", "80",
                        "--memory-limit", "2048", "--output-dir", tmp / name,
                        *(["--rodata"] if rodata else []),
                        *[arg for target in targets for arg in ("--indirect-target", target)]], expected)
            if expected != 2:
                run([asmc.parent / "goto-instrument", "--validate-goto-model",
                     tmp / name / "lifted.gb", tmp / name / "roundtrip.gb"])
            print("PASS " + name, flush=True)
            return text

        assert "PASS:" in check("compiled-switch")
        assert "PASS:" in check("symbol-target", targets=targets + ["choose"])
        assert "--indirect-target" in check("missing-target-list", targets=[], expected=2)
        assert "indirect jump outside supplied targets" in check("omitted-case", targets=targets[1:], expected=10)
        assert "memory access outside RAM" in check("missing-rodata", rodata=False, expected=10)
        overlapping = tmp / "overlap.c"
        overlapping.write_text((EXAMPLE / "harness.c").read_text().replace("0x1000", hex(base)))
        assert "RAM overlaps immutable ELF .rodata" in check("overlap", harness=overlapping, expected=10)
        elf = tmp / "readonly.elf"
        run(["gcc", "-nostdlib", "-static", "-no-pie", "-Wl,-e,read32",
             ROOT / "tests/readonly.S", "-o", elf])
        symbols = run(["nm", elf])
        base = int(next(line.split()[0] for line in symbols.splitlines()
                        if line.endswith(" constant_bytes")), 16)
        harness = tmp / "readonly.c"
        for name, function, address, value, expected in [
            ("read-end", "read32", base + 4, 0x88776655, 0),
            ("read-full", "read64", base, 0x8877665544332211, 0),
            ("read-ram", "read64", 0x1000, 0, 0),
            ("read-cross-end", "read32", base + 5, 0, 10),
            ("read-cross-start", "read64", base - 1, 0, 10),
            ("read-wrap", "read32", (1 << 64) - 2, 0, 10),
            ("write-readonly", "write32", base, 0, 10),
        ]:
            harness.write_text('''#include "asmc_x86.h"
#include <assert.h>
void harness(void) {
  uint8_t ram[128] = {0};
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter_at_end(&s, ram, 0x1000, sizeof ram);
  asmc_sysv_arg64(&s, 0, ''' + str(address) + '''ULL);
  asmc_target(&s);
  assert(asmc_sysv_result64(&s) == ''' + str(value) + '''ULL);
  asmc_sysv_check(&s, &frame);
}
''')
            text = run([asmc, elf, "--function", function, "--harness", harness,
                        "--rodata", "--memory-limit", "2048", "--timeout", "80",
                        "--output-dir", tmp / name], expected)
            assert ("PASS:" if expected == 0 else "FAIL:") in text
            run([asmc.parent / "goto-instrument", "--validate-goto-model",
                 tmp / name / "lifted.gb", tmp / name / "roundtrip.gb"])
            print("PASS " + name, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
