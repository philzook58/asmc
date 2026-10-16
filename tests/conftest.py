import shutil
import sys

import pytest

from support import ROOT, run


def pytest_collection_modifyitems(items):
    for item in items:
        if not item.get_closest_marker("fast") and not item.get_closest_marker("slow"):
            item.add_marker(pytest.mark.slow)


@pytest.fixture(scope="session")
def asmc(pytestconfig, tmp_path_factory):
    binary = pytestconfig.getoption("--build-dir").resolve() / "bin/asmc"
    if not binary.is_file():
        pytest.fail(f"Missing {binary}; build the asmc-tools target first")
    if pytestconfig.getoption("--scalar-registers"):
        return scalar_tools(binary, tmp_path_factory.mktemp("scalar-tools"))
    return binary


def scalar_tools(binary, directory):
    tools = directory / "bin"
    tools.mkdir()
    for name in ("asmc", "goto-cc", "asmc-lift", "cbmc", "goto-instrument"):
        path = tools / name
        if name in ("asmc", "goto-cc"):
            flags = ["--scalar-registers"] if name == "asmc" else ["-DASMC_SCALAR_REGISTERS"]
            solver = ["--z3"]
            local_solver = ROOT / ".venv/bin/z3"
            if local_solver.is_file():
                solver += ["--solver-path", str(local_solver)]
            path.write_text(
                f"#!{sys.executable}\nimport os, sys\n"
                f"extra = {flags!r}\n"
                "objects = '--memory' in sys.argv and sys.argv[sys.argv.index('--memory') + 1] == 'objects'\n"
                "if objects and not any(x in sys.argv for x in ('--beautify', '--z3', '--cvc5', '--bitwuzla', '--external-sat-solver')):\n"
                f"    extra += {solver if name == 'asmc' else []!r}\n"
                f"os.execv({str(binary.with_name(name))!r}, [{name!r}, *sys.argv[1:], *extra])\n"
            )
            path.chmod(0o755)
        else:
            path.symlink_to(binary.with_name(name))
    return tools / "asmc"


@pytest.fixture(scope="session")
def scalar_asmc(asmc, pytestconfig, tmp_path_factory):
    if pytestconfig.getoption("--scalar-registers"):
        return asmc
    return scalar_tools(asmc, tmp_path_factory.mktemp("scalar-tools"))


@pytest.fixture(scope="session")
def lifter(asmc):
    return asmc.with_name("asmc-lift")


@pytest.fixture(scope="session")
def seed(asmc, tmp_path_factory):
    model = tmp_path_factory.mktemp("runtime") / "seed.gb"
    run(
        [
            asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            "-c",
            ROOT / "runtime/runtime.c",
            "-o",
            model,
        ]
    )
    return model


@pytest.fixture(scope="session")
def machine(architecture):
    if architecture == "x86":
        return "gcc", ["-no-pie", "-fcf-protection=none"], []
    bits = int(architecture[2:])
    return (
        "riscv64-unknown-elf-gcc",
        [f"-march=rv{bits}imc", "-mabi=" + ("ilp32" if bits == 32 else "lp64")],
        [f"-m{bits}", "-funsigned-char", f"-DASMC_RISCV_XLEN={bits}"],
    )


@pytest.fixture(scope="session")
def machine_seed(asmc, machine, tmp_path_factory):
    model = tmp_path_factory.mktemp("machine-runtime") / "seed.gb"
    run(
        [
            asmc.parent / "goto-cc",
            "-I",
            ROOT / "include",
            *machine[2],
            "-c",
            ROOT / "runtime/runtime.c",
            "-o",
            model,
        ]
    )
    return model


@pytest.fixture(scope="session")
def x86_elf(tmp_path_factory):
    elf = tmp_path_factory.mktemp("elf") / "functions with spaces.elf"
    run(["gcc", "-nostdlib", "-no-pie", "-Wl,-e,inc", ROOT / "tests/challenges.S", "-o", elf])
    return elf


@pytest.fixture(scope="session", params=("x86", "rv32", "rv64"))
def architecture(request):
    if request.param != "x86" and not shutil.which("riscv64-unknown-elf-gcc"):
        pytest.skip("riscv64-unknown-elf-gcc is not installed")
    return request.param


@pytest.fixture(scope="session")
def instructions(architecture, x86_elf, tmp_path_factory):
    if architecture == "x86":
        return x86_elf
    bits = int(architecture[2:])
    elf = tmp_path_factory.mktemp(architecture) / "instructions.elf"
    run(
        [
            "riscv64-unknown-elf-gcc",
            f"-march=rv{bits}imc",
            "-mabi=" + ("ilp32" if bits == 32 else "lp64"),
            "-nostdlib",
            "-static",
            "-Wl,--no-relax,-e,zero_test",
            ROOT / "examples/riscv/instructions.S",
            "-o",
            elf,
        ]
    )
    return elf


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed and "tmp_path" in item.funcargs:
        report.sections.append(("Test artifacts", str(item.funcargs["tmp_path"])))
