# Scaling experiments

`scaling.py` generates independent x86-64 assembly and C contracts, lifts each
model once, and reuses the exact linked GOTO binary across solver/profile runs.
It records construction costs separately from checking. The benchmark does not
change the input domain or disable assertions to make a difficult point pass.
[Measured findings and charts](results/2026-10-14/README.md) describe the first run.

| Family | Varied parameter | Comparison |
|---|---|---|
| `linear` | Repeated increments | Straight-line instruction/flag overhead, modular result |
| `dead-work` | Unobserved multiplies/adds | Cost of state updates that do not affect the result |
| `memory-read` | Buffer capacity | Symbolic vs fixed 8-byte offset, numeric RAM vs C objects |
| `memory-write` | Buffer capacity | Read-after-write and a symbolic unchanged byte outside the write |
| `calls` | Repeated direct calls | Dispatcher table and call/return transitions; fixed stack depth |
| `call-bound` | Extra unwinding | Always two actual calls; bounds 6/12/24 expose redundant expansion |
| `branches` | Independent conditional increments | Same ELF lifted with direct branches or `--dispatch` |
| `multiply` | Admitted input/result precision | `(x+y)^2 == x*x + 2*x*y + y*y` modulo the selected width |
| `objects` | Distinct C objects | A symbolic pointer selects among independent allocations |

The multiplication widths are distinct bounded input domains/specifications;
they are not an optimization of a 64-bit claim. Pointer and numeric-RAM cases
also have different address representations. They share the intended buffer
contract, not identical full machine states. Call tests reserve the SysV stack
alignment adjustment and preserve actual return-address stores/loads.

From the ASMC directory:

```sh
# A focused solver comparison. Directory must be empty.
python3 benchmarks/scaling.py build/bin --family memory-write \
  --size 64 --size 256 --size 1024 \
  --solver sat --solver z3 --solver cvc5 --solver bitwuzla --solver kissat \
  --timeout 10 --repetitions 3 --output-dir build/scaling-memory

# Encoding options for a fixed call workload and increasingly loose bounds.
python3 benchmarks/scaling.py build/bin --family call-bound \
  --solver sat --variant plain --variant slice --variant fields-768 \
  --timeout 10 --output-dir build/scaling-calls

python3 benchmarks/report.py build/scaling-memory build/scaling-calls \
  --output-dir build/scaling-report --plot
```

Omit selectors for all families with default sizes and MiniSat/Z3/cvc5/Bitwuzla.
`--solver-path bitwuzla=/path/to/bitwuzla` overrides discovery; Z3/cvc5 binaries
in the project venv take precedence over PATH. Missing executables are listed
in the manifest. A solver must be a CLI executable; Python bindings alone do
not provide CBMC's process interface. `--plot` uses gnuplot; otherwise reporting
uses only Python's standard library.

Variants include formula slicing, array theory, scalarization thresholds 0/128/768/1024,
dereference caching, path exploration, refinement, reachability slicing, and
early inlining. `--help` lists the names. Unsafe/approximating shortcuts such as
partial loops, search-depth/complexity cutoffs, aggressive slicing and disabling
checks are excluded. CBMC's goto-instrument constant propagator and full slicer
explicitly warn of unsoundness, so neither is used. `arrays-uf` is an experiment,
not a recommendation: the local SAT backend failed its known-good control.

Add `--scalar-registers` to build the register bank as three flat arrays of
32 storage words each, keeping data arrays unchanged. [Measured comparison](results/2026-10-14-registers/README.md).
Run it and the default encoding into separate
output directories with identical selectors, bounds, solvers, and repetitions;
the manifest and each result record the encoding. This differs from raising the
global field-sensitivity threshold, which also scalarizes qualifying data arrays.

Every profile first checks a passing increment, a wrong postcondition, an
insufficient call bound, and an invalid native object load. A failed control
disables that profile's subsequent workload runs and makes the script exit
nonzero. `manifest.json` records the rejected profile; report.py excludes it
from comparisons. Resource failures at ordinary measurement points remain
TIMEOUT/OOM, not PASS. The initial survey predates the additional invalid-pointer
control; the option/confirmation runs include it.

Runs are serial, with a default 1 GiB address-space cap **per process** and a
ten-second wall limit. Timeout/interrupt kills the process group, including
external solver children. The cap is not a combined process-tree RSS limit.
All solver choices retain default safety checks, ABI checks, model validation,
and explicit unwinding assertions. Counterexample traces are retained.
Every lifted model also passes a serialization round-trip.

Outputs include generated assembly, object-selection headers, ELF/GOTO models,
native listings, commands, tool logs, model construction costs, solver paths and
versions, incremental JSONL, and CSV. Timings include cold process startup and
trace/report work. Use more repetitions and longer limits for close comparisons;
the first short survey locates cliffs, not definitive solver rankings.
The host may have unrelated background work and no CPU affinity is enforced.

`wait4` supplies **per invocation** CPU usage and peak RSS, avoiding cumulative
`RUSAGE_CHILDREN` comparisons. Linux reports the largest process/previously reaped
child RSS, not simultaneous summed tree memory. On timeout an external solver
may not have been reaped by CBMC, making its reported RSS a lower bound.
The child also inherits the Python launcher's image before exec; this can impose
a variable RSS floor on tiny jobs. Large increases remain informative, but these
are reported process peaks, not isolated solver allocation measurements.
Plots mark timeout values separately; they are never treated as completed times.

The logs use CBMC verbosity 9 with monotonic timestamps. The phase columns split
symbolic execution, initial equation conversion, and the first decision call.
`solver_call_s` sums CBMC's own reported solver-call timings where available.
These calls can include refinement/encoding/postprocessing, not just a SAT
kernel. Path exploration may have multiple calls, so first-stage durations do
not measure the full job. SSA steps are recorded before formula slicing.
Absent metrics are null, not zero.

The `tests/test_scaling.py` test runs only tiny semantic checks with MiniSat. It has no
performance pass/fail thresholds. Larger sweeps are deliberately opt-in:

```sh
python3 -m pytest tests/test_scaling.py --build-dir build -q
```

No synthetic routine is copied from an upstream project. CBMC implementation
references used for interpreting results are pinned in the findings report.
