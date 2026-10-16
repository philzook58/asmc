# ASMC - Assembly Model Checker

Converts [Ghidra](https://github.com/nationalsecurityagency/ghidra) P-Code directly to [CBMC](https://github.com/diffblue/cbmc) GOTO IR.

CBMC is a powerful model checking system.

P-Code supports many architectures out of the box. The tool has currently been tested with x86-64, RV32, and RV64.

This is useful for both verification about standalone assembly but also assembly in relation to C code (Translation validation or linking C code to external assembly routines)

This project is similar to [pcode2c](https://github.com/philzook58/pcode2c) in many ways but removes the intermediary of printing C code. This has advantages and disadvantages.

Related Blog posts:

- [PCode2C: Steps Towards Translation Validation with Ghidra and CBMC](https://www.philipzucker.com/pcode2c/)
- [DWARF Verification via Ghidra and CBMC](https://www.philipzucker.com/pcode2c-dwarf/)
- <https://www.philipzucker.com/refine_assembly/>
- <https://www.philipzucker.com/asm_verify4/>
- <https://www.philipzucker.com/asm_verify3/>
- <https://www.philipzucker.com/asm_verify2/>
- <https://www.philipzucker.com/assembly_verify/>

My thanks to the makers of Ghidra, CBMC, Trail of Bits SLEIGH Build, and ELFIO.

The tool inserts checks abi compliance and can be used in `--memory objects` mode to use CBMC's memory model.

# Usage

Contains both the translator `asmc-lift` to convert `.elf` files to `.gb` and also a driver program `asmc`. `asmc` has some convenience modes.

A simple example:

Save this as `/tmp/mov42.s`

```
.text
.globl myfun
myfun:
    mov $42, %rax
    ret
```

```sh
./build/bin/asmc /tmp/mov42.s --function myfun --post 'outreg.rax == 42'
```

Generally speaking, the tool requires a C harness to be written to setup more complicated state, preconditions or postconditions. Look in the `examples/` directory for more.

# Building

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target asmc-tools -j2
```

# AI Disclosure

This was produced using an agent using my notes and directions.
