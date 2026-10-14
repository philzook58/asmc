# Assembly challenges with C specifications

The most useful progression is small production routines, array contracts,
then interpreters and vector kernels. These fixtures compare assembly with C
and also compile the C implementations into native ELF. Sources, authors,
modifications, and retained licenses are recorded in [SOURCES.md](SOURCES.md).

| Example | Checked domain and observations |
|---|---|
| AWS saturating add | Every pair of `uint32_t` inputs. Compiled C on x86-64/RV32/RV64 and hand assembly versus a widened-add C specification. Includes wrap/carry boundaries. |
| ACSL lower bound | Sorted prefixes of length 0–4, arbitrary signed values and key, including duplicates. Compiled C versus linear search; additionally check both partition postconditions and all input bytes unchanged. x86-64/RV32/RV64. |
| simdjson SWAR | GCC/Clang x86-64, RV64 GCC and hand assembly versus the C reductions for all eight ASCII digits. An independent Horner specification also passes for the 10,000 strings `0000dddd`. |
| Literal/add calculator | Well-formed programs of 1–5 tokens, literals 0–127, stack depth at most four. GCC/Clang `-O0` and hand assembly versus C evaluation, plus the independent sum-of-literals contract. Input bytes and ABI must remain intact. |

Every successful check includes ABI preservation, stack restoration, memory
bounds, model validation, serialization readback, and unwinding assertions.
Mutations invert carry, change a SWAR multiplier, replace calculator addition
with subtraction, or skip duplicate search keys. Each
must fail. A deliberately insufficient dispatcher bound must report INCOMPLETE.

## Useful next sources

