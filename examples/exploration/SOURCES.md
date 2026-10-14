# Source provenance and licenses

Inspected on October 14, 2026. Imported code is kept in separate directories;
license texts and notices remain with it. No research checkout is a build
dependency. Native ELF/GOTO files are generated locally, not vendored.

| Fixture | Pinned source | License and changes |
|---|---|---|
| `acsl-by-example/lower_bound.c` | [ACSL by Example](https://github.com/fraunhoferfokus/acsl-by-example/blob/3e8cd9adf79955d9b722185f9beb4518c66d57f2/StandardAlgorithms/BinarySearch/lower_bound.c), `3e8cd9adf79955d9b722185f9beb4518c66d57f2` | MIT; copyright 2020–2026 Fraunhofer FOKUS. Replace the ACSL header include with the original `int`/`unsigned int` typedefs; keep the body and loop annotations. License retained. |
| `aws-c-common/saturating.c` | [AWS C Common](https://github.com/awslabs/aws-c-common/blob/2a29f7ea85397ff15e41ae086fb3662484fd305d/include/aws/common/math.fallback.inl), `2a29f7ea85397ff15e41ae086fb3662484fd305d` | Apache-2.0; Amazon.com, Inc. or its affiliates. Extract `aws_add_u32_saturating`, rename it, replace framework scaffolding with `<stdint.h>` and external linkage. Body unchanged. LICENSE and NOTICE retained. |
| `simdjson/swar.c` | [simdjson fallback parser](https://github.com/simdjson/simdjson/blob/15e7eb8bc6a225caac66dae67e41a3c83cb03280/include/simdjson/fallback/numberparsing_defs.h), `15e7eb8bc6a225caac66dae67e41a3c83cb03280` | Use the MIT option of simdjson's dual license; copyright 2018–2025 simdjson authors. Convert `parse_eight_digits_unrolled` to C and accept an already packed little-endian word instead of `memcpy` from a C++ pointer. Preserve the three reductions. License retained. Upstream credits [Johnny Lee](https://johnnylee-sde.github.io/Fast-numeric-string-to-int/). |

`scalar.S` implements the saturating-add specification independently and
adapts the attributed SWAR reductions to x86-64 instructions. The simdjson
notice and MIT license apply to that SWAR adaptation too. `reference.c`,
`rpn.c`, `rpn.S`, harnesses, and `abi.h` are independently written teaching
code. The literal/add calculator is inspired by the expression language used
in [Graham Hutton's compiler-calculation work](https://people.cs.nott.ac.uk/pszgmh/bib.html).
It copies no book or paper implementation.

Other pinned repositories inspected, with no code imported:

* [Jonesforth](https://github.com/nornagon/jonesforth/blob/d97a25bb0b06fb58da1975eac291f45618fd2ada/jonesforth.S),
  `d97a25bb0b06fb58da1975eac291f45618fd2ada`: Richard W. M. Jones's public-domain
  release statement is embedded in the source. Its i386 architecture and
  `NEXT` indirect dispatch are outside current support.
* [FFmpeg asm-lessons](https://github.com/FFmpeg/asm-lessons/tree/171e7261abcdd69e702c4c9b4bbb6f67fe0ade83),
  `171e7261abcdd69e702c4c9b4bbb6f67fe0ade83`: instructional Markdown rather than
  a ready collection of linkable kernels. No repository-level LICENSE/COPYING
  was found in this checkout; none of its lesson code was copied.
* [StefanoBelli/x86_64-samples](https://github.com/StefanoBelli/x86_64-samples/tree/15bd45941c3e180d3f0dcffb8b24268070e8fd0d),
  `15bd45941c3e180d3f0dcffb8b24268070e8fd0d`: useful strings/array routines and
  architecture probes. No repository-level LICENSE/COPYING was found in this
  checkout; no code was copied.

The books and xorpd puzzles below are discovery references, not sources of
vendored code. An accessible example or PDF alone was not treated as a grant
to redistribute its source. No license assumption was made for inaccessible
FASM archives or for projects linked by awesome-simd.
