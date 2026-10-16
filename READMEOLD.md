# ASMC

ASMC checks x86-64, RV32, or RV64 ELF functions against C specifications.
`asmc` is the top-level verification driver: it runs `asmc-lift`, links the
result with an explicit or generated C harness, and invokes CBMC. `asmc-lift` is the native C++
frontend that translates Ghidra's raw p-code into CBMC GOTO objects. The driver
is a small Python executable. The frontend uses neither cbmcpy nor the Ghidra
decompiler.

## Build

Prerequisites: Linux, a C++17 compiler, CMake 3.24+, Ninja or Make, Git,
Bison, Flex, zlib development headers, and Python 3 for the verification driver and tests.
The challenge suite uses GCC, Clang, and the Z3 executable (for the full
64-by-64-bit multiplication and upstream bignum proofs). The frontend itself
does not require Z3.

~~~sh
cmake -S . -B build -G Ninja
cmake --build build --target asmc-tools -j8
ctest --test-dir build -R '^asmc-' --output-on-failure
~~~

The [GitHub Actions workflow](.github/workflows/ci.yml) builds on Ubuntu 24.04
and runs every `asmc-*` CTest suite on pushes and pull requests, including
RISC-V, scalar registers, tutorial regressions, and Rust/Kani smoke tests.
It uses two build workers and sequential tests, caches compiler results, and
uploads build/CTest logs. Kani and Z3 versions are recorded in the workflow.

CMake downloads and builds CBMC and lifting-bits/SLEIGH; SLEIGH downloads
and patches its Ghidra dependency. No preinstalled CBMC or SLEIGH is needed.
The asmc target builds the driver, asmc-lift, goto-cc, cbmc, and the x86-64,
RV32 and RV64 processor specifications. The asmc-tools target also builds
goto-instrument and the arithmetic test executable. Build only asmc-lift when
you need the lift-only frontend.
RISC-V tests are registered when `riscv64-unknown-elf-gcc` is available.

The upstream tips resolved on October 13, 2026 are recorded in
CMakeLists.txt: CBMC **32441ee38f8b2be63281a88a0df1a585dd4fdc43**
(6.11.0), SLEIGH **bfe2771eb304c2b4f01c2fa61f5342be54a91906**
(Ghidra 12.1.4). Override ASMC_CBMC_REV and ASMC_SLEIGH_REV to update.
Every tool used by the tests comes from this same build.

Existing source checkouts can optionally be supplied through the standard
FETCHCONTENT_SOURCE_DIR_CBMC and FETCHCONTENT_SOURCE_DIR_SLEIGH CMake
variables. The default build does not require them.
ELFIO's header library and license are included under vendor/elfio.
Two unmodified s2n-bignum routines and their license are included as test
fixtures, with the upstream commit recorded in tests/s2n-bignum/VERSION.

## First verification

Run from the ASMC directory:

~~~sh
build/bin/asmc examples/inc.S --function inc \
  --post 'outreg.rax == inreg.rdi + 1'
~~~

The asmc driver compiles the runtime template, lifts the selected ELF symbol,
links a C harness, and runs CBMC with model validation, traces, and unwinding
assertions. It uses asmc-lift, goto-cc, and cbmc from the same build directory.
No template needs to be created by hand. Without --harness,
[tools/demo.py](tools/demo.py) generates an ordinary C harness, saved as
`demo.c` in the output directory printed by ASMC.

For `.s`/`.S` input, the driver first assembles and links a static ELF with
`CC` (default `cc`) and `CPPFLAGS`, `CFLAGS`, `LDFLAGS`. Shell-style quoting is
accepted in those variables; commands run without a shell. The compiler is
responsible for target selection, and the harness ABI is then selected from ELF:

~~~sh
CC=riscv64-unknown-elf-gcc CFLAGS='-march=rv32imc -mabi=ilp32' \
  build/bin/asmc examples/riscv/instructions.S --function zero_test \
  --post 'outreg.a0 == inreg.a0 + 1'
~~~

