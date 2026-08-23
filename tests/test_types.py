"""Acceptance tests for the shared contract in `samanvaya.types`.

Authored by the maintainer — tests are not delegated.

NOTE ON PROVENANCE: `types.py` was authored by the delegate BEFORE this file existed,
so this suite is honestly **test-after** for that module. Every other module in this
build has its tests written first. Recorded so the TDD claim stays falsifiable.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from samanvaya.types import (
    DISCLAIMER,
    FACT_NEEDED_PREFIX,
    FEDERATED_REGIMES,
    AppliesIf,
    Declaration,
    Divergence,
    DivergencePosition,
    Finding,
    JurisdictionRef,
    Obligation,
    ObligationResult,
    ObligationTopic,
    Organisation,
    PredicateOp,
    RegimeId,
    SafeguardPair,
    SubTopic,
    fact_needed,
)


def _obligation(**overrides: object) -> Obligation:
    base: dict[str, object] = {
        "obligation_id": "test.ob.1",
        "regime": RegimeId.EU_GDPR,
        "sub_unit": None,
        "instrument": "Regulation (EU) 2016/679",
        "provision": "Article 8(1)",
        "topic": ObligationTopic.CHILDREN,
        "sub_topic": SubTopic("child_consent_age", "16", "years"),
        "obligation_summary": "Age of consent for information society services.",
        "citation_pointer": "Regulation (EU) 2016/679, Article 8(1)",
    }
    base.update(overrides)
    return Obligation(**base)  # type: ignore[arg-type]


class TestDisclaimer:
    def test_disclaimer_is_present_and_says_not_legal_advice(self) -> None:
        assert "not legal advice" in DISCLAIMER.lower()

    def test_disclaimer_disclaims_a_lawyer_client_relationship(self) -> None:
        assert "lawyer-client" in DISCLAIMER.lower() or "solicitor" in DISCLAIMER.lower()


class TestFactNeeded:
    def test_marker_round_trips(self) -> None:
        marker = fact_needed("what is the age threshold in X?")
        assert marker.startswith(FACT_NEEDED_PREFIX)
        assert marker.endswith("]")

    def test_obligation_reports_unsourced_constant_in_provision(self) -> None:
        ob = _obligation(provision=fact_needed("which article?"))
        assert ob.has_unsourced_constant() is True

    def test_obligation_reports_unsourced_constant_in_sub_topic_value(self) -> None:
        ob = _obligation(sub_topic=SubTopic("child_consent_age", fact_needed("age?"), "years"))
        assert ob.has_unsourced_constant() is True

    def test_fully_sourced_obligation_is_clean(self) -> None:
        assert _obligation().has_unsourced_constant() is False


class TestRegimeNaming:
    def test_the_six_regimes_are_exactly_these(self) -> None:
        assert {r.value for r in RegimeId} == {"IN", "EU", "UK", "SG", "US", "CA"}

    def test_us_and_canada_are_the_federated_regimes(self) -> None:
        assert FEDERATED_REGIMES == frozenset({RegimeId.US, RegimeId.CANADA})

    def test_no_banned_instrument_name_appears_in_the_module(self) -> None:
        import samanvaya.types as mod

        source = open(mod.__file__, encoding="utf-8").read().lower()
        for banned in ("us gdpr", "singapore gdpr", "canada gdpr"):
            # The names may be quoted only to say they are banned.
            for line in source.splitlines():
                if banned in line:
                    assert "banned" in line or "not instrument" in line, (
                        f"banned name {banned!r} used substantively: {line!r}"
                    )


class TestObligationKeys:
    def test_slot_key_carries_instrument_so_ccpa_and_hipaa_do_not_merge(self) -> None:
        """A2. One Californian hospital, two instruments, two slots."""
        ccpa = _obligation(
            regime=RegimeId.US,
            sub_unit="US-CA",
            instrument="California Consumer Privacy Act",
            topic=ObligationTopic.BREACH,
            sub_topic=SubTopic("breach_notice_deadline", "unspecified"),
        )
        hipaa = _obligation(
            regime=RegimeId.US,
            sub_unit="US-CA",
            instrument="HIPAA Breach Notification Rule",
            topic=ObligationTopic.BREACH,
            sub_topic=SubTopic("breach_notice_deadline", "1440", "hours"),
        )
        assert ccpa.slot_key != hipaa.slot_key
        assert ccpa.slot_key[2] != hipaa.slot_key[2]

    def test_comparison_key_is_topic_and_dimension_only(self) -> None:
        """A1. Two regimes fixing different ages compare on one axis."""
        eu = _obligation(sub_topic=SubTopic("child_consent_age", "16", "years"))
        india = _obligation(
            regime=RegimeId.INDIA,
            instrument="Digital Personal Data Protection Act 2023",
            sub_topic=SubTopic("child_consent_age", "18", "years"),
        )
        assert eu.comparison_key == india.comparison_key

    def test_differing_dimensions_do_not_compare(self) -> None:
        a = _obligation(sub_topic=SubTopic("child_consent_age", "16"))
        b = _obligation(sub_topic=SubTopic("breach_notice_deadline", "72"))
        assert a.comparison_key != b.comparison_key


class TestInForce:
    def test_not_yet_commenced_obligation_is_not_in_force(self) -> None:
        ob = _obligation(in_force_from=date(2027, 5, 13))
        assert ob.is_in_force(date(2026, 8, 19)) is False

    def test_commenced_obligation_is_in_force(self) -> None:
        ob = _obligation(in_force_from=date(2018, 5, 25))
        assert ob.is_in_force(date(2026, 8, 19)) is True

    def test_repealed_obligation_is_not_in_force(self) -> None:
        ob = _obligation(in_force_until=date(2024, 1, 1))
        assert ob.is_in_force(date(2026, 8, 19)) is False

    def test_obligation_with_no_dates_is_always_in_force(self) -> None:
        assert _obligation().is_in_force(date(1999, 1, 1)) is True


class TestNoRanking:
    def test_divergence_carries_positions_and_never_ranks_them(self) -> None:
        """C1. Ranking statutes is statutory interpretation. The tool must not."""
        div = Divergence(
            topic=ObligationTopic.CHILDREN,
            dimension="child_consent_age",
            positions=(
                DivergencePosition(
                    RegimeId.EU_GDPR, None, "Regulation (EU) 2016/679",
                    "Article 8(1)", "16", "years", ObligationResult.SATISFIED,
                ),
                DivergencePosition(
                    RegimeId.INDIA, None, "Digital Personal Data Protection Act 2023",
                    "Section 2(f)", "18", "years", ObligationResult.GAP,
                ),
            ),
        )
        assert len(div.positions) == 2
        field_names = {f.name for f in dataclasses.fields(div)}
        assert not any("strong" in n or "rank" in n or "sever" in n for n in field_names)

    def test_the_token_strongest_appears_nowhere_in_the_package(self) -> None:
        """C1. A codebase-wide search; zero hits required."""
        import pathlib

        import samanvaya

        root = pathlib.Path(samanvaya.__file__).parent
        offenders = [
            str(p)
            for p in root.rglob("*.py")
            if "strongest" in p.read_text(encoding="utf-8").lower()
        ]
        assert offenders == [], f"'strongest' found in: {offenders}"


class TestDeclarationHelpers:
    def _declaration(self) -> Declaration:
        return Declaration(
            schema_version="1.0",
            organisation=Organisation(legal_name="Acme Pvt Ltd"),
            jurisdictions=(JurisdictionRef("IN"),),
            declaration_author="adviser",
            security_safeguards=(
                SafeguardPair("Encryption", "AES-256 at rest"),
                SafeguardPair("Access control", "role based"),
            ),
        )

    def test_declared_safeguard_matches_case_insensitively(self) -> None:
        assert self._declaration().declared_safeguard("encryption") is not None
        assert self._declaration().declared_safeguard("  ENCRYPTION ") is not None

    def test_undeclared_safeguard_returns_none(self) -> None:
        assert self._declaration().declared_safeguard("data backups") is None

    def test_declaration_is_frozen(self) -> None:
        decl = self._declaration()
        with pytest.raises(dataclasses.FrozenInstanceError):
            decl.schema_version = "2.0"  # type: ignore[misc]

    def test_organisation_fields_default_to_none_not_zero(self) -> None:
        """A4 depends on 'not declared' being distinguishable from 'declared zero'."""
        org = Organisation(legal_name="X")
        assert org.employee_count is None
        assert org.is_healthcare_provider is None


class TestSubUnitsComplete:
    def test_default_is_incomplete_so_silence_never_asserts_coverage(self) -> None:
        """A3. Absent assertion must not be read as 'we checked all fifty states'."""
        assert JurisdictionRef("US").sub_units_complete is False


class TestPredicateOps:
    def test_the_operator_set_is_closed_and_complete(self) -> None:
        assert {op.value for op in PredicateOp} == {
            "==", "!=", ">", ">=", "<", "<=", "in", "contains", "truthy",
        }

    def test_applies_if_records_a_dotted_path(self) -> None:
        pred = AppliesIf("organisation.employee_count", PredicateOp.GTE, 250)
        assert pred.path.split(".") == ["organisation", "employee_count"]


class TestFinding:
    def test_finding_carries_its_obligation_and_a_rationale(self) -> None:
        f = Finding(_obligation(), ObligationResult.GAP, "no consent age declared")
        assert f.obligation.instrument == "Regulation (EU) 2016/679"
        assert f.rationale
