"""Tutorial contracts, stack separation, aliasing, and frame-condition mutations."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/tutorial"


def run(command, expected=0):
    env = dict(os.environ, CC="cc", CPPFLAGS="", CFLAGS="", LDFLAGS="")
    process = subprocess.run([str(arg) for arg in command], capture_output=True,
                             text=True, timeout=75, env=env)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="asmc-tutorial-") as directory:
        tmp = Path(directory)
        flags = ["gcc", "-O0", "-fno-stack-protector", "-fcf-protection=none",
                 "-nostdlib", "-static", "-no-pie"]
        assembly = tmp / "instructions.elf"
        compiled = tmp / "functions.elf"
        run([*flags, "-Wl,-e,answer", EXAMPLES / "instructions.S", "-o", assembly])
        run([*flags, "-Wl,-e,swap", EXAMPLES / "functions.c", "-o", compiled])

        def check(name, function, options=(), expected=0, contains=None, elf=assembly):
            output = tmp / name
            text = run([asmc, elf, "--function", function, *options, "-o", output,
                        "--timeout", "60", "--memory-limit", "2048"], expected)
            assert (output / "result.txt").read_text().strip() in text, text
            if contains:
                assert contains in text, text
            if expected != 2:
                run([asmc.parent / "goto-instrument", "--validate-goto-model",
                     output / "lifted.gb", output / "roundtrip.gb"])
            print("PASS tutorial " + name, flush=True)
            return text

        check("constant", "answer", ["--post", "outreg.rax == 42"])
        check("constant_wrong", "answer", ["--post", "outreg.rax == 43"], 10, "post:")
        check("increment", "increment", ["--post", "outreg.rax == outreg.rdi + 1"])
        check("increment_wrap", "increment", ["--pre", "inreg.rdi == UINT64_MAX",
                                               "--post", "outreg.rax == 0"])
        check("increment_wrong_snapshot", "increment", ["--post", "outreg.rax == outreg.rdi + 1",
              "--post", "outreg.rax == inreg.rax"], 10, "post: outreg.rax == inreg.rax")
        check("minimum", "minimum", ["--post",
              "outreg.rax == (inreg.rdi < inreg.rsi ? inreg.rdi : inreg.rsi)"])
        check("minimum_not_maximum", "minimum", ["--post",
              "outreg.rax == (inreg.rdi > inreg.rsi ? inreg.rdi : inreg.rsi)"], 10, "post:")
        check("minimum_not_signed", "minimum", ["--pre", "inreg.rdi == UINT64_MAX && inreg.rsi == 0",
              "--post", "(int64_t)outreg.rax == -1"], 10, "post:")
        for mode in ("ram", "objects"):
            load = "asmc_load(&st, inreg.rsp - 8, 8) == 42"
            check("scratch_" + mode, "stack_scratch", ["--memory", mode, "--post", load])
            check("scratch_wrong_snapshot_" + mode, "stack_scratch", ["--memory", mode,
                  "--post", "asmc_load(&st, outreg.rsp - 8, 8) == 42"], 10, "post:")
            check("corrupt_return_" + mode, "corrupt_return", ["--memory", mode], 10,
                  "Return destination: 0x2a (42)")
        check("compiled_add42", "add42", ["--post", "outreg.eax == inreg.edi + 42"], elf=compiled)
        check("compiled_add42_wrap", "add42", ["--pre", "inreg.edi == UINT32_MAX",
              "--post", "outreg.eax == 41 && outreg.rax == 41"], elf=compiled)
        check("compiled_add42_bad64", "add42", ["--pre", "inreg.rdi == UINT32_MAX",
              "--post", "outreg.rax == inreg.rdi + 42"], 10, "post:", elf=compiled)

        check("swap_missing_lower_bound", "swap_spills", ["--pre", "inreg.rdi <= inreg.rsp - 64",
              "--pre", "inreg.rsi <= inreg.rsp - 64"], 10, "memory address below RAM base")
        # Both initial arguments satisfy <= entry RSP - 32. The first store
        # corrupts the saved second pointer, redirecting the next store to RET.
        check("swap_saved_pointer_alias", "swap_spills", ["--pre", "inreg.rdi == inreg.rsp - 40",
              "--pre", "inreg.rsi == st.ram_base",
              "--pre", "asmc_load(&st, inreg.rsi, 4) == inreg.rsp"], 10, "unexpected return address")
        region = ["--pre", "inreg.rdi >= st.ram_base && inreg.rdi <= st.ram_base + 124",
                  "--pre", "inreg.rsi >= st.ram_base && inreg.rsi <= st.ram_base + 124"]
        check("swap_separated_region", "swap_spills", region,
              contains="safety/ABI only, no functional postcondition")
        check("swap_final_equality_is_wrong", "swap_spills", [*region,
              "--post", "asmc_load(&st, inreg.rdi, 4) == asmc_load(&st, inreg.rsi, 4)"], 10, "post:")

        objects = ["--memory", "objects", "--harness", EXAMPLES / "swap_objects.c"]
        array = ["--memory", "objects", "--harness", EXAMPLES / "swap_array.c"]
        for name, options in (("both_alias_cases", objects), ("distinct", [*objects, "-DALIAS_CASE=0"]),
                              ("same_object", [*objects, "-DALIAS_CASE=1"]),
                              ("manual_abi", [*objects, "-DMANUAL_ABI"]), ("array", array)):
            check("swap_" + name, "swap", options, elf=compiled)
        check("swap_bad_distinct", "swap_bad", [*objects, "-DALIAS_CASE=0"], 10,
              "swap second value", compiled)
        check("swap_bad_hidden_by_alias", "swap_bad", [*objects, "-DALIAS_CASE=1"], elf=compiled)
        check("xor_distinct_only", "swap_xor", [*objects, "-DALIAS_CASE=0"], elf=compiled)
        check("xor_same_object", "swap_xor", [*objects, "-DALIAS_CASE=1"], 10, "swap first value", compiled)
        check("xor_both_alias_cases", "swap_xor", objects, 10, "swap first value", compiled)
        check("xor_array", "swap_xor", array, 10, "swap first value", compiled)
        text = check("swap_frame_violation", "swap_extra", [*array, "-DFIXED_INDICES"], 10,
                     "swap unchanged element", compiled)
        assert "swap first value" not in text and "swap second value" not in text, text
        check("objects_harness_in_ram_mode", "swap", ["--harness", EXAMPLES / "swap_objects.c"],
              2, "ERROR:", compiled)


if __name__ == "__main__":
    main()
