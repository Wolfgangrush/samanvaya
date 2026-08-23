"""Acceptance tests for the US pack. Tests are not delegated.

There is no "US GDPR" and no federal omnibus privacy statute. The US layer is federal
sectoral law plus roughly twenty comprehensive state statutes, and it is a TREE.

**Falsifier #1** lives here: a Californian hospital sits under CCPA (state) and HIPAA
(federal). Those must be two obligations that neither merge nor duplicate.

**The single most important behaviour in this pack** is what happens for a state nobody
has researched. Returning nothing would read as a clean bill of health. It must return an
explicit unsourced obligation instead, so an unresearched state is *reported* as
unresearched.

COPPA, HIPAA and the GLBA Safeguards Rule were read verbatim on ecfr.gov. CCPA could not
be reached, so it is unsourced.
"""

from __future__ import annotations

from datetime import date

from samanvaya.packs.us import pack
from samanvaya.types import ObligationResult, RegimeId

from ._helpers import decl

AS_AT = date(2026, 8, 19)
HOSPITAL = dict(is_healthcare_provider=True, offers_services_to_children=True,
                is_financial_institution=True, is_educational_institution=True)


class TestMetadata:
    def test_the_regime_is_the_us(self) -> None:
        assert pack.info().regime is RegimeId.US

    def test_it_covers_california_as_a_sub_unit(self) -> None:
        assert "US-CA" in pack.info().covers_sub_units

    def test_it_is_draft_and_says_why(self) -> None:
        assert pack.info().draft is True
        assert pack.info().draft_reason.strip()

    def test_no_instrument_is_called_a_gdpr(self) -> None:
        assert "gdpr" not in " ".join(pack.info().instruments).lower()


class TestTheTree:
    def test_federal_evaluation_returns_only_federal_obligations(self) -> None:
        findings = pack.evaluate(decl("US", **HOSPITAL), AS_AT, None)
        assert findings
        assert all(f.obligation.sub_unit is None for f in findings)

    def test_california_evaluation_returns_only_california_obligations(self) -> None:
        findings = pack.evaluate(decl("US", **HOSPITAL), AS_AT, "US-CA")
        assert findings
        assert all(f.obligation.sub_unit == "US-CA" for f in findings)

    def test_an_unresearched_state_is_reported_not_silently_empty(self) -> None:
        """Silence would read as a clean bill of health. It must not be silent."""
        findings = pack.evaluate(decl("US", **HOSPITAL), AS_AT, "US-CO")
        assert len(findings) == 1
        assert findings[0].obligation.has_unsourced_constant()
        assert findings[0].result is ObligationResult.CONTESTED

    def test_the_unresearched_state_obligation_names_the_state(self) -> None:
        f = pack.evaluate(decl("US", **HOSPITAL), AS_AT, "US-CO")[0]
        assert "US-CO" in f.obligation.provision or "us-co" in f.obligation.obligation_id

    def test_a_non_us_sub_unit_returns_nothing(self) -> None:
        assert pack.evaluate(decl("US"), AS_AT, "CA-QC") == []


class TestVerifiedFederalConstants:
    def _by_id(self, oid: str):
        return next(
            (f for f in pack.evaluate(decl("US", **HOSPITAL), AS_AT, None)
             if f.obligation.obligation_id == oid), None
        )

    def test_coppa_fixes_thirteen_and_cites_16_cfr_312_2(self) -> None:
        ob = self._by_id("us.coppa.age").obligation
        assert ob.sub_topic.value == "13"
        assert ob.provision == "16 CFR 312.2"

    def test_hipaa_individual_notice_is_sixty_days_and_cites_164_404_b(self) -> None:
        ob = self._by_id("us.hipaa.breach.individual").obligation
        assert ob.sub_topic.value == "60"
        assert ob.provision == "45 CFR 164.404(b)"

    def test_hipaa_secretary_notice_is_contemporaneous_not_sixty_days(self) -> None:
        """A delegate reported 60 days for the 500-or-more case. The rule says
        contemporaneously. This test exists because that error was made."""
        ob = self._by_id("us.hipaa.breach.secretary").obligation
        assert ob.sub_topic.value == "contemporaneous"
        assert ob.provision == "45 CFR 164.408(b)"
        assert "60 day" not in ob.obligation_summary.lower()

    def test_the_under_500_rule_is_recorded_separately(self) -> None:
        meta = dict(self._by_id("us.hipaa.breach.secretary").obligation.evaluation_metadata)
        assert "164.408(c)" in meta.get("under_500_rule", "")

    def test_the_glba_exemption_is_described_as_partial(self) -> None:
        """Reporting 'GLBA does not apply' below 5,000 consumers would be wrong."""
        ob = self._by_id("us.glba.safeguards").obligation
        assert ob.sub_topic.value == "5000"
        assert "partial" in ob.obligation_summary.lower()

    def test_the_glba_summary_names_the_four_disapplied_paragraphs(self) -> None:
        summary = self._by_id("us.glba.safeguards").obligation.obligation_summary
        assert "314.4" in summary

    def test_hipaa_security_cites_45_cfr_164_306(self) -> None:
        assert self._by_id("us.hipaa.security").obligation.provision == "45 CFR 164.306"


class TestSectoralApplicability:
    def test_a_non_healthcare_org_gets_not_applicable_for_hipaa(self) -> None:
        findings = pack.evaluate(decl("US", is_healthcare_provider=False), AS_AT, None)
        hipaa = [f for f in findings if "hipaa" in f.obligation.obligation_id]
        assert hipaa
        assert all(f.result is ObligationResult.NOT_APPLICABLE for f in hipaa)

    def test_an_undeclared_sector_is_contested_not_a_pass(self) -> None:
        """A4. 'Not stated' and 'not a hospital' are different findings."""
        findings = pack.evaluate(decl("US"), AS_AT, None)
        hipaa = [f for f in findings if "hipaa" in f.obligation.obligation_id]
        assert hipaa
        assert all(f.result is ObligationResult.CONTESTED for f in hipaa)


class TestCaliforniaIsHonestlyUnsourced:
    def test_every_california_obligation_is_unsourced_and_contested(self) -> None:
        findings = pack.evaluate(decl("US", **HOSPITAL), AS_AT, "US-CA")
        for f in findings:
            assert f.obligation.has_unsourced_constant()
            assert f.result is ObligationResult.CONTESTED

    def test_no_ccpa_revenue_threshold_leaked_into_the_code(self) -> None:
        """A delegate reported $25,000,000 / 100,000 consumers / 50 per cent."""
        import inspect

        source = inspect.getsource(pack)
        for figure in ("25,000,000", "100,000 consumers", "1798.140"):
            assert figure not in source, figure
