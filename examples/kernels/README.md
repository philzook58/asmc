# Small compilation and optimization checks

These are independently written teaching kernels, not imported upstream code.
They illustrate ideas from [STOKE's population-count tutorial](https://github.com/StanfordPL/stoke#running-example),
[compiler-rt's integer builtins](https://github.com/llvm/llvm-project/tree/main/compiler-rt/lib/builtins),
[s2n-bignum's conditional selection routines](https://github.com/awslabs/s2n-bignum/tree/main/x86/generic),
and Philip's [swap](https://www.philipzucker.com/asm_verify3/) and
[array-sum](https://www.philipzucker.com/asm_verify4/) posts.

| Target | Specification and purpose |
|---|---|
| `count_bits` | Compiled C versus a C reference, across all 64-bit inputs |
| `count_bits_fast` | One `popcnt` versus the simple 64-step reference |
| `choose` / `choose_fast` | C selection / `cmovne` versus `condition ? y : x`, including every nonzero condition |
| `sum_words` | Read 0–4 words, accumulate modulo 2^32, leave inputs unchanged |
| `swap_words` | Swap aligned words, including identical argument pointers, leave other words unchanged |

All harnesses check callee-saved GPRs, SP restoration, DF, and the return sentinel.
The memory harness relates four C `uint32_t` objects to little-endian machine
addresses `0x1000 + 4*i`. Stack storage is separate in the upper part of RAM.
It checks the entire declared four-word application buffer after execution.
Unsigned addition makes overflow intentional; no restriction on element values
is needed. Swap permits identical or disjoint C objects. Partially overlapping
unaligned word accesses would require a separate byte-memory specification.

From the ASMC directory, verify an optimized instruction against readable C:

```sh
mkdir -p build/examples
gcc -nostdlib -no-pie -Wl,-e,count_bits_fast examples/kernels/optimized.S \
  -o build/examples/optimized.elf
build/bin/asmc build/examples/optimized.elf --function count_bits_fast \
  --harness examples/kernels/scalar_spec.c --reference examples/kernels/kernels.c \
  --unwind 66 --slice-formula
```

Use `--function choose_fast -DSELECT` with the same harness for conditional
selection. `popcnt` is interpreted by SLEIGH; the verifier does not execute the
instruction on the host CPU.

For a compiled memory function:

```sh
gcc -O2 -nostdlib -no-pie -fno-stack-protector -fcf-protection=none \
  -fno-tree-vectorize -Wl,-e,sum_words examples/kernels/kernels.c \
  -o build/examples/kernels.elf
build/bin/asmc build/examples/kernels.elf --function sum_words \
  --harness examples/kernels/memory_spec.c --reference examples/kernels/kernels.c \
  --show-loops
```

Inspection reports **INSPECT**, not PASS. Use the printed loop IDs to choose
bounds, then remove `--show-loops` and add
`--unwindset asmc_target.0:6,sum_words.0:6`. For swap, use
`--function swap_words -DSWAP` without that unwindset.

`tests/kernels.py` checks GCC and Clang at `-O2`, both assembly alternatives,
and mutations that miss the top bit, invert selection, replace addition with
XOR, or fail to write one swapped value. Good targets pass; each mutation fails.

The missing-zero-check copy from [refine_assembly](https://www.philipzucker.com/refine_assembly/)
already has x86 counterparts in `tests/challenges.S`: `copy` and `copy_bad`.
The regression harness gives `copy_bad` length zero and requires a concrete
failure, while checking correct copy for lengths 0–32 and testing insufficient
unwinding separately. These are bounded whole-function checks; they do not
reproduce the post's unbounded cutpoint proof.

```sh
ctest --test-dir build -R '^asmc-(check|kernels)$' --output-on-failure
```