The native link uses `-nostdlib -static -no-pie` and the selected function as
entry point. `assemble.log`, the command, and `target.elf` are retained alongside
the check. Environment flags affect that native build; use `-I`/`-D` for the C
specifications. Existing ELF inputs still go straight to lifting.

ASMC normally takes the lifting range from the ELF function's size, supplied
by `.type foo,@function` and `.size foo,.-foo` in GNU assembly. When the symbol
has no size, it uses the end of the containing executable section (usually
`.text`) as the available code window and reports that range. For several
admitted functions in one section, inferred windows end at the next admitted
entry to keep them disjoint. Only reachable instructions are lifted: padding,
other routines and embedded data are not decoded unless control flow reaches them.

`--lift-end-address 0x...` overrides the entry's **exclusive lifting-window end**
in the linked ELF. It does not insert an execution stop. Reaching a boundary
without returning or transferring to another admitted range is an error.
The postcondition and ABI checks still run after a normal return. Existing
ELF size metadata remains authoritative unless explicitly overridden.
Use `nm -n OUTPUT/target.elf` to read a label's linked address, or
`objdump -d OUTPUT/target.elf` to inspect the code. No address calculation is
needed for ordinary `.s` demos. The former `--end-address` name is removed.

The default harness selects x86-64 SysV, RV32 or RV64 from ELF. It supplies
a 256-byte stack (change with --stack-size, minimum 16), a valid return sentinel,
and the ABI's entry state. Other registers and unused memory bytes stay arbitrary.
In the default RAM mode the stack occupies numeric addresses starting at 0x1000;
--memory objects instead uses a C stack object's encoded pointer addresses.
--rodata remains available in RAM mode.

--pre and --post take **C expressions**, parsed by goto-cc, and can be repeated.
Each precondition is assumed after ABI setup and before calling the assembly;
each postcondition is asserted after it returns. inreg.REG and outreg.REG are entry
and exit register snapshots. x86 full general-purpose fields (`rax`, `rdi`,
`r8`, etc.) are uint64_t. Their standard aliases are available as uint32_t
(`eax`, `edi`, `r8d`), uint16_t (`ax`, `di`, `r8w`), and uint8_t
(`al`, `ah`, `dil`, `r8b`, etc.). Aliases are derived from the same captured
register value. For example, `--post 'outreg.eax == inreg.edi + 42'` expresses
unsigned 32-bit addition, including wraparound. Signed interpretations still
need casts; C promotes 8/16-bit arithmetic to `int`, so use an explicit result
cast for narrow wraparound, e.g. `outreg.al == (uint8_t)(inreg.dil + 1)`.
Flag fields cf/pf/af/zf/sf/of/df are uint8_t. RISC-V fields use ABI names
(zero, ra, sp, gp, tp, a0–a7, s0–s11, t0–t6) and uint32_t or uint64_t
according to XLEN. Arithmetic follows C's type/promotion rules; cast explicitly
for signed or narrower results. For example:

~~~sh
build/bin/asmc examples/inc.S --function inc \
  --pre 'inreg.rdi == UINT64_MAX' --post 'outreg.rax == 0'
# For a RISC-V increment ELF:
build/bin/asmc build/examples/rv32.elf --function inc \
  --post 'outreg.a0 == inreg.a0 + 1'
~~~

The [tutorial regression examples](examples/tutorial/README.md) include correct
and deliberately incorrect register/memory contracts, stack aliasing, and swap
harnesses that exercise both alias cases and check untouched array elements.
Run them with `ctest --test-dir build -R '^asmc-tutorial$' --output-on-failure`.

[Rust/Kani smoke tests](examples/kani/README.md) exercise Rust harnesses calling
lifted assembly and compare compiled Rust functions with their source models.
Kani is optional; run `ctest --test-dir build -R '^asmc-kani$' --output-on-failure`.

