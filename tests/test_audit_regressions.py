"""Regressions for defects found by the cross-model audit on 2026-08-19.

Authored by the maintainer. Tests are not delegated.

Two delegates audited the halves of the codebase they had not written. Most of what
came back was real, and the pattern is worth recording: every confirmed defect below is
a **false clean bill** or a **false accusation** — the tool telling an adviser something
about a client that is not true. None of them broke a test that already existed, and none
would have been caught by reading the code for style.

Each test names the finding it discharges. Findings that did NOT survive verification are
recorded at the foot of this file, with the reason, so nobody re-litigates them.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from samanvaya.credentials import scan
from samanvaya.declaration import load
from samanvaya.types import ObligationResult, SafeguardPair

FIXTURES = Path(__file__).parent / "fixtures"
AS_AT = date(2026, 8, 19)


class TestCredentialFirewallWordBoundary:
    """The `\\b` in the secret-name pattern does not match between `_` and a letter,
    because both are word characters. So `my_password=` and `db_secret=` walked straight
    through the firewall whose entire purpose is to stop exactly that."""

    @pytest.mark.parametrize(
        "value",
        [
            "my_password=hunter2123",
            "db_secret=abcd1234efgh",
            "app_api_key=AKIAIOSFODNN7EXAMPLE",
            "prod_client_secret=xyz12345678",
            "the_token=eyJhbGciOiJIUzI1NiJ9abc",
        ],
    )
    def test_an_underscore_prefixed_secret_name_is_caught(self, value: str) -> None:
        assert scan({"recipients": [value]}) is not None, value

    @pytest.mark.parametrize(
        "value", ["password=hunter2123", "client_secret=xyz12345678"]
    )
    def test_the_plain_forms_still_work(self, value: str) -> None:
        assert scan({"recipients": [value]}) is not None, value

    @pytest.mark.parametrize(
        "value",
        [
            "Cloud hosting provider (contract dated 1 April 2026)",
            "Payment processor: settlement only, no card data retained",
            "encryption: AES-256 at rest and TLS 1.3 in transit",
            "our password policy is documented in the ISMS",
            "token bucket rate limiting is applied",
        ],
    )
    def test_widening_the_pattern_did_not_create_false_positives(self, value: str) -> None:
        assert scan({"recipients": [value]}) is None, value


class TestLogRetentionIsComparedNumerically:
    """`"1" in "21 days"` is true, so a twenty-one day retention satisfied the one-year
    minimum in DPDP Rule 6(1)(e). A substring test is not a comparison."""

    def _run(self, period: str):
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import adapter

        decl = load(FIXTURES / "canonical_declaration.json")
        amended = dataclasses.replace(
            decl,
            security_safeguards=tuple(
                SafeguardPair(p.control, period) if p.control == "log retention" else p
                for p in decl.security_safeguards
            ),
        )
        return next(
            f for f in adapter.run_checks(amended, AS_AT)
            if f.obligation.obligation_id == "in.security.log_retention"
        )

    @pytest.mark.parametrize("period", ["21 days", "10 months", "31 days", "6 months"])
    def test_a_period_under_one_year_does_not_satisfy(self, period: str) -> None:
        assert self._run(period).result is not ObligationResult.SATISFIED

    @pytest.mark.parametrize("period", ["one year", "1 year", "12 months", "2 years"])
    def test_a_period_of_at_least_one_year_satisfies(self, period: str) -> None:
        assert self._run(period).result is ObligationResult.SATISFIED

    @pytest.mark.parametrize("period", ["as long as necessary", "per policy", ""])
    def test_an_unparseable_period_is_contested_not_satisfied(self, period: str) -> None:
        """The adviser is told to go and ask, not given a pass."""
        assert self._run(period).result is ObligationResult.CONTESTED


class TestChildrenInputsAreNotFabricated:
    """Tracking, targeted advertising and detriment were hardcoded to `False` and fed to
    the upstream check. A client that tracks children could be reported compliant."""

    def _children_finding(self, **consent: object):
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import adapter
        from samanvaya.types import ChildProcessingDeclaration

        decl = load(FIXTURES / "canonical_declaration.json")
        amended = dataclasses.replace(
            decl,
            organisation=dataclasses.replace(
                decl.organisation, offers_services_to_children=True
            ),
            children=ChildProcessingDeclaration(**consent),  # type: ignore[arg-type]
        )
        return next(
            f for f in adapter.run_checks(amended, AS_AT)
            if f.obligation.obligation_id == "in.children.processing"
        )

    def test_undeclared_tracking_is_contested_not_a_pass(self) -> None:
        f = self._children_finding()
        assert f.result is ObligationResult.CONTESTED

    def test_the_rationale_names_the_undeclared_child_facts(self) -> None:
        f = self._children_finding()
        assert "children." in f.rationale

    def test_a_declared_tracker_is_a_gap_not_a_pass(self) -> None:
        f = self._children_finding(
            processes_data_of_children=True,
            verifiable_parental_consent=True,
            tracks_children=True,
            targeted_advertising_to_children=False,
            likely_detrimental_effect=False,
        )
        assert f.result is ObligationResult.GAP

    def test_a_fully_compliant_child_declaration_can_satisfy(self) -> None:
        f = self._children_finding(
            processes_data_of_children=True,
            verifiable_parental_consent=True,
            tracks_children=False,
            targeted_advertising_to_children=False,
            likely_detrimental_effect=False,
        )
        assert f.result is ObligationResult.SATISFIED


class TestNoticeLimbCountIsNotDerivedByArithmetic:
    """The Sec 5(1) limb count was computed as `SECURITY_MINIMUM_LIMBS - 1` — a statutory
    count invented by subtracting one from an unrelated Rule 6(1) constant."""

    def test_the_notice_dimension_carries_no_arithmetic_constant(self) -> None:
        pytest.importorskip("dpdp")
        import inspect

        from samanvaya.packs.india import adapter

        source = inspect.getsource(adapter)
        assert "SECURITY_MINIMUM_LIMBS - 1" not in source
        assert "SECURITY_MINIMUM_LIMBS-1" not in source

    def test_the_notice_limb_count_is_three_as_the_section_enumerates(self) -> None:
        """Sec 5(1) enumerates three limbs, and the value must be that — not six.

        Six is the trap, twice over. It is what the original bug produced
        (``SECURITY_MINIMUM_LIMBS - 1``, i.e. 7 - 1, borrowed from an unrelated Rule 6(1)
        constant), AND it is the number of notice fields the declaration happens to
        carry. A wrong answer that matches the field count looks right to a reader
        checking casually, which is why it survived until a cross-model audit.

        The statute lists (i) personal data and purpose, (ii) manner of exercising rights
        under Sec 6(4) and Sec 13, (iii) manner of complaining to the Board. Three.
        """
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import adapter

        ob = next(
            f.obligation for f in adapter.run_checks(
                load(FIXTURES / "canonical_declaration.json"), AS_AT
            ) if f.obligation.obligation_id == "in.notice.content"
        )
        assert ob.sub_topic.value == "3", ob.sub_topic.value
        assert ob.sub_topic.value != "6", "limb count matches the arithmetic bug"
        assert "FACT NEEDED" not in ob.sub_topic.value
        assert not ob.has_unsourced_constant()


class TestUpstreamComplianceIsReadExplicitly:
    """`bool(result)` worked only because the upstream dataclass happens to define
    `__bool__`. The contract check verifies the `compliant` ATTRIBUTE and not `__bool__`,
    so upstream could drop `__bool__` and every India check would silently become a pass."""

    def test_the_adapter_reads_the_compliant_attribute(self) -> None:
        pytest.importorskip("dpdp")
        import inspect

        from samanvaya.packs.india import adapter

        source = inspect.getsource(adapter)
        assert "upstream_compliant=bool(result)" not in source
        assert "result.compliant" in source

    def test_the_contract_check_would_notice_a_missing_compliant_attribute(self) -> None:
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import adapter

        assert "compliant" in adapter.REQUIRED_COMPLIANCE_RESULT_ATTRS


class TestIndiaCommencementIsHonoured:
    """DPDP Rule 1(4) commences Rules 3 and 5 to 16 EIGHTEEN MONTHS after publication of
    G.S.R. 846(E). On any 2026 as-at date those Rules are not yet in force, so reporting
    a client as failing them is a false accusation about a duty that has not arrived."""

    def _india(self, as_at: date):
        pytest.importorskip("dpdp")
        from samanvaya.engine import run
        from samanvaya.types import RegimeId

        result = run(load(FIXTURES / "canonical_declaration.json"), as_at)
        return {f.obligation.obligation_id: f for f in result.per_regime[RegimeId.INDIA].findings}

    def test_a_rules_obligation_is_not_in_force_in_august_2026(self) -> None:
        findings = self._india(date(2026, 8, 19))
        assert findings["in.security.rule6"].result is ObligationResult.NOT_APPLICABLE

    def test_the_rationale_says_it_is_not_in_force(self) -> None:
        findings = self._india(date(2026, 8, 19))
        assert "force" in findings["in.security.rule6"].rationale.lower()

    def test_the_same_obligation_binds_after_commencement(self) -> None:
        findings = self._india(date(2027, 12, 1))
        assert findings["in.security.rule6"].result is not ObligationResult.NOT_APPLICABLE

    def test_an_act_obligation_is_not_gated_by_the_rules_schedule(self) -> None:
        """The Act's own sections are not commenced by Rule 1; only the Rules are."""
        findings = self._india(date(2026, 8, 19))
        assert findings["in.consent.quality"].result is not ObligationResult.NOT_APPLICABLE

    def test_the_commencement_uncertainty_is_recorded_not_hidden(self) -> None:
        findings = self._india(date(2026, 8, 19))
        meta = dict(findings["in.security.rule6"].obligation.evaluation_metadata)
        assert any("publication" in v.lower() for v in meta.values())


