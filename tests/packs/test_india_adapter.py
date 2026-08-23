"""Acceptance tests for the India adapter over `dpdp-law-to-code`.

Authored BEFORE the implementation. Tests are not delegated.

India is the correctness anchor. It is the only rail whose constants are settled on
the primary Gazette text, and the only one with an existing tested engine — 407
upstream tests — standing behind it. Two things therefore have to hold absolutely.

**A7, falsifier #2.** If the upstream package changes its `ComplianceResult` shape or
a `check_*` signature, the adapter must fail with a *named, actionable* error that
says which upstream version is installed and what did not match. An opaque
`TypeError` or `ImportError` at the moment a finding is needed means the adviser
loses the India rail with no recovery path, mid-engagement.

**No fabricated inputs.** Where the declaration does not state a fact, the adapter
must NOT hand the upstream engine a `False` and report the resulting gap. "The client
did not say" and "the client said no" are different findings, and only the second is
a gap. Undeclared facts resolve to `contested` without an upstream call.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from samanvaya.declaration import load
from samanvaya.types import (
    Finding,
    ObligationResult,
    RegimeId,
    UpstreamContractError,
)

pytest.importorskip("dpdp", reason="pinned dpdp-law-to-code is not importable")

from samanvaya.packs.india import adapter  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AS_AT = date(2026, 8, 19)
UPSTREAM_CLONE = Path(__file__).resolve().parents[2].parent / "dpdp-law-to-code"


@pytest.fixture
def canonical():
    return load(FIXTURES / "canonical_declaration.json")


class TestContractCheckPasses:
    def test_the_contract_check_passes_against_the_pinned_upstream(self) -> None:
        assert adapter.contract_check() == adapter.EXPECTED_UPSTREAM_VERSION

    def test_the_expected_version_is_pinned_not_inferred(self) -> None:
        """Reading the version off the installed package would make the check vacuous."""
        assert isinstance(adapter.EXPECTED_UPSTREAM_VERSION, str)
        assert adapter.EXPECTED_UPSTREAM_VERSION.strip()

    def test_the_adapter_names_the_upstream_distribution(self) -> None:
        assert adapter.UPSTREAM_DISTRIBUTION == "dpdp-law-to-code"

    def test_the_required_check_functions_are_declared_not_discovered(self) -> None:
        """The contract is a fixed list. Discovering it from the package proves nothing."""
        assert len(adapter.REQUIRED_CHECKS) >= 6


class TestContractCheckFailsLoudly:
    """A7. Every one of these must raise UpstreamContractError, never a bare TypeError."""

    def test_a_version_bump_raises_a_named_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dpdp

        monkeypatch.setattr(dpdp, "__version__", "0.2.0", raising=False)
        with pytest.raises(UpstreamContractError):
            adapter.contract_check()

    def test_the_version_error_names_both_versions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dpdp

        monkeypatch.setattr(dpdp, "__version__", "0.2.0", raising=False)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        message = str(exc.value)
        assert "0.2.0" in message
        assert adapter.EXPECTED_UPSTREAM_VERSION in message

    def test_the_version_error_names_the_distribution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dpdp

        monkeypatch.setattr(dpdp, "__version__", "0.2.0", raising=False)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        assert "dpdp-law-to-code" in str(exc.value)

    def test_the_version_error_tells_the_reader_what_to_do(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Actionable means it says how to recover, not merely that something broke."""
        import dpdp

        monkeypatch.setattr(dpdp, "__version__", "0.2.0", raising=False)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        assert "pin" in str(exc.value).lower() or "re-verify" in str(exc.value).lower()

    def test_a_missing_compliance_result_attribute_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dpdp.types as upstream_types

        class Mutilated:
            compliant = True
            section = "Sec 6(1)"
            # `reason`, `citation` and `sub_results` have been removed upstream.

        monkeypatch.setattr(upstream_types, "ComplianceResult", Mutilated, raising=False)
        monkeypatch.setattr(
            sys.modules["dpdp"], "ComplianceResult", Mutilated, raising=False
        )
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        assert "citation" in str(exc.value) or "ComplianceResult" in str(exc.value)

    def test_a_missing_check_function_raises_and_names_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dpdp.notice as upstream_notice

        monkeypatch.delattr(upstream_notice, "check_notice", raising=False)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        assert "check_notice" in str(exc.value)

    def test_a_changed_check_signature_raises_and_names_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dpdp.notice as upstream_notice

        def check_notice(something_else: object, and_another: object) -> None:  # noqa: ANN401
            raise AssertionError("must never be called")

        monkeypatch.setattr(upstream_notice, "check_notice", check_notice)
        with pytest.raises(UpstreamContractError) as exc:
            adapter.contract_check()
        assert "check_notice" in str(exc.value)

    def test_run_checks_refuses_to_run_when_the_contract_is_broken(
        self, monkeypatch: pytest.MonkeyPatch, canonical
    ) -> None:
        """The check gates evaluation. It must not be advisory."""
        import dpdp

        monkeypatch.setattr(dpdp, "__version__", "0.2.0", raising=False)
        with pytest.raises(UpstreamContractError):
            adapter.run_checks(canonical, AS_AT)


