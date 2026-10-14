"""Native call stacks, repeated return sites, tail calls and bounded recursion."""
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/calls"


def run(command, expected=0):
    result = subprocess.run([str(arg) for arg in command], capture_output=True,
                            text=True, timeout=120)
    text = result.stdout + result.stderr
    assert result.returncode == expected, f"{command}\nexit {result.returncode}\n{text}"
    return text


def main():
    # Keep a regression in the shared call CFG from exhausting the host.
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    asmc = Path(sys.argv[1]).resolve()
    lifter = asmc.with_name("asmc-lift")
    with tempfile.TemporaryDirectory(prefix="asmc-calls-") as temp:
        tmp = Path(temp)
        for arch, compiler, flags in [
            ("x86", "gcc", ["-no-pie", "-fcf-protection=none"]),
            ("rv32", "riscv64-unknown-elf-gcc", ["-march=rv32imc", "-mabi=ilp32"]),
            ("rv64", "riscv64-unknown-elf-gcc", ["-march=rv64imc", "-mabi=lp64"]),
        ]:
            if not shutil.which(compiler):
                continue
            for opt in ("0", "2"):
                tag = arch + "-O" + opt
                elf = tmp / (tag + ".elf")
                run([compiler, *flags, "-O" + opt, "-fno-stack-protector", "-fno-inline",
                     "-fno-optimize-sibling-calls", "-nostdlib", "-static", "-Wl,-e,nested",
                     EXAMPLE / "functions.c", "-o", elf])
                for case, function, callees in [
                    (1, "nested", ["middle", "leaf"]),
                    (2, "repeated", ["leaf"]),
                    (3, "recursive", []),
                    (5, "mutual_even", ["mutual_odd"]),
                ]:
                    output = tmp / (tag + "-" + function)
                    options = [item for callee in callees for item in ("--callee", callee)]
                    text = run([asmc, elf, "--function", function, "--harness", EXAMPLE / "spec.c",
                                "-DCASE=" + str(case), "--unwind", "18", "--unwindset", "asmc_target.0:7", "--timeout", "45",
                                "--output-dir", output, *options])
                    assert "PASS: all checked properties" in text
                    run([asmc.parent / "goto-instrument", "--validate-goto-model", output / "lifted.gb",
                         output / "roundtrip.gb"])
                    print("PASS " + tag + " " + function, flush=True)

                # Admitting middle alone cannot make its unadmitted leaf call disappear.
                text = run([lifter, elf, "--function", "nested", "--callee", "middle",
                            "--template", output / "seed.gb", "-o", tmp / "unadmitted.gb"], 2)
                assert "CALL" in text and "--callee" in text and not (tmp / "unadmitted.gb").exists()
                print("PASS rejects unadmitted callee " + tag, flush=True)

                # Discover the CFG loop IDs rather than assuming their numbering.
                output = tmp / (tag + "-recursive")
                loops = run([asmc.parent / "cbmc", output / "check.gb", "--function", "harness", "--show-loops"])
                ids = re.findall(r"Loop (asmc_target\.\d+):", loops)
                assert ids == ["asmc_target.0"], loops
                small = tmp / (tag + "-incomplete")
                text = run([asmc, elf, "--function", "recursive", "--harness", EXAMPLE / "spec.c",
                            "-DCASE=3", "--unwind", "18", "--unwindset", ",".join(name + ":1" for name in ids),
                            "--output-dir", small], 11)
                assert "INCOMPLETE:" in text and "PASS:" not in text
                print("PASS recursive insufficient bound " + tag, flush=True)

            # Permit the compiler's usual tail-call optimization here.
            elf = tmp / (arch + "-tail.elf")
            run([compiler, *flags, "-O2", "-fno-stack-protector", "-nostdlib", "-static",
                 "-Wl,-e,tail", EXAMPLE / "functions.c", "-o", elf])
            text = run([asmc, elf, "--function", "tail", "--callee", "leaf",
                        "--harness", EXAMPLE / "spec.c", "-DCASE=4", "--unwind", "18",
                        "--output-dir", tmp / (arch + "-tail")])
            assert "PASS:" in text
            print("PASS " + arch + " tail call", flush=True)

        for name, body in [
            ("bad_result", "mov %edi,%eax\nadd $2,%eax\nret"),
            ("clobber_saved", "xor %ebx,%ebx\nmov %edi,%eax\nadd $1,%eax\nret"),
            ("corrupt_return", "movq $0,(%rsp)\nret"),
        ]:
            source = tmp / (name + ".S")
            source.write_text(".text\n.globl entry,helper\n.type entry,@function\n"
                              "entry:\ncall helper\nret\n.size entry,.-entry\n"
                              ".type helper,@function\nhelper:\n" + body +
                              '\n.size helper,.-helper\n.section .note.GNU-stack,"",@progbits\n')
            elf = tmp / (name + ".elf")
            run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,entry", source, "-o", elf])
            text = run([asmc, elf, "--function", "entry", "--callee", "helper",
                        "--harness", EXAMPLE / "spec.c", "-DCASE=4", "--unwind", "18",
                        "--unwindset", "asmc_target.0:3", "--output-dir", tmp / name], 10)
            assert "FAIL:" in text
            if name == "corrupt_return":
                assert "unexpected return address" in text
            print("PASS rejects " + name, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
