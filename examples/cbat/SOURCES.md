# CBAT fixture provenance

All imported functions/instructions come from Draper's
[CBAT repository](https://github.com/draperlaboratory/cbat_tools/tree/21d58d7a0cadeb57c5654a0d0b4b8ca22cb95a54),
pinned at `21d58d7a0cadeb57c5654a0d0b4b8ca22cb95a54`.
Copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
The MIT notice is retained in [LICENSE](LICENSE) and identified in each adapted
source file. No upstream binaries or build dependencies are imported.

Paths below are relative to that pinned repository:

| Local pair | Upstream sources | Adaptation |
|---|---|---|
| `same_signs_*.c` | `wp/resources/sample_binaries/same_signs/src/main_{1,2}.c` | Remove the I/O main and unused includes. Keep both `same_signs` bodies. |
| `switch_*.c` | `wp/resources/sample_binaries/switch_case_assignments/src/main_{1,2}.c` | Remove the I/O main and unused includes. Keep enum values, fall-through and `process_status` bodies. |
| `pointer_*.c` | `wp/resources/sample_binaries/pointer_flag/src/main_{1,2}.c` | Remove main. Keep both `deref` bodies, including the patched local variable. |
| `increment_*.S` | `wp/resources/sample_binaries/init_var_compare/src/main_{1,2}.S` | Extract main's three instructions; rename the entry `increment`, add symbol type/size and a GNU-stack note. Omit `_start` and syscalls. |
| `debruijn_*.c` | `wp/resources/sample_binaries/debruijn/src/main_{1,2}.c` | Extract only `rightmost_index_8`, with `<stdint.h>`. Keep the lookup table, formula and conditional scan. |
| `goto_fail_*.c` | `docs/exercises/04/binary/main_{1,2}.c` | Remove main and unused includes. Keep the control flow and zero-returning stubs. Add optional `RECORD_CALL` annotations in four stubs, disabled by default. |

The upstream De Bruijn example credits
[the MIT CSAIL paper](http://supertech.csail.mit.edu/papers/debruijn.pdf) and
[Chessprogramming's BitScan discussion](https://www.chessprogramming.org/BitScan#DeBruijnMultiplation).
Those are algorithm references; no further implementation was imported.
The goto-fail example is CBAT's teaching model with toy crypto stubs, not an
implementation of TLS verification.

`abi.h`, `entries.c`, `harness.c`, `record_calls.h`, and `tests/test_cbat.py` are
independently written ASMC teaching/test support. Deliberately broken/fixed
variants are generated in the test output directory; original fixtures remain
unchanged.
