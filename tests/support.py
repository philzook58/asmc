"""Small helpers for tests that exercise the real toolchain."""

import os
import resource
import shlex
import signal
import subprocess
from contextlib import suppress
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(command, expected=0, timeout=120, *, env=None, input=None, log=None, memory_gib=None):
    command = [str(arg) for arg in command]
    if log:
        with (log.parent / "commands.txt").open("a") as stream:
            stream.write(shlex.join(command) + "\n")

    def limit_memory():
        limit = memory_gib * 1024**3
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if input is not None else None,
            text=True,
            start_new_session=True,
            env=env,
            preexec_fn=limit_memory if memory_gib is not None else None,
        )
    except OSError as error:
        pytest.fail(f"Cannot run {shlex.join(command)}: {error}", pytrace=False)
    try:
        output, _ = process.communicate(input=input, timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        # Let ASMC stop its independently grouped checker/solver before killing it.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGINT)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        if log:
            log.write_text(output)
        if isinstance(error, KeyboardInterrupt):
            raise
        pytest.fail(f"Timed out after {timeout}s: {shlex.join(command)}\n{output}", pytrace=False)
    if log:
        log.write_text(output)
    if process.returncode != expected:
        pytest.fail(
            f"Command: {shlex.join(command)}\n"
            f"Expected exit {expected}, got {process.returncode}\n{output}",
            pytrace=False,
        )
    return output


# Suites that already imposed a memory limit retain the same bound.
bounded_run = partial(run, memory_gib=2)


def roundtrip(asmc, output):
    run(
        [
            asmc.parent / "goto-instrument",
            "--validate-goto-model",
            output / "lifted.gb",
            output / "roundtrip.gb",
        ]
    )
