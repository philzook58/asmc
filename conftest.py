"""Project-wide test options, available even without an explicit tests/ argument."""

from pathlib import Path


def pytest_addoption(parser):
    parser.addoption(
        "--build-dir",
        type=Path,
        default=Path(__file__).parent / "build",
        help="CMake build directory containing bin/asmc",
    )
    parser.addoption(
        "--scalar-registers",
        action="store_true",
        help="run the same tests with register-word storage",
    )
