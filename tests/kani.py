"""Optional Rust/Kani <-> lifted native code checks, including failing controls."""
import os
from pathlib import Path
import resource
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/kani"


def main():
    asmc = Path(sys.argv[1]).resolve()
    kani, rustc = shutil.which("kani"), shutil.which("rustc")
    if not kani or not rustc or os.uname().machine != "x86_64":
        print("SKIP: Kani, rustc and an x86-64 host are required")
        return 77
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    with tempfile.TemporaryDirectory(prefix="asmc-kani-") as directory:
        tmp = output or Path(directory)
        if output:
            output.mkdir(parents=True, exist_ok=True)
            assert not any(output.iterdir()), "output directory must be empty"

        def run(stage, command, expected=0):
            command = [str(arg) for arg in command]
            with (tmp / "commands.txt").open("a") as stream:
                stream.write(shlex.join(command) + "\n")
            process = subprocess.run(command, capture_output=True, text=True, timeout=90)
            text = process.stdout + process.stderr
            (tmp / (stage + ".log")).write_text(text)
            assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text}"
            return text

        print(run("kani-version", [kani, "--version"]).strip(), flush=True)
        print(run("rustc-version", [rustc, "--version"]).strip(), flush=True)
        # Copy first: Kani's retained artifacts must not be written in examples/.
        source = tmp / "equivalence.rs"
        shutil.copyfile(EXAMPLES / "equivalence.rs", source)
        native_object, native_elf = tmp / "native.o", tmp / "native.elf"
        run("rustc", [rustc, "--edition", "2021", "--crate-type", "lib", "--emit", "obj",
                      "-C", "opt-level=1", "-C", "panic=abort", source, "-o", native_object])
        run("native-link", ["cc", "-nostdlib", "-static", "-no-pie", "-Wl,-e,add_one",
                            native_object, "-o", native_elf])
        assembly = tmp / "increment.elf"
        run("assembly-link", ["cc", "-nostdlib", "-static", "-no-pie", "-Wl,-e,inc",
                              ROOT / "examples/inc.S", "-o", assembly])
        cc, instrument = asmc.parent / "goto-cc", asmc.parent / "goto-instrument"
        c_options = ["-I", ROOT / "include", "-DASMC_OBJECT_MEMORY"]
        seed = tmp / "seed.gb"
        run("seed", [cc, *c_options, "-c", ROOT / "runtime/runtime.c", "-o", seed])
        cases = [
            ("hand_assembly", assembly, "inc", "scalar_equivalence", 0),
            ("compiled_rust", native_elf, "add_one", "scalar_equivalence", 0),
            ("wrong_increment", native_elf, "add_two", "scalar_equivalence", 1),
            ("rust_pointer_swap", native_elf, "swap_words", "swap_equivalence", 0),
            ("aliasing_swap_mutant", native_elf, "swap_xor", "swap_equivalence", 1),
        ]
        for name, elf, function, harness, expected in cases:
            lifted, bridge = tmp / (name + ".gb"), tmp / (name + "-bridge.gb")
            run(name + "-lift", [asmc, elf, "--function", function, "--template", seed,
                                  "--memory", "objects", "-o", lifted])
            run(name + "-validate", [instrument, "--validate-goto-model", lifted,
                                      tmp / (name + "-roundtrip.gb")])
            defines = ["-DSWAP"] if harness == "swap_equivalence" else []
            run(name + "-bridge", [cc, *c_options, *defines, lifted, EXAMPLES / "bridge.c", "-o", bridge])
            text = run(name + "-kani", [kani, source, "-Z", "c-ffi", "--c-lib", bridge,
                       "--harness", "proofs::" + harness, "--keep-temps", "--unwind", "40",
                       "--output-format", "terse"], expected)
            status = "FAILED" if expected else "SUCCESSFUL"
            assert "VERIFICATION:- " + status in text, text
            if expected:
                assert "Failed Checks: assertion failed:" in text and "in proofs::" + harness in text, text
            print("PASS Kani " + name + (" (expected counterexample)" if expected else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
