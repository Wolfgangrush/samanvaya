"""Acceptance tests for the obligation engine.

Authored BEFORE the implementation. Tests are not delegated.

The engine is where three of the seven accepted findings actually bite.

**A4 — `applies_if`.** Without it every obligation applies to everybody, so a
twelve-person startup is told it has failed a records-of-processing duty that does not
reach it. With it, the engine can say `not_applicable`. The trap is the missing input:
if the declaration does not state the employee count, the answer is `contested`, never
a silent pass and never a gap.

**A6 — `depends_on`.** "Appoint an officer if you are a Significant Data Fiduciary"
cannot be evaluated before the SDF determination. Evaluated in the wrong order the
finding oscillates, and a false stable answer on the highest-stakes obligation in the
India rail is exactly the failure the adviser carries indemnity for. A cycle is a pack
**load** error — discovered when the pack is loaded, not as a surprise mid-run.

**A3 — the incompleteness notice** appears once per country on the `EngineResult`, not
once per obligation.
"""

from __future__ import annotations

from datetime import date

import pytest

from samanvaya.engine import evaluate_obligations, run
from samanvaya.types import (
    AppliesIf,
    Declaration,
    JurisdictionRef,
    Obligation,
    ObligationResult,
    ObligationTopic,
    Organisation,
    PackInfo,
    PackLoadError,
    PredicateOp,
    RegimeId,
    SubTopic,
)

AS_AT = date(2026, 8, 19)


def _decl(**org: object) -> Declaration:
    return Declaration(
        schema_version="1.0",
        organisation=Organisation(legal_name="Acme", **org),  # type: ignore[arg-type]
        jurisdictions=(JurisdictionRef("IN", (), True),),
        declaration_author="adviser",
    )


def _ob(oid: str, **kw: object) -> Obligation:
    base: dict[str, object] = {
        "obligation_id": oid,
        "regime": RegimeId.EU_GDPR,
        "sub_unit": None,
        "instrument": "Regulation (EU) 2016/679",
        "provision": "Article 30(5)",
        "topic": ObligationTopic.RECORDS,
        "sub_topic": SubTopic("records_threshold", "250", "persons"),
        "obligation_summary": "Records of processing activities.",
        "citation_pointer": "Regulation (EU) 2016/679, Article 30(5)",
    }
    base.update(kw)
    return Obligation(**base)  # type: ignore[arg-type]


def _always_satisfied(_ob: Obligation, _d: Declaration) -> ObligationResult:
    return ObligationResult.SATISFIED


class TestAppliesIf:
    def test_an_org_below_the_threshold_is_not_applicable(self) -> None:
        ob = _ob(
            "eu.records",
            applies_if=(AppliesIf("organisation.employee_count", PredicateOp.GTE, 250),),
        )
        findings = evaluate_obligations([ob], _decl(employee_count=40), AS_AT, _always_satisfied)
        assert findings[0].result is ObligationResult.NOT_APPLICABLE

    def test_an_org_above_the_threshold_is_evaluated_normally(self) -> None:
        ob = _ob(
            "eu.records",
            applies_if=(AppliesIf("organisation.employee_count", PredicateOp.GTE, 250),),
        )
        findings = evaluate_obligations([ob], _decl(employee_count=900), AS_AT, _always_satisfied)
        assert findings[0].result is ObligationResult.SATISFIED

    def test_a_missing_input_is_contested_never_a_silent_pass(self) -> None:
        ob = _ob(
            "eu.records",
            applies_if=(AppliesIf("organisation.employee_count", PredicateOp.GTE, 250),),
        )
        findings = evaluate_obligations([ob], _decl(), AS_AT, _always_satisfied)
        assert findings[0].result is ObligationResult.CONTESTED

    def test_the_contested_rationale_names_the_missing_path(self) -> None:
        ob = _ob(
            "eu.records",
            applies_if=(AppliesIf("organisation.employee_count", PredicateOp.GTE, 250),),
        )
        findings = evaluate_obligations([ob], _decl(), AS_AT, _always_satisfied)
        assert "organisation.employee_count" in findings[0].rationale

    def test_an_unresolvable_path_is_contested_not_a_crash(self) -> None:
        ob = _ob("eu.x", applies_if=(AppliesIf("organisation.no_such_field", PredicateOp.TRUTHY, True),))
        findings = evaluate_obligations([ob], _decl(), AS_AT, _always_satisfied)
        assert findings[0].result is ObligationResult.CONTESTED

    def test_all_predicates_must_hold_for_the_obligation_to_apply(self) -> None:
        ob = _ob(
            "eu.x",
            applies_if=(
                AppliesIf("organisation.employee_count", PredicateOp.GTE, 250),
                AppliesIf("organisation.is_public_authority", PredicateOp.EQ, True),
            ),
        )
        findings = evaluate_obligations(
            [ob], _decl(employee_count=900, is_public_authority=False), AS_AT, _always_satisfied
        )
        assert findings[0].result is ObligationResult.NOT_APPLICABLE

    @pytest.mark.parametrize(
        ("op", "declared", "expected_applies"),
        [
            (PredicateOp.EQ, 250, True),
            (PredicateOp.NE, 250, False),
            (PredicateOp.GT, 250, False),
            (PredicateOp.GTE, 250, True),
            (PredicateOp.LT, 250, False),
            (PredicateOp.LTE, 250, True),
        ],
    )
    def test_each_comparison_operator_behaves(
        self, op: PredicateOp, declared: int, expected_applies: bool
    ) -> None:
        ob = _ob("eu.x", applies_if=(AppliesIf("organisation.employee_count", op, 250),))
        findings = evaluate_obligations([ob], _decl(employee_count=declared), AS_AT, _always_satisfied)
        got = findings[0].result is ObligationResult.SATISFIED
        assert got is expected_applies

    def test_truthy_on_a_declared_false_does_not_apply(self) -> None:
        ob = _ob("eu.x", applies_if=(AppliesIf("organisation.is_healthcare_provider", PredicateOp.TRUTHY, True),))
        findings = evaluate_obligations([ob], _decl(is_healthcare_provider=False), AS_AT, _always_satisfied)
        assert findings[0].result is ObligationResult.NOT_APPLICABLE


