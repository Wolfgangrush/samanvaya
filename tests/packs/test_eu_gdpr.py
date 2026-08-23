"""Acceptance tests for the EU pack. Tests are not delegated.

The EU rail's core Articles were read verbatim on the EUR-Lex consolidated text
(CELEX 02016R0679-20160504) on 2026-08-19. These tests pin the constants that were
verified, so a later edit cannot quietly change one.
"""

from __future__ import annotations

from datetime import date

import pytest

from samanvaya.packs.eu_gdpr import pack
from samanvaya.types import ObligationResult, RegimeId

AS_AT = date(2026, 8, 19)


def _obligation(oid: str):
    return next(o for o in pack._OBLIGATIONS if o.obligation_id == oid)


class TestPackMetadata:
    def test_the_regime_is_the_eu(self) -> None:
        assert pack.info().regime is RegimeId.EU_GDPR

    def test_the_instrument_is_named_correctly(self) -> None:
        assert pack.info().instruments == ("Regulation (EU) 2016/679",)

    def test_it_is_a_draft_pack_and_says_why(self) -> None:
        assert pack.info().draft is True
        assert pack.info().draft_reason.strip()

    def test_it_covers_no_sub_units(self) -> None:
        assert pack.info().covers_sub_units == frozenset()

    def test_a_sub_unit_yields_nothing(self) -> None:
        """The EU is not a jurisdictional tree in this tool."""
        assert pack.evaluate(_decl(), AS_AT, "DE-BY") == []


def _decl():
    from samanvaya.types import Declaration, JurisdictionRef, Organisation

    return Declaration(
        schema_version="1.0",
        organisation=Organisation(legal_name="Acme"),
        jurisdictions=(JurisdictionRef("DE"),),
        declaration_author="adviser",
    )


class TestVerifiedConstants:
    def test_the_child_consent_age_is_sixteen_per_article_8_1(self) -> None:
        ob = _obligation("eu.children.age")
        assert ob.sub_topic.value == "16"
        assert ob.sub_topic.unit == "years"
        assert ob.provision == "Article 8(1)"

    def test_the_summary_records_the_thirteen_year_floor(self) -> None:
        assert "13" in _obligation("eu.children.age").obligation_summary

    def test_the_member_state_derogation_is_flagged_as_unsourced(self) -> None:
        meta = dict(_obligation("eu.children.age").evaluation_metadata)
        assert "FACT NEEDED" in meta.get("member_state_derogation", "")

    def test_the_breach_deadline_is_seventy_two_hours_per_article_33_1(self) -> None:
        ob = _obligation("eu.breach.authority")
        assert ob.sub_topic.value == "72"
        assert ob.sub_topic.unit == "hours"
        assert ob.provision == "Article 33(1)"

    def test_the_records_threshold_is_250_persons_per_article_30_5(self) -> None:
        ob = _obligation("eu.records.ropa")
        assert ob.sub_topic.value == "250"
        assert ob.provision == "Article 30(5)"

    def test_the_records_carve_outs_are_recorded(self) -> None:
        """Below 250 the derogation still fails on three grounds. Omitting them
        would turn a conditional exemption into an unconditional one."""
        meta = dict(_obligation("eu.records.ropa").evaluation_metadata)
        assert meta.get("derogation_carve_outs")

    def test_article_5_is_six_principles_not_seven(self) -> None:
        """Art 5(1) has points (a)-(f). Accountability is a separate duty in 5(2)."""
        assert _obligation("eu.principles").sub_topic.value == "6"

    def test_the_security_obligation_prescribes_no_standard(self) -> None:
        """A5. Art 32(1) names encryption as an example, not a required value."""
        assert _obligation("eu.security.measures").required_value is None

    def test_the_dsr_period_records_that_one_month_is_modelled_as_thirty_days(self) -> None:
        meta = dict(_obligation("eu.rights.deadline").evaluation_metadata)
        assert any("month" in v.lower() for v in meta.values())

    def test_every_obligation_is_in_force_only_from_the_application_date(self) -> None:
        for ob in pack._OBLIGATIONS:
            assert ob.in_force_from == date(2018, 5, 25)

    def test_no_obligation_predates_the_regulation(self) -> None:
        for ob in pack._OBLIGATIONS:
            assert ob.is_in_force(date(2017, 1, 1)) is False


class TestDraftBehaviour:
    def test_the_pack_never_reports_satisfied(self) -> None:
        """The engine downgrades a draft pack's satisfied verdicts."""
        from samanvaya.types import (
            ConsentMechanism, Declaration, GovernanceDeclaration, JurisdictionRef,
            NoticeDeclaration, Organisation, SafeguardPair,
        )

        generous = Declaration(
            schema_version="1.0",
            organisation=Organisation(legal_name="Acme", employee_count=900),
            jurisdictions=(JurisdictionRef("DE"),),
            declaration_author="adviser",
            purposes=("service delivery",),
            security_safeguards=(SafeguardPair("encryption", "AES-256"),),
            notice=NoticeDeclaration(described=True, describes_purpose=True,
                                     describes_personal_data=True, identifies_recipients=True,
                                     states_retention_period=True, states_controller_identity=True),
            consent_mechanism=ConsentMechanism(described=True),
            governance=GovernanceDeclaration(maintains_processing_records=True,
                                             processor_contracts_in_place=True,
                                             has_privacy_officer=True),
        )
        results = {f.result for f in pack.evaluate(generous, AS_AT, None)}
        assert ObligationResult.SATISFIED not in results

    def test_every_obligation_cites_an_instrument_and_provision(self) -> None:
        for f in pack.evaluate(_decl(), AS_AT, None):
            assert f.obligation.instrument.strip()
            assert f.obligation.provision.strip()