class TestEuDeclaredFalseIsAGapNotContested:
    """"The client said no" and "the client did not say" are different findings, and the
    EU pack collapsed both to CONTESTED. An adviser was never told a client affirmatively
    fails Article 33(1)."""

    def _eu(self, **workflow: object):
        from samanvaya.packs.eu_gdpr import pack
        from samanvaya.types import BreachWorkflow

        decl = load(FIXTURES / "multi_regime.json")
        amended = dataclasses.replace(decl, breach_workflow=BreachWorkflow(**workflow))  # type: ignore[arg-type]
        return {
            f.obligation.obligation_id: f for f in pack.evaluate(amended, AS_AT, None)
        }

    def test_a_declared_refusal_to_notify_is_a_gap(self) -> None:
        f = self._eu(described=True, notifies_regulator=False)
        assert f["eu.breach.authority"].result is ObligationResult.GAP

    def test_a_declared_deadline_beyond_seventy_two_hours_is_a_gap(self) -> None:
        f = self._eu(described=True, notifies_regulator=True, regulator_deadline_hours=96)
        assert f["eu.breach.authority"].result is ObligationResult.GAP

    def test_an_undeclared_deadline_is_still_contested(self) -> None:
        f = self._eu(described=True, notifies_regulator=True)
        assert f["eu.breach.authority"].result is ObligationResult.CONTESTED

    def test_the_contested_rationale_names_the_missing_field(self) -> None:
        f = self._eu(described=True, notifies_regulator=True)
        assert "regulator_deadline_hours" in f["eu.breach.authority"].rationale


