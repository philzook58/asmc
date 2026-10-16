# pcode2c examples with explicit ASMC harnesses

Adapted from [philzook58/pcode2c](https://github.com/philzook58/pcode2c), commit
`a88f732f2522ea198a74ff3287fa61c7380ed9e4`, by Philip Zucker. The functions come
from `examples/min`, `examples/fact_iter`, `examples/all_equal`, and
`examples/cmp`. Further examples are cleaned-up cores of `examples/fact_rec`
and `examples/tv/prime.c`. These are whole-function checks; no DWARF or
instruction-breakpoint validation is claimed.

| Example | What its harness checks |
|---|---|
| `min.c` | Compiled signed minimum agrees with C for every 64-bit input pair |
| `factorial.c` | Compiled factorial agrees with C for inputs 0–12 |
| `equal.c` | Signed lengths −2–8; arbitrary values; identical, overlapping, and disjoint slices |
| `cmpxchg.S` | Both success/failure paths, ZF, unaligned memory writes, and unchanged surrounding bytes |
| `fact_recursive.c` | Native recursive factorial agrees with iterative C for inputs 0–3 |
| `unsupported.c` | Integer division/remainder is rejected explicitly |

Every successful harness also checks preserved GPRs, stack restoration, and DF.
The factorial bound excludes negative-input nontermination and signed overflow.
Array values are explicitly initialized symbolically; reading uninitialized C
integers is not used as the specification. Vectorization is disabled so these
examples exercise the scalar instruction subset ASMC supports. `cmpxchg` models
sequential behavior, without LOCK or concurrent threads.

Run from the ASMC directory. The same C source supplies machine code and the
CBMC reference, with the harness providing the relation between them:

```sh
mkdir -p build/examples
gcc -O2 -nostdlib -no-pie -fno-stack-protector -fcf-protection=none \
  -fno-tree-vectorize -Wl,-e,mymin examples/pcode2c/min.c -o build/examples/min.elf
build/bin/asmc build/examples/min.elf --function mymin \
  --harness examples/pcode2c/min_spec.c --link-arg examples/pcode2c/min.c
```

For the array example, choose enough checked iterations for lengths up to 8:

```sh
gcc -O0 -nostdlib -no-pie -fno-stack-protector -fcf-protection=none \
  -fno-tree-vectorize -Wl,-e,equal examples/pcode2c/equal.c -o build/examples/equal.elf
build/bin/asmc build/examples/equal.elf --function equal \
  --harness examples/pcode2c/equal_spec.c --link-arg examples/pcode2c/equal.c \
  --unwindset asmc_target.0:10,equal.0:10
```

The equal harness puts the sixteen C integers into little-endian modeled RAM.
`data[i]` corresponds to four bytes starting at machine address `0x1000 + 4*i`.
The two argument pointers are numeric addresses into this same region, so
aliasing is retained. The stack is placed separately in the upper part of the
same buffer. Application values are checked unchanged after execution.

The small SysV helpers reduce repeated setup without translating any pointers:

```c
uint8_t ram[256];
struct asmc_state s;
struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model_at(&s, ram, 0x1000, sizeof(ram), 0x10c8);
asmc_sysv_arg32(&s, 0, (uint32_t)n);
asmc_sysv_arg64(&s, 1, 0x1000);
asmc_target(&s);
asmc_sysv_check(&s, &frame);
```

The 32-bit argument helper initializes only the declared value bits; excess
register bits retain their previous values (arbitrary in these harnesses).
The result helpers read EAX for 32-bit results and AL for `_Bool`, checking that
the Boolean byte is 0 or 1. Higher return-register bits are ignored accordingly.

The regression script runs GCC and Clang at `-O0` and `-O2`, proves each C
example against its reference, and checks deliberate wrong implementations.
Additional mutations must fail when they clobber RBX, pop excess stack bytes,
or leave DF set. Boolean tests use dirty upper RAX bits; an invalid Boolean
byte must fail. Too little unwinding must report INCOMPLETE.

```sh
python3 -m pytest tests/test_pcode2c.py --build-dir build -q
```