class TestDependsOn:
    def test_obligations_are_evaluated_in_dependency_order(self) -> None:
        order: list[str] = []

        def recording(ob: Obligation, _d: Declaration) -> ObligationResult:
            order.append(ob.obligation_id)
            return ObligationResult.SATISFIED

        dependent = _ob("in.sdf.officer", depends_on=("in.sdf.determination",))
        determination = _ob("in.sdf.determination")
        evaluate_obligations([dependent, determination], _decl(), AS_AT, recording)
        assert order.index("in.sdf.determination") < order.index("in.sdf.officer")

    def test_a_dependency_that_is_not_applicable_makes_the_dependent_not_applicable(self) -> None:
        def by_id(ob: Obligation, _d: Declaration) -> ObligationResult:
            if ob.obligation_id == "in.sdf.determination":
                return ObligationResult.NOT_APPLICABLE
            return ObligationResult.SATISFIED

        findings = evaluate_obligations(
            [_ob("in.sdf.determination"), _ob("in.sdf.officer", depends_on=("in.sdf.determination",))],
            _decl(), AS_AT, by_id,
        )
        officer = next(f for f in findings if f.obligation.obligation_id == "in.sdf.officer")
        assert officer.result is ObligationResult.NOT_APPLICABLE

    def test_a_contested_dependency_makes_the_dependent_contested(self) -> None:
        def by_id(ob: Obligation, _d: Declaration) -> ObligationResult:
            if ob.obligation_id == "in.sdf.determination":
                return ObligationResult.CONTESTED
            return ObligationResult.SATISFIED

        findings = evaluate_obligations(
            [_ob("in.sdf.determination"), _ob("in.sdf.officer", depends_on=("in.sdf.determination",))],
            _decl(), AS_AT, by_id,
        )
        officer = next(f for f in findings if f.obligation.obligation_id == "in.sdf.officer")
        assert officer.result is ObligationResult.CONTESTED

    def test_an_unresolved_dependency_is_contested_not_a_crash(self) -> None:
        findings = evaluate_obligations(
            [_ob("in.sdf.officer", depends_on=("in.sdf.nonexistent",))], _decl(), AS_AT, _always_satisfied
        )
        assert findings[0].result is ObligationResult.CONTESTED
        assert "in.sdf.nonexistent" in findings[0].rationale

    def test_a_satisfied_dependency_lets_the_dependent_evaluate(self) -> None:
        findings = evaluate_obligations(
            [_ob("a"), _ob("b", depends_on=("a",))], _decl(), AS_AT, _always_satisfied
        )
        assert all(f.result is ObligationResult.SATISFIED for f in findings)

    def test_a_dependency_cycle_is_a_pack_load_error(self) -> None:
        """A6. Discovered on load, never as a surprise mid-run."""
        with pytest.raises(PackLoadError):
            evaluate_obligations(
                [_ob("a", depends_on=("b",)), _ob("b", depends_on=("a",))],
                _decl(), AS_AT, _always_satisfied,
            )

    def test_a_self_dependency_is_a_pack_load_error(self) -> None:
        with pytest.raises(PackLoadError):
            evaluate_obligations([_ob("a", depends_on=("a",))], _decl(), AS_AT, _always_satisfied)

    def test_the_cycle_error_names_the_obligations_involved(self) -> None:
        with pytest.raises(PackLoadError) as exc:
            evaluate_obligations(
                [_ob("a", depends_on=("b",)), _ob("b", depends_on=("a",))],
                _decl(), AS_AT, _always_satisfied,
            )
        assert "a" in str(exc.value) and "b" in str(exc.value)


