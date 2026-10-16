# Rust harnesses and compiled Rust equivalence

Kani and ASMC both produce CBMC GOTO models. A small C ABI bridge lets a Rust
harness call a lifted machine-code function, without exposing `asmc_state` or
its register layout to Rust.

Tested with Kani 0.68.0 (bundled CBMC 6.11.0), ASMC's CBMC 6.11.0, and native
rustc 1.98.0. Kani selects its own compiler, rustc 1.100.0-nightly from
nightly-2026-08-21. The same Rust source is given to the native compiler and Kani;
this checks these concrete compilations, not arbitrary Rust compiler versions.
The native ABI in these examples is x86-64 SysV with `extern "C"` exports.

Install Kani using its [official instructions](https://model-checking.github.io/kani/install-guide.html):

```sh
cargo install --locked kani-verifier
cargo kani setup
```

Run the smoke tests:

```sh
python3 -m pytest tests/test_kani.py --build-dir build -q
# Or retain logs, native ELF, lifted models, and linking commands in an empty directory:
python3 -m pytest tests/test_kani.py --build-dir build --basetemp build/kani-demo -o tmp_path_retention_policy=all
```

The CTest test skips if Kani/rustc are absent or the host is not x86-64. Kani is
an optional testing dependency; normal ASMC usage does not require it. Compatible
GOTO readers/linkers are needed: both toolchains above use CBMC 6.11.0.

| Case | Result |
|---|---|
| Rust harness calls `examples/inc.S` | Pass for all u64 inputs |
| Rust `add_one` compiled to native ELF vs its Kani source model | Pass, including wraparound |
| Compiled `add_two` linked in place of `add_one` | Expected Rust assertion failure |
| Compiled Rust `swap_words` vs its Kani source model | Pass for all u32 values, distinct and aliased pointers |
| Compiled Rust XOR swap vs ordinary swap | Expected Rust assertion failure on aliased pointers |

The `swap_equivalence` harness uses raw pointers rather than simultaneous
aliased `&mut` references. It makes separate initial copies for the reference
and machine executions and compares both objects afterward. A nondeterministic
boolean selects whether the two arguments are the same pointer.

## How the pieces connect

1. Native `rustc --emit obj -C opt-level=1 -C panic=abort` compiles `equivalence.rs`.
   Its exported functions are linked into a static non-PIE ELF.
2. ASMC lifts the selected native function into `asmc_target`, using a runtime
   template compiled with `ASMC_OBJECT_MEMORY`.
3. `goto-cc` links `bridge.c` and the lifted GOTO object. The bridge sets argument
   registers, runs the target, and checks scalar ABI preservation. Pointer
   arguments carry CBMC's object-pointer encoding, so stores modify Rust objects.
4. Kani compiles the Rust proof harness and reference function. Its experimental
   C-FFI path links our GOTO object using `-Z c-ffi --c-lib FILE.gb`.
5. Kani runs its normal CBMC checks on the combined model. The assertions are
   Rust assertions in the Rust harness, not reconstructed C specifications.

After the retained-output command above, this reruns the scalar equivalence:

```sh
kani build/kani-demo/equivalence.rs -Z c-ffi \
  --c-lib build/kani-demo/compiled_rust-bridge.gb \
  --harness proofs::scalar_equivalence --keep-temps --unwind 40 --output-format terse
```

`machine_swap` returns a u32 zero status from the bridge. In the tested Kani
version, declaring it as returning Rust `()` conflicts at GOTO linking with C
`void` (Rust's generated unit struct versus void). The scalar status keeps that
FFI boundary compatible; the lifted swap itself still has no return-value contract.

These are bounded checks with unwinding assertions. This smoke test does not add
Rust input handling to the `asmc` driver, import a native Rust runtime, or claim
support for arbitrary Rust ABI layouts. Ordinary Rust functions used as source
references remain Kani's responsibility; native callees and instructions remain
subject to ASMC's admitted ranges and supported p-code operations.
