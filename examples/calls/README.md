# Calls through the native machine state

`--callee NAME` admits another sized function symbol from the same linked ELF.
Repeat it for every helper that can be reached, including helpers of helpers.
The entry function is already admitted, so self-recursion needs no extra flag.
ASMC decodes each reachable instruction once, including when the call graph
contains cycles. It does not inline or recursively expand functions.

Run from the ASMC directory:

```sh
mkdir -p build/examples
gcc -O0 -nostdlib -no-pie -fno-stack-protector -fcf-protection=none \
  -fno-optimize-sibling-calls -Wl,-e,nested examples/calls/functions.c \
  -o build/examples/calls.elf
build/bin/asmc build/examples/calls.elf --function nested \
  --callee middle --callee leaf --harness examples/calls/spec.c -DCASE=1 \
  --unwindset asmc_target.0:7 --memory-limit 2048
build/bin/asmc build/examples/calls.elf --function recursive \
  --harness examples/calls/spec.c -DCASE=3 \
  --unwindset asmc_target.0:7 --memory-limit 2048
```

`CASE=1` checks nested calls; `CASE=2` checks repeated calls to `leaf` through
different return sites; `CASE=3` checks recursive summation for inputs 0–3;
`CASE=4` checks `tail`; `CASE=5` checks mutually recursive even/odd functions.
Every case checks the result, preserved registers, and
stack restoration. The harness uses a 160-byte RAM region with space for the
native stack. The same harness works on RV32/RV64; `asmc` selects the ABI
header configuration from the ELF. Use ordinary linker relaxation for RISC-V
so calls become direct JAL instructions; unrelaxed AUIPC/JALR calls remain
unsupported indirect calls.

The translator preserves SLEIGH's stack stores, stack-pointer changes, and
RISC-V return-register writes. CALL transfers to the native callee address.
RETURN reads the actual destination from that modeled state: it must be a
known call continuation or the outer return sentinel. There is no additional
verification call stack. This also allows direct tail branches into admitted
helpers. Calls to C models, libc, or dynamically loaded code are unsupported.

Calls and returns meet at one address-dispatch loop. Its table contains the
entry, reached callee entries, and call continuations. Ordinary branches still
use direct GOTO edges. One iteration of this loop handles the code between
call/return transitions, rather than one instruction or one recursion level.
Use `--show-loops` to discover its ID when your function also has native loops.
The examples above need at most six transitions and use a checked bound of
seven. Lowering the bound to one reports INCOMPLETE. All bounds keep unwinding
assertions enabled.

Keep RAM and bounds as small as the admitted inputs allow. A symbolic return
address can make subsequent stack addresses symbolic, and the SAT backend
then expands byte-array accesses. Try `--z3` for larger buffers. The optional
`--memory-limit` caps address space per tool/solver process in MiB; exhausted
checker memory reports INCOMPLETE, never PASS.

`tests/test_calls.py` checks `-O0`/`-O2` on x86-64, RV32, and RV64, tail calls,
serialization validation, missing admitted helpers, insufficient bounds, and
mutations of results, saved registers, and return addresses. The regression
itself runs under a 2 GiB address-space cap.

```sh
python3 -m pytest tests/test_calls.py --build-dir build -q
```
