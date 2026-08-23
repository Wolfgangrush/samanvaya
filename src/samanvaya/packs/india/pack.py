"""India obligations pack — registration and entry point.

This module is the small public surface of the India pack: it advertises a
:func:`PackInfo` record and forwards evaluation requests to
:mod:`samanvaya.packs.india.adapter`. India is the correctness anchor of
the whole tool, so this file is intentionally thin: every obligation lives
in the adapter where the upstream contract lives, and the pack wrapper
exists only to plug into the samanvaya loader.
"""

from __future__ import annotations

from datetime import date

from samanvaya.packs.india import adapter
from samanvaya.types import (
    Declaration,
    Finding,
    ObligationResult,
    PackInfo,
    RegimeId,
)


PACK_ID: str = "india"
"""Identifier under which the loader registers this pack."""

AS_AT: date = date(2026, 8, 19)
"""The canonical as-at date used for this pack. Aligned with the adapter's
test fixture so evaluations are reproducible across runs."""

OBLIGATION_COUNT: int = len(adapter.OBLIGATION_REGISTRY)
"""Number of obligations emitted by this pack.

Computed directly from ``adapter.OBLIGATION_REGISTRY`` so the count cannot
drift out of sync with the adapter: if a future change adds or removes an
obligation in the registry, ``OBLIGATION_COUNT`` reflects it on the next
import. The registry is the single source of truth."""

INSTRUMENTS: tuple[str, ...] = (
    adapter.ACT_INSTRUMENT,
    adapter.RULES_INSTRUMENT,
)
"""The two instruments whose text this pack is anchored against."""


def info() -> PackInfo:
    """Return the metadata block describing this pack."""
    return PackInfo(
        pack_id=PACK_ID,
        regime=RegimeId.INDIA,
        version="0.1.0",
        covers_sub_units=frozenset(),
        as_at=AS_AT,
        draft=False,
        obligation_count=OBLIGATION_COUNT,
        instruments=INSTRUMENTS,
    )


def _apply_in_force(findings: list[Finding], as_at: date) -> list[Finding]:
    """Apply the in-force rule inline so the pack is correct under direct calls.

    The engine re-applies the same rule idempotently in its post-pass, so this
    duplication is deliberate: ``engine.run()`` remains correct, and a direct
    ``pack.evaluate(declaration, as_at, None)`` call (bypassing the engine)
    now also returns NOT_APPLICABLE for not-yet-commenced Rules-based
    obligations instead of CONTESTED.
    """
    result: list[Finding] = []
    for finding in findings:
        obligation = finding.obligation
        in_force_from = getattr(obligation, "in_force_from", None)
        is_in_force = getattr(obligation, "is_in_force", None)
        if (
            in_force_from is not None
            and callable(is_in_force)
            and not is_in_force(as_at)
            and finding.result is not ObligationResult.NOT_APPLICABLE
        ):
            result.append(
                Finding(
                    obligation=obligation,
                    result=ObligationResult.NOT_APPLICABLE,
                    rationale=(
                        f"This obligation is not in force on the as-at date "
                        f"{as_at.isoformat()}; in_force_from="
                        f"{in_force_from.isoformat()}. The duty has not yet "
                        "commenced and is therefore not yet engaged."
                    ),
                    declaration_summary=finding.declaration_summary,
                    evidence_paths=finding.evidence_paths,
                )
            )
            continue
        result.append(finding)
    return result


def evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]:
    """Evaluate the declaration against the India rail.

    India has no sub-national rail in this tool — supplying any sub-unit is a
    caller error in the sense that nothing in this pack is calibrated for it,
    so we return an empty list and let the loader surface the situation. With
    ``sub_unit is None`` we delegate to the adapter and then apply the
    in-force rule inline so the pack is correct when called directly (the
    engine re-applies the same rule idempotently; the duplication is
    deliberate so the pack honours its contract under both callers).
    """
    if sub_unit is not None:
        return []
    findings = adapter.run_checks(declaration, as_at)
    return _apply_in_force(findings, as_at)


__all__ = ["PACK_ID", "AS_AT", "OBLIGATION_COUNT", "INSTRUMENTS", "info", "evaluate"]
