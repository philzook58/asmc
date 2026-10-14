# Register storage comparison

ASMC's opt-in `--scalar-registers` uses three flat arrays of 32 uint64_t storage
cells. The 768-byte bank retains the same byte offsets and aliases; data/stack
arrays are unchanged. No architectural register grouping or cached state is used.

These focused serial runs use CBMC 6.11.0, pinned SLEIGH/Ghidra 12.1.4, two
repetitions, and a 1 GiB address-space cap per process. Call runs have an eight-
second limit; memory runs have five seconds. All four semantic controls pass
for every measured profile. The register-only flag remains **opt-in**.

## Registers and stack both matter for calls

The function always executes two calls with a 128-byte RAM stack. Only the
GOTO dispatch bound varies. Times are medians of successful repetitions;
TIMEOUT and OOM remain incomplete observations.

| Storage / global field threshold | Bound | SSA steps | Outcome | PASS seconds | Largest reported RSS MiB |
|---|---:|---:|---|---:|---:|
| Byte bank / default 64 | 6 | 4,332 | 2 PASS | 0.952 | 132.7 |
| Storage cells / default 64 | 6 | 3,079 | 2 PASS | 1.473 | 77.8 |
| Byte bank / default 64 | 24 | 17,328 | 2 PASS | 6.519 | 712.9 |
| Storage cells / default 64 | 24 | 13,915 | 2 TIMEOUT | — | 506.9 |
| Byte bank / default 64 | 48 | 34,656 | 2 OOM | — | 919.0 |
| Storage cells / default 64 | 48 | 28,363 in one repetition | 2 TIMEOUT | — | 564.7 |
| Byte bank / 768 | 48 | 1,652 | 2 PASS | 2.242 | 27.6 |
| Storage cells / 128 | 48 | 867 | 2 PASS | 0.444 | 22.2 |

Tracking register cells helps, but does not resolve a symbolic stack by itself.
Covering this small stack as well lets CBMC propagate return destinations and
prune redundant dispatch expansion. The narrower global threshold avoids
scalarizing large buffers solely to cover the register bank. A larger stack
needs a corresponding experiment; 128 is not a universal recommended value.

## Memory performance can regress

With Bitwuzla and its default field threshold, the 64-byte symbolic C-object
write passed twice with the byte bank (median 3.706 s) but timed out twice at
five seconds with storage cells. The 1024-byte object passed with both layouts
(0.253 vs 0.266 s). Fixed-offset 64-byte object writes passed with both (0.722
vs 0.939 s). Numeric RAM checks also pass, but their small wall times vary.
Raising thresholds affects qualifying C objects too and can hurt SMT array
encodings. This is why the flag and global threshold are separate choices.

SSA reductions are evidence about the generated equation, not proof that every
solver/workload is faster. CPU scheduling/background activity is uncontrolled;
RSS is a process peak and may omit an unreaped external solver on timeout.
Do not infer a precise speed ratio from these short, two-repetition measurements.

## Reproduce

```sh
python3 benchmarks/scaling.py build/bin --family call-bound \
  --size 1 --size 4 --size 8 --solver sat --repetitions 2 --timeout 8 \
  --variant plain --variant fields-768 --output-dir build/register-flat-calls
python3 benchmarks/scaling.py build/bin --family call-bound \
  --size 1 --size 4 --size 8 --solver sat --repetitions 2 --timeout 8 \
  --scalar-registers --variant plain --variant fields-128 \
  --output-dir build/register-cells-calls
```

For the memory runs substitute `--family memory-write --size 64 --size 1024
--solver bitwuzla --timeout 5`, using the corresponding variants/encoding.
The compact CSV/JSONL records and solver manifests are retained here. Full
models, listings, logs and commands are under `build/register-scaling/` locally.
`report.py` labels the layouts separately rather than pooling measurements.

## Validation and rejected prototypes

All nine scalarized semantic/oracle suites pass (340 printed PASS checks,
including required counterexamples and incomplete bounds). These cover x86,
RV32/RV64, calls/recursion, memory, read-only data, C objects, native executions,
and original/patched binary comparisons. Helper tests cross cell/block edges
and test an assembly STORE through a C pointer that aliases the register bank.
The suites validate models and serialization round-trips.

An earlier array-of-arrays prototype produced invalid flattened SMT for
Bitwuzla and was discarded; its measurements are excluded. The final bank
uses flat arrays. Separately, RV32 pointer results exposed an integer-to-pointer
SMT narrowing bug reproducible with C alone. ASMC temporarily uses an explicit
uintptr_t snapshot; the one-line fix and regression tests are on
[the review branch in Philip's CBMC fork](https://github.com/philzook58/cbmc/tree/fix/smt2-integer-pointer-width).
No upstream pull request has been opened.