The default harness always checks scalar ABI preservation, stack restoration,
return destinations and memory bounds. With no --post it reports **safety/ABI
only**, making no functional claim. x86 checks RBX, RBP, R12–R15 and cleared DF;
RISC-V checks s0–s11, gp, tp and x0. These are entry/exit obligations, not complete
ABI conformance checks such as SIMD preservation or alignment at every nested call.
As with an explicit harness, contradictory --pre expressions make checks vacuous;
ASMC does not currently check precondition feasibility. x86 flags remain subject
to the documented [SLEIGH AF limitation](tests/NATIVE.md).

The live machine state is `st`; inreg/outreg snapshot registers, **not memory**.
Use `asmc_load(&st, address, bytes)` in a postcondition to read current memory
as a little-endian integer (1–8 bytes), with bounds checks. For example,
`movq $42, -8(%rsp); ret` satisfies
`--post 'asmc_load(&st, inreg.rsp - 8, 8) == 42'`. This uses the x86-64 SysV
red zone below entry RSP. Writing at entry RSP would overwrite the return address;
reading at outreg.rsp after return is beyond the default stack buffer.
Using inreg.rsp selects an entry address, not a copy of entry memory.
For buffer contracts, C allocations,
aliasing or custom setup, use --harness examples/inc_spec.c or adapt the saved
demo.c and pass it as --harness. The --pre/--post/--stack-size options apply only
to the generated harness; custom harnesses express their contracts in C.

The result is **PASS** (exit 0), **FAIL** with a counterexample (exit 10),
**INCOMPLETE** for insufficient unwinding, exhausted checker memory, or a checker timeout (exit 11), or
**ERROR** for a tool/input failure (exit 2). Interrupting exits 130. If both a
counterexample and an unwinding failure occur, the result is FAIL and reports
both. PASS means the harness's checked properties hold under its assumptions
and the checked bounds.

Each run saves seed.gb, lifted.gb, check.gb, the lifted.gb.asm listing,
commands.txt, result.txt, and the four tool logs in a new directory under
asmc-out/. Failed properties and counterexample values from the harness/reference
are printed directly, followed by CBMC's violated assertion. Helper/machine steps
are omitted from this view; --full-trace prints the complete CBMC trace and
--compact-trace prints CBMC's own compact trace. The unfiltered CBMC output always
remains in cbmc.log. Unexpected-return failures also show the actual destination
and expected harness return sentinel; check for a clobbered saved return address
or incorrect stack restoration (or RA corruption on RISC-V).
For generated-harness postconditions, the brief view shows the `inreg.FIELD` and
`outreg.FIELD` references used in the pre/postconditions, rather than every register
alias. Safety/ABI failures retain the full-width register context. This filters
only the display; all views remain in the harness and raw trace. The postcondition
is printed once, without repeating CBMC's expanded formula. Use `--beautify` to
ask the solver for simpler counterexample values; large arbitrary values alone
do not indicate a harder check.
Use --output-dir to choose an empty directory. Existing results are preserved.
All relative input paths and include directories are resolved from your current
directory, so the command can be used from another project.

Add --reference reference.c (repeatable), -I path, or -DNAME=value as needed.
Use --entry to select a C entry other than harness, --unwindset for per-loop
bounds, --z3 or --cvc5 for an SMT backend, and --timeout to change the per-tool limit
(default 300 seconds). asmc --help lists all options. CBMC's assertion
and unwinding checks remain enabled.
Use --memory-limit MiB to cap address space per tool/solver process.

For solver/encoding tradeoffs, see the [scaling benchmarks](benchmarks/README.md).
The driver also accepts `--bitwuzla` (with optional `--solver-path`),
`--external-sat-solver /path/to/kissat`, and
`--max-field-sensitivity-array-size N`. CBMC defaults to 64; 0 disables array
scalarization, while 768 covers the ASMC register bank and can help call dispatch.
These settings have different costs for symbolic buffers; defaults remain unchanged.