class TestPackMetadataMatchesImplementation:
    """`OBLIGATION_COUNT` was `len(REQUIRED_CHECKS) + 5`, which matched the real count by
    coincidence, and the "load-time mismatch" the docstring promised did not exist."""

    def test_the_india_obligation_count_matches_what_is_emitted(self) -> None:
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import pack

        findings = pack.evaluate(load(FIXTURES / "canonical_declaration.json"), AS_AT, None)
        assert pack.info().obligation_count == len(findings)

    def test_every_pack_count_matches_what_it_emits_for_its_own_regime(self) -> None:
        from samanvaya import registry
        from samanvaya.types import RegimeId

        decl = load(FIXTURES / "canonical_declaration.json")
        # registry.PACKS, not RegimeId: two regime identifiers survive with no pack
        # behind them since the 2026-08-20 parking.
        for regime in registry.PACKS:
            if regime is RegimeId.INDIA:
                pytest.importorskip("dpdp")
            module = registry.get(regime)
            emitted = len(module.evaluate(decl, AS_AT, None))
            declared = module.info().obligation_count
            if regime in (RegimeId.US, RegimeId.CANADA):
                # Federated packs split their obligations across the tree, so the
                # declared count is the whole set and the federal call is a subset.
                assert declared >= emitted, regime
            else:
                assert declared == emitted, regime


class TestNoUnusedStatutoryConstants:
    """An unused constant carrying a statutory figure is a claim nobody checks."""

    def test_the_consent_manager_net_worth_constant_is_not_dead(self) -> None:
        pytest.importorskip("dpdp")
        import inspect

        from samanvaya.packs.india import adapter

        source = inspect.getsource(adapter)
        if "CONSENT_MANAGER_NET_WORTH_INR" in source:
            assert source.count("CONSENT_MANAGER_NET_WORTH_INR") > 1, (
                "declared but never used"
            )


