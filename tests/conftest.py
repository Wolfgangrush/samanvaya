"""Test bootstrap.

The India rail consumes `dpdp-law-to-code` as a library, pinned in `pyproject.toml`.
In a real install pip puts it on the path. During this build it lives as a sibling
clone, so if it is not already importable we add that clone — and ONLY that clone —
to `sys.path`.

This is a test convenience, not a runtime behaviour: nothing in `src/` manipulates
`sys.path`. If the package is genuinely absent the India tests skip loudly rather
than silently passing, because a silently-skipped India rail is the one failure this
project cannot afford — it is the only rail with a verified constant set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

#: Candidate locations for a sibling working clone, tried in order. Deliberately relative:
#: hard-coding one developer's absolute path into a repository both breaks on every other
#: machine and publishes that developer's directory layout. `DPDP_LAW_TO_CODE_PATH`
#: overrides all of them.
def _candidate_paths() -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[1]
    return (
        repo_root.parent / "dpdp-law-to-code",   # sibling checkout
        repo_root / "dpdp-law-to-code",          # nested checkout
        Path.home() / "dpdp-law-to-code",        # home checkout
    )


def _ensure_upstream_importable() -> None:
    try:
        import dpdp  # noqa: F401
        return
    except ImportError:
        pass
    override = os.environ.get("DPDP_LAW_TO_CODE_PATH")
    candidates = (Path(override),) if override else _candidate_paths()
    for clone in candidates:
        if (clone / "dpdp" / "__init__.py").is_file():
            sys.path.insert(0, str(clone))
            return


_ensure_upstream_importable()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "upstream: requires the pinned dpdp-law-to-code package"
    )


@pytest.fixture(scope="session")
def upstream_available() -> bool:
    try:
        import dpdp  # noqa: F401
    except ImportError:
        return False
    return True
