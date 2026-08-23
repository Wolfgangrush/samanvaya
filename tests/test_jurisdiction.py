"""Acceptance tests for the jurisdiction resolver.

Authored BEFORE the implementation. Tests are not delegated.

The resolver is where A3 lives. Two federations, two failure modes:

* Flattening the United States or Canada into one regime produces **false
  negatives** — the adviser reports "compliant" and the client is exposed under
  a state or provincial statute. Banned by the PRD.
* Demanding that an organisation enumerate fifty states to prove it operates in
  none of them produces **false positives** and a report nobody reads. That is
  what ``sub_units_complete`` exists to prevent.

Sub-national units are ISO 3166-2 codes (``US-CA``, ``CA-QC``) so that "CA" as a
country always means Canada and never California.
"""

from __future__ import annotations

import pytest

from samanvaya.jurisdiction import expand, resolve
from samanvaya.types import (
    Declaration,
    JurisdictionRef,
    Organisation,
    RegimeId,
)


def _decl(*jurisdictions: JurisdictionRef) -> Declaration:
    return Declaration(
        schema_version="1.0",
        organisation=Organisation(legal_name="Acme"),
        jurisdictions=tuple(jurisdictions),
        declaration_author="adviser",
    )


class TestCountryToRegime:
    def test_india_maps_to_the_india_regime(self) -> None:
        assert RegimeId.INDIA in resolve(_decl(JurisdictionRef("IN"))).regimes

    def test_an_eu_member_state_maps_to_the_gdpr_regime(self) -> None:
        assert RegimeId.EU_GDPR in resolve(_decl(JurisdictionRef("DE"))).regimes

    def test_the_united_kingdom_is_never_swept_into_the_eu_regime(self) -> None:
        """The Brexit trap, and it outlives the UK pack being parked.

        This originally asserted GB resolves to UK_GDPR. The UK pack was parked on
        2026-08-20 with every obligation unsourced, so GB now resolves to nothing — but
        the dangerous failure was never "GB has no regime", it was "GB quietly gets
        assessed as an EU member state". A tool that did that would tell a British
        controller it had satisfied Regulation (EU) 2016/679 obligations that do not bind
        it, and miss the retained-law ones that do. That half of the test is permanent.
        """
        res = resolve(_decl(JurisdictionRef("GB")))
        assert RegimeId.EU_GDPR not in res.regimes
        assert res.regimes == frozenset()
        assert "GB" in res.unknown_countries, "GB was dropped without a word"

    def test_singapore_is_reported_as_uncovered_not_dropped(self) -> None:
        """Parked pack, so SG resolves to nothing — but must still be named."""
        res = resolve(_decl(JurisdictionRef("SG")))
        assert res.regimes == frozenset()
        assert "SG" in res.unknown_countries

    def test_country_code_ca_means_canada_never_california(self) -> None:
        res = resolve(_decl(JurisdictionRef("CA")))
        assert RegimeId.CANADA in res.regimes
        assert RegimeId.US not in res.regimes

    def test_country_names_are_accepted_as_well_as_codes(self) -> None:
        assert RegimeId.INDIA in resolve(_decl(JurisdictionRef("India"))).regimes

    def test_an_unknown_country_is_reported_never_silently_dropped(self) -> None:
        res = resolve(_decl(JurisdictionRef("Wakanda")))
        assert res.unknown_countries == ("Wakanda",)
        assert res.regimes == frozenset()


class TestFederationsExpandAsTrees:
    def test_us_with_named_states_expands_to_one_target_per_state(self) -> None:
        res = resolve(_decl(JurisdictionRef("US", ("US-CA", "US-CO"))))
        assert (RegimeId.US, "US-CA") in res.targets
        assert (RegimeId.US, "US-CO") in res.targets

    def test_us_always_carries_a_federal_target_alongside_its_states(self) -> None:
        """HIPAA, GLBA, COPPA and FERPA bind federally, whatever the state list."""
        res = resolve(_decl(JurisdictionRef("US", ("US-CA",))))
        assert (RegimeId.US, None) in res.targets

    def test_canada_always_carries_the_federal_pipeda_target(self) -> None:
        res = resolve(_decl(JurisdictionRef("CA", ("CA-ON",))))
        assert (RegimeId.CANADA, None) in res.targets

    def test_a_province_other_than_quebec_never_triggers_quebec_law(self) -> None:
        res = resolve(_decl(JurisdictionRef("CA", ("CA-ON",))))
        assert (RegimeId.CANADA, "CA-QC") not in res.targets

    def test_quebec_is_targeted_only_when_declared(self) -> None:
        res = resolve(_decl(JurisdictionRef("CA", ("CA-QC",))))
        assert (RegimeId.CANADA, "CA-QC") in res.targets

    def test_unitary_regimes_carry_exactly_one_target_with_no_sub_unit(self) -> None:
        """India stands in for Singapore here, which was parked on 2026-08-20.

        The property under test is about UNITARY regimes generally — one target, no
        sub-unit — not about Singapore, so any covered unitary regime proves it.
        """
        res = resolve(_decl(JurisdictionRef("IN")))
        assert res.targets == ((RegimeId.INDIA, None),)


