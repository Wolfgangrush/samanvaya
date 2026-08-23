"""The five falsifiers from `BMAD/04-BMAD-SPEC.md`, executed.

Authored by the maintainer. Tests are not delegated.

A falsifier is a statement of what would prove the design wrong. Writing them down and
never running them is the failure mode this file exists to prevent, so each one is a
test here, named for the falsifier it discharges.

**Falsifier 4 was live.** Before the fix on 2026-08-19, an organisation that declared it
had NOT been notified as a Significant Data Fiduciary was still reported as having a
*gap* on the Rule 13 twelve-monthly DPIA and audit. The India pack builds its Findings
directly against the upstream engine rather than through `evaluate_obligations`, so its
`depends_on` edges were never honoured, and the tool accused a client of failing a duty
that did not reach it. The fix moved dependency propagation into the engine's post-pass,
which every pack goes through. This file is the regression.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from samanvaya.declaration import load
from samanvaya.engine import run
from samanvaya.types import ObligationResult, RegimeId

FIXTURES = Path(__file__).parent / "fixtures"
AS_AT = date(2026, 8, 19)


class TestFalsifier1UsTreeSemantics:
    """If CCPA and HIPAA merge on one hospital, or the incompleteness notice is not
    emitted once, the US rail is a false-positive engine and the delta is lying."""

    def test_ccpa_and_hipaa_remain_two_distinct_obligations(self) -> None:
        result = run(load(FIXTURES / "us_hospital.json"), AS_AT)
        us = result.per_regime[RegimeId.US]
        slots = {f.obligation.slot_key for f in us.findings}
        assert len(slots) == len(us.findings), "two obligations collapsed into one slot"

    def test_the_hospital_is_evaluated_against_both_federal_and_state_law(self) -> None:
        result = run(load(FIXTURES / "us_hospital.json"), AS_AT)
        us = result.per_regime[RegimeId.US]
        sub_units = {f.obligation.sub_unit for f in us.findings}
        assert None in sub_units, "federal sectoral layer was not evaluated"
        assert "US-CA" in sub_units, "the declared state was not evaluated"

    def test_us_without_states_emits_exactly_one_incompleteness_notice(self) -> None:
        result = run(load(FIXTURES / "us_no_states_incomplete.json"), AS_AT)
        assert len([n for n in result.notices if n.regime is RegimeId.US]) == 1

    def test_that_notice_is_not_repeated_per_obligation(self) -> None:
        result = run(load(FIXTURES / "us_no_states_incomplete.json"), AS_AT)
        assert len(result.notices) < len(result.all_findings)

    def test_asserting_completeness_removes_the_notice(self) -> None:
        result = run(load(FIXTURES / "us_hospital.json"), AS_AT)
        assert [n for n in result.notices if n.regime is RegimeId.US] == []


class TestFalsifier2UpstreamContract:
    """If an upstream version bump produces an opaque TypeError or ImportError instead
    of a named, actionable error, the adviser loses the India rail with no recovery
    path, mid-engagement."""

    def test_a_version_bump_raises_a_named_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("dpdp")
        import dpdp

        from samanvaya.packs.india import adapter
        from samanvaya.types import UpstreamContractError

        monkeypatch.setattr(dpdp, "__version__", "0.3.0", raising=False)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        message = str(exc.value)
        assert "0.3.0" in message and "dpdp-law-to-code" in message
        assert "pin" in message.lower()

    def test_a_missing_upstream_package_is_named_not_an_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CLI must never surface a bare ImportError to an adviser.

        Patching `builtins.__import__` would be unreliable here: once `dpdp` is in
        `sys.modules` — which it is, as soon as any other test has touched it — the
        import hook is never consulted. The adapter resolves the package through
        `importlib.import_module` on every call precisely so the contract check cannot
        go stale, so that is what this test intercepts.
        """
        pytest.importorskip("dpdp")
        import importlib

        from samanvaya.packs.india import adapter
        from samanvaya.types import UpstreamContractError

        def refuse(name: str, *args: object, **kwargs: object) -> object:
            raise ImportError(f"no module named {name}")

        monkeypatch.setattr(adapter.importlib, "import_module", refuse, raising=True)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        assert "dpdp-law-to-code" in str(exc.value)


