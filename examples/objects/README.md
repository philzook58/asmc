# Assembly accessing ordinary C memory objects

`--memory objects` makes every assembly **data address** a CBMC-encoded C
pointer. The default `--memory ram` retains numeric RAM and optional `--rodata`.
Object mode rejects `--rodata`; it never falls back to ELF data after an invalid
C pointer. Code addresses, jump destinations, and stored return addresses
remain numeric ELF addresses. Loading a return address from the stack is a
data access; the loaded value itself is subsequently used as a code address.

The independently written `functions.c` includes increment, aliasing, pointer
return, and byte-copy routines. Compile it and check the increment via a helper
call, for every `uint32_t` initial value:

```sh
mkdir -p build/objects
gcc -O0 -nostdlib -static -no-pie -fcf-protection=none \
  -Wl,-e,relay examples/objects/functions.c -o build/objects/functions.elf
build/bin/asmc build/objects/functions.elf --function relay --callee bump \
  --memory objects --harness examples/objects/harness.c \
  --unwind 20 --unwindset asmc_target.0:4 --memory-limit 2048
```

The harness passes its actual malloc pointer in an argument register. Assembly
writes update that C object directly; there is no copy to a numeric RAM buffer.
`asmc_sysv_arg_ptr` and `asmc_sysv_result_ptr` handle pointer arguments/results.
`asmc_sysv_setup_objects_model` uses a separate C byte-array object for the machine
stack. RISC-V provides corresponding `asmc_riscv_*` helpers. Other registers
remain arbitrary, and the usual ABI/stack-restoration checks still apply.

For example, the essential x86 harness pattern is:

```c
uint8_t stack[128];
struct asmc_state s;
uint32_t *p = malloc(sizeof *p);
__CPROVER_assume(p != 0);
uint32_t before = nondet_u32();
*p = before;
asmc_sysv_arg_ptr(&s, 0, p);
asmc_sysv_call_objects_model(&s, stack, sizeof stack);
assert(*p == before + 1);
free(p);
```

`asmc_sysv_call_objects_model` sets up the ABI, calls the target, and checks
scalar ABI preservation. Set arguments before this call. To inspect or modify
the entry state after setup, use `asmc_sysv_setup_objects_model`, call the target,
and then `asmc_sysv_check` explicitly.

This is the core pattern; `harness.c` is a complete compilable example. The
caller's C allocation can also be an array, a field in a struct, or a C global
passed by pointer. A fixed address embedded in ELF is not bound to a C global
by matching its name. There is no automatic import of `.rodata`, `.data`, or
`.bss`, nor any classification based on whether a pointer happens to be valid.

Each p-code load/store asserts `__CPROVER_r_ok`/`__CPROVER_w_ok` for the **whole
access**, then uses byte accesses to the C object. The driver also enables
CBMC pointer checks. Invalid-access predicates are asserted, not assumed, so
the failing executions are not pruned away. The runtime `asmc_load` and
`asmc_store` helpers use the selected address scheme too. Stack entry checks
validate the supplied C stack object's full capacity. The state layout is
unchanged; its RAM fields describe the stack buffer for the existing entry
helpers. Object-mode assembly accesses do not use those fields as a data-memory
mapping or restrict accesses to that stack object.

The mode uses CBMC's pointer casts rather than decoding or reserving identifier
bits. `--object-bits` forwards CBMC's encoding parameter. The numbers are
synthetic addresses: physical placement, address ordering across objects,
pointer truncation, alignment tests, and large arithmetic that changes object
bits can behave differently from native execution. Access checks validate the
resulting pointer, not the history of an integer that happens to encode a valid
pointer. This mode is intended for C-object contracts and bug finding under
that address model, not arbitrary physical-address equivalence.

`asmc` supplies `-DASMC_OBJECT_MEMORY` when compiling the runtime and C
harness. For manual lift/link workflows, compile both with that define and lift
with `--memory objects`. Runtime templates carry a mode marker; a mismatched
runtime is rejected before writing a GOTO object. Choose one runtime mode for
a linked model; the shared runtime helper names have that mode's semantics.

Object-mode failures show a short property list and the first counterexample,
with native instruction locations and pointer/stack setup guidance. Use
`--full-trace` or the saved `cbmc.log` to inspect all follow-on failures. This
only changes presentation; verification and result classification still use
the complete property results.

```sh
python3 -m pytest tests/test_objects.py --build-dir build -q
```

Tests cover x86-64/RV32/RV64, `-O0` pointer spills and `-O2` calls/tail calls,
aliasing, pointer returns, C globals via arguments, copies of 0–8 bytes, and a
non-default object-bit encoding. Deliberate failures cover a too-small
allocation, a freed allocation, null, an access crossing the object boundary,
an undersized stack, fixed ELF reads/writes, and a truncated pointer becoming
an ELF address. Every emitted model is validated and read back after
serialization. Incompatible modes and runtime templates are rejected.
