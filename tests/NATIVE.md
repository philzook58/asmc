# Concrete execution comparison

`test_native.py` builds a statically linked x86-64 executable from the independently
written `native.S` and `native_runner.c`. It executes that ELF on 12 boundary
inputs and 12 pseudo-random pairs (fixed seed `0xA5C`). It records the native
return value and six output words, then lifts the **same ELF** and asks CBMC
to check every recorded execution.

The outputs observe addition, five arithmetic flags (CF/PF/ZF/SF/OF), AL/AH/RAX
aliasing, EAX zero extension, variable shifts, memory writes, and a direct
call/return. Shift cases include 63, 64, 65 and 255. The lifted harness also
checks the ABI, stack restoration, and application bytes outside the outputs.
Native stack scratch and undefined flag bits are not compared.

A deliberately corrupted observation must fail. Models undergo validation and
serialization readback. Each tool is bounded in time and address-space use.
These finite, reproducible comparisons supplement symbolic C-specification
checks; they do not establish arbitrary-input instruction equivalence.
`test_riscv_native.py` performs the same kind of finite execution comparison on
RV32 and RV64 through QEMU user mode. Its independently written probe observes
addition, signed/unsigned comparisons, variable shifts, sign-extending loads,
memory writes, and a direct call/return. Each width uses 12 boundary inputs and
12 fixed-seed random pairs. Separate corrupted return and memory observations
must produce counterexamples. The lifted harness checks the ABI and bytes
outside the output and stack scratch areas. The runner uses Linux syscalls and
needs no RISC-V libc. Tests skip if the cross compiler or matching QEMU is absent.
QEMU is an independent emulator oracle, not a substitute for hardware testing.

```sh
python3 -m pytest tests/test_native.py --build-dir build -q
python3 -m pytest tests/test_riscv_native.py --build-dir build -q
```

The executable also records AF. The pinned x86 SLEIGH `resultflags` macro
explicitly leaves AF unimplemented, so the ordinary comparison masks that bit.
A separate regression checks all six flags and requires the resulting
counterexample. This is a known semantic limitation, not an undefined hardware
flag: ADD defines AF, and ASMC currently inherits SLEIGH's incomplete behavior.
Checks depending on arithmetic AF are not reliable.