`--scalar-registers` is an experimental, register-only encoding change: it stores
the same 768 bytes as three flat `uint64_t[32]` blocks so CBMC can track
96 storage cells at its default array threshold of 64.
It leaves RAM and C object arrays unchanged. The words are
not architectural registers: `AL`, `AH`, `AX`, `EAX`, and `RAX` still share bytes,
and accesses can span blocks. SLEIGH supplies effects such as clearing the upper
half of `RAX` on an `EAX` write. This also works on RV32/RV64 without another
register map. It does not cache register values or change pointer aliasing.
Whole-word accesses use assignments directly; partial accesses use CBMC's
little-endian byte extract/update operations, preserving neighboring bytes.

For low-level `asmc-lift` workflows, compile **every C input** with
`-DASMC_SCALAR_REGISTERS`; the lifter detects the layout from the seed. The driver
supplies that definition for you. Precompiled GOTO inputs must use the same layoutreg.
Use `ASMC_REG_BYTE(s, offset)` for direct byte access, or the existing get/set
helpers. The flat layout remains the default while performance is evaluated;
`--max-field-sensitivity-array-size 0` disables CBMC scalarization for either
layoutreg. The global threshold still controls RAM, stacks and other C arrays;
for a 128-byte call stack, compare a threshold of 128 with the default 64. Re-run the existing semantic and
native-oracle tests with the new layout:
`ctest --test-dir build -R '^asmc-scalar-registers$' --output-on-failure -j1`.
That suite keeps the existing backends and uses Z3 for object-mode driver checks.
Keep the flag opt-in: storage changes can improve call dispatch and hurt
other models. See the [measured comparison](benchmarks/results/2026-10-14-registers/README.md).

Use --show-loops to discover loop IDs for --unwindset, or --show-properties to
list obligations. These modes lift and link normally but do not verify: they
report **INSPECT** (exit 0), save the listing in cbmc.log, and never report PASS.
For counterexamples, --trace-hex, --compact-trace, and --beautify control the
presentation. --slice-formula removes assignments unrelated to properties;
validation and unwinding assertions remain enabled.

Failures now include recent native instructions from CBMC's assignment trace.
Generated machine properties retain their function name and show the assembly
address/p-code operation for the failed source line. Unwinding failures identify
the loop to inspect; missing C bodies report ERROR and suggest --reference; resource failures
show the last checker stage and practical next options.

Use --dispatch when native control flow has troublesome overlapping backward
edges. It joins machine branches at one basic-block dispatch loop; its unwind
bound counts basic blocks. The default keeps direct native branches. See the
[production and interpreter challenges](examples/exploration/README.md) for
upstream examples, C contracts, solver limitations, licenses, and a progression
toward threaded interpretation and SIMD.

The [CBAT comparison examples](examples/cbat/README.md) lift original and edited
ELF files into two named functions and check them with one C harness. They cover
equivalent rewrites, a switch fall-through bug, pointer inputs, table bit scans,
and why checking return values alone can miss changed function calls. Run
`ctest --test-dir build -R '^asmc-cbat$' --output-on-failure -j1`.

### Project-local SMT solvers

The optional solver environment pins Z3 5.1.0 and cvc5 1.4.2, resolved on
October 13, 2026. Python packages are recorded in requirements-solvers.txt:

~~~sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-solvers.txt
~~~

