# Comparing original and edited binaries

These [attributed MIT fixtures](SOURCES.md) adapt six CBAT examples. ASMC lifts
the functions from **two separate ELF files** into named GOTO functions,
`original` and `patched`, and links one C comparison harness. They demonstrate
binary-to-binary checks without adding a comparison DSL or changing the lifter.
The top-level driver's proposed `--compare` option is not implemented.

| Example | Expected check | Lesson |
|---|---|---|
| `same_signs` | PASS | Branching and XOR agree for every pair of signed 32-bit inputs. Compare the declared boolean result bits. |
| `switch` | FAIL, `status=0` (NAV) | Removing LOG_STATUS lets NAV fall through to DEPLOY. The test also checks a fixed version passes. |
| `increment` | PASS | Reordering increment/move changes RDI but preserves the 64-bit return value, including wraparound. RDI is caller-saved. |
| `pointer` | PASS | Adding a local changes stack layout but preserves signed 32-bit results and the pointed-to input. A wrong threshold and an unexpected write both fail. |
| `debruijn` | PASS | An 8-bit lookup-table implementation agrees with conditional scanning and a simple C bit-scan specification. A bad scan result fails. |
| `goto_fail` | Return-only PASS; observed-effects FAIL | Removing the extra unconditional return changes which verification helpers run, while both toy functions still return zero. |

All checks validate the GOTO model, serialization round-trips, stack restoration,
scalar ABI preservation, complete memory access bounds, and unwinding assertions.
The C harness additionally checks simple independent specifications where
appropriate; equality alone would allow both implementations to have the same
bug. Negative tests require the intended property failure and no unwinding
failure. Runs are capped at 2 GiB, execute serially, and have per-tool timeouts.

From the ASMC directory:

```sh
cmake --build build --target asmc-tools -j2
ctest --test-dir build -R '^asmc-cbat$' --output-on-failure -j1

# Keep the two ELF files, GOTO models, commands and full checker logs to inspect:
python3 tests/cbat.py build/bin/asmc --arch x86 --only same_signs \
  --output-dir build/cbat-signs
```

The output directory must be empty. For the switch edit use `--only switch`;
the script exits successfully when it finds the **expected** counterexample.
Read each `cbmc.log` for the actual verification result. `commands.txt` records
the concrete commands to reproduce each case.
With no selectors the suite exercises x86-64 and, when its cross-compiler is
available, RV32/RV64. C routines are checked at O0/O2; `increment` is x86-specific,
and goto-fail uses O2 to keep this regression small. Its empty helpers may be
eliminated or inlined; the optionally recorded effects remain observable.
RISC-V linking retains
ordinary relaxation so calls become supported direct jumps. x86 fixtures use
scalar compiler flags to avoid SIMD table initialization; these tests do not
imply SIMD support.

For a manual two-binary workflow, compile `runtime/runtime.c` and `entries.c`
with goto-cc, replace `original` using the first ELF with asmc-lift, then replace
`patched` in that resulting model using the second ELF. Link `harness.c` with
the selected CASE and run CBMC. The saved commands demonstrate the exact steps.
Both code listings retain their own ELF addresses and target names.

The register-only cases share initial register bytes and copies of initial
numeric RAM. The pointer case uses separate C data and stack objects through
`--memory objects`; argument pointers are rebound to corresponding objects,
not compared as raw encodings. The read-only input contract excludes stack
scratch bytes from output comparison. Distinct spills, frame sizes or unused
stack bytes are allowed.

For goto-fail, `ASMC_RECORD_CALLS` makes four existing helper stubs set bits in
a caller-provided byte. The original records preparation/update (`3`), whereas
the fixed version also records finalization/verification (`15`). This is
**explicit source instrumentation of this fixture**, not automatic observation
of calls in arbitrary binaries. Without it, both return zero and the bounded
return-value comparison passes; that result says nothing about skipped
verification. Call-observation hooks remain a possible ASMC extension.

Mutable ELF globals, external C call models, and unbounded loop invariants are
still separate feature work. These fixtures introduce none of those implicitly.
