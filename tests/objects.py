"""Actual lifted accesses to C objects, bounds/lifetimes, and address-mode isolation."""
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/objects"


def run(command, expected=0):
    process = subprocess.run([str(arg) for arg in command], capture_output=True,
                             text=True, timeout=90)
    text = process.stdout + process.stderr
    assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text}"
    return text


def main():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    asmc = Path(sys.argv[1]).resolve()
    lifter = asmc.with_name("asmc-lift")
    arches = ["x86"]
    if shutil.which("riscv64-unknown-elf-gcc"): arches += ["rv32", "rv64"]
    with tempfile.TemporaryDirectory(prefix="asmc-objects-") as directory:
        tmp = Path(directory)

        def compile(arch, opt):
            elf = tmp / f"functions-{arch}-O{opt}.elf"
            flags = ["-no-pie", "-fcf-protection=none"] if arch == "x86" else [
                "-march=" + arch + "imc", "-mabi=" + ("ilp32" if arch == "rv32" else "lp64")]
            cc = "gcc" if arch == "x86" else "riscv64-unknown-elf-gcc"
            run([cc, *flags, "-O" + opt, "-nostdlib", "-static", "-fno-builtin",
                 "-fno-stack-protector", "-Wl,-e,bump", EXAMPLE / "functions.c", "-o", elf])
            return elf

        def check(elf, function, case, name, expected=0, options=(), harness=EXAMPLE / "harness.c"):
            output = tmp / name
            text = run([asmc, elf, "--function", function, "--harness", harness,
                        "--memory", "objects", "--unwind", "20", "--timeout", "80",
                        "--memory-limit", "2048", "-DCASE=" + str(case),
                        "--output-dir", output, *options], expected)
            assert (output / "result.txt").read_text().startswith("PASS:" if expected == 0 else "FAIL:")
            if expected == 10 and case == 6:
                assert text.count("Trace for ") == 1 and "more failed properties" in text
            commands = (output / "commands.txt").read_text()
            assert "--pointer-check" in commands and "-DASMC_OBJECT_MEMORY" in commands
            run([asmc.parent / "goto-instrument", "--validate-goto-model", output / "lifted.gb", output / "roundtrip.gb"])
            print("PASS " + name, flush=True)
            return text

        for arch in arches:
            for opt in ("0", "2"):
                elf = compile(arch, opt)
                check(elf, "relay", 1, f"{arch}-O{opt}-spilled-pointer-call",
                      options=["--callee", "bump", "--unwindset", "asmc_target.0:4"])
            elf = compile(arch, "0")
            check(elf, "combine", 2, arch + "-alias")
            check(elf, "next_word", 3, arch + "-pointer-result")
            check(elf, "bump", 9, arch + "-C-global-argument")
            check(elf, "bump", 1, arch + "-object-bits", options=["--object-bits", "12"])
            check(elf, "bump", 5, arch + "-allocation-too-small", 10)
            check(elf, "bump", 6, arch + "-use-after-free", 10)
            check(elf, "bump", 7, arch + "-null", 10)
            check(elf, "bump", 8, arch + "-cross-object-edge", 10)
            check(elf, "bump", 1, arch + "-stack-too-small", 10, ["-DSTACK_SIZE=16"])
            check(elf, "copy_bytes", 4, arch + "-copy")

        # A fixed ELF read must fail in object mode, even though the ELF contains
        # the bytes. Code addresses remain numeric; data has no ELF fallback.
        elf = tmp / "fixed.elf"
        source = tmp / "fixed.S"
        source.write_text('''.text
.globl fixed
.type fixed,@function
fixed:
  mov constant(%rip),%eax
  ret
.size fixed,.-fixed
.globl truncated
.type truncated,@function
truncated:
  mov %edi,%edi
  lea constant(%rip),%rax
  add %rax,%rdi
  mov (%rdi),%eax
  ret
.size truncated,.-truncated
.globl fixed_write
.type fixed_write,@function
fixed_write:
  movl $0,constant(%rip)
  ret
.size fixed_write,.-fixed_write
.section .rodata
constant: .long 42
.section .note.GNU-stack,"",@progbits
''')
        run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,fixed", source, "-o", elf])
        text = check(elf, "fixed", 1, "fixed-ELF-no-fallback", 10)
        assert "invalid CBMC object read" in text and "Machine: 0x" in text
        assert "Fixed ELF data addresses are not mapped" in text
        assert "invalid CBMC object read" in check(elf, "truncated", 1, "truncated-no-fallback", 10)
        assert "invalid CBMC object write" in check(elf, "fixed_write", 1, "fixed-write-no-fallback", 10)
        for objects in (False, True):
            seed = tmp / ("object-seed.gb" if objects else "ram-seed.gb")
            run([asmc.parent / "goto-cc", "-I", ROOT / "include", "-c", ROOT / "runtime/runtime.c",
                 *(["-DASMC_OBJECT_MEMORY"] if objects else []), "-o", seed])
            text = run([lifter, elf, "--function", "fixed", "--template", seed, "-o", tmp / "mismatch.gb",
                        "--memory", "ram" if objects else "objects"], 2)
            assert "template runtime memory mode differs" in text and not (tmp / "mismatch.gb").exists()
        print("PASS mismatched runtime templates rejected", flush=True)
        text = run([asmc, elf, "--function", "fixed", "--harness", EXAMPLE / "harness.c",
                    "--memory", "objects", "--rodata"], 2)
        assert "cannot be combined" in text
        text = run([lifter, elf, "--function", "fixed", "--template", tmp / "unused.gb",
                    "-o", tmp / "unused-out.gb", "--memory", "objects", "--rodata"], 2)
        assert "cannot be combined" in text and not (tmp / "unused-out.gb").exists()
        print("PASS incompatible address schemes rejected by both CLIs", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