class TestRendererSharesTheMarkerConstant:
    """`report.py` grepped for the literal "FACT NEEDED" instead of importing
    FACT_NEEDED_PREFIX, so the renderer and the engine could drift apart."""

    def test_the_renderer_imports_the_shared_constant(self) -> None:
        import inspect

        from samanvaya import report

        source = inspect.getsource(report)
        assert "FACT_NEEDED_PREFIX" in source


# ---------------------------------------------------------------------------
# Findings that did NOT survive verification. Recorded so they are not re-raised.
#
# one delegate model #2 — "`_propagate_dependencies` drops `evaluation_metadata` and
#   `required_value` from downgraded findings." REJECTED: `Finding` has exactly five
#   fields and all five are carried. `evaluation_metadata` and `required_value` live on
#   `Obligation`, which is passed through unchanged.
#
# one delegate model #7 — "`_propagate_dependencies` is dead defensive code; every pack delegates to
#   `evaluate_obligations`." REJECTED: the India pack does NOT. It builds Findings
#   directly against the upstream engine, which is exactly why falsifier 4 fired. That
#   function is the fix, and `TestFalsifier4DependencyOrder` proves it is live.
#
# another delegate model #1 — "`bool(result)` is always True because ComplianceResult may not define
#   `__bool__`." PARTLY REJECTED: upstream DOES define `__bool__` returning `.compliant`,
#   so it was never wrong at runtime. The latent risk was real, though — the contract
#   check verifies the `compliant` attribute and not `__bool__` — so the code now reads
#   `.compliant` explicitly. See TestUpstreamComplianceIsReadExplicitly.
#
# another delegate model #11 — "Rule 14(3) does not impose a publication duty." REJECTED on the Gazette
#   text: Rule 14(3) reads "shall prominently publish on its website or app, or both, as
#   the case may be, within a reasonable period not exceeding ninety days under its
#   grievance redressal system...". The publication duty is in the rule. The sentence is
#   syntactically incomplete as printed in the Gazette, which is a drafting infelicity in
#   the instrument and not a transcription error here.
# ---------------------------------------------------------------------------


# ===========================================================================
# SECOND AUDIT — 2026-08-19, post-rename, before the first push.
#
# The first audit fixed twelve defects. This pass, run against the renamed tree, found
# nine more. Two were false clean bills that no existing test caught, and both were the
# same shape: a rule with a documented condition that the code never evaluated.
# ===========================================================================


class TestArticle30DerogationIsConditional:
    """Article 30(5) does not exempt every organisation below 250 persons.

    The derogation is defeated where the processing is likely to result in a risk, is not
    occasional, or includes Article 9(1) or Article 10 data. The pack cited all three
    carve-outs in its metadata and gated on the headcount alone, so a 200-person
    organisation processing special-category data was told it owed no records duty. It
    does.
    """

    def _ropa(self, **org: object):
        from samanvaya.packs.eu_gdpr import pack

        decl = load(FIXTURES / "canonical_declaration.json")
        amended = dataclasses.replace(
            decl, organisation=dataclasses.replace(decl.organisation, **org)  # type: ignore[arg-type]
        )
        return next(
            f for f in pack.evaluate(amended, AS_AT, None)
            if f.obligation.obligation_id == "eu.records.ropa"
        )

    def test_a_small_org_processing_special_category_data_is_not_exempt(self) -> None:
        f = self._ropa(employee_count=200, processes_special_category_data=True)
        assert f.result is not ObligationResult.NOT_APPLICABLE

    def test_a_small_org_that_has_not_declared_special_categories_is_contested(self) -> None:
        """The tool must not certify a derogation on a fact it never asked for."""
        f = self._ropa(employee_count=200, processes_special_category_data=None)
        assert f.result is ObligationResult.CONTESTED

    def test_a_large_org_owes_records_regardless_of_the_carve_outs(self) -> None:
        f = self._ropa(employee_count=900, processes_special_category_data=False)
        assert f.result is not ObligationResult.NOT_APPLICABLE

    def test_an_undeclared_headcount_is_contested_not_exempt(self) -> None:
        f = self._ropa(employee_count=None)
        assert f.result is ObligationResult.CONTESTED


