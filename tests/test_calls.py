"""Shared native call graphs, return sites, tail calls, and bounded recursion."""

import re
import pytest
from support import ROOT, bounded_run as run, roundtrip

pytestmark = pytest.mark.slow
EXAMPLE = ROOT / "examples/calls"


@pytest.fixture(scope="session", params=["0", "2"], ids=["O0", "O2"])
def calls_elf(request, machine, tmp_path_factory):
    compiler, flags, _ = machine
    elf = tmp_path_factory.mktemp("calls") / "functions.elf"
    run(
        [
            compiler,
            *flags,
            "-O" + request.param,
            "-fno-stack-protector",
            "-fno-inline",
            "-fno-optimize-sibling-calls",
            "-nostdlib",
            "-static",
            "-Wl,-e,nested",
            EXAMPLE / "functions.c",
            "-o",
            elf,
        ]
    )
    return elf


@pytest.mark.parametrize(
    "case,function,callees",
    [
        (1, "nested", ["middle", "leaf"]),
        (2, "repeated", ["leaf"]),
        (3, "recursive", []),
        (5, "mutual_even", ["mutual_odd"]),
    ],
    ids=["nested", "repeated-return-sites", "recursive", "mutual-recursion"],
)
def test_native_calls(asmc, calls_elf, tmp_path, case, function, callees):
    output = tmp_path / "check"
    options = [arg for callee in callees for arg in ("--callee", callee)]
    text = run(
        [
            asmc,
            calls_elf,
            "--function",
            function,
            "--harness",
            EXAMPLE / "spec.c",
            f"-DCASE={case}",
            "--unwind",
            "18",
            "--unwindset",
            "asmc_target.0:7",
            "--timeout",
            "45",
            "--output-dir",
            output,
            *options,
        ]
    )
    assert "PASS: all checked properties" in text
    roundtrip(asmc, output)


def test_unadmitted_nested_callee(lifter, machine_seed, calls_elf, tmp_path):
    output = tmp_path / "unadmitted.gb"
    text = run(
        [
            lifter,
            calls_elf,
            "--function",
            "nested",
            "--callee",
            "middle",
            "--template",
            machine_seed,
            "-o",
            output,
        ],
        2,
    )
    assert "CALL" in text and "--callee" in text and not output.exists()


def test_recursive_bound_is_incomplete(asmc, lifter, calls_elf, machine_seed, tmp_path):
    model = tmp_path / "recursive.gb"
    run([lifter, calls_elf, "--function", "recursive", "--template", machine_seed, "-o", model])
    listing = run([asmc.parent / "goto-instrument", "--show-loops", model])
    ids = re.findall(r"Loop (asmc_target\.\d+):", listing)
    assert ids == ["asmc_target.0"], listing
    text = run(
        [
            asmc,
            calls_elf,
            "--function",
            "recursive",
            "--harness",
            EXAMPLE / "spec.c",
            "-DCASE=3",
            "--unwind",
            "18",
            "--unwindset",
            ",".join(name + ":1" for name in ids),
            "--output-dir",
            tmp_path / "check",
        ],
        11,
    )
    assert "INCOMPLETE:" in text and "PASS:" not in text


def test_tail_call(asmc, machine, tmp_path):
    compiler, flags, _ = machine
    elf = tmp_path / "tail.elf"
    run(
        [
            compiler,
            *flags,
            "-O2",
            "-fno-stack-protector",
            "-nostdlib",
            "-static",
            "-Wl,-e,tail",
            EXAMPLE / "functions.c",
            "-o",
            elf,
        ]
    )
    text = run(
        [
            asmc,
            elf,
            "--function",
            "tail",
            "--callee",
            "leaf",
            "--harness",
            EXAMPLE / "spec.c",
            "-DCASE=4",
            "--unwind",
            "18",
            "--output-dir",
            tmp_path / "check",
        ]
    )
    assert "PASS:" in text


@pytest.mark.parametrize(
    "body,diagnostic",
    [
        ("mov %edi,%eax\nadd $2,%eax\nret", "FAIL:"),
        ("xor %ebx,%ebx\nmov %edi,%eax\nadd $1,%eax\nret", "FAIL:"),
        ("movq $0,(%rsp)\nret", "unexpected return address"),
    ],
    ids=["wrong-result", "clobbered-register", "corrupted-return"],
)
def test_called_function_mutant(asmc, tmp_path, body, diagnostic):
    source, elf = tmp_path / "bad.S", tmp_path / "bad.elf"
    source.write_text(
        ".text\n.globl entry,helper\n.type entry,@function\nentry:\ncall helper\nret\n.size entry,.-entry\n"
        ".type helper,@function\nhelper:\n"
        + body
        + '\n.size helper,.-helper\n.section .note.GNU-stack,"",@progbits\n'
    )
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,entry", source, "-o", elf])
    text = run(
        [
            asmc,
            elf,
            "--function",
            "entry",
            "--callee",
            "helper",
            "--harness",
            EXAMPLE / "spec.c",
            "-DCASE=4",
            "--unwind",
            "18",
            "--unwindset",
            "asmc_target.0:3",
            "-o",
            tmp_path / "check",
        ],
        10,
    )
    assert "FAIL:" in text and diagnostic in text
