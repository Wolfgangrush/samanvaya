"""Acceptance tests for the cross-regime delta.

Authored BEFORE the implementation. Tests are not delegated.

**The delta is the product.** "Compliant under Regulation (EU) 2016/679, exposed under
the Digital Personal Data Protection Act 2023" is the one sentence no incumbent tool
emits, and the reason this repo exists. Cutting it would leave a worse version of tools
that already ship.

**C1 — but it must not rank.** Deciding which regime's standard is the more demanding is
statutory interpretation. A tool that ranks statutes is giving legal advice, and its
author is an enrolled advocate whose public tool emitting advice engages professional
conduct rules. The delta reports the divergence and names every position. The advocate
ranks it. There is a codebase-wide test that the token "strongest" appears nowhere.

**A1 — one row, not N.** Two regimes fixing a child-consent age of 16 and 18 are ONE
divergence on the `child_consent_age` dimension, not a string mismatch between
`age_threshold_16` and `age_threshold_18` and not a pairwise explosion.

**A2 — instrument is in the slot key.** A Californian hospital sits under CCPA and under
HIPAA. Those are two obligations, and they must neither merge nor duplicate ambiguously.
"""

from __future__ import annotations

from datetime import date

import pytest

from samanvaya.delta import compute
from samanvaya.types import (
    Finding,
    Obligation,
    ObligationResult,
    ObligationTopic,
    PackInfo,
    RegimeId,
    RegimeRollup,
    SubTopic,
)

AS_AT = date(2026, 8, 19)


def _pack(regime: RegimeId) -> PackInfo:
    return PackInfo(
        pack_id=regime.value.lower(), regime=regime, version="0.1.0",
        covers_sub_units=frozenset(), as_at=AS_AT, draft=False, obligation_count=1,
    )


def _finding(
    regime: RegimeId, instrument: str, topic: ObligationTopic, dimension: str,
    value: str, *, unit: str | None = None, sub_unit: str | None = None,
    provision: str = "Article 1", result: ObligationResult = ObligationResult.SATISFIED,
) -> Finding:
    ob = Obligation(
        obligation_id=f"{regime.value}.{dimension}.{value}",
        regime=regime, sub_unit=sub_unit, instrument=instrument, provision=provision,
        topic=topic, sub_topic=SubTopic(dimension, value, unit),
        obligation_summary="x", citation_pointer=f"{instrument}, {provision}",
    )
    return Finding(obligation=ob, result=result, rationale="r")


def _rollups(*findings: Finding) -> dict[RegimeId, RegimeRollup]:
    out: dict[RegimeId, RegimeRollup] = {}
    for f in findings:
        r = f.obligation.regime
        existing = out.get(r)
        acc = (existing.findings if existing else ()) + (f,)
        out[r] = RegimeRollup(regime=r, pack_info=_pack(r), findings=acc, counts={})
    return out


class TestOneRowPerDimension:
    def test_two_regimes_fixing_different_ages_produce_exactly_one_divergence(self) -> None:
        """A1. The whole point. 16 versus 18 is one CHILDREN divergence."""
        divs = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
        ))
        assert len(divs) == 1

    def test_that_row_names_the_dimension_and_topic(self) -> None:
        div = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
        ))[0]
        assert div.dimension == "child_consent_age"
        assert div.topic is ObligationTopic.CHILDREN

    def test_that_row_carries_every_position(self) -> None:
        div = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
        ))[0]
        assert {p.value for p in div.positions} == {"16", "18"}
        assert {p.regime for p in div.positions} == {RegimeId.EU_GDPR, RegimeId.INDIA}

    def test_three_regimes_diverging_still_produce_one_row_not_three_pairs(self) -> None:
        """A pairwise delta would emit three rows for three positions. It must not."""
        divs = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
            _finding(RegimeId.US, "Children's Online Privacy Protection Rule, 16 CFR part 312",
                     ObligationTopic.CHILDREN, "child_consent_age", "13", unit="years"),
        ))
        assert len(divs) == 1
        assert len(divs[0].positions) == 3

    def test_positions_carry_the_provision_so_the_reader_can_verify(self) -> None:
        div = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years", provision="Article 8(1)"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years",
                     provision="Section 2(f)"),
        ))[0]
        assert {p.provision for p in div.positions} == {"Article 8(1)", "Section 2(f)"}

    def test_the_unit_is_carried_on_the_row(self) -> None:
        div = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
        ))[0]
        assert div.unit == "years"


class TestAgreementIsNotDivergence:
    def test_two_regimes_fixing_the_same_value_produce_no_row(self) -> None:
        divs = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.BREACH,
                     "breach_notice_deadline", "72", unit="hours"),
            _finding(RegimeId.UK_GDPR, "UK GDPR", ObligationTopic.BREACH,
                     "breach_notice_deadline", "72", unit="hours"),
        ))
        assert divs == ()

    def test_a_dimension_present_in_only_one_regime_is_not_a_divergence(self) -> None:
        """Nothing to compare it against. Reporting it would be noise."""
        divs = compute(_rollups(
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Rules 2025",
                     ObligationTopic.SECURITY, "log_retention_period", "1", unit="years"),
        ))
        assert divs == ()

    def test_different_dimensions_never_compare(self) -> None:
        divs = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.BREACH,
                     "breach_notice_deadline", "72", unit="hours"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Rules 2025",
                     ObligationTopic.RIGHTS, "grievance_response_period", "90", unit="days"),
        ))
        assert divs == ()


