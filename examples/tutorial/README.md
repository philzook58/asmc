# Tutorial regression examples

These fixtures preserve the executable ideas from Philip Zucker's
[`play/tutorial.ipynb`](../../play/tutorial.ipynb), using the current API names.
The notebook is left untouched. The original assembly discussions are
[Assembly Verification](https://www.philipzucker.com/assembly_verify/),
[Assembly Verification 2](https://www.philipzucker.com/asm_verify2/), and
[Assembly Verification 3](https://www.philipzucker.com/asm_verify3/).
These are tutorial-derived fixtures and newly written mutants; no external
third-party implementation was added.

Run all cases, including expected failures:

```sh
python3 -m pytest tests/test_tutorial.py --build-dir build -q
# Without reconfiguring CMake:
python3 -m pytest tests/test_tutorial.py --build-dir build
```

| Example | Positive check | Negative check |
|---|---|---|
| Constant 42 | Result is 42 | Result is 43 |
| LEA increment | Entry argument + 1; unsigned wraparound | Result equals unrelated entry RAX |
| Conditional move | Unsigned minimum | Maximum or signed-minimum interpretation |
| Compiled uint32 addition | EAX aliases and 32-bit wraparound | Unrestricted 64-bit interpretation |
| Stack scratch | Current memory at entry RSP - 8 | Reading relative to exit RSP; overwriting return address |
| Spilled swap | Argument region separated from stack | Missing RAM lower bound; aliasing a saved pointer |
| Object swap | Both distinct-object and same-object inputs | Mutant that loses an original value |
| XOR swap | Distinct-object inputs | Same-object inputs, exposed by a broader harness |
| Array swap | Symbolic indices, original values, untouched elements | Correct swapped values plus an unrelated write |

The short explicit `swap_spills` assembly reproduces the notebook's compiled
stack layout without depending on a particular compiler version. The separate
`swap` C function is compiled at `-O0` and its assembly is verified against
both C harnesses.

## Object harness

```sh
mkdir -p build/tutorial
gcc -O0 -fno-stack-protector -fcf-protection=none -nostdlib -static -no-pie \
  -Wl,-e,swap examples/tutorial/functions.c -o build/tutorial/functions.elf
build/bin/asmc build/tutorial/functions.elf --function swap --memory objects \
  --harness examples/tutorial/swap_objects.c
build/bin/asmc build/tutorial/functions.elf --function swap --memory objects \
  --harness examples/tutorial/swap_array.c
```

`swap_objects.c` uses an explicit `same_object` choice. `-DALIAS_CASE=0` checks
only distinct objects; `-DALIAS_CASE=1` checks only the same object; the default
covers both. The XOR-swap mutant deliberately passes the first restricted
harness and fails when the alias case is admitted. Conversely, the duplicate-store
mutant passes the same-object-only harness but fails on distinct values.

`swap_array.c` chooses any two elements of one four-integer array and checks
that all other elements are unchanged. It admits identical pointers and distinct
elements in either order, while `swap_objects.c` also covers distinct C objects.
These are bounded layouts, not a claim about all possible pointer configurations.
The array frame check covers only the remaining array elements; it is not a
universal assertion that no other live C object was written.

Use `-DMANUAL_ABI` with the object harness to exercise separate setup, call,
and ABI assertions instead of the convenience wrapper. Always pass
`--memory objects` for these harnesses. Omitting it is also a negative test.

The source-input and default-harness suites additionally cover the notebook's
unsized functions, explicit lifting boundaries, dead padding, register aliases,
and RV32/RV64 constant functions.
