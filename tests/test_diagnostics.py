"""Captured checker output should be interpreted without running the toolchain."""

import importlib.util
import sys
from pathlib import Path

import pytest

from support import ROOT

pytestmark = pytest.mark.fast


@pytest.fixture(scope="module")
def driver():
    # The executable normally adds tools/ to its module search path.
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec = importlib.util.spec_from_file_location("asmc_driver", ROOT / "tools/driver.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


@pytest.mark.parametrize(
    "code,text,expected",
    [
        (0, "VERIFICATION SUCCESSFUL\n", "PASS"),
        (10, "[harness.assertion.1] assertion x == y: FAILURE\nVERIFICATION FAILED\n", "FAIL"),
        (
            10,
            "[foo.unwind.0] unwinding assertion loop 0: FAILURE\nVERIFICATION FAILED\n",
            "INCOMPLETE",
        ),
        (
            10,
            "[foo.recursion] recursion unwinding assertion: FAILURE\nVERIFICATION FAILED\n",
            "INCOMPLETE",
        ),
        (
            10,
            "[foo.unwind.0] unwinding assertion loop 0: FAILURE\n"
            "[harness.assertion.1] assertion x == y: FAILURE\nVERIFICATION FAILED\n",
            "FAIL",
        ),
        (
            10,
            "[harness.assertion.1] assertion unwinding assertion: FAILURE\nVERIFICATION FAILED\n",
            "FAIL",
        ),
        (6, "SAT checker ran out of memory\n", "MEMORY"),
        (0, "", "ERROR"),
        (0, "VERIFICATION SUCC", "ERROR"),
        (0, "solver returned unknown\n", "ERROR"),
        (0, "[harness.assertion.1] assertion false: FAILURE\nVERIFICATION SUCCESSFUL\n", "ERROR"),
        (10, "[harness.assertion.1] assertion false: FAILURE\n", "ERROR"),
        (10, "VERIFICATION FAILED\n", "ERROR"),
        (
            10,
            "[harness.assertion.1] assertion false: FAILURE\nState contains VERIFICATION FAILED\n",
            "ERROR",
        ),
        (1, "VERIFICATION SUCCESSFUL\n", "ERROR"),
        (6, "solver returned unknown\n", "ERROR"),
    ],
    ids=[
        "pass",
        "assertion",
        "unwind",
        "recursion",
        "mixed",
        "misleading-description",
        "memory",
        "empty",
        "truncated",
        "unknown",
        "contradictory",
        "missing-footer",
        "missing-properties",
        "footer-in-user-text",
        "wrong-exit",
        "other-solver-error",
    ],
)
def test_checker_result(driver, code, text, expected):
    status, failures = driver.checker_result(code, text)
    assert status == expected
    assert len(failures) == text.count(": FAILURE")


def test_trace_filters_helpers_and_deduplicates_instructions(driver, tmp_path, capsys):
    listing = tmp_path / "lifted.gb.asm"
    listing.write_text(
        "0x401000 pcode[0] ADD RAX,1 (COPY)\n" "0x401000 pcode[1] ADD RAX,1 (INT_ADD)\n"
    )
    source = Path("/example/harness.c")
    text = f"""Trace for harness.assertion.1:

State 1 file {source} function harness line 7 thread 0
----------------------------------------------------
  x=41ul (00000000)

State 2 file {listing} function asmc_target line 1 thread 0
----------------------------------------------------
  asmc_tmp_1=41ul (00000000)

State 3 file {listing} function asmc_target line 2 thread 0
----------------------------------------------------
  asmc_tmp_2=42ul (00000000)

Violated property:
  file {source} function harness line 9 thread 0
  assertion x == 43
  x == 43

"""
    driver.print_counterexample(text, [source], listing)
    output = capsys.readouterr().out
    assert "harness.c:7  x=41ul" in output
    assert "asmc_tmp_" not in output
    assert output.count("0x401000 ADD RAX,1") == 1
    assert output.count("Violated property:") == 1
    assert output.count("assertion x == 43") == 1
    assert "\n  x == 43\n" not in output
    driver.print_counterexample(text, [source], listing, full=True)
    assert capsys.readouterr().out == text
    two_traces = text + text.replace("harness.assertion.1", "harness.assertion.2")
    driver.print_counterexample(two_traces, [source], listing, first_only=True)
    output = capsys.readouterr().out
    assert "Trace for harness.assertion.1:" in output
    assert "Trace for harness.assertion.2:" not in output
    assert output.count("Violated property:") == 1


def test_trace_without_counterexample(driver, tmp_path, capsys):
    driver.print_counterexample("VERIFICATION SUCCESSFUL\n", [], tmp_path / "absent.asm")
    assert capsys.readouterr().out == ""