class TestInForceFiltering:
    def test_an_obligation_not_yet_commenced_is_never_satisfied(self) -> None:
        ob = _ob("future", in_force_from=date(2027, 5, 13))
        findings = evaluate_obligations([ob], _decl(), AS_AT, _always_satisfied)
        assert findings[0].result is not ObligationResult.SATISFIED

    def test_a_repealed_obligation_is_never_satisfied(self) -> None:
        ob = _ob("past", in_force_until=date(2020, 1, 1))
        findings = evaluate_obligations([ob], _decl(), AS_AT, _always_satisfied)
        assert findings[0].result is not ObligationResult.SATISFIED

    def test_the_rationale_explains_that_it_is_not_in_force(self) -> None:
        ob = _ob("future", in_force_from=date(2027, 5, 13))
        findings = evaluate_obligations([ob], _decl(), AS_AT, _always_satisfied)
        assert "force" in findings[0].rationale.lower()


class TestDraftPacksNeverSatisfy:
    def test_a_draft_pack_cannot_emit_satisfied(self) -> None:
        """A pack whose constants are not primary-sourced must not tick a box."""
        draft = PackInfo(
            pack_id="uk_gdpr", regime=RegimeId.UK_GDPR, version="0.1.0",
            covers_sub_units=frozenset(), as_at=AS_AT, draft=True, obligation_count=1,
            draft_reason="constants not yet primary-sourced",
        )
        findings = evaluate_obligations(
            [_ob("uk.x", regime=RegimeId.UK_GDPR)], _decl(), AS_AT, _always_satisfied, pack_info=draft
        )
        assert findings[0].result is not ObligationResult.SATISFIED
        assert findings[0].result is ObligationResult.CONTESTED

    def test_the_draft_rationale_says_why_and_names_the_reason(self) -> None:
        draft = PackInfo(
            pack_id="uk_gdpr", regime=RegimeId.UK_GDPR, version="0.1.0",
            covers_sub_units=frozenset(), as_at=AS_AT, draft=True, obligation_count=1,
            draft_reason="constants not yet primary-sourced",
        )
        findings = evaluate_obligations(
            [_ob("uk.x", regime=RegimeId.UK_GDPR)], _decl(), AS_AT, _always_satisfied, pack_info=draft
        )
        assert "draft" in findings[0].rationale.lower()
        assert "primary-sourced" in findings[0].rationale

    def test_a_draft_pack_may_still_report_a_gap(self) -> None:
        """Downgrading `satisfied` must not also suppress genuine gaps."""
        draft = PackInfo(
            pack_id="uk_gdpr", regime=RegimeId.UK_GDPR, version="0.1.0",
            covers_sub_units=frozenset(), as_at=AS_AT, draft=True, obligation_count=1,
            draft_reason="constants not yet primary-sourced",
        )
        findings = evaluate_obligations(
            [_ob("uk.x", regime=RegimeId.UK_GDPR)], _decl(), AS_AT,
            lambda _o, _d: ObligationResult.GAP, pack_info=draft,
        )
        assert findings[0].result is ObligationResult.GAP


class TestRun:
    def test_run_produces_a_rollup_per_declared_regime(self) -> None:
        result = run(_decl(), AS_AT)
        assert RegimeId.INDIA in result.per_regime

    def test_run_never_evaluates_an_undeclared_regime(self) -> None:
        result = run(_decl(), AS_AT)
        assert RegimeId.SINGAPORE_PDPA not in result.per_regime

    def test_the_result_carries_the_disclaimer(self) -> None:
        assert "not legal advice" in run(_decl(), AS_AT).disclaimer.lower()

    def test_the_result_carries_a_declaration_hash(self) -> None:
        assert len(run(_decl(), AS_AT).declaration_hash) == 64

    def test_the_incompleteness_notice_appears_once_per_country(self) -> None:
        """A3. Once per country on the result, never once per obligation."""
        decl = Declaration(
            schema_version="1.0",
            organisation=Organisation(legal_name="Acme"),
            jurisdictions=(JurisdictionRef("US"),),
            declaration_author="adviser",
        )
        result = run(decl, AS_AT)
        assert len([n for n in result.notices if n.regime is RegimeId.US]) == 1

    def test_rollup_counts_match_the_findings(self) -> None:
        result = run(_decl(), AS_AT)
        rollup = result.per_regime[RegimeId.INDIA]
        assert sum(rollup.counts.values()) == len(rollup.findings)

    def test_running_twice_gives_the_same_hash_and_the_same_verdicts(self) -> None:
        a, b = run(_decl(), AS_AT), run(_decl(), AS_AT)
        assert a.declaration_hash == b.declaration_hash
        assert [(f.obligation.obligation_id, f.result) for f in a.all_findings] == [
            (f.obligation.obligation_id, f.result) for f in b.all_findings
        ]

    def test_restricting_to_a_regime_evaluates_only_that_regime(self) -> None:
        result = run(_decl(), AS_AT, regimes=(RegimeId.INDIA,))
        assert set(result.per_regime) == {RegimeId.INDIA}