class TestFindingsAreProperlyCited:
    def test_the_adapter_produces_findings(self, canonical) -> None:
        findings = adapter.run_checks(canonical, AS_AT)
        assert findings and all(isinstance(f, Finding) for f in findings)

    def test_every_finding_is_in_the_india_regime(self, canonical) -> None:
        assert all(f.obligation.regime is RegimeId.INDIA for f in adapter.run_checks(canonical, AS_AT))

    def test_every_finding_names_an_instrument_and_a_provision(self, canonical) -> None:
        for f in adapter.run_checks(canonical, AS_AT):
            assert f.obligation.instrument.strip()
            assert f.obligation.provision.strip()

    def test_the_instrument_is_the_real_statute_name(self, canonical) -> None:
        names = {f.obligation.instrument for f in adapter.run_checks(canonical, AS_AT)}
        assert names <= {
            "Digital Personal Data Protection Act 2023",
            "Digital Personal Data Protection Rules 2025",
        }

    def test_no_finding_uses_a_banned_regime_name(self, canonical) -> None:
        for f in adapter.run_checks(canonical, AS_AT):
            blob = (f.obligation.instrument + f.obligation.citation_pointer).lower()
            assert "gdpr" not in blob

    def test_every_upstream_section_is_traceable_from_the_citation_pointer(self, canonical) -> None:
        """The upstream `section` must be reachable from the human-facing pointer.

        Not `provision == upstream_section`: this tool's `provision` names the provision
        that fixes the constant being reported — DPDP Rule 13 for the twelve-month DPIA
        and audit cycle — while the upstream engine cites the section imposing the duty,
        Sec 10(2). Both citations are correct and neither substitutes for the other, so
        what has to hold is that the reader can get from the report to the upstream
        result without opening the machine metadata.
        """
        for f in adapter.run_checks(canonical, AS_AT):
            meta = dict(f.obligation.evaluation_metadata)
            if meta.get("source") == "upstream":
                assert meta["upstream_section"] in f.obligation.citation_pointer

    def test_upstream_citation_is_carried_verbatim(self, canonical) -> None:
        for f in adapter.run_checks(canonical, AS_AT):
            meta = dict(f.obligation.evaluation_metadata)
            if meta.get("source") == "upstream":
                assert meta.get("upstream_citation")
                assert meta["upstream_citation"] in f.obligation.citation_pointer

    def test_every_finding_records_the_upstream_version_it_came_from(self, canonical) -> None:
        for f in adapter.run_checks(canonical, AS_AT):
            meta = dict(f.obligation.evaluation_metadata)
            if meta.get("source") == "upstream":
                assert meta.get("upstream_version") == adapter.EXPECTED_UPSTREAM_VERSION

    #: The India RULES constants are all read verbatim from the Gazette. One ACT figure
    #: is not: how many limbs Sec 5(1) enumerates. That count used to be computed as
    #: `SECURITY_MINIMUM_LIMBS - 1` — a statutory number invented by subtracting one from
    #: an unrelated Rule 6(1) constant — until the cross-model audit caught it. It is now
    #: honestly marked unsourced, so this test names the single permitted exception rather
    #: than asserting zero and being quietly wrong.
    #: SOURCED 2026-08-20. The Sec 5(1) limb count was read on the Act's own Gazette text
    #: and is three. This set is now EMPTY and asserting zero is no longer "quietly wrong"
    #: — it is the point. A new entry appearing here means someone shipped a statutory
    #: number nobody read.
    KNOWN_UNSOURCED: set[str] = set()

    def test_no_unexpected_finding_carries_an_unsourced_constant(self, canonical) -> None:
        offenders = {
            f.obligation.obligation_id
            for f in adapter.run_checks(canonical, AS_AT)
            if f.obligation.has_unsourced_constant()
        }
        assert offenders <= self.KNOWN_UNSOURCED, offenders - self.KNOWN_UNSOURCED

    def test_no_india_constant_is_unsourced(self, canonical) -> None:
        """Every statutory number on the India rail traces to a primary text.

        This asserted the opposite until 2026-08-20 — it named ``in.notice.content`` as a
        permitted exception, because the Sec 5(1) limb count had never been read on the
        Act. An unsourced constant is not cosmetic: it makes
        ``has_unsourced_constant()`` true, which downgrades an otherwise SATISFIED
        finding to CONTESTED on every single India run. The count is now three, read on
        the Act's Gazette text, and the permitted-exception set is empty.
        """
        offenders = {
            f.obligation.obligation_id
            for f in adapter.run_checks(canonical, AS_AT)
            if f.obligation.has_unsourced_constant()
        }
        assert offenders == set(), offenders

    def test_obligation_ids_are_unique(self, canonical) -> None:
        ids = [f.obligation.obligation_id for f in adapter.run_checks(canonical, AS_AT)]
        assert len(ids) == len(set(ids))

    def test_running_twice_gives_identical_results(self, canonical) -> None:
        """No hidden state, no clock reads, no randomness in the conformance path."""
        a = adapter.run_checks(canonical, AS_AT)
        b = adapter.run_checks(canonical, AS_AT)
        assert [(f.obligation.obligation_id, f.result) for f in a] == [
            (f.obligation.obligation_id, f.result) for f in b
        ]


