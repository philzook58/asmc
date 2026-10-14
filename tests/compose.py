"""Named lifts, independent GOTO objects, and ordinary C-to-assembly wrappers."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/compose"


def run(command, expected=0):
    result = subprocess.run([str(arg) for arg in command], capture_output=True,
                            text=True, timeout=120)
    text = result.stdout + result.stderr
    assert result.returncode == expected, f"{command}\nexit {result.returncode}\n{text}"
    return text


def main():
    asmc = Path(sys.argv[1]).resolve()
    lifter = asmc.with_name("asmc-lift")
    cc, cbmc = asmc.parent / "goto-cc", asmc.parent / "cbmc"
    with tempfile.TemporaryDirectory(prefix="asmc-compose-") as temp:
        tmp = Path(temp)
        elf = tmp / "functions.elf"
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,machine_add_one", EXAMPLE / "functions.S", "-o", elf])
        seed = tmp / "seed.gb"
        run([cc, "-I", ROOT / "include", ROOT / "runtime/runtime.c", EXAMPLE / "entries.c", "-o", seed])

        def lift(source, function, target, template, output, expected=0):
            return run([lifter, source, "--function", function, "--target", target,
                        "--template", template, "-o", output], expected)

        def verify(objects, name, expected=0):
            linked = tmp / (name + ".gb")
            run([cc, "-I", ROOT / "include", *objects, EXAMPLE / "wrappers.c",
                 EXAMPLE / "harness.c", "-o", linked])
            text = run([cbmc, linked, "--function", "harness", "--unwind", "40",
                        "--unwinding-assertions", "--validate-goto-model", "--trace"], expected)
            assert ("VERIFICATION SUCCESSFUL" if expected == 0 else "VERIFICATION FAILED") in text
            print("PASS " + name, flush=True)

        add = tmp / "add.gb"
        both = tmp / "both.gb"
        lift(elf, "machine_add_one", "lifted_add_one", seed, add)
        lift(elf, "machine_sum", "lifted_sum", add, both)
        verify([both], "sequential-lifts")

        # Separate objects contain only their own stub; link the common runtime once.
        objects = []
        for function, target in [("machine_add_one", "lifted_add_one"), ("machine_sum", "lifted_sum")]:
            source = tmp / (target + ".c")
            source.write_text('#include "asmc_state.h"\nvoid ' + target +
                              '(struct asmc_state *s) { (void)s; }\n')
            stub, obj = tmp / (target + "-seed.gb"), tmp / (target + ".gb")
            run([cc, "-I", ROOT / "include", "-c", source, "-o", stub])
            lift(elf, function, target, stub, obj)
            objects.append(obj)
        verify([*objects, ROOT / "runtime/runtime.c"], "independent-objects")

        text = run([asmc, elf, "--function", "machine_add_one", "--target", "lifted_add_one",
                    "--harness", EXAMPLE / "single.c", "--reference", EXAMPLE / "wrappers.c",
                    "--output-dir", tmp / "named-check"])
        assert "PASS: all checked properties" in text
        print("PASS named-check wrapper", flush=True)

        for name, before, after in [("wrong-result", "lea 1", "lea 2"),
                                    ("wrong-memory-stride", "add $4", "add $8"),
                                    ("wrong-memory-effect", "add (%rdi),%eax",
                                     "add (%rdi),%eax\n  movl $0,(%rdi)")]:
            source, bad_elf = tmp / (name + ".S"), tmp / (name + ".elf")
            source.write_text((EXAMPLE / "functions.S").read_text().replace(before, after))
            run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,machine_add_one", source, "-o", bad_elf])
            first, second = tmp / (name + "-add.gb"), tmp / (name + "-both.gb")
            lift(bad_elf, "machine_add_one", "lifted_add_one", seed, first)
            lift(bad_elf, "machine_sum", "lifted_sum", first, second)
            verify([second], name, 10)

        text = lift(elf, "machine_add_one", "missing", seed, tmp / "missing.gb", 2)
        assert "template must define void missing" in text and not (tmp / "missing.gb").exists()
        bad_source = tmp / "bad-signature.c"
        bad_source.write_text("int lifted_add_one(int x) { return x; }\n")
        bad_seed = tmp / "bad-seed.gb"
        run([cc, "-c", bad_source, "-o", bad_seed])
        text = lift(elf, "machine_add_one", "lifted_add_one", bad_seed, tmp / "bad.gb", 2)
        assert "incompatible lifted_add_one signature" in text and not (tmp / "bad.gb").exists()
        print("PASS rejects missing target and incompatible signature", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