class TestIncompletenessNotice:
    def test_us_without_states_and_not_complete_emits_exactly_one_notice(self) -> None:
        """A3. One notice per country. Never one per obligation."""
        res = resolve(_decl(JurisdictionRef("US")))
        us_notices = [n for n in res.notices if n.regime is RegimeId.US]
        assert len(us_notices) == 1

    def test_that_notice_names_the_country(self) -> None:
        res = resolve(_decl(JurisdictionRef("US")))
        assert "US" in res.notices[0].country

    def test_asserting_completeness_suppresses_the_notice(self) -> None:
        res = resolve(_decl(JurisdictionRef("US", (), sub_units_complete=True)))
        assert res.notices == ()

    def test_completeness_is_recorded_per_regime_for_the_engine(self) -> None:
        res = resolve(_decl(JurisdictionRef("US", (), sub_units_complete=True)))
        assert res.completeness[RegimeId.US] is True

    def test_incompleteness_is_recorded_per_regime_for_the_engine(self) -> None:
        res = resolve(_decl(JurisdictionRef("US")))
        assert res.completeness[RegimeId.US] is False

    def test_naming_states_does_not_by_itself_assert_completeness(self) -> None:
        """Listing California says nothing about Colorado."""
        res = resolve(_decl(JurisdictionRef("US", ("US-CA",))))
        assert res.completeness[RegimeId.US] is False
        assert len([n for n in res.notices if n.regime is RegimeId.US]) == 1

    def test_a_unitary_regime_never_produces_an_incompleteness_notice(self) -> None:
        assert resolve(_decl(JurisdictionRef("SG"))).notices == ()

    def test_two_incomplete_federations_produce_one_notice_each(self) -> None:
        res = resolve(_decl(JurisdictionRef("US"), JurisdictionRef("CA")))
        assert len(res.notices) == 2
        assert {n.regime for n in res.notices} == {RegimeId.US, RegimeId.CANADA}


class TestEdgeCases:
    def test_duplicate_country_declarations_do_not_duplicate_targets(self) -> None:
        res = resolve(_decl(JurisdictionRef("IN"), JurisdictionRef("IN")))
        assert res.targets.count((RegimeId.INDIA, None)) == 1

    def test_duplicate_sub_units_do_not_duplicate_targets(self) -> None:
        res = resolve(_decl(JurisdictionRef("US", ("US-CA", "US-CA"))))
        assert res.targets.count((RegimeId.US, "US-CA")) == 1

    def test_a_sub_unit_on_a_unitary_country_is_reported_not_silently_ignored(self) -> None:
        res = resolve(_decl(JurisdictionRef("IN", ("IN-MH",))))
        assert res.stray_sub_units

    def test_a_sub_unit_whose_prefix_contradicts_its_country_is_reported(self) -> None:
        """Declaring 'US-CA' under Canada is a declaration error, not a Quebec run."""
        res = resolve(_decl(JurisdictionRef("CA", ("US-CA",))))
        assert res.stray_sub_units

    def test_sub_unit_codes_are_matched_case_insensitively(self) -> None:
        res = resolve(_decl(JurisdictionRef("us", ("us-ca",))))
        assert (RegimeId.US, "US-CA") in res.targets

    def test_no_jurisdictions_declared_yields_no_targets_and_says_so(self) -> None:
        res = resolve(_decl())
        assert res.targets == ()
        assert res.regimes == frozenset()

    def test_targets_are_deterministically_ordered(self) -> None:
        a = resolve(_decl(JurisdictionRef("US", ("US-CO", "US-CA")), JurisdictionRef("IN")))
        b = resolve(_decl(JurisdictionRef("IN"), JurisdictionRef("US", ("US-CA", "US-CO"))))
        assert a.targets == b.targets


class TestExpandConvenience:
    def test_expand_returns_the_same_pairs_as_resolve(self) -> None:
        decl = _decl(JurisdictionRef("US", ("US-CA",)), JurisdictionRef("IN"))
        assert tuple(expand(decl)) == resolve(decl).targets

    def test_expand_returns_a_sequence_of_regime_subunit_pairs(self) -> None:
        pairs = expand(_decl(JurisdictionRef("IN")))
        assert list(pairs) == [(RegimeId.INDIA, None)]