class TestUndeclaredFactsAreContestedNotGaps:
    def test_an_undeclared_notice_is_contested_not_a_gap(self, canonical) -> None:
        import dataclasses

        from samanvaya.types import NoticeDeclaration

        bare = dataclasses.replace(canonical, notice=NoticeDeclaration())
        notice_findings = [
            f for f in adapter.run_checks(bare, AS_AT) if f.obligation.topic.value == "notice"
        ]
        assert notice_findings
        assert all(f.result is ObligationResult.CONTESTED for f in notice_findings)

    def test_the_contested_rationale_names_the_missing_declaration_field(self, canonical) -> None:
        import dataclasses

        from samanvaya.types import NoticeDeclaration

        bare = dataclasses.replace(canonical, notice=NoticeDeclaration())
        for f in adapter.run_checks(bare, AS_AT):
            if f.result is ObligationResult.CONTESTED:
                assert "notice" in f.rationale.lower() or "declar" in f.rationale.lower()

    def test_undeclared_facts_never_produce_satisfied(self, canonical) -> None:
        import dataclasses

        from samanvaya.types import (
            BreachWorkflow,
            ConsentMechanism,
            GovernanceDeclaration,
            NoticeDeclaration,
        )

        from samanvaya.types import CrossBorderDeclaration, DsrWorkflow

        empty = dataclasses.replace(
            canonical,
            notice=NoticeDeclaration(),
            consent_mechanism=ConsentMechanism(),
            breach_workflow=BreachWorkflow(),
            governance=GovernanceDeclaration(),
            dsr_workflow=DsrWorkflow(),
            cross_border=CrossBorderDeclaration(),
            retention=(),
            security_safeguards=(),
        )
        results = {f.result for f in adapter.run_checks(empty, AS_AT)}
        assert ObligationResult.SATISFIED not in results


class TestUpstreamSuiteStillPasses:
    """Cut-over criterion: the upstream 407 tests must pass unmodified against the pin."""

    @pytest.mark.slow
    def test_the_upstream_test_suite_passes_unmodified(self) -> None:
        if not (UPSTREAM_CLONE / "tests").is_dir():
            pytest.skip("upstream clone not present")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=UPSTREAM_CLONE,
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert proc.returncode == 0, proc.stdout[-3000:]
        assert "407 passed" in proc.stdout, proc.stdout[-2000:]


