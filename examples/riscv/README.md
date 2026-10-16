# RV32 and RV64 scalar checks

ASMC selects RV32/RV64 and the bundled SLEIGH specification from the linked
ELF header. `asmc` selects ILP32/LP64 for the C model and defines
`ASMC_RISCV_XLEN=32` or `64`. No architecture flag or external emulator is needed.

From the ASMC directory, using the installed bare-metal cross-compiler:

```sh
mkdir -p build/examples
riscv64-unknown-elf-gcc -march=rv32imc -mabi=ilp32 -O2 \
  -DASMC_RISCV_XLEN=32 -nostdlib -static -fno-builtin \
  -Wl,--no-relax,-e,inc examples/riscv/functions.c -o build/examples/rv32.elf
build/bin/asmc build/examples/rv32.elf --function inc \
  --post 'outreg.a0 == inreg.a0 + 1'
```

For RV64, change `rv32imc` to `rv64imc`, `ilp32` to `lp64`, and the compiler
define to `64`. The harness define is supplied automatically from ELF.
The default harness checks stack restoration and scalar ABI preservation as well
as the supplied property. Entry/exit register snapshots use XLEN-bit unsigned
fields. Use `--pre` for C assumptions or `--harness examples/riscv/spec.c
--reference examples/riscv/functions.c -DCASE=1` for the explicit C reference check.
The Linux cross-compiler can also build statically linked leaf routines.
No libc, globals, calls, or relocation processing is needed for these examples.

| Function | Harness define | Domain |
|---|---|---|
| `inc` | `-DCASE=1` | Every XLEN-bit value, including wraparound |
| `maximum` | `-DCASE=2` | Every signed XLEN-bit pair |
| `shift` | `-DCASE=3` | Every input and shift count, masked to XLEN |
| `multiply` | `-DCASE=4` | Low XLEN product; use `--z3` for practical solver performance |
| `sum` | `-DCASE=5` | 0–4 arbitrary 32-bit words, modular sum |
| `copy` | `-DCASE=6` | 0–4 bytes, unchanged surrounding application bytes |

For sum/copy use `--show-loops`, then set bounds such as
`--unwindset asmc_target.0:6,sum.0:6` or `asmc_target.0:6,copy.0:6`.

Include `asmc_riscv.h` for explicit integer-register helpers:

```c
struct asmc_riscv_frame frame =
  asmc_riscv_setup_ram_model_at(&s, ram, 0x1000, sizeof(ram), 0x10f0);
asmc_riscv_arg(&s, 0, value); /* a0: one XLEN-bit value or numeric address */
asmc_target(&s);
assert(asmc_riscv_result(&s) == expected);
asmc_riscv_check(&s, &frame);
```

Entry sets x0 to zero, initializes `ra` with an even return sentinel, and checks
16-byte SP alignment. The checkpoint checks restored SP, `s0–s11`, `gp`, `tp`,
and x0. Return p-code checks the actual destination against the sentinel.
There is no return-address word pushed on the stack. Other registers and RAM
remain arbitrary. `asmc_riscv_arg32` sign-extends a 32-bit argument on RV64,
including unsigned arguments; cast the result to its declared C width when
comparing a narrow return value. The pinned SLEIGH semantics discard x0 writes.

The existing state layout is reused. RISC-V GPR xN occupies bytes
`N * (XLEN/8)` in its register bank; the translator checks and maps SLEIGH's
raw GPR offsets. Listings retain the original p-code offsets. Machine addresses
remain numeric, with RV32 access bounds checked against the 32-bit limit.

The C reference uses host GCC preprocessing with `-m32`/`-m64` and unsigned
plain char. Use explicit-width integers and portable scalar C; this is not a
RISC-V sysroot or a reproduction of target-specific preprocessor macros,
library typedef choices, floating-point types, or compiler builtins. For manual
templates compile `runtime/runtime.c` with `goto-cc -m32` for RV32, `-m64` for
RV64. A template with the wrong pointer width is rejected.

Integer I/M operations (except division/remainder) and compressed integer
instructions are tested. Direct calls and bounded recursion are covered by
[the shared call examples](../calls/README.md). RV32E, indirect calls/jumps, floating point,
vectors, atomics, CSR/system operations and external data loading are outside
this version. The byte-memory model permits unaligned accesses; alignment
faults, interrupts and hardware timing are not modeled. Helpers cover values
up to XLEN in the first eight argument registers; RV32 64-bit register pairs,
stack arguments and aggregate signatures require an explicit harness.

`tests/riscv.py` checks both widths, three compiler configurations, serialization
round-trips, all eight arguments, zero-register writes, signed loads, RV64
`addiw`, ABI mutations, RV32 memory wrapping, unsupported instructions and
insufficient unwinding. It requires `riscv64-unknown-elf-gcc` and Z3.

```sh
ctest --test-dir build -R '^asmc-riscv$' --output-on-failure
```
