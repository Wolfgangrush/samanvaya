"""Offline guarantees for the samanvaya conformance tool.

This module provides TWO independent guards, each labelled honestly for what it
is:

1. The runtime ``socket`` guard is a **tripwire**, not a proof. A C extension
   can open a socket without going through :func:`socket.socket`, so the
   guard can be bypassed. Pretending otherwise would be worse than having no
   guard at all, because it would invite reliance on something that is
   merely a defence-in-depth check.

2. The real assurance is the install-time dependency audit: the tool's
   declared dependencies are enumerated and any that brings a network
   capability is refused. Belt and braces, each labelled as what it is.

This module never imports networking libraries and never reaches the network.
"""

from __future__ import annotations

import socket
from typing import Any, Sequence
ALLOWED_DEPENDENCIES: frozenset[str] = frozenset(
    {
        "PyYAML",
        "dpdp-law-to-code",
        # PDF writer and its transitive set. None of these opens a socket: fpdf2 and
        # defusedxml are pure Python, fonttools ships compiled extensions for font
        # parsing only, and Pillow is pulled in by fpdf2's metadata but is never
        # imported here because this report embeds no images.
        "fpdf2",
        "defusedxml",
        "fonttools",
        "pillow",
    }
)

KNOWN_NETWORK_PACKAGES: frozenset[str] = frozenset(
    {
        "requests",
        "httpx",
        "urllib3",
        "aiohttp",
        "boto3",
        "websockets",
        "httplib2",
        "grpcio",
        "paramiko",
        "pycurl",
        "tornado",
        "twisted",
    }
)

_ORIGINAL_SOCKET: Any = None
_ORIGINAL_CREATE_CONNECTION: Any = None
_TRIPWIRE_INSTALLED: bool = False


def _normalise(name: str) -> str:
    """Lower-case and convert underscores to hyphens so allowlist comparison is canonical."""
    return name.strip().lower().replace("_", "-")


def audit_dependencies(declared: Sequence[str] | None = None) -> None:
    """Audit the declared dependency set against the offline allowlist.

    The audit fails closed: an unrecognised package is NOT evidence of a
    harmless package, because the cost of accidentally importing a
    networking library is data exfiltration, and that cost is borne by the
    client, not by us.
    """
    packages = list(ALLOWED_DEPENDENCIES) if declared is None else list(declared)
    normalised_allowed = {_normalise(name) for name in ALLOWED_DEPENDENCIES}
    normalised_network = {_normalise(name) for name in KNOWN_NETWORK_PACKAGES}
    for raw in packages:
        canonical = _normalise(raw)
        if canonical in normalised_network:
            raise RuntimeError(
                f"offline guarantee refused: {raw!r} is a known networking package; "
                "remove it to keep the tool offline"
            )
        if canonical not in normalised_allowed:
            raise RuntimeError(
                f"offline guarantee refused: {raw!r} is not on the allowlist; "
                "either add it explicitly or remove it to keep the tool offline"
            )


def _raise_offline(*_args: Any, **_kwargs: Any) -> None:
    """Tripwire replacement for socket constructors."""
    raise RuntimeError(
        "offline guarantee tripped: socket access is blocked in this tool; "
        "remove the tripwire only if you have reviewed the call site"
    )


def install_tripwire() -> None:
    """Install the runtime socket tripwire. Idempotent.

    Saves the originals on first install; subsequent installs are no-ops so
    ``remove_tripwire`` can restore the original ``socket.socket`` object.
    """
    global _ORIGINAL_SOCKET, _ORIGINAL_CREATE_CONNECTION, _TRIPWIRE_INSTALLED
    if not _TRIPWIRE_INSTALLED:
        _ORIGINAL_SOCKET = socket.socket
        _ORIGINAL_CREATE_CONNECTION = socket.create_connection
        _TRIPWIRE_INSTALLED = True
    # Rebinding a module-level name that mypy treats as a TYPE. The whole point of a
    # tripwire is to violate the contract, so the suppression is the design, not a
    # workaround — scoped to the two codes it actually raises.
    socket.socket = _raise_offline  # type: ignore[assignment, misc]
    socket.create_connection = _raise_offline  # type: ignore[assignment]


def remove_tripwire() -> None:
    """Remove the runtime socket tripwire. Safe to call when not installed."""
    global _TRIPWIRE_INSTALLED
    if not _TRIPWIRE_INSTALLED:
        return
    socket.socket = _ORIGINAL_SOCKET  # type: ignore[misc]
    socket.create_connection = _ORIGINAL_CREATE_CONNECTION
    _TRIPWIRE_INSTALLED = False


__all__ = [
    "ALLOWED_DEPENDENCIES",
    "KNOWN_NETWORK_PACKAGES",
    "audit_dependencies",
    "install_tripwire",
    "remove_tripwire",
]
