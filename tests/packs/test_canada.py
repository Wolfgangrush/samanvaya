"""Acceptance tests for the Canada pack. Tests are not delegated.

Canada is a jurisdictional TREE, and the tree is the whole point. Two failure modes:

* Running Quebec Law 25 against an organisation that operates only in Ontario invents
  obligations it does not have.
* Flattening Canada into "PIPEDA" hides Quebec entirely from one that does operate there,
  which is a false negative the adviser carries indemnity for.

PIPEDA and SOR/2018-64 were read verbatim on laws-lois.justice.gc.ca. Quebec could not be
reached — legisquebec.gouv.qc.ca timed out — so every Quebec constant is unsourced.

Bill C-27, which would have replaced PIPEDA, died on the Order Paper in January 2025.
PIPEDA remains in force.
"""

from __future__ import annotations

from datetime import date

from samanvaya.packs.canada import pack
from samanvaya.types import ObligationResult, RegimeId

from ._helpers import decl

AS_AT = date(2026, 8, 19)


class TestMetadata:
    def test_the_regime_is_canada(self) -> None:
        assert pack.info().regime is RegimeId.CANADA

    def test_it_covers_quebec_as_a_sub_unit(self) -> None:
        assert "CA-QC" in pack.info().covers_sub_units

    def test_it_is_draft_because_quebec_is_unsourced(self) -> None:
        assert pack.info().draft is True
        assert "quebec" in pack.info().draft_reason.lower()

    def test_it_names_no_invented_instrument(self) -> None:
        assert "canada gdpr" not in " ".join(pack.info().instruments).lower()


class TestTheTree:
    def test_federal_evaluation_returns_pipeda_obligations(self) -> None:
        findings = pack.evaluate(decl("CA"), AS_AT, None)
        assert findings
        assert all(f.obligation.sub_unit is None for f in findings)

    def test_federal_evaluation_never_returns_a_quebec_obligation(self) -> None:
        """The single most important behaviour in this pack."""
        for f in pack.evaluate(decl("CA"), AS_AT, None):
            assert "qc" not in f.obligation.obligation_id.lower()

    def test_quebec_evaluation_returns_only_quebec_obligations(self) -> None:
        findings = pack.evaluate(decl("CA"), AS_AT, "CA-QC")
        assert findings
        for f in findings:
            assert f.obligation.sub_unit == "CA-QC"

    def test_an_unresearched_province_is_reported_not_silently_empty(self) -> None:
        """Raised by the cross-model audit on 2026-08-19, and it was right.

        This pack used to return nothing for Ontario or Alberta, while the US pack
        emitted an explicit unsourced obligation for an unresearched state. Two
        federations behaving differently in the same situation is itself a defect, and
        the silent one is the dangerous one: an omitted section reads to a client as a
        clean bill of health. Alberta and British Columbia each have their own
        private-sector privacy statute, and this pack has researched neither.
        """
        findings = pack.evaluate(decl("CA"), AS_AT, "CA-ON")
        assert len(findings) == 1
        assert findings[0].obligation.has_unsourced_constant()
        assert findings[0].result is ObligationResult.CONTESTED

    def test_the_unresearched_province_finding_names_the_province(self) -> None:
        f = pack.evaluate(decl("CA"), AS_AT, "CA-AB")[0]
        assert "CA-AB" in f.obligation.provision or "ca-ab" in f.obligation.obligation_id

    def test_a_non_canadian_sub_unit_returns_nothing(self) -> None:
        assert pack.evaluate(decl("CA"), AS_AT, "US-CA") == []


class TestVerifiedFederalConstants:
    def _by_id(self, oid: str):
        return next(
            f for f in pack.evaluate(decl("CA"), AS_AT, None)
            if f.obligation.obligation_id == oid
        )

    def test_the_breach_trigger_is_real_risk_of_significant_harm(self) -> None:
        ob = self._by_id("ca.breach.commissioner").obligation
        assert ob.sub_topic.value == "real risk of significant harm"
        assert ob.provision == "Section 10.1(1)"

    def test_individual_notification_cites_section_10_1_3(self) -> None:
        assert self._by_id("ca.breach.individual").obligation.provision == "Section 10.1(3)"

    def test_the_breach_record_retention_is_24_months(self) -> None:
        ob = self._by_id("ca.breach.records").obligation
        assert ob.sub_topic.value == "24"
        assert ob.sub_topic.unit == "months"

    def test_the_retention_obligation_cites_the_regulations(self) -> None:
        ob = self._by_id("ca.breach.records").obligation
        assert "SOR/2018-64" in ob.instrument or "SOR/2018-64" in ob.provision

    def test_schedule_1_carries_ten_principles(self) -> None:
        ob = self._by_id("ca.principles").obligation
        assert ob.sub_topic.value == "10"
        assert ob.provision == "Schedule 1"

    def test_no_federal_obligation_is_unsourced(self) -> None:
        for f in pack.evaluate(decl("CA"), AS_AT, None):
            assert not f.obligation.has_unsourced_constant(), f.obligation.obligation_id


class TestQuebecIsHonestlyUnsourced:
    def test_every_quebec_obligation_carries_a_fact_needed_marker(self) -> None:
        for f in pack.evaluate(decl("CA"), AS_AT, "CA-QC"):
            assert f.obligation.has_unsourced_constant(), f.obligation.obligation_id

    def test_every_quebec_finding_is_contested(self) -> None:
        for f in pack.evaluate(decl("CA"), AS_AT, "CA-QC"):
            assert f.result is ObligationResult.CONTESTED

    def test_no_quebec_penalty_figure_leaked_into_the_code(self) -> None:
        """A delegate reported CAD 25,000,000 and 4%. Neither is sourced."""
        import inspect

        source = inspect.getsource(pack)
        assert "25,000,000" not in source and "25000000" not in source

    def test_no_quebec_age_leaked_into_the_code(self) -> None:
        import inspect
        import re

        source = inspect.getsource(pack)
        body = "\n".join(
            line for line in source.splitlines() if "FACT NEEDED" not in line
        )
        assert not re.search(r"\b14\s*(?:years|$)", body)
