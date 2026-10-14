"""CBAT fixtures: two ELF bodies, shared inputs, explicit output contracts."""
import argparse
from contextlib import nullcontext
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/cbat"
CASES = {"same_signs": (1, "same_signs"), "switch": (2, "process_status"),
         "pointer": (3, "deref"), "debruijn": (4, "rightmost_index_8"),
         "increment": (5, "increment"), "goto_fail": (6, "SSLVerifySignedServerKeyExchange")}
CALLEES = ["ReadyHash", "SSLHashSHA1_update", "SSLHashSHA1_final", "sslRawVerify", "cleanUp", "SSLFreeBuffer"]


def run(command, expected=0, log=None):
    process = subprocess.Popen([str(arg) for arg in command], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        text, _ = process.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        text, _ = process.communicate()
        if log:
            log.write_text(text)
        raise AssertionError(f"tool timed out; see {log}")
    if log:
        log.write_text(text)
    assert process.returncode == expected, f"{command}\nexit {process.returncode}\n{text[-6000:]}"
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asmc", type=Path)
    parser.add_argument("--only", choices=CASES, action="append")
    parser.add_argument("--arch", choices=("x86", "rv32", "rv64"), action="append")
    parser.add_argument("--output-dir", type=Path, help="empty directory to retain ELF, GOTO, commands and logs")
    args = parser.parse_args()
    # SAT encodings of symbolic stack accesses can grow sharply with call bounds.
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    tools = args.asmc.resolve().parent
    arches = args.arch or ["x86", "rv32", "rv64"]
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if any(args.output_dir.iterdir()):
            parser.error("--output-dir must be empty")
    directory = nullcontext(str(args.output_dir.resolve())) if args.output_dir else tempfile.TemporaryDirectory(prefix="asmc-cbat-")
    with directory as temp:
        base = Path(temp)
        for arch in arches:
            compiler = "gcc" if arch == "x86" else "riscv64-unknown-elf-gcc"
            if not shutil.which(compiler):
                print("SKIP " + arch + ": compiler unavailable", flush=True)
                continue
            bits = 32 if arch == "rv32" else 64
            machine_flags = ["-no-pie", "-fcf-protection=none", "-mno-sse", "-mno-sse2"] if arch == "x86" else [
                "-march=" + arch + "imc", "-mabi=" + ("ilp32" if bits == 32 else "lp64")]
            c_flags = ["-I", ROOT / "include", "-I", EXAMPLES]
            if arch != "x86":
                c_flags += [f"-m{bits}", "-funsigned-char", f"-DASMC_RISCV_XLEN={bits}"]
            for name in args.only or CASES:
                case, function = CASES[name]
                if case == 5 and arch != "x86":
                    continue  # This fixture is specifically an x86 instruction reorder.
                optimizations = ("0", "2")
                if case == 5:
                    optimizations = ("0",)
                elif case == 6:
                    optimizations = ("2",)  # Recorded effects survive optimization/inlining.
                for opt in optimizations:

                    def compare(tag, expected=0, mutation=None, record=False, fixed=False):
                        output = base / f"{arch}-{name}-O{opt}-{tag}"
                        output.mkdir()
                        for notice in ("LICENSE", "SOURCES.md"):
                            shutil.copyfile(EXAMPLES / notice, output / notice)
                        commands = []

                        def stage(label, command, code=0):
                            commands.append(shlex.join(str(arg) for arg in command))
                            (output / "commands.txt").write_text("\n".join(commands) + "\n")
                            return run(command, code, output / (label + ".log"))

                        object_mode = case in (3, 6)
                        options = [*c_flags, f"-DCASE={case}"]
                        if object_mode:
                            options += ["-DASMC_OBJECT_MEMORY"]
                        if record:
                            options += ["-DASMC_RECORD_CALLS"]
                        if fixed:
                            options += ["-DASMC_FIXED_SWITCH"]
                        for side in ("original", "patched"):
                            suffix = ".S" if case == 5 else ".c"
                            source = EXAMPLES / f"{name}_{side}{suffix}"
                            if side == "patched" and mutation:
                                changed = output / source.name
                                before, after = mutation
                                text = source.read_text()
                                assert before in text
                                changed.write_text(text.replace(before, after))
                                source = changed
                            stage("compile-" + side, [compiler, *machine_flags, "-O" + opt,
                                  "-fno-stack-protector", "-fno-tree-vectorize", "-fno-builtin", "-I", EXAMPLES,
                                  *(["-DASMC_RECORD_CALLS"] if record else []), "-nostdlib", "-static",
                                  "-Wl,-e," + function, source, "-o", output / (side + ".elf")])
                        stage("seed", [tools / "goto-cc", *options, ROOT / "runtime/runtime.c",
                              EXAMPLES / "entries.c", "-o", output / "seed.gb"])
                        template = output / "seed.gb"
                        for side in ("original", "patched"):
                            model = output / (side + ".gb")
                            lift = [tools / "asmc-lift", output / (side + ".elf"), "--function", function,
                                    "--target", side, "--template", template, "-o", model,
                                    "--memory", "objects" if object_mode else "ram"]
                            if case == 4:
                                lift += ["--rodata"]
                            if case == 6:
                                lift += [item for callee in CALLEES for item in ("--callee", callee)]
                            stage("lift-" + side, lift)
                            stage("roundtrip-" + side, [tools / "goto-instrument", "--validate-goto-model", model,
                                  output / (side + "-roundtrip.gb")])
                            template = model
                        stage("link", [tools / "goto-cc", *options, template, EXAMPLES / "harness.c",
                              "-o", output / "check.gb"])
                        checker = [tools / "cbmc", output / "check.gb", "--function", "harness", "--unwind", "260",
                                   "--unwinding-assertions", "--validate-goto-model", "--trace"]
                        if object_mode:
                            checker += ["--pointer-check"]
                        if case == 6:
                            checker += ["--unwindset", "original.0:10,patched.0:14"]
                        text = stage("cbmc", checker, expected)
                        assert ("VERIFICATION SUCCESSFUL" if expected == 0 else "VERIFICATION FAILED") in text
                        assert not any("unwind" in line and line.endswith("FAILURE") for line in text.splitlines()), text[-4000:]
                        if expected == 10:
                            property_name = "selected call effects agree" if record else (
                                "pointed-to inputs unchanged" if tag == "unexpected_write" else
                                "original and patched declared results agree")
                            assert property_name + ": FAILURE" in text, text[-4000:]
                        print("PASS CBAT " + output.name, flush=True)
                        return text

                    text = compare("pair", 10 if case == 2 else 0)
                    if case == 2:
                        assert "status=0u" in text and "before=0" in text and "after=1" in text
                    if opt == "0" or case == 6:
                        if case == 1:
                            compare("broken", 10, ("!((x ^ y) < 0)", "((x ^ y) < 0)"))
                        elif case == 2:
                            compare("fixed", mutation=("nav = true;", "nav = true;\n      break;"), fixed=True)
                        elif case == 3:
                            compare("wrong_threshold", 10, ("num_2 = 12", "num_2 = 13"))
                            compare("unexpected_write", 10, ("return 0;", "*num_1 = 0;\n    return 0;"))
                        elif case == 4:
                            compare("broken", 10, ("return 7;", "return 6;"))
                        elif case == 5:
                            compare("broken", 10, ("inc     %rdi", "add $2, %rdi"))
                        elif case == 6:
                            text = compare("observed_calls", 10, record=True)
                            assert "selected call effects agree: FAILURE" in text
        if args.output_dir:
            print("Artifacts: " + str(base), flush=True)


if __name__ == "__main__":
    main()