class TestFalsifier3Offline:
    """If a dependency can emit a network call the install-time audit did not flag, the
    offline posture is defeated. "Almost offline" is operationally and legally the same
    as "online"."""

    def test_the_dependency_audit_passes_on_the_declared_set(self) -> None:
        from samanvaya.offline_check import audit_dependencies

        audit_dependencies()

    def test_a_networking_dependency_would_be_refused(self) -> None:
        from samanvaya.offline_check import audit_dependencies

        with pytest.raises(RuntimeError):
            audit_dependencies(declared=("PyYAML", "requests"))

    def test_no_source_module_imports_a_network_client(self) -> None:
        import samanvaya

        root = Path(samanvaya.__file__).parent
        offenders = []
        for path in root.rglob("*.py"):
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith(("import ", "from ")) and any(
                    lib in s for lib in ("requests", "httpx", "urllib.request", "aiohttp")
                ):
                    offenders.append(f"{path.name}: {s}")
        assert offenders == [], offenders

    def test_a_full_run_makes_no_network_call(self, tmp_path: Path) -> None:
        """The strongest available check short of a syscall trace: run the real CLI with
        the socket tripwire armed and prove it completes."""
        pytest.importorskip("dpdp")
        from samanvaya.offline_check import install_tripwire, remove_tripwire
        from samanvaya.report import write

        install_tripwire()
        try:
            result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
            write(result, tmp_path / "report", "both")
        finally:
            remove_tripwire()
        assert (tmp_path / "report.md").is_file()


class TestFalsifier4DependencyOrder:
    """If the report emits satisfied or gap for an SDF-dependent obligation without
    first resolving the SDF determination, that is a false negative — or here, a false
    accusation — on the highest-stakes obligation in the India rail.

    THIS FALSIFIER FIRED FOR REAL on 2026-08-19. These are its regressions.
    """

    #: A6 can only be exercised AFTER the Rules commence. DPDP Rule 1(4) brings Rules 3
    #: and 5 to 16 into force eighteen months after publication of G.S.R. 846(E), so on
    #: any 2026 date the engine correctly returns NOT_APPLICABLE for Rule 13 on
    #: in-force grounds alone and the dependency logic never runs. Testing dependency
    #: propagation at an as-at date before commencement would pass for the wrong reason.
    AFTER_COMMENCEMENT = date(2027, 12, 1)

    def _india(self, fixture: str, as_at: date | None = None):
        pytest.importorskip("dpdp")
        result = run(load(FIXTURES / fixture), as_at or self.AFTER_COMMENCEMENT)
        return {f.obligation.obligation_id: f for f in result.per_regime[RegimeId.INDIA].findings}

    def test_a_non_sdf_is_not_accused_of_failing_the_sdf_duties(self) -> None:
        findings = self._india("canonical_declaration.json")
        determination = findings["in.sdf.determination"]
        obligations = findings["in.sdf.obligations"]
        assert determination.result is ObligationResult.NOT_APPLICABLE
        assert obligations.result is ObligationResult.NOT_APPLICABLE

    def test_the_rationale_explains_why_the_duty_is_not_engaged(self) -> None:
        """Asserting the ENGINE's exact wording would be testing the wrong layer.

        The adapter now refuses at source: seeing that the entity is not notified, it
        returns NOT_APPLICABLE itself rather than emitting a gap for the engine to
        correct downstream. That is the better behaviour — the fabricated risk scores
        never get built — but it means the engine's propagation text never appears. What
        must hold is that the adviser is told WHY, and the reason names the notification.
        """
        rationale = self._india("canonical_declaration.json")["in.sdf.obligations"].rationale
        assert "notif" in rationale.lower()
        assert "10(1)" in rationale

    def test_the_engine_still_propagates_for_a_pack_that_does_not_refuse_at_source(self) -> None:
        """The belt-and-braces path must stay live even though India no longer needs it."""
        from samanvaya.engine import _propagate_dependencies
        from samanvaya.types import (
            Finding, Obligation, ObligationTopic, SubTopic,
        )

        def ob(oid: str, deps: tuple[str, ...] = ()) -> Obligation:
            return Obligation(
                obligation_id=oid, regime=RegimeId.INDIA, sub_unit=None,
                instrument="X", provision="Y", topic=ObligationTopic.GOVERNANCE,
                sub_topic=SubTopic("d", "v"), obligation_summary="s",
                citation_pointer="c", depends_on=deps,
            )

        out = _propagate_dependencies((
            Finding(ob("a"), ObligationResult.NOT_APPLICABLE, "precondition unmet"),
            Finding(ob("b", ("a",)), ObligationResult.GAP, "underlying check failed"),
        ))
        dependent = next(f for f in out if f.obligation.obligation_id == "b")
        assert dependent.result is ObligationResult.NOT_APPLICABLE
        assert "a" in dependent.rationale
        assert "Original verdict" in dependent.rationale

    def test_the_dependent_never_reports_gap_while_its_precondition_is_unmet(self) -> None:
        findings = self._india("canonical_declaration.json")
        assert findings["in.sdf.obligations"].result is not ObligationResult.GAP

    def test_an_undeclared_sdf_status_makes_the_dependent_contested(self) -> None:
        """Not declared is not the same as not an SDF."""
        import dataclasses

        pytest.importorskip("dpdp")
        decl = load(FIXTURES / "canonical_declaration.json")
        undeclared = dataclasses.replace(
            decl,
            organisation=dataclasses.replace(
                decl.organisation, notified_significant_data_fiduciary=None
            ),
        )
        result = run(undeclared, self.AFTER_COMMENCEMENT)
        findings = {f.obligation.obligation_id: f for f in result.per_regime[RegimeId.INDIA].findings}
        assert findings["in.sdf.determination"].result is ObligationResult.CONTESTED
        assert findings["in.sdf.obligations"].result is ObligationResult.CONTESTED


