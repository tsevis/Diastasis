"""The floors in `pyproject.toml` must be something CI can actually install.

`[project.dependencies]` states a minimum for every runtime dependency, and
nothing ever installed those minimums: CI resolves whatever is newest, so the
floors were prose. Measured 2026-09-20, the first time anyone tried them:
170 passed, 1 skipped on Python 3.10 with every dependency at its floor.

`scripts/floor_constraints.py` turns each `>=X` into a `==X` constraint so the
floors job installs exactly what the declaration promises. The failure this
guards against is not a crash -- it is the generator quietly emitting nothing
for a dependency, which leaves the job resolving the newest version while
reporting that it tested the floor.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10, which this project still supports
    import tomli as tomllib

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "floor_constraints.py"


def _runtime_dependencies() -> list[str]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["dependencies"]


def _generated() -> dict[str, str]:
    out = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=True, cwd=REPO
    ).stdout
    pins = {}
    for line in out.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, _, version = line.partition("==")
            pins[name.lower()] = version
    return pins


def test_every_runtime_dependency_gets_a_floor_pin():
    """A dependency with no pin is a dependency the floors job does not test."""
    import re

    declared = {re.split(r"[<>=!\[ ]", spec)[0].lower() for spec in _runtime_dependencies()}
    pinned = set(_generated())

    missing = sorted(declared - pinned)
    assert not missing, (
        f"{missing} have no floor pin, so the floors job would install the NEWEST "
        "version of each and still report that it tested the floor. Either give "
        "them a `>=` floor in pyproject.toml or make the generator refuse."
    )


def test_a_dependency_without_a_floor_is_refused_rather_than_skipped(tmp_path):
    """Silence is the dangerous outcome, so the generator must fail loudly."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["shapely"]\n',
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode != 0, "a dependency with no floor must not pass silently"
    assert "shapely" in result.stderr


def test_a_floor_that_is_itself_excluded_is_refused(tmp_path):
    """`>=2.1.0,!=2.1.0` must fail here, not on the runner.

    An exclusion opens a failure mode that plain floors do not have: the pin
    this generator derives can contradict the specifier that produced it, and
    `pip install -c` then dies with `ResolutionImpossible` before a single
    test is collected -- the worst place to fail, because nothing has been
    measured yet.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["shapely>=2.1.0,!=2.1.0"]\n',
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode != 0, "a floor the specifier excludes must not be emitted as a pin"
    assert "2.1.0" in result.stderr
