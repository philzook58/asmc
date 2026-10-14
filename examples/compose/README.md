# Calling lifted assembly from ordinary C

This example puts two lifted functions behind normal C signatures:

```c
uint32_t add_one(uint32_t value);
uint32_t sum_words(const uint32_t *data, unsigned n);
```

`harness.c` is an ordinary C caller. `wrappers.c` contains the explicit ABI
adapters: it creates machine state, marshals arguments, invokes a named lift,
checks the ABI, and reads the result. The sum adapter maps input words to
little-endian numeric machine addresses and verifies that the whole application
region is unchanged. Its contract requires `n <= 4` and `n` readable C words.
There is no automatic pointer conversion or implicit aliasing policy.
The wrapper's numeric RAM layout is part of the model; vary it explicitly when
address dependence is relevant to the property being checked.

The stack helper `asmc_sysv_enter_at_end` chooses the highest valid entry SP
inside RAM, leaving stack space below it. Here the first 128 bytes are
application RAM and the upper half is stack. The numeric base and RAM capacity
remain explicit. A larger stack frame needs a larger buffer or another layout.

From the ASMC directory, a single named lift can be checked with the driver:

```sh
mkdir -p build/compose
gcc -nostdlib -no-pie -Wl,-e,machine_add_one examples/compose/functions.S \
  -o build/compose/functions.elf
build/bin/asmc build/compose/functions.elf --function machine_add_one \
  --target lifted_add_one --harness examples/compose/single.c \
  --reference examples/compose/wrappers.c
```

`--function` selects the machine-code symbol. `--target` selects the GOTO/C
function to replace, defaulting to `asmc_target`. The driver creates its empty
stub automatically. The harness or wrapper calls that name explicitly.

For two entries, create one template and replace its stubs in succession:

```sh
build/bin/goto-cc -I include runtime/runtime.c examples/compose/entries.c \
  -o build/compose/seed.gb
build/bin/asmc-lift build/compose/functions.elf --function machine_add_one \
  --target lifted_add_one --template build/compose/seed.gb -o build/compose/add.gb
build/bin/asmc-lift build/compose/functions.elf --function machine_sum \
  --target lifted_sum --template build/compose/add.gb -o build/compose/both.gb
build/bin/goto-cc -I include build/compose/both.gb examples/compose/wrappers.c \
  examples/compose/harness.c -o build/compose/check.gb
build/bin/cbmc build/compose/check.gb --function harness --unwind 40 \
  --unwinding-assertions --validate-goto-model --trace
```

Both entries can also come from different ELF files. Generated temporaries are
scoped to each target name. For independent GOTO objects, compile a separate
stub-only C template for each target using `asmc_state.h`, lift each, and link
the resulting objects with `runtime/runtime.c` once. Do not link multiple copies
of the common runtime. `tests/compose.py` exercises both workflows, a named
driver check, wrong-result, wrong-memory-stride and unwanted-write mutations, and invalid
target signatures.

These are verification adapters, not implementations for running the assembly
on the host. For calls between admitted native ELF functions, see
[the call examples](../calls/README.md).
Memory-writing routines can use the same pattern with explicit output copying,
frame checks, and a documented overlap policy.

```sh
ctest --test-dir build -R '^asmc-compose$' --output-on-failure
```
