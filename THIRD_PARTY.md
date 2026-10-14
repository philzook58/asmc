# Dependencies

* [CBMC](https://github.com/diffblue/cbmc): downloaded by CMake, with its
  license retained in the fetched source directory.
* [lifting-bits/SLEIGH](https://github.com/lifting-bits/sleigh) and
  [Ghidra](https://github.com/NationalSecurityAgency/ghidra): downloaded by
  CMake, with their upstream license files retained.
* [ELFIO](https://github.com/serge1/ELFIO): headers vendored at commit
  ebe6e819789720a84ebb17700681089a5d93e6eb. Its MIT license is in
  vendor/elfio/LICENSE.txt; headers preserve their copyright notices.
* [s2n-bignum](https://github.com/awslabs/s2n-bignum): two unmodified test
  routines and headers from commit 4d1356a7470663c752660a59375dc3a9ef548428,
  with its license retained in tests/s2n-bignum/LICENSE.
* Additional licensed test fixtures from ACSL by Example, AWS C Common,
  and simdjson are recorded in
  [examples/exploration/SOURCES.md](examples/exploration/SOURCES.md), with pinned
  source links, authors, adaptation notes, and license/NOTICE files alongside
  each fixture.
* [CBAT](https://github.com/draperlaboratory/cbat_tools): adapted MIT-licensed
  comparison fixtures, with provenance in
  [examples/cbat/SOURCES.md](examples/cbat/SOURCES.md) and the license retained
  in examples/cbat/LICENSE.

CBMC and SLEIGH revisions are CMake cache defaults. SLEIGH records the Ghidra
version and patches it uses in its own dependency setup.