class TestInstrumentIsAFirstClassKey:
    def test_ccpa_and_hipaa_on_one_hospital_stay_distinct(self) -> None:
        """A2 + falsifier #1. Two instruments, one sub-unit, two positions — never merged."""
        divs = compute(_rollups(
            _finding(RegimeId.US, "California Consumer Privacy Act", ObligationTopic.BREACH,
                     "breach_notice_deadline", "unspecified", sub_unit="US-CA"),
            _finding(RegimeId.US, "HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
                     ObligationTopic.BREACH, "breach_notice_deadline", "1440", unit="hours"),
        ))
        assert len(divs) == 1
        instruments = {p.instrument for p in divs[0].positions}
        assert instruments == {
            "California Consumer Privacy Act",
            "HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
        }

    def test_the_same_instrument_twice_on_one_dimension_is_not_duplicated(self) -> None:
        divs = compute(_rollups(
            _finding(RegimeId.US, "HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
                     ObligationTopic.BREACH, "breach_notice_deadline", "1440", unit="hours"),
            _finding(RegimeId.US, "HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
                     ObligationTopic.BREACH, "breach_notice_deadline", "1440", unit="hours"),
        ))
        assert divs == ()

    def test_the_sub_unit_is_carried_on_the_position(self) -> None:
        div = compute(_rollups(
            _finding(RegimeId.US, "California Consumer Privacy Act", ObligationTopic.BREACH,
                     "breach_notice_deadline", "unspecified", sub_unit="US-CA"),
            _finding(RegimeId.US, "HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
                     ObligationTopic.BREACH, "breach_notice_deadline", "1440", unit="hours"),
        ))[0]
        assert "US-CA" in {p.sub_unit for p in div.positions}


class TestNoRanking:
    def test_the_divergence_exposes_no_ranking_field(self) -> None:
        """C1. Ranking statutes is legal interpretation. The advocate ranks."""
        import dataclasses

        div = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
        ))[0]
        names = {f.name for f in dataclasses.fields(div)}
        for banned in ("strongest", "strictest", "rank", "severity", "winner", "highest"):
            assert not any(banned in n for n in names), banned

    def test_the_delta_module_contains_no_ranking_vocabulary(self) -> None:
        import inspect

        from samanvaya import delta

        source = inspect.getsource(delta).lower()
        for banned in ("strongest", "strictest", "most onerous", "winner"):
            assert banned not in source, banned

    def test_positions_are_not_sorted_by_value_magnitude(self) -> None:
        """Ordering by magnitude would imply a ranking through the back door."""
        div = compute(_rollups(
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
        ))[0]
        # RegimeId declares INDIA first, so declaration order puts India before the EU
        # here even though the EU finding was passed in second and holds the lower value.
        # That is the point: the order tracks the enum, never the magnitude of the value.
        assert [p.regime for p in div.positions] == [RegimeId.INDIA, RegimeId.EU_GDPR]


class TestDeterminismAndOrdering:
    def test_rows_are_ordered_deterministically(self) -> None:
        a = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.BREACH,
                     "breach_notice_deadline", "72", unit="hours"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Rules 2025",
                     ObligationTopic.BREACH, "breach_notice_deadline", "72", unit="hours"),
        ))
        b = compute(_rollups(
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Rules 2025",
                     ObligationTopic.BREACH, "breach_notice_deadline", "72", unit="hours"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.BREACH,
                     "breach_notice_deadline", "72", unit="hours"),
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
        ))
        assert [(d.topic, d.dimension) for d in a] == [(d.topic, d.dimension) for d in b]

    def test_an_empty_input_produces_no_rows(self) -> None:
        assert compute({}) == ()

    def test_the_result_is_a_tuple_so_it_cannot_be_mutated(self) -> None:
        assert isinstance(compute({}), tuple)


class TestUnsourcedValuesAreNotCompared:
    def test_a_fact_needed_value_never_becomes_a_divergence_position(self) -> None:
        """Comparing a real age against "[FACT NEEDED: ...]" would report a fake conflict."""
        from samanvaya.types import fact_needed

        divs = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.UK_GDPR, "Data Protection Act 2018", ObligationTopic.CHILDREN,
                     "child_consent_age", fact_needed("UK age?"), unit="years"),
        ))
        assert divs == ()

    def test_two_real_values_still_diverge_when_a_third_is_unsourced(self) -> None:
        from samanvaya.types import fact_needed

        divs = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years"),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years"),
            _finding(RegimeId.UK_GDPR, "Data Protection Act 2018", ObligationTopic.CHILDREN,
                     "child_consent_age", fact_needed("UK age?"), unit="years"),
        ))
        assert len(divs) == 1
        assert len(divs[0].positions) == 2


class TestResultIsCarried:
    def test_each_position_carries_the_conformance_verdict(self) -> None:
        """The adviser needs to see compliant-here-exposed-there, not just the values."""
        div = compute(_rollups(
            _finding(RegimeId.EU_GDPR, "Regulation (EU) 2016/679", ObligationTopic.CHILDREN,
                     "child_consent_age", "16", unit="years",
                     result=ObligationResult.SATISFIED),
            _finding(RegimeId.INDIA, "Digital Personal Data Protection Act 2023",
                     ObligationTopic.CHILDREN, "child_consent_age", "18", unit="years",
                     result=ObligationResult.GAP),
        ))[0]
        by_regime = {p.regime: p.result for p in div.positions}
        assert by_regime[RegimeId.EU_GDPR] is ObligationResult.SATISFIED
        assert by_regime[RegimeId.INDIA] is ObligationResult.GAP