| Source | Promising bite | What it would expose |
|---|---|---|
| [ACSL by Example](https://github.com/fraunhoferfokus/acsl-by-example) | `reverse`, `rotate`, partition, insertion sort | Mutation frame conditions, duplicates, multiple loops, and calls to `swap`. Its C contracts translate well into bounded executable assertions; ASMC does not consume ACSL automatically. |
| [AWS C Common](https://github.com/awslabs/aws-c-common) and [CBMC project index](https://model-checking.github.io/cbmc-training/projects.html) | Checked arithmetic, endian loads/stores, bounded byte-buffer operations | Existing C specifications are valuable. Larger library harnesses need an explicit adapter from C objects to numeric RAM, error/globals models, and allocation/call policies. They cannot be applied to machine pointers unchanged. |
| [Hutton's compiler work](https://people.cs.nott.ac.uk/pszgmh/bib.html) / Forth | Literal/add evaluator, DUP/SWAP, then bounded threaded execution | Separate data and native return stacks; interpreter invariants; eventually a supplied whitelist for indirect dispatch. A tiny calculator is more tractable than a full Forth environment. |
| [Jonesforth](https://github.com/nornagon/jonesforth/blob/d97a25bb0b06fb58da1975eac291f45618fd2ada/jonesforth.S) | Isolated primitives, then `NEXT` | Public-domain code, but the supplied interpreter is i386. `NEXT` loads a dictionary codeword and jumps indirectly. Needs i386 state/ABI support, indirect destinations, dictionary/global loading; the complete interpreter also uses Linux syscalls. |
| [Daniel Lemire's SWAR explanation](https://lemire.me/blog/2022/01/21/swar-explained-parsing-eight-digits/) | Byte classification and short decimal parsing | Scalar packed arithmetic works today. Full semantic equivalence of different arithmetic formulas can challenge solvers even when translation equivalence is easy. |
| [Geoff Langdale's SIMD taxonomy](https://branchfree.org/2024/06/09/a-draft-taxonomy-of-simd-usage/) and [Wojciech Muła's work](https://0x80.pl/) | Byte-mask extraction, shuffles, character-class lookup | Start with isolated integer lanes, then cross-lane permutations and table loads. SIMD needs register storage, wider varnodes, opcode/user-op coverage, and hardware preconditions; it is not just a new ABI flag. |
| [FFmpeg assembly lessons](https://github.com/FFmpeg/asm-lessons) / [awesome-simd](https://github.com/awesome-simd/awesome-simd) | A small packed average/saturating-add kernel and its scalar reference | Good guides to real SIMD idioms. The lesson repository is instructional material; awesome-simd is a discovery list. Check each actual kernel's license and isolate build macros before importing it. |
| [StefanoBelli's samples](https://github.com/StefanoBelli/x86_64-samples) | Scalar string and array routines | `lodsb`, bounded `strlen`, DF assumptions and ABI details are useful now. x87, SSE floating point and CPUID examples identify later gaps. No code imported without established reuse terms. |
| [xorpd puzzles](https://www.xorpd.net/) | Short flag/register identities | Excellent independent micro-harness ideas. Some snippets intentionally violate function ABI conventions or have input-dependent termination; specify entry state and observed state explicitly. No puzzle code copied. |
| [Knuth's TAOCP](https://www-cs-faculty.stanford.edu/~knuth/taocp.html) | Independently implement Euclid, binary search, insertion sort or multiword arithmetic | Algorithmic contracts and invariant challenges; MIX/MMIX programs add another architecture rather than testing today's x86/RISC-V frontend directly. No book code copied. |
| [Randall Hyde's Art of Assembly](https://www.plantation-productions.com/Webster/www.artofasm.com/index.html) | Independently implement integer conversion and string routines | Useful explanations; check the specific edition's architecture, runtime dependencies and source permissions. Integer conversion naturally motivates division and fault semantics. |
| [FASM examples](https://flatassembler.net/examples.php) | Isolated leaf algorithms from suitable ELF examples | The page could not be retrieved during this inspection, so no particular archive or license was assessed. Inspect format, entry conventions, globals, OS dependencies and license before importing an archive. |

## Run a contract on compiled C

From the ASMC directory:

```sh
mkdir -p build/exploration
gcc -O2 -nostdlib -no-pie -fcf-protection=none -fno-stack-protector \
  -Wl,-e,lower_bound examples/exploration/acsl-by-example/lower_bound.c \
  -o build/exploration/search.elf
build/bin/asmc build/exploration/search.elf --function lower_bound \
  --harness examples/exploration/search_spec.c \
  --reference examples/exploration/reference.c \
  --dispatch --unwindset asmc_target.0:12,linear_lower_bound.0:5 \
  --memory-limit 2048
```

`--dispatch` sends native branches through one basic-block dispatcher. The
optimized GCC search has two backward machine edges; normal address ordering
made its unwinding troublesome even for a short search. Dispatcher bounds
count executed basic blocks, not C iterations. Twelve is checked sufficient
for the admitted inputs. Calls retain their usual dispatcher without this flag.
Indirect branches remain unsupported; this mode reorganizes already known
native destinations.

For the calculator:

```sh
gcc -nostdlib -no-pie -Wl,-e,rpn_asm examples/exploration/rpn.S \
  -o build/exploration/rpn.elf
build/bin/asmc build/exploration/rpn.elf --function rpn_asm \
  --harness examples/exploration/rpn_spec.c --reference examples/exploration/rpn.c \
  --unwindset asmc_target.0:6,rpn.0:6 --memory-limit 2048
```

These are bounded complete-function checks. The calculator uses conditional
branches, not Jonesforth's indirect threaded `NEXT`.

## SWAR scope

Full eight-digit translation equivalence is established against the imported
C reductions. Independent Horner arithmetic is established for `0000dddd`.
The independent all-eight-digit assertion timed out after 45 seconds with
SAT, both installed Z3 versions, and cvc5. It remains a solver/compositional
proof challenge; a timeout is not evidence for or against the formula.
`-DDIGIT_CONTRACT` enables the restricted independent contract.

The full independent challenge can be reproduced by adding `-DDIGITS
-DDIGIT_CONTRACT -DDIGIT_FULL` to a SWAR check, linking both `reference.c` and
`simdjson/swar.c`. This removes the leading-zero restriction without editing
the harness; retain the memory/time limits while experimenting.
Do not call the full semantic property proved just because the C/assembly
translation-equivalence checks pass.

```sh
ctest --test-dir build -R '^asmc-exploration$' --output-on-failure
```
