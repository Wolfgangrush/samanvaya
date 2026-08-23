"""Cross-regime divergence reporting — the deliverable of this tool.

"Compliant under Regulation (EU) 2016/679, exposed under the Digital Personal Data
Protection Act 2023" is the one sentence no incumbent tool emits, and this module is
where it comes from: a single row per (topic, dimension) that names every regime's
position side by side.

Reporting divergence and ranking divergence are different acts, and only the first
belongs in a tool. Deciding which regime's standard is the more demanding is statutory
interpretation; a tool that ranks statutes is giving legal advice, and its author is an
enrolled advocate whose public tool emitting advice engages professional conduct rules.
This module therefore reports the divergence, names every position, and stops there.
The advocate ranks it.

Values marked as unsourced (``[FACT NEEDED: ...]``) are excluded from comparison rather
than compared, because juxtaposing a real age against a placeholder would report a
fabricated conflict between a known rule and an unknown one — which is worse than
saying nothing.
"""

from __future__ import annotations

from typing import Mapping

from samanvaya.types import (
    FACT_NEEDED_PREFIX,
    Divergence,
    DivergencePosition,
    Finding,
    ObligationResult,
    ObligationTopic,
    RegimeId,
    RegimeRollup,
)

_REGIME_ORDER: dict[RegimeId, int] = {
    regime: index for index, regime in enumerate(RegimeId)
}
"""Declaration order of regimes, used for deterministic ordering of positions."""

_TOPIC_ORDER: dict[ObligationTopic, int] = {
    topic: index for index, topic in enumerate(ObligationTopic)
}
"""Declaration order of topics, used for deterministic ordering of rows."""


def _is_compareable(finding: Finding) -> bool:
    """Return True if the finding's value may take part in a comparison.

    A value that is still awaiting sourcing must not be juxtaposed against a
    sourced one: the resulting row would assert a conflict between a known
    rule and an unknown one. Silence is the honest output until the constant
    is sourced.
    """
    obligation = finding.obligation
    if obligation.has_unsourced_constant():
        return False
    if FACT_NEEDED_PREFIX in obligation.sub_topic.value:
        return False
    return True


def _position_sort_key(position: DivergencePosition) -> tuple[int, str, str]:
    """Deterministic position ordering keyed on identity, never on value.

    Ordering by the magnitude of the value would imply a comparison between
    the regimes through the back door, so the key uses only the regime's
    declaration order, the sub-unit name and the instrument name.
    """
    return (
        _REGIME_ORDER[position.regime],
        position.sub_unit or "",
        position.instrument,
    )


def _row_sort_key(divergence: Divergence) -> tuple[int, str]:
    """Deterministic row ordering keyed on the topic's declaration order."""
    return (_TOPIC_ORDER[divergence.topic], divergence.dimension)


def compute(per_regime: Mapping[RegimeId, RegimeRollup]) -> tuple[Divergence, ...]:
    """Compute the cross-regime delta as one row per (topic, dimension).

    The delta groups slots by comparison key so that two regimes fixing a
    child-consent age of 16 and 18 produce exactly ONE divergence on
    ``child_consent_age`` — never a string mismatch, never a pairwise
    explosion. A dimension seen in only one regime produces nothing, because
    there is nothing to compare it against; agreement likewise produces
    nothing, because agreement is not divergence.
    """
    # Step 1 — gather every finding, in regime declaration order so that the
    # "first wins" rule for duplicate slots is itself deterministic.
    findings: list[Finding] = []
    for regime in RegimeId:
        rollup = per_regime.get(regime)
        if rollup is None:
            continue
        findings.extend(rollup.findings)

    # Step 2 — drop unsourced values before anything is compared.
    sourced = [finding for finding in findings if _is_compareable(finding)]

    # Step 3 — one slot per slot_key. Two instruments on one sub-unit (CCPA
    # and HIPAA over a Californian hospital, say) occupy two slots and must
    # neither merge nor duplicate; the same instrument twice on one dimension
    # collapses to one slot, so it cannot manufacture a divergence against
    # itself.
    slots: dict[tuple[str, str | None, str, str, str], Finding] = {}
    for finding in sourced:
        obligation = finding.obligation
        key = obligation.slot_key
        if key not in slots:
            slots[key] = finding

    # Step 4 — group the slots by comparison key (topic, dimension).
    groups: dict[tuple[str, str], list[Finding]] = {}
    for finding in slots.values():
        obligation = finding.obligation
        groups.setdefault(obligation.comparison_key, []).append(finding)

    # Steps 5–7 — emit at most one row per group, carrying every position.
    rows: list[Divergence] = []
    for (topic_value, dimension), group in groups.items():
        distinct_values = {f.obligation.sub_topic.value for f in group}
        if len(distinct_values) < 2:
            # Agreement is not divergence; a lone dimension has no counterpart.
            continue

        positions = tuple(
            sorted(
                (
                    DivergencePosition(
                        regime=finding.obligation.regime,
                        sub_unit=finding.obligation.sub_unit,
                        instrument=finding.obligation.instrument,
                        provision=finding.obligation.provision,
                        value=finding.obligation.sub_topic.value,
                        unit=finding.obligation.sub_topic.unit,
                        result=finding.result,
                    )
                    for finding in group
                ),
                key=_position_sort_key,
            )
        )

        # The row's unit is the single unit when every position agrees on it,
        # otherwise None — a mixed-unit row must not silently adopt one unit as canonical
        # among the units by fiat.
        units = {position.unit for position in positions}
        row_unit: str | None
        if len(units) == 1:
            row_unit = next(iter(units))
        else:
            row_unit = None

        rows.append(
            Divergence(
                topic=ObligationTopic(topic_value),
                dimension=dimension,
                positions=positions,
                unit=row_unit,
            )
        )

    # Step 8 — deterministic row ordering by topic declaration order, then
    # dimension name. Never by value, never alphabetical on topic value.
    rows.sort(key=_row_sort_key)

    # Step 9 — a tuple, so the caller cannot mutate the report.
    return tuple(rows)


__all__ = ["compute"]