class TestLawfulBasisIsNotSatisfiedByPurposes:
    """Article 6 requires an identified lawful basis. "We have purposes" is not one."""

    def _basis(self, **consent: object):
        from samanvaya.packs.eu_gdpr import pack
        from samanvaya.types import ConsentMechanism

        decl = load(FIXTURES / "canonical_declaration.json")
        amended = dataclasses.replace(
            decl,
            consent_mechanism=ConsentMechanism(**consent),  # type: ignore[arg-type]
            purposes=("marketing", "analytics"),
        )
        return next(
            f for f in pack.evaluate(amended, AS_AT, None)
            if f.obligation.obligation_id == "eu.lawful_basis"
        )

    def test_bare_purposes_do_not_satisfy(self) -> None:
        f = self._basis()
        assert f.result is not ObligationResult.SATISFIED

    def test_a_declared_mechanism_can_satisfy(self) -> None:
        f = self._basis(described=True, mechanism="explicit opt-in consent per purpose")
        assert f.result in (ObligationResult.SATISFIED, ObligationResult.CONTESTED)

    def test_a_declared_absence_of_any_mechanism_is_a_gap(self) -> None:
        f = self._basis(described=False)
        assert f.result is ObligationResult.GAP


class TestSection9AttachesToProcessingNotToOffering:
    """DPDP s.9 binds a fiduciary that PROCESSES a child's personal data.

    Gating it on `offers_services_to_children` told a hospital or a school back office —
    which processes a great deal of children's data while offering no service directed at
    children — that the duty did not engage.
    """

    def _children(self, **kids: object):
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import adapter
        from samanvaya.types import ChildProcessingDeclaration

        decl = load(FIXTURES / "canonical_declaration.json")
        amended = dataclasses.replace(
            decl,
            organisation=dataclasses.replace(
                decl.organisation, offers_services_to_children=False
            ),
            children=ChildProcessingDeclaration(**kids),  # type: ignore[arg-type]
        )
        return next(
            f for f in adapter.run_checks(amended, AS_AT)
            if f.obligation.obligation_id == "in.children.processing"
        )

    def test_processing_children_data_engages_the_duty_even_with_no_child_facing_service(
        self,
    ) -> None:
        f = self._children(
            described=True, processes_data_of_children=True,
            verifiable_parental_consent=False, tracks_children=False,
            targeted_advertising_to_children=False, likely_detrimental_effect=False,
        )
        assert f.result is ObligationResult.GAP

    def test_declaring_no_children_data_is_not_applicable(self) -> None:
        f = self._children(described=True, processes_data_of_children=False)
        assert f.result is ObligationResult.NOT_APPLICABLE

    def test_an_undeclared_processing_fact_is_contested(self) -> None:
        f = self._children(described=True)
        assert f.result is ObligationResult.CONTESTED
        assert "processes_data_of_children" in f.rationale

    def test_offering_services_never_decides_the_gate_on_its_own(self) -> None:
        """The substitution of one fact for the other IS the defect."""
        f = self._children(described=True)
        assert f.result is not ObligationResult.NOT_APPLICABLE


class TestRule7IndividualNoticeReadsTheDeclaredTrigger:
    """Rule 7(1) requires intimation to each affected Data Principal WITHOUT DELAY.

    A client declaring it notifies "only when a data principal complains" was reported
    satisfied, because the evaluator read the boolean and ignored the trigger field the
    schema carries for exactly this.
    """

    def _principal(self, **workflow: object):
        pytest.importorskip("dpdp")
        from samanvaya.engine import run
        from samanvaya.types import RegimeId

        decl = load(FIXTURES / "canonical_declaration.json")
        amended = dataclasses.replace(
            decl, breach_workflow=dataclasses.replace(decl.breach_workflow, **workflow)  # type: ignore[arg-type]
        )
        result = run(amended, date(2027, 12, 1))
        return next(
            f for f in result.per_regime[RegimeId.INDIA].findings
            if f.obligation.obligation_id == "in.breach.principal"
        )

    def test_a_complaint_conditioned_trigger_is_not_satisfied(self) -> None:
        f = self._principal(
            notifies_affected_individuals=True,
            individual_notification_trigger="only when a data principal complains",
        )
        assert f.result is not ObligationResult.SATISFIED

    def test_a_without_delay_trigger_satisfies(self) -> None:
        f = self._principal(
            notifies_affected_individuals=True,
            individual_notification_trigger="without delay, on becoming aware",
        )
        assert f.result is ObligationResult.SATISFIED

    def test_an_undeclared_trigger_is_contested(self) -> None:
        """Explicitly None. The canonical fixture already declares a without-delay
        trigger, so inheriting it would have tested the satisfied path twice and the
        undeclared path never."""
        f = self._principal(
            notifies_affected_individuals=True, individual_notification_trigger=None
        )
        assert f.result is ObligationResult.CONTESTED

    def test_a_declared_refusal_to_notify_is_a_gap(self) -> None:
        f = self._principal(notifies_affected_individuals=False)
        assert f.result is ObligationResult.GAP


