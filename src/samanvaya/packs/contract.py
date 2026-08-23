"""Samanvaya conformance engine — the pack contract.

Every first-party pack implements this contract. The contract exists so the
registry can validate a pack's shape at load time rather than discovering a
malformed pack mid-run, and so that a pack's metadata cannot disagree with
its implementation.

The contract, in full:

- **One evaluation entry point per pack.** A pack exposes exactly
  ``evaluate(declaration, as_at, sub_unit)`` and nothing else is called by
  the engine. There is no plugin discovery, no dynamic loading, and no way
  for anything on the path to substitute a pack by name.
- **Scope is the declared regime and jurisdiction only.** A pack evaluates
  obligations for the regime it is registered under and the supplied
  sub-unit; it never reaches into another regime's territory.
- **Every obligation cites a named instrument and provision.** A finding
  without a primary-source citation is unusable to an adviser, so the
  ``Obligation`` carried by each ``Finding`` must name both.
- **A pack emits DOES_NOT_EXIST for a covered topic it does not impose.**
  Where a declared jurisdiction triggers the regime but a topic in the
  comparison vocabulary has no obligation there, the honest answer is that
  the instrument imposes nothing on that topic — not a fabricated gap.
- **The pack applies the supplied ``as_at``.** In-force windows are checked
  against the caller's date; a pack never reads the wall clock, so the same
  inputs always produce the same output.
- **A draft pack never emits SATISFIED.** A draft indicates the statutory
  constants are not yet primary-sourced; any satisfied judgment could be
  reversed by a later edit, so the engine downgrades it. A draft pack MAY
  still report GAP — suppressing genuine gaps would be worse than draft
  status.
- **Nothing is persisted beyond the call.** No file I/O, no network, no
  caches that outlive the evaluation; the pack is a pure function of its
  arguments.

This module defines the contract only. It contains no implementation and no
side effects.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from samanvaya.types import Declaration, Finding, PackInfo

__all__ = ["PackProtocol"]


@runtime_checkable
class PackProtocol(Protocol):
    """The shape every obligations pack must implement.

    Implementations are modules (the registry stores modules directly), so
    this protocol describes module-level ``info`` and ``evaluate`` callables
    rather than a class instance.
    """

    def info(self) -> PackInfo:
        """Return the pack's metadata.

        The returned ``regime`` must equal the registry key the pack is
        registered under; the registry validates this on import.
        """
        ...

    def evaluate(
        self, declaration: Declaration, as_at: date, sub_unit: str | None
    ) -> list[Finding]:
        """Evaluate the pack's obligations for one resolved target.

        ``sub_unit`` is ``None`` for unitary regimes and an ISO 3166-2 code
        for federated ones. The pack applies the supplied ``as_at`` and
        persists nothing beyond the call.
        """
        ...