class TestTheConsentRailActuallyRuns:
    """Regression. Found 2026-08-22, and the way it was found is the point.

    `_eval_consent_quality` builds its upstream kwargs by stripping the
    `consent_mechanism.` prefix off its own declaration paths. That works for six of
    the eight required fields, whose names happen to match upstream's, and fails for
    the two that do not: this schema calls them `limited_to_specified_purpose` and
    `withdrawal_as_easy_as_giving`, and `dpdp.types.ConsentRecord` calls them
    `is_limited_to_specified_purpose` and `is_withdrawable_easily`. Passing the
    stripped names raises a bare `TypeError` from the constructor.

    **It is reachable only when all eight required consent facts are declared**, because
    anything undeclared short-circuits at the `missing` guard above the call. No shipped
    example reaches it — `01-india-saas-startup.json` declares ONE of the eight — so the
    DPDP s.6 consent-quality rail had never executed to completion in any example or any
    test since the tool shipped.

    The reason nothing caught it is worth writing down: the product had no way to
    *produce* a fully-answered declaration. There was no form, the interview was a
    terminal flow nobody ran to the end, and every fixture was written by hand with gaps
    in it. The missing feature was hiding the bug. It surfaced the moment BMAD/08 part B
    made a complete declaration easy to build.

    This is also falsifier #2 firing for real, per this file's own docstring: the adviser
    gets an opaque `TypeError` at the moment a finding is needed, mid-engagement, with no
    recovery path. The rail must either produce a finding or raise
    `UpstreamContractError` — never a constructor error.
    """

    def _fully_declared(self, tmp_path: Path):
        """A declaration whose consent block leaves nothing undeclared."""
        import json

        source = json.loads((FIXTURES / "canonical_declaration.json").read_text())
        source["consent_mechanism"] = {
            "described": True,
            "is_free": True,
            "is_specific": True,
            "is_informed": True,
            "is_unconditional": True,
            "is_unambiguous": True,
            "has_clear_affirmative_action": True,
            "limited_to_specified_purpose": True,
            "withdrawal_as_easy_as_giving": True,
        }
        target = tmp_path / "fully_declared.json"
        target.write_text(json.dumps(source))
        return load(target)

    def test_a_fully_declared_consent_block_produces_a_finding(
        self, tmp_path: Path
    ) -> None:
        """The whole rail, end to end, on the input a real engagement produces."""
        findings = adapter.run_checks(self._fully_declared(tmp_path), AS_AT)
        assert findings, "the India rail returned nothing at all"

    def test_it_does_not_raise_a_bare_type_error(self, tmp_path: Path) -> None:
        """A6/A7: an opaque constructor error is the failure mode this pack forbids."""
        try:
            adapter.run_checks(self._fully_declared(tmp_path), AS_AT)
        except UpstreamContractError:
            pass  # named and actionable — allowed
        except TypeError as exc:  # pragma: no cover - the defect being fixed
            raise AssertionError(
                f"the consent rail raised a bare TypeError mid-run: {exc}"
            ) from exc

    def test_the_consent_finding_is_reached_not_short_circuited(
        self, tmp_path: Path
    ) -> None:
        """Prove the guarded branch actually executed rather than the missing-facts one."""
        findings = adapter.run_checks(self._fully_declared(tmp_path), AS_AT)
        consent = [
            f for f in findings if "Sec 6" in (f.obligation.citation_pointer or "")
        ]
        assert consent, "no DPDP s.6 consent finding was produced"
        assert consent[0].result is not ObligationResult.CONTESTED, (
            "every consent fact was declared, yet the rail still reported it unresolved"
        )

    def test_every_upstream_consent_field_this_adapter_names_really_exists(self) -> None:
        """The durable guard: name drift fails here, not in front of a client.

        The defect was a silent assumption that two schemas use the same words. This
        asserts the mapping against the upstream dataclass itself, so the next rename
        on either side fails a test instead of an engagement.
        """
        import dataclasses

        from dpdp.types import ConsentRecord

        upstream_fields = {f.name for f in dataclasses.fields(ConsentRecord)}
        mapped = set(adapter.CONSENT_FIELD_TO_UPSTREAM.values())
        unknown = mapped - upstream_fields
        assert not unknown, (
            f"the adapter names upstream consent fields that do not exist: {sorted(unknown)}"
        )