class TestIndiaPackHonoursAsAtWhenCalledDirectly:
    """Every other pack routes through `evaluate_obligations` and honours `as_at`.

    India built its findings directly, so `pack.evaluate()` returned `contested` where
    `engine.run()` returned `not_applicable`. A pack that is only correct when called
    through one particular caller is not honouring its contract.
    """

    def test_a_direct_pack_call_applies_the_in_force_rule(self) -> None:
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import pack

        decl = load(FIXTURES / "canonical_declaration.json")
        direct = {
            f.obligation.obligation_id: f.result
            for f in pack.evaluate(decl, date(2026, 8, 19), None)
        }
        assert direct["in.security.rule6"] is ObligationResult.NOT_APPLICABLE

    def test_the_direct_call_and_the_engine_agree(self) -> None:
        pytest.importorskip("dpdp")
        from samanvaya.engine import run
        from samanvaya.packs.india import pack
        from samanvaya.types import RegimeId

        decl = load(FIXTURES / "canonical_declaration.json")
        as_at = date(2026, 8, 19)
        direct = {f.obligation.obligation_id: f.result for f in pack.evaluate(decl, as_at, None)}
        engine = {
            f.obligation.obligation_id: f.result
            for f in run(decl, as_at).per_regime[RegimeId.INDIA].findings
        }
        assert direct == engine


class TestUnsourcedAssertionVersusStatedCaveat:
    """An unsourced ASSERTION disqualifies a finding. A stated CAVEAT qualifies it.

    Collapsing the two forced every India Rules obligation to `contested` over a
    one-day question about a Gazette publication date, gutting the one rail whose
    substance is fully sourced.
    """

    def _ob(self, metadata: tuple[tuple[str, str], ...]):
        from samanvaya.types import (
            Obligation, ObligationTopic, RegimeId, SubTopic, fact_needed,
        )

        del fact_needed
        return Obligation(
            obligation_id="x", regime=RegimeId.INDIA, sub_unit=None, instrument="I",
            provision="P", topic=ObligationTopic.SECURITY, sub_topic=SubTopic("d", "v"),
            obligation_summary="s", citation_pointer="c", evaluation_metadata=metadata,
        )

    def test_a_note_key_is_a_caveat_and_does_not_disqualify(self) -> None:
        from samanvaya.types import fact_needed

        ob = self._ob((("commencement_note", fact_needed("which date?")),))
        assert ob.has_unsourced_constant() is False
        assert ob.has_unsourced_caveat() is True

    def test_any_other_metadata_key_is_an_assertion_and_disqualifies(self) -> None:
        from samanvaya.types import fact_needed

        ob = self._ob((("member_state_derogation", fact_needed("which states?")),))
        assert ob.has_unsourced_constant() is True

    def test_the_engine_downgrades_an_unsourced_assertion_to_contested(self) -> None:
        """Enforced in the engine, not merely asserted in a test."""
        from samanvaya.engine import run
        from samanvaya.types import RegimeId

        result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        for f in result.all_findings:
            if f.obligation.has_unsourced_constant():
                assert f.result is ObligationResult.CONTESTED, f.obligation.obligation_id

    def test_india_rules_obligations_survive_the_commencement_caveat(self) -> None:
        """The caveat must not gut the rail whose substance IS sourced."""
        pytest.importorskip("dpdp")
        from samanvaya.engine import run
        from samanvaya.types import RegimeId

        result = run(load(FIXTURES / "canonical_declaration.json"), date(2027, 12, 1))
        india = result.per_regime[RegimeId.INDIA].findings
        substantive = [f for f in india if f.result is not ObligationResult.CONTESTED]
        assert substantive, "every India finding collapsed to contested"