The Z3 wheel installs .venv/bin/z3. The cvc5 wheel provides Python bindings
only; CBMC needs its command-line executable. For Linux x86-64, install the
matching [official release](https://github.com/cvc5/cvc5/releases/tag/cvc5-1.4.2)
inside the environment:

~~~sh
gh release download cvc5-1.4.2 --repo cvc5/cvc5 \
  --pattern cvc5-Linux-x86_64-static.zip --dir .venv
unzip .venv/cvc5-Linux-x86_64-static.zip -d .venv/cvc5-1.4.2
ln -s ../cvc5-1.4.2/cvc5-Linux-x86_64-static/bin/cvc5 .venv/bin/cvc5
~~~

The release archive's SHA-256 is
7eb18f8c814c36a46c5a7d003983e9cfbc4b0a9828d6dd596239291bd4cc61d8.
Choose the solver and its executable explicitly:

~~~sh
build/bin/asmc examples/inc.S --function inc \
  --harness examples/inc_spec.c --z3 --solver-path .venv/bin/z3
build/bin/asmc examples/inc.S --function inc \
  --harness examples/inc_spec.c --cvc5 --solver-path .venv/bin/cvc5
~~~

Alternatively, source .venv/bin/activate and omit --solver-path. CBMC resolves
the selected solver on PATH; the Python interpreter running the driver does
not determine which solver executable CBMC uses. The default backend remains
CBMC's built-in SAT solver. To run the challenges with a selected SMT solver,
activate the environment and use tests/run.py's --solver z3 or --solver cvc5.

Use asmc-lift for the individual toolchain steps:

~~~sh
mkdir -p build/demo
gcc -nostdlib -no-pie -Wl,-e,inc examples/inc.S -o build/demo/inc.elf
build/bin/goto-cc -I include -c runtime/runtime.c -o build/demo/seed.gb
build/bin/asmc-lift build/demo/inc.elf --function inc \
  --template build/demo/seed.gb -o build/demo/inc.gb
build/bin/goto-cc -I include build/demo/inc.gb examples/inc_spec.c \
  -o build/demo/check.gb
build/bin/cbmc build/demo/check.gb --function harness --unwind 40 \
  --unwinding-assertions --validate-goto-model --trace
~~~

The example checks RAX == input + 1 for all 64-bit inputs, including
wraparound, the return address, stack restoration, and callee-saved registers.
[examples/inc_spec.c](examples/inc_spec.c) is a small complete harness to adapt.
Memory and loop examples are in tests/harness.c and tests/reference.c.
The [pcode2c examples](examples/pcode2c/README.md) provide small complete
source-versus-compiled checks for signed minimum, factorial, and array equality,
plus a sequential compare-exchange example.
The [kernel examples](examples/kernels/README.md) compare `popcnt` and branchless
selection against C, and explain explicit memory mappings with array sum and swap.
The [RISC-V examples](examples/riscv/README.md) show RV32/RV64 compilation,
register helpers, memory checks and the supported integer ABI subset.
The [composition example](examples/compose/README.md) links two named lifts and
calls them through ordinary C wrappers, keeping ABI and buffer mapping in the adapters.

The emitted **inc.gb.asm** listing associates assembly addresses with p-code
indices and opcodes. GOTO source locations point to corresponding lines:

~~~sh
build/bin/goto-instrument --show-goto-functions build/demo/inc.gb
~~~

The lift-only command exits 0 after producing a validated object, or 2 on invalid input or
unsupported instructions. **Its exit status is not a verification result.**
Run CBMC to verify the linked harness. CBMC exits 10 for a failed property,
including an insufficient unwinding bound.

## Machine-state interface

The default target declaration in `include/asmc_state.h` is:

~~~c
void asmc_target(struct asmc_state *s);
~~~

`--target name` replaces another function with this same signature. The check
driver creates a named stub automatically; manual templates define their own
empty bodies. Multiple lifts can replace different stubs in one model, or use
separate stub-only objects linked with one common runtime.

`asmc_state.h` defines the common state and register/memory accessors;
`runtime/runtime.c` implements those accessors and the default target stub.
`asmc_x86.h` holds x86 names and header-local SysV helpers, while
`asmc_riscv.h` holds RISC-V helpers. Harnesses include their architecture's header;
stub-only templates include `asmc_state.h`.

The harness supplies a byte register bank, a C RAM buffer, its numeric machine
base and length, and the expected return destination. GPR and flag offsets
are checked against the loaded SLEIGH specification.

Machine addresses are integers, **not CBMC pointers**. Address ram_base + k
corresponds to ram[k]. Stack and application data share the same address
space, preserving aliasing. Every complete load/store must fit in the region,
which must not wrap the selected machine address space.

The helper asmc_setup_stack writes a return sentinel and sets RSP. For a SysV
function entry choose a pointer congruent to 8 modulo 16, leaving room below
it for spills and the red zone. The helper asmc_assume_flags establishes
well-formed Boolean flag bytes.

For integer-only SysV AMD64 signatures, asmc_sysv_arg64(s, index, value)
sets one of the first six 64-bit register arguments (indices 0..5), and
asmc_sysv_result64(s) reads the 64-bit RAX result. These helpers select registers;
they do not translate C pointers. For a pointer argument, pass an explicit
numeric machine address such as s.ram_base + offset. Stack arguments, other
integer widths, and other calling conventions can use the existing register/memory
helpers directly.

asmc_sysv_setup_ram_model_at(s, ram, base, size, sp) combines that scalar SysV entry setup
and returns an asmc_sysv_frame checkpoint. Addresses and buffer sizes stay
explicit. It constrains Boolean flags, clears DF, writes the return sentinel,
checks entry stack alignment, and captures the six preserved GPRs. RAM and
other registers retain their initial values. Call asmc_sysv_check(s, &frame)
after the target to assert GPR preservation, RSP == entry_sp + 8, and DF == 0.
`asmc_sysv_setup_ram_model(s, ram, base, size)` chooses the highest valid entry SP
in that buffer, avoiding a hand-picked stack address. Application data must
still leave room below it for the stack and red zone.

For object-memory harnesses, set pointer/scalar arguments first and use
`asmc_sysv_call_objects_model(&st, stack, sizeof stack)` to set up the stack,
execute `ASMC_TARGET`, and assert the scalar ABI obligations in one call:

```c
uint8_t stack[256];
struct asmc_state st;
asmc_sysv_arg_ptr(&st, 0, &a);
asmc_sysv_arg_ptr(&st, 1, &b);
asmc_sysv_call_objects_model(&st, stack, sizeof stack);
/* Assert functional postconditions here. */
```

`asmc_sysv_call_ram_model(&st, ram, base, size)` provides the same wrapper for
numeric RAM. RISC-V provides the corresponding `asmc_riscv_*` helpers.
The wrappers preserve argument registers during setup and leave RAM bytes
unchanged except for the x86 return sentinel. Use separate `*_setup_objects_model`
or `*_setup_ram_model` and `*_check` calls when you need entry-state snapshots,
custom flags, or register setup after ABI initialization. `*_setup_ram_model_at`
accepts an explicit entry SP; `*_setup_ram_model` chooses one automatically.

asmc_sysv_arg32 writes only the low 32 argument bits. asmc_sysv_result32 reads
EAX; asmc_sysv_result_bool reads AL and checks a canonical Boolean byte.
These helpers make the declared C width visible and keep unspecified excess
register bits out of the comparison.

RAM and registers can begin nondeterministically. Initialize only required
inputs, so accidentally depending on an unused register is detectable.
For memory equivalence, copy the initial buffer and run the ordinary C
reference on pointers into that copy. Compare all application bytes,
including bytes that should remain unchanged. Exclude only the designated
stack scratch region from that comparison.

## Supported first version

* Unstripped, statically linked, non-PIE, little-endian x86-64 or RV32/RV64 ET_EXEC ELF.
  ELF supplies code; the harness supplies mutable data and stack.
  Optional --rodata embeds immutable `.rodata*` bytes at their linked addresses.
  Relocatable `.o` inputs report a shell-quoted linker command for the selected
  symbol and architecture; ASMC does not execute the suggested command.
* Lifting windows use ELF function sizes, or the containing executable section
  for unsized symbols. --lift-end-address overrides the entry window. Repeat
  --callee NAME to admit helper functions in the same ELF. Reachable bytes and
  explicitly admitted indirect targets in these ranges are decoded.
* Integer arithmetic up to 128 bits: copy, extensions, add/subtract/multiply,
  comparisons, carry/overflow, bitwise and Boolean operations, shifts, pieces,
  population count and leading-zero count.
* Flat loads/stores, direct and conditional branches, intra-instruction
  relative branches, direct calls/tail calls, and returns. Bounded recursion
  uses the native stack/return registers. See [the call examples](examples/calls/README.md)
  for the address dispatcher and checked bounds.

Indirect jumps require repeated --indirect-target SYMBOL_OR_ADDRESS options;
computed destinations outside that set fail a property. See the
[compiled-switch example](examples/switch/README.md). Indirect calls,
calls to C models, division, SIMD, floating point,
TLS/segmentation, user operations, dynamic loading, relocatable objects,
and overlapping instruction encodings are rejected. Unsupported reachable
operations name the address, instruction, and opcode; unreachable unsupported
instructions are harmless.

Do not disable unwinding assertions when claiming equivalence. A failed
unwinding assertion means admitted executions were not all covered.
Verification concerns the supplied machine-state assumptions and the pinned
SLEIGH semantics. This version does not implement unbounded cutpoint proofs.

## Reading the C++

Start with [src/pcode_expr.cpp](src/pcode_expr.cpp): its switch constructs
symbolic arithmetic terms. The constructor plus_exprt(a, b) represents
the bitvector sum; it does not add concrete host values. A typecast fixes
the result width.

Then read [src/translate.cpp](src/translate.cpp): read, write_bytes, and
memory_offset connect those terms to storage. Outputs are evaluated before
any byte is written, preserving overlapping input/output registers.
Temporary bytes are shared within an instruction and distinct across
instructions. Jumps are resolved after all labels have been emitted.

The lifter captures raw p-code and walks its control flow. The ELF loader
selects executable bytes through ELFIO. The main program reads the C-compiled
template, invokes translation, validates the complete model, and writes GOTO.

The C template supplies the state structure, function signature, parameter
symbols, helpers, and architecture configuration. ASMC replaces only the
asmc_target body.

## Tests

The arithmetic tests exhaust all 8-bit operand pairs for carry and signed
overflow, and check larger-width boundaries, oversized shifts, extraction,
bit counts, and signed p-code-relative branches.

The challenges build real assembly, lift it, validate and round-trip each
successful test object through goto-instrument, link C references, and run
CBMC. Cases include mixed-width register writes, branch/cmov maximum,
byte swap/rotate, two-limb ADC/SBB arithmetic, copy lengths 0–32, and bounded
linear search.
Additional cases cover sign/zero extension, full 128-bit multiplication,
REP MOVSB, and upstream s2n-bignum word_max and bignum_add (all input and
output lengths from 0 to 2 limbs). The s2n fixtures use their NO_IBT build
option because CET is outside the initial model.
The 27 bignum length triples are verified separately, with arbitrary 64-bit
limbs in each proof and checked loop bounds of four. Multiplication and
bignum proofs use CBMC's Z3 backend; the remaining cases use its default SAT
backend. The test runner's --solver option can
override this choice. Timeouts fail the tests and never count as proofs.

Mutations test wrong results, lost carry, zero-length copy, memory bounds
and wraparound, corrupted returns, callee-saved corruption, and insufficient
unwinding. GCC/Clang kernels at -O0 and -O2 exercise compiler output and spills.

To debug one challenge:

~~~sh
python3 tests/run.py build/bin/asmc-lift --tools build/bin --only add2
~~~

Concrete execution checks against the same native ELF are described in
[tests/NATIVE.md](tests/NATIVE.md). A
[compiled-switch example](examples/switch/README.md) uses explicit indirect
jump destinations and immutable ELF `.rodata` without hiding machine addresses.

The native tests found that pinned x86 SLEIGH leaves arithmetic auxiliary carry
(`AF`) unimplemented. ASMC warns when lifted p-code reads AF. Checks depending
on that flag can disagree with hardware; [the regression](tests/NATIVE.md)
records this limitation explicitly.

An optional [CBMC-object memory mode](examples/objects/README.md) lets assembly
access actual C arrays, globals passed by pointer, and malloc allocations:
`--memory objects`. Pointer arguments/results and a separate C stack object
have explicit ABI helpers. The default numeric RAM mode and `--rodata` remain
available; the two address schemes are not mixed automatically.
