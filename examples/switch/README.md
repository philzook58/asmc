# A compiled switch with a jump table

`switch.c` and `harness.c` are independently written examples. Compile the C
function, then compare its assembly with the same C implementation:

```sh
mkdir -p build/switch
gcc -O2 -nostdlib -static -no-pie -fcf-protection=none \
  -fno-reorder-blocks-and-partition -Wl,-e,choose \
  examples/switch/switch.c -o build/switch/switch.elf
objdump -d -s build/switch/switch.elf
```

GCC emits eight signed 32-bit offsets in `.rodata`. The assembly loads one,
adds the table base, and jumps to the resulting address. Inspect the table
and disassembly, then supply **all eight case-entry addresses**:

```sh
build/bin/asmc build/switch/switch.elf --function choose \
  --harness examples/switch/harness.c --reference examples/switch/switch.c \
  --rodata --indirect-target ADDRESS_0 --indirect-target ADDRESS_1 \
  --indirect-target ADDRESS_2 --indirect-target ADDRESS_3 \
  --indirect-target ADDRESS_4 --indirect-target ADDRESS_5 \
  --indirect-target ADDRESS_6 --indirect-target ADDRESS_7 \
  --unwind 20 --unwindset asmc_target.0:3
```

Addresses depend on the compiler and linker. `tests/switch.py` extracts this
fixture's table and performs the complete check automatically; it deliberately
does not implement general jump-table recovery:

```sh
ctest --test-dir build -R '^asmc-switch$' --output-on-failure
```

`--indirect-target` accepts an address or ELF symbol within admitted function
ranges. It admits code for decoding and checks every computed indirect jump
against the supplied set. Missing destinations fail an assertion; they are
not assumed unreachable. Indirect jumps use the existing dispatcher, so its
unwind bound counts executed basic blocks. Indirect calls remain unsupported.
A target list is shared by the lifted function and its admitted callees.

`--rodata` embeds allocated, non-writable, non-executable `.rodata*` sections
as immutable bytes at their linked numeric addresses (maximum 64 KiB per
section). A complete load must fit within one such section or the harness's
RAM. Stores still go only to RAM. RAM must not overlap these immutable regions.
There is no large backing allocation spanning the gap between code and stack.
The C `asmc_load`/`asmc_store` helpers continue to access harness RAM; they do
not load ELF regions. Mutable globals, `.bss`, dynamic linking and relocatable
objects are outside this extension.

The tests also remove a case destination, omit the target list or `.rodata`,
and overlap RAM with `.rodata`; none may return PASS. Additional tests check
full-width reads, the last valid bytes, RAM reads alongside ELF data, boundary
crossings, address wrap, and rejected stores to immutable memory.