class TestFalsifier5NoInventedCitations:
    """If any report emits a section number, rule number, date, threshold or deadline
    not sourced from the Verified Facts Brief, that is the malpractice vector the PRD
    bans. One guessed citation invalidates the report."""

    def test_every_finding_carries_an_instrument_and_a_provision(self) -> None:
        result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        for f in result.all_findings:
            assert f.obligation.instrument.strip(), f.obligation.obligation_id
            assert f.obligation.provision.strip(), f.obligation.obligation_id

    def test_every_finding_carries_a_citation_pointer(self) -> None:
        result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        for f in result.all_findings:
            assert f.obligation.citation_pointer.strip(), f.obligation.obligation_id

    def test_an_unsourced_constant_is_never_reported_as_satisfied_or_gap(self) -> None:
        """An unsourced constant can support neither a pass nor an accusation."""
        result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        for f in result.all_findings:
            if f.obligation.has_unsourced_constant():
                assert f.result is ObligationResult.CONTESTED, f.obligation.obligation_id

    def test_the_india_rules_constants_are_all_sourced(self) -> None:
        """Every India constant, Rules and Act alike, is read from a primary text.

        Until 2026-08-20 this test named one permitted exception — the number of limbs
        Sec 5(1) enumerates, which had never been read on the Act. It has now been read
        on the Act's Gazette text and is three, so the exception is gone and this asserts
        the empty set. Anything appearing here is a statutory number nobody sourced.
        """
        pytest.importorskip("dpdp")
        result = run(load(FIXTURES / "canonical_declaration.json"), AS_AT)
        offenders = {
            f.obligation.obligation_id
            for f in result.per_regime[RegimeId.INDIA].findings
            if f.obligation.has_unsourced_constant()
        }
        assert offenders == set(), offenders

    def test_no_finding_names_an_instrument_that_does_not_exist(self) -> None:
        result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        for f in result.all_findings:
            lowered = f.obligation.instrument.lower()
            for banned in ("us gdpr", "singapore gdpr", "canada gdpr"):
                assert banned not in lowered, f.obligation.obligation_id


class TestCutOverCriterionIndia:
    """The India rail becomes authoritative when the upstream suite passes unmodified
    against the pin AND the contract check passes. The third limb — the adviser
    verifying on one real engagement — is the maintainer's, and cannot be tested here."""

    @pytest.mark.slow
    def test_the_upstream_407_tests_pass_unmodified(self) -> None:
        clone = Path(__file__).resolve().parents[1].parent / "dpdp-law-to-code"
        if not (clone / "tests").is_dir():
            pytest.skip("upstream clone not present")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=clone, capture_output=True, text=True, timeout=900,
        )
        assert proc.returncode == 0, proc.stdout[-2000:]
        assert "407 passed" in proc.stdout

    def test_the_contract_check_passes(self) -> None:
        pytest.importorskip("dpdp")
        from samanvaya.packs.india import adapter

        assert adapter.contract_check() == adapter.EXPECTED_UPSTREAM_VERSION
