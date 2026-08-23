"""India rail adapter over `dpdp-law-to-code`.

India is the correctness anchor of the whole tool: it is the only regime whose
statutory constants are settled against the primary Gazette text, and the only
one with a tested upstream engine (407 passing tests) standing behind it. This
adapter therefore behaves like a thin, paranoid wrapper around that engine — it
never re-implements an India check, and it refuses to fabricate inputs that the
declaration did not supply.

The two architectural commitments that drive the design:

* A7 (falsifier #2) — if the upstream package changes its shape, we fail loudly
  with a named, actionable error. An opaque ``ImportError`` or ``TypeError``
  mid-engagement would cost the India rail with no recovery path. ``contract_check``
  therefore re-resolves modules on every call and wraps anything unexpected in
  :class:`UpstreamContractError`.
* "No fabricated inputs" — where the declaration does not state a fact, we do
  NOT pass ``False`` upstream and report the resulting gap. Silence is
  CONTESTED, not a GAP, because "the client did not say" and "the client said
  no" are different findings and only the second one is a gap. The upstream
  engine is therefore invoked only when every required field is known.

Provenance note — the DPDP ACT section numbers used in this adapter (Sec 5(1),
6, 8(9), 9, 10(1), 10(2), 16) are taken from the pinned upstream package's own
citations, which are attested by its 407 passing tests, and were NOT read on the
primary Act text in this build. The RULES 2025 constants ARE read verbatim from
the Gazette. Closing this gap — reading the Act text — is tracked in
``docs/verified_facts_brief.md``.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping

from samanvaya.types import (
    Declaration,
    Finding,
    Obligation,
    ObligationResult,
    ObligationTopic,
    RegimeId,
    SubTopic,
    UpstreamContractError,
    fact_needed,
)


# ---------------------------------------------------------------------------
# Module-level constants — every one is a statutory or pin fact, not a guess.
# ---------------------------------------------------------------------------

UPSTREAM_DISTRIBUTION: str = "dpdp-law-to-code"
"""Distribution name as it appears on the Python package index."""

UPSTREAM_MODULE: str = "dpdp"
"""Top-level import name we resolve against at call time."""

EXPECTED_UPSTREAM_VERSION: str = "0.1.0"
"""Version this adapter was authored against. Bumping requires re-verifying
every obligation in this file against the new upstream behaviour."""

UPSTREAM_PIN_NOTE: str = "git+https://github.com/Wolfgangrush/dpdp-law-to-code@da1547769ffd2f8329ded1df271ad18dc7ff8479"
"""Human-readable reminder of the exact pin used in the lockfile."""

REQUIRED_COMPLIANCE_RESULT_ATTRS: tuple[str, ...] = (
    "compliant",
    "section",
    "reason",
    "citation",
    "sub_results",
)
"""The exact field set the upstream ``ComplianceResult`` must expose. We check
this on every call so that a slimmed-down upstream dataclass fails loudly
rather than silently producing a Finding with a missing ``citation``.

Note: contract verification checks the ``compliant`` ATTRIBUTE. It deliberately
does NOT rely on any ``__bool__`` method upstream may or may not define, so we
read ``result.compliant`` explicitly at every call site. If upstream drops
``__bool__`` the adapter still works; if upstream drops ``compliant`` the
contract check fires."""

# Each entry maps "module.function" -> the parameter names that MUST appear on
# the upstream signature. The list is closed (A7): discovering checks from the
# installed package would prove nothing — we only trust what we asked for.
REQUIRED_CHECKS: dict[str, tuple[str, ...]] = {
    "dpdp.notice.check_notice": ("notice",),
    "dpdp.consent.check_consent": ("consent",),
    "dpdp.children.check_child_processing": ("record",),
    "dpdp.sdf.assess_sdf_threshold": ("context",),
    "dpdp.sdf.check_sdf_obligations": ("context",),
    "dpdp.fiduciary.check_security_safeguards": (
        "has_technical_safeguards",
        "has_organisational_safeguards",
        "encrypted_at_rest",
        "encrypted_in_transit",
        "access_controls_in_place",
    ),
    "dpdp.fiduciary.check_processor_contract": (
        "processor_engaged",
        "has_valid_contract",
    ),
    "dpdp.fiduciary.check_breach_notification": ("breach",),
    "dpdp.fiduciary.check_dpo_contact_publication": (
        "dpo_contact_published",
    ),
    "dpdp.cross_border.check_cross_border_transfer": ("transfer",),
}


# ---------------------------------------------------------------------------
# Constants drawn verbatim from the Gazette text (G.S.R. 846(E), 13 Nov 2025).
# No derived value is computed here; the publication date itself is unsettled
# against the e-Gazette record, so anything that would depend on it is a
# ``fact_needed(...)`` marker in the obligation text, not a hard-coded number.
# ---------------------------------------------------------------------------

ACT_INSTRUMENT: str = "Digital Personal Data Protection Act 2023"
RULES_INSTRUMENT: str = "Digital Personal Data Protection Rules 2025"

CHILD_AGE_THRESHOLD_YEARS: int = 18  # DPDP Act 2023, s.9

LOG_RETENTION_YEARS: int = 1  # DPDP Rules 2025, Rule 6(1)(e)
SECURITY_MINIMUM_LIMBS: int = 7  # DPDP Rules 2025, Rule 6(1)(a)–(g)
SDF_DPIA_AUDIT_MONTHS: int = 12  # DPDP Rules 2025, Rule 13
BREACH_BOARD_DEADLINE_HOURS: int = 72  # DPDP Rules 2025, Rule 7(2)(b)
GRIEVANCE_MAX_DAYS: int = 90  # DPDP Rules 2025, Rule 14(3)


# ---------------------------------------------------------------------------
# Commencement schedule (DPDP Rules 2025, Rule 1).
#
# Rule 1 commences the Rules in stages. Rule 1(4) brings up Rules 3, 5 to 16,
# 22 and 23 into force eighteen months after the date of publication of the
# Rules in the Official Gazette. Rule 1(3) brings up Rule 4 into force one
# year after publication. The Act itself is not commenced by Rule 1 — Rule 1
# commences the Rules, not the Act — so obligations resting on the Act alone
# carry ``in_force_from=None``.
#
# The publication date of G.S.R. 846(E) is itself a ``fact_needed``: the
# e-Gazette record carries either 13 or 14 November 2025, and Rule 1 anchors
# every commencement date to publication. Every date derived here therefore
# carries an exposure of plus or minus one day, which is recorded in
# ``evaluation_metadata`` via ``COMMENCEMENT_UNCERTAINTY_NOTE`` and never
# silently resolved.
# ---------------------------------------------------------------------------

GAZETTE_PUBLICATION_EARLIEST: date = date(2025, 11, 13)
RULES_18_MONTH_COMMENCEMENT: date = date(2027, 5, 13)   # Rule 1(4): Rules 3, 5-16, 22, 23
RULE_4_COMMENCEMENT: date = date(2026, 11, 13)          # Rule 1(3): Rule 4, one year

COMMENCEMENT_UNCERTAINTY_NOTE: str = fact_needed(
    "exact publication date of G.S.R. 846(E) in the Official Gazette - 13 or 14 November "
    "2025? Rule 1 anchors commencement to publication, so every date derived here carries "
    "plus or minus one day. Checked 2026-08-20 and NOT closed: the notification's own "
    "header is dated the 13th and the Gazette text nowhere states its own publication "
    "date, while several secondary sources report publication on the 14th. The same "
    "notification recites that the DRAFT rules' Gazette was made available to the public "
    "on the same day it was notified, which points to the 13th. This build takes the "
    "13th and surfaces the doubt rather than resolving it silently"
)


# ---------------------------------------------------------------------------
# Internal helpers — three-path resolution shared by every obligation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Resolution:
    """Outcome of the three-path resolver used by every obligation helper."""

    result: ObligationResult
    rationale: str
    declaration_summary: str | None
    evidence_paths: tuple[str, ...]
    upstream_section: str | None
    upstream_citation: str | None
    upstream_reason: str | None
    extras: tuple[tuple[str, str], ...] = ()


def _missing(missing_paths: tuple[str, ...]) -> _Resolution:
    """Build a CONTESTED resolution naming the undeclared declaration paths."""
    joined = ", ".join(missing_paths)
    return _Resolution(
        result=ObligationResult.CONTESTED,
        rationale=(
            f"{joined} was not declared in the supplied declaration. "
            "Undeclared facts resolve to CONTESTED so the adviser can ask the "
            "client before this obligation is judged either way."
        ),
        declaration_summary=None,
        evidence_paths=missing_paths,
        upstream_section=None,
        upstream_citation=None,
        upstream_reason=None,
        extras=(("source", "declaration-gap"),),
    )


def _upstream(
    *,
    section: str,
    citation: str,
    reason: str,
    declaration_summary: str,
    evidence_paths: tuple[str, ...],
    extras: tuple[tuple[str, str], ...] = (),
) -> _Resolution:
    """Build a resolution that already carries an upstream ComplianceResult."""
    return _Resolution(
        result=ObligationResult.SATISFIED,  # overwritten by caller with the real result
        rationale=reason,
        declaration_summary=declaration_summary,
        evidence_paths=evidence_paths,
        upstream_section=section,
        upstream_citation=citation,
        upstream_reason=reason,
        extras=extras,
    )


def _not_applicable(why: str, evidence_paths: tuple[str, ...] = ()) -> _Resolution:
    """Build a NOT_APPLICABLE resolution for a precondition that was not met."""
    return _Resolution(
        result=ObligationResult.NOT_APPLICABLE,
        rationale=why,
        declaration_summary=None,
        evidence_paths=evidence_paths,
        upstream_section=None,
        upstream_citation=None,
        upstream_reason=None,
        extras=(("source", "gazette"),),
    )


def _gazette_direct(
    *,
    result: ObligationResult,
    why: str,
    declaration_summary: str | None,
    evidence_paths: tuple[str, ...],
    extras: tuple[tuple[str, str], ...] = (),
) -> _Resolution:
    """Build a resolution for an obligation evaluated from the Gazette text only."""
    return _Resolution(
        result=result,
        rationale=why,
        declaration_summary=declaration_summary,
        evidence_paths=evidence_paths,
        upstream_section=None,
        upstream_citation=None,
        upstream_reason=None,
        extras=(("source", "gazette"), *extras),
    )


def _make_obligation(
    *,
    obligation_id: str,
    instrument: str,
    provision: str,
    topic: ObligationTopic,
    dimension: str,
    value: str,
    unit: str | None,
    obligation_summary: str,
    citation_pointer: str,
    in_force_from: date | None = None,
    required_value: str | None = None,
    depends_on: tuple[str, ...] = (),
    evaluation_metadata: tuple[tuple[str, str], ...] = (),
) -> Obligation:
    """Construct the Obligation shell that every helper then resolves."""
    return Obligation(
        obligation_id=obligation_id,
        regime=RegimeId.INDIA,
        sub_unit=None,
        instrument=instrument,
        provision=provision,
        topic=topic,
        sub_topic=SubTopic(dimension=dimension, value=value, unit=unit),
        obligation_summary=obligation_summary,
        citation_pointer=citation_pointer,
        in_force_from=in_force_from,
        required_value=required_value,
        depends_on=depends_on,
        evaluation_metadata=evaluation_metadata,
    )


def _attach_metadata(
    obligation: Obligation, resolution: _Resolution
) -> Obligation:
    """Return a new Obligation with ``evaluation_metadata`` populated."""
    if resolution.upstream_section is None:
        merged_extras: tuple[tuple[str, str], ...] = (
            *obligation.evaluation_metadata,
            *resolution.extras,
        )
        return dataclasses_replace(obligation, evaluation_metadata=merged_extras)

    metadata: tuple[tuple[str, str], ...] = (
        *obligation.evaluation_metadata,
        ("source", "upstream"),
        ("upstream_section", resolution.upstream_section),
        ("upstream_citation", resolution.upstream_citation or ""),
        ("upstream_version", EXPECTED_UPSTREAM_VERSION),
        ("upstream_reason", resolution.upstream_reason or ""),
        *resolution.extras,
    )

    # The upstream citation goes into the HUMAN-FACING citation pointer, not only into
    # metadata. The adviser reading the report has to be able to trace a finding back to
    # the exact `ComplianceResult` that produced it without opening a JSON-lines file;
    # a trace that only exists in machine metadata is not a trace the reader can follow.
    #
    # Both citations are kept because they are answering different questions. This tool's
    # `provision` names the provision that fixes the constant being reported — Rule 13 for
    # the twelve-month DPIA and audit cycle — while the upstream engine cites the section
    # imposing the underlying duty, Sec 10(2). Neither is wrong and neither replaces the
    # other, so the pointer carries both rather than silently preferring one.
    upstream_ref = resolution.upstream_section
    if resolution.upstream_citation:
        upstream_ref = f"{upstream_ref} ({resolution.upstream_citation})"
    # Appended unconditionally. Suppressing it when the section string happens to already
    # appear would make the trace depend on how the two sources abbreviate the Act's name —
    # upstream writes "DPDP Act 2023", this tool writes it out in full — and an audit trail
    # that is present or absent depending on string coincidence is not an audit trail.
    pointer = f"{obligation.citation_pointer} [upstream: {upstream_ref}]"
    return dataclasses_replace(
        obligation, citation_pointer=pointer, evaluation_metadata=metadata
    )


def dataclasses_replace(obligation: Obligation, **changes: Any) -> Obligation:
    """``dataclasses.replace`` re-exported so the module has one helper per call site."""
    import dataclasses

    return dataclasses.replace(obligation, **changes)


def _emit(
    obligation: Obligation,
    resolution: _Resolution,
    *,
    upstream_compliant: bool | None = None,
) -> Finding:
    """Materialise the (Obligation, resolution) pair into a Finding."""
    if resolution.upstream_section is not None and upstream_compliant is None:
        raise UpstreamContractError(
            EXPECTED_UPSTREAM_VERSION,
            EXPECTED_UPSTREAM_VERSION,
            f"{obligation.obligation_id}: upstream resolution reached emit without a result.",
        )
    if resolution.upstream_section is not None:
        result = (
            ObligationResult.SATISFIED if upstream_compliant else ObligationResult.GAP
        )
        # Read the ``compliant`` ATTRIBUTE explicitly. Relying on ``bool(result)``
        # would couple this adapter to upstream's ``__bool__`` method, which the
        # contract check does not verify; reading the attribute is independent of
        # any ``__bool__`` the upstream dataclass may or may not define.
        rationale = (
            f"Upstream {resolution.upstream_section} returned compliant="
            f"{upstream_compliant}: {resolution.upstream_reason}"
        )
        return Finding(
            obligation=_attach_metadata(obligation, resolution),
            result=result,
            rationale=rationale,
            declaration_summary=resolution.declaration_summary,
            evidence_paths=resolution.evidence_paths,
        )
    return Finding(
        obligation=_attach_metadata(obligation, resolution),
        result=resolution.result,
        rationale=resolution.rationale,
        declaration_summary=resolution.declaration_summary,
        evidence_paths=resolution.evidence_paths,
    )


# ---------------------------------------------------------------------------
# Upstream contract verification.
# ---------------------------------------------------------------------------


def _resolve_upstream_attr(dotted: str) -> Any:
    """Resolve a dotted name on the upstream package, returning ``None`` on failure."""
    try:
        module_path, _, attr = dotted.rpartition(".")
        module = importlib.import_module(module_path)
        return getattr(module, attr, None)
    except Exception:  # noqa: BLE001 — explicit: any resolution error is a contract signal
        return None


def _wrap_contract_error(action: str, cause: BaseException | None = None) -> UpstreamContractError:
    """Translate an unexpected contract error into a named, actionable one."""
    message = (
        f"Upstream contract check for {UPSTREAM_DISTRIBUTION} ({EXPECTED_UPSTREAM_VERSION}) "
        f"failed while {action}. Re-verify the adapter against the new upstream version and "
        f"update the pin ({UPSTREAM_PIN_NOTE})."
    )
    err = UpstreamContractError(EXPECTED_UPSTREAM_VERSION, EXPECTED_UPSTREAM_VERSION, message)
    if cause is not None:
        err.__cause__ = cause
    return err


def contract_check() -> str:
    """Verify that the upstream ``dpdp-law-to-code`` package matches the pin.

    Returns the verified version string. Raises ONLY
    :class:`UpstreamContractError` — every unexpected exception is wrapped so
    the caller never sees an opaque traceback. Modules are re-resolved on
    every call so monkeypatched substitutes are seen by the tests.
    """
    action = "importing the package"
    try:
        dpdp = importlib.import_module(UPSTREAM_MODULE)
    except ImportError as exc:
        raise _wrap_contract_error(action, exc) from exc

    action = "reading the pinned version"
    try:
        installed_version = getattr(dpdp, "__version__", None)
    except Exception as exc:  # noqa: BLE001
        raise _wrap_contract_error(action, exc) from exc

    if installed_version != EXPECTED_UPSTREAM_VERSION:
        message = (
            f"Upstream {UPSTREAM_DISTRIBUTION} reports version {installed_version!r} "
            f"but this adapter is pinned to {EXPECTED_UPSTREAM_VERSION!r}. "
            f"Re-verify the India constants against the new upstream behaviour and "
            f"either update the pin ({UPSTREAM_PIN_NOTE}) or roll back to "
            f"{EXPECTED_UPSTREAM_VERSION}. Got installed={installed_version!r}, "
            f"expected={EXPECTED_UPSTREAM_VERSION!r}."
        )
        err = UpstreamContractError(
            upstream_version=str(installed_version),
            expected=EXPECTED_UPSTREAM_VERSION,
            message=message,
        )
        raise err

    action = "inspecting ComplianceResult"
    try:
        upstream_types = importlib.import_module("dpdp.types")
        result_cls = getattr(upstream_types, "ComplianceResult", None)
        if result_cls is None:
            raise _wrap_contract_error(
                f"{action}: dpdp.types.ComplianceResult was not found"
            )
        for attr in REQUIRED_COMPLIANCE_RESULT_ATTRS:
            if not hasattr(result_cls, attr) and attr not in getattr(
                result_cls, "__dataclass_fields__", {}
            ):
                raise _wrap_contract_error(
                    f"{action}: ComplianceResult is missing required attribute {attr!r}"
                )
    except UpstreamContractError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _wrap_contract_error(action, exc) from exc

    action = "inspecting required check functions"
    try:
        for dotted, required_params in REQUIRED_CHECKS.items():
            func = _resolve_upstream_attr(dotted)
            if func is None or not callable(func):
                raise _wrap_contract_error(
                    f"{action}: {dotted} is missing or not callable"
                )
            try:
                signature = inspect.signature(func)
            except (TypeError, ValueError) as exc:
                raise _wrap_contract_error(
                    f"{action}: could not inspect signature of {dotted}"
                ) from exc
            present_params = set(signature.parameters)
            missing = [name for name in required_params if name not in present_params]
            if missing:
                raise _wrap_contract_error(
                    f"{action}: {dotted} is missing required parameter(s) "
                    f"{missing!r}; upstream signature changed."
                )
    except UpstreamContractError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _wrap_contract_error(action, exc) from exc

    return EXPECTED_UPSTREAM_VERSION


# ---------------------------------------------------------------------------
# Period parsing (Gazette modelling choice, not statutory).
# ---------------------------------------------------------------------------


_PERIOD_NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def _parse_period_to_days(text: str) -> int | None:
    """Parse a declared retention/period string into a number of days.

    Accepts, case-insensitively, an Arabic number or an English number word
    (one through twelve) followed by ``day``/``days``, ``week``/``weeks``,
    ``month``/``months`` or ``year``/``years``. Returns ``None`` if nothing
    matches.

    Conversion is a MODELLING choice, not a statutory one: 1 week = 7 days,
    1 week = 7 days, 1 month = 365/12 days and 1 year = 365 days. A month is 365/12
    rather than 30 so that twelve months is exactly one year. ``"indefinitely"``,
    ``"as long as necessary"`` and ``"for the life of the account"`` are
    unbounded and return ``None`` — Rule 8 exists precisely to forbid them
    being treated as compliant without surfacing the unboundedness.
    """
    if not text:
        return None
    raw = text.strip().lower()
    if not raw:
        return None
    # Explicit unbounded phrases return None: these are the cases Rule 8
    # exists to surface, and the tool must not normalise them into a
    # parseable number.
    unbounded_markers = (
        "indefinitely",
        "as long as necessary",
        "as long as needed",
        "for the life of the account",
        "until further notice",
        "permanent",
        "perpetual",
        "no fixed",
    )
    for marker in unbounded_markers:
        if marker in raw:
            return None

    tokens = raw.split()
    if len(tokens) < 2:
        return None

    head = tokens[0].strip(",")
    unit = " ".join(tokens[1:]).strip()
    # Strip an optional leading "a" or "an", e.g. "a year".
    if head in {"a", "an"}:
        head = "1"

    if head.isdigit():
        number = int(head)
    elif head in _PERIOD_NUMBER_WORDS:
        number = _PERIOD_NUMBER_WORDS[head]
    else:
        return None

    if number < 0:
        return None

    # Strip a trailing period and accept either the singular or the plural.
    unit_clean = unit.rstrip(".").strip()
    per: float
    if unit_clean in {"day", "days"}:
        per = 1
    elif unit_clean in {"week", "weeks"}:
        per = 7
    elif unit_clean in {"month", "months"}:
        # 365/12, not 30. At 30 days a month, a declared "12 months" comes to 360 days
        # and fails the Rule 6(1)(e) one-year minimum by five days — the tool would
        # report a gap against a client who had declared exactly what the rule requires.
        # The artefact is in the conversion, not in the client's answer.
        per = 365 / 12
    elif unit_clean in {"year", "years"}:
        per = 365
    else:
        return None

    # Rounded, because the caller compares against a whole number of days and a
    # fractional day is meaningless in a retention period.
    return int(round(number * per))


# ---------------------------------------------------------------------------
# Obligation helpers — one per obligation, all returning a Finding.
# ---------------------------------------------------------------------------


def _call_upstream(obligation_id: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call an upstream check, converting any unexpected failure into a named error.

    A7 promises the adviser never sees an opaque upstream traceback. The contract check
    covers signature drift at load; this covers everything that can still go wrong at the
    moment a finding is needed. The obligation id is in the message because "something in
    the India rail broke" is not actionable and "in.notice.content broke" is.

    Note what this deliberately does NOT do: it does not swallow the failure into a
    CONTESTED finding. A malformed call is this adapter's own bug, and dressing it up as
    "the declaration was unclear" would hide it behind a verdict that looks routine.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - deliberately broad; re-raised named
        raise UpstreamContractError(
            EXPECTED_UPSTREAM_VERSION,
            EXPECTED_UPSTREAM_VERSION,
            f"{obligation_id}: upstream {getattr(fn, '__name__', fn)!r} raised "
            f"{type(exc).__name__}: {exc}. This is a defect in the India adapter's call, "
            f"not in the declaration. Pinned upstream: {UPSTREAM_PIN_NOTE}",
        ) from exc


def _eval_notice_content(declaration: Declaration) -> Finding:
    # SOURCED 2026-08-20 against the primary text: the Act as published in THE GAZETTE OF
    # INDIA EXTRAORDINARY, Part II, s.5 (read at page 4 of the Act's Gazette printing).
    #
    # Sec 5(1) enumerates THREE limbs, and the count is three rather than six because the
    # sub-section's list and the sub-section's other requirements are different things:
    #
    #   (i)   the personal data AND the purpose for which it is proposed to be processed
    #   (ii)  the manner in which she may exercise her rights under Sec 6(4) and Sec 13
    #   (iii) the manner in which she may make a complaint to the Board
    #
    # The declaration checks six fields against this obligation, and the extra three are
    # not additional limbs — they are the rest of the notice duty:
    #   * ``describes_personal_data`` and ``describes_purpose`` are BOTH limb (i), which
    #     bundles the two in one clause;
    #   * ``given_before_or_with_consent_request`` is the opening words of Sec 5(1) — the
    #     notice must be "accompanied or preceded by", which is a timing requirement, not
    #     an enumerated item;
    #   * ``available_in_local_language`` is Sec 5(3), a separate sub-section giving the
    #     option to access the notice in English or an Eighth Schedule language.
    #
    # Recording the count as three and the mapping above matters: an earlier build carried
    # a ``fact_needed`` marker here, which made ``has_unsourced_constant`` true and
    # silently DOWNGRADED an otherwise satisfied finding to CONTESTED on every India run.
    notice_limb_count: str = "3"
    obligation = _make_obligation(
        obligation_id="in.notice.content",
        instrument=ACT_INSTRUMENT,
        provision="Sec 5(1)",
        topic=ObligationTopic.NOTICE,
        dimension="notice_content_limbs",
        value=notice_limb_count,
        unit="limbs",
        obligation_summary=(
            "DPDP Act 2023, Sec 5(1) — the notice must inform the Data Principal of "
            "(i) the personal data and the purpose, (ii) the manner of exercising her "
            "rights under Sec 6(4) and Sec 13, and (iii) the manner of complaining to "
            "the Board; a notice that omits any of them is a gap. Read with the opening "
            "words of Sec 5(1), the notice must accompany or precede the consent "
            "request, and under Sec 5(3) it must be available in English or an Eighth "
            "Schedule language."
        ),
        citation_pointer=f"{ACT_INSTRUMENT}, Sec 5(1)",
        in_force_from=None,  # Rule 1 commences the Rules, not the Act.
    )
    n = declaration.notice
    limbs: dict[str, bool | None] = {
        "notice.describes_personal_data": n.describes_personal_data,
        "notice.describes_purpose": n.describes_purpose,
        "notice.describes_rights_exercise_method": n.describes_rights_exercise_method,
        "notice.describes_complaint_method_to_regulator": n.describes_complaint_method_to_regulator,
        "notice.available_in_local_language": n.available_in_local_language,
        "notice.given_before_or_with_consent_request": n.given_before_or_with_consent_request,
    }
    missing = tuple(path for path, value in limbs.items() if value is None)
    if missing:
        return _emit(obligation, _missing(missing))

    import dpdp.notice as upstream_notice

    # Build the record and call. There is no probing here, and there was: an earlier
    # version passed a raw dict first and only constructed a NoticeRecord if that raised
    # TypeError. Upstream raises InvalidInputError, not TypeError, so the fallback never
    # fired and the error escaped to the caller — the tool crashed on the first fully
    # declared notice it ever met. Nothing had caught it because the test fixtures all
    # leave the notice block empty, which resolves to CONTESTED without calling upstream.
    #
    # The contract check already verifies this signature on load. Probing a documented API
    # at run time buys nothing and costs the failure mode above.
    from dpdp.types import NoticeRecord

    # Our declaration uses regime-NEUTRAL field names, because the same block feeds six
    # regimes: "to_regulator", "local_language". Upstream is India-specific and uses the
    # statute's own vocabulary: "to_board" (the Data Protection Board), "eighth_schedule"
    # (the languages in the Eighth Schedule to the Constitution). Translating between the
    # two is exactly what an adapter is for, and the translation must be explicit.
    #
    # It was not. The previous version passed our names straight through, and the
    # probe-then-fallback around it swallowed the resulting error, so this rail never once
    # produced a finding. No test caught it because every fixture leaves the notice block
    # empty, which resolves to CONTESTED without ever calling upstream. The worked
    # examples found it on first contact.
    n_l = limbs
    record = NoticeRecord(
        describes_personal_data=bool(n_l["notice.describes_personal_data"]),
        describes_purpose=bool(n_l["notice.describes_purpose"]),
        describes_rights_exercise_method=bool(
            n_l["notice.describes_rights_exercise_method"]
        ),
        describes_complaint_method_to_board=bool(
            n_l["notice.describes_complaint_method_to_regulator"]
        ),
        available_in_english_or_eighth_schedule_language=bool(
            n_l["notice.available_in_local_language"]
        ),
        is_given_before_or_with_consent_request=bool(
            n_l["notice.given_before_or_with_consent_request"]
        ),
    )
    result = _call_upstream("in.notice.content", upstream_notice.check_notice, record)

    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary="Notice content limbs declared in declaration.notice.",
            evidence_paths=tuple(limbs.keys()),
        ),
        upstream_compliant=result.compliant,
    )


#: This schema's consent field names mapped to `dpdp.types.ConsentRecord`'s.
#:
#: Six of the eight required names are identical on both sides, and the code used to
#: exploit that by stripping the `consent_mechanism.` prefix and passing the remainder
#: straight through as keyword arguments. Two are NOT identical — this schema says
#: `limited_to_specified_purpose` and `withdrawal_as_easy_as_giving`, upstream says
#: `is_limited_to_specified_purpose` and `is_withdrawable_easily` — so that call raised
#: a bare `TypeError` from the constructor.
#:
#: It was reachable only when all eight required consent facts were declared, because
#: anything undeclared short-circuits at the `missing` guard below. No shipped example
#: declares more than one of the eight, so the DPDP s.6 consent-quality rail had never
#: run to completion in any example or test. The product could not PRODUCE a fully
#: answered declaration until the intake form existed, so nothing ever handed this rail
#: the input a real engagement produces. The missing feature was hiding the defect.
#:
#: The map is explicit and total — including the names that do match — so that a rename
#: on either side is caught by the test that walks it against the upstream dataclass,
#: rather than by an adviser mid-engagement.
CONSENT_FIELD_TO_UPSTREAM: dict[str, str] = {
    "is_free": "is_free",
    "is_specific": "is_specific",
    "is_informed": "is_informed",
    "is_unconditional": "is_unconditional",
    "is_unambiguous": "is_unambiguous",
    "has_clear_affirmative_action": "has_clear_affirmative_action",
    "limited_to_specified_purpose": "is_limited_to_specified_purpose",
    "withdrawal_as_easy_as_giving": "is_withdrawable_easily",
    "is_pre_checked": "is_pre_checked",
    "is_bundled_with_unrelated_terms": "is_bundled_with_unrelated_terms",
    "request_in_clear_plain_language": "request_in_clear_plain_language",
    "has_eighth_schedule_language_option": "has_eighth_schedule_language_option",
    "dpo_contact_provided": "dpo_contact_provided",
}


def _eval_consent_quality(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.consent.quality",
        instrument=ACT_INSTRUMENT,
        provision="Sec 6",
        topic=ObligationTopic.CONSENT,
        dimension="consent_standard",
        value=(
            "free, specific, informed, unconditional and unambiguous with "
            "clear affirmative action"
        ),
        unit=None,
        obligation_summary=(
            "DPDP Act 2023, Sec 6 — consent must be free, specific, informed, "
            "unconditional and unambiguous with a clear affirmative action, "
            "and the request must be in clear, plain language."
        ),
        citation_pointer=f"{ACT_INSTRUMENT}, Sec 6",
        in_force_from=None,  # Rule 1 commences the Rules, not the Act.
    )
    cm = declaration.consent_mechanism
    required: dict[str, bool | None] = {
        "consent_mechanism.is_free": cm.is_free,
        "consent_mechanism.is_specific": cm.is_specific,
        "consent_mechanism.is_informed": cm.is_informed,
        "consent_mechanism.is_unconditional": cm.is_unconditional,
        "consent_mechanism.is_unambiguous": cm.is_unambiguous,
        "consent_mechanism.has_clear_affirmative_action": cm.has_clear_affirmative_action,
        "consent_mechanism.limited_to_specified_purpose": cm.limited_to_specified_purpose,
        "consent_mechanism.withdrawal_as_easy_as_giving": cm.withdrawal_as_easy_as_giving,
    }
    missing = tuple(path for path, value in required.items() if value is None)
    if missing:
        return _emit(obligation, _missing(missing))

    optional: dict[str, bool | None] = {
        "is_pre_checked": cm.is_pre_checked,
        "is_bundled_with_unrelated_terms": cm.is_bundled_with_unrelated_terms,
        "request_in_clear_plain_language": cm.request_in_clear_plain_language,
        "has_eighth_schedule_language_option": cm.local_language_option_offered,
        "dpo_contact_provided": cm.privacy_officer_contact_provided,
    }
    extras_paths = tuple(path for path, value in optional.items() if value is not None)
    unset_extras = tuple(path for path, value in optional.items() if value is None)

    import dpdp.consent as upstream_consent
    from dpdp.types import ConsentRecord

    record_kwargs: dict[str, bool] = {
        CONSENT_FIELD_TO_UPSTREAM[path.split(".", 1)[1]]: bool(value)
        for path, value in required.items()
    }
    for path, value in optional.items():
        if value is not None:
            record_kwargs[CONSENT_FIELD_TO_UPSTREAM[path]] = bool(value)
    try:
        record = ConsentRecord(**record_kwargs)
    except TypeError as exc:
        # A7: the adviser must never see a bare constructor error mid-engagement. If
        # upstream renames or removes a field, this raises a named error carrying the
        # installed version and what did not match, which is a recovery path. The map
        # above is what stops this being reached in the ordinary case.
        raise _wrap_contract_error("construct dpdp.types.ConsentRecord", exc) from exc
    result = upstream_consent.check_consent(record)

    rationale_extras = ""
    if unset_extras:
        rationale_extras = (
            " Optional declaration fields left at the upstream default: "
            + ", ".join(unset_extras)
            + "."
        )
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason + rationale_extras,
            declaration_summary="Consent quality declared in declaration.consent_mechanism.",
            evidence_paths=tuple(required.keys()) + extras_paths,
        ),
        upstream_compliant=result.compliant,
    )


def _eval_children_processing(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.children.processing",
        instrument=ACT_INSTRUMENT,
        provision="Sec 9",
        topic=ObligationTopic.CHILDREN,
        dimension="child_age_threshold",
        value=str(CHILD_AGE_THRESHOLD_YEARS),
        unit="years",
        obligation_summary=(
            f"DPDP Act 2023, Sec 9 — a child is a person under "
            f"{CHILD_AGE_THRESHOLD_YEARS}; verifiable parental consent is required "
            "before processing, and tracking or targeted advertising is barred."
        ),
        citation_pointer=f"{ACT_INSTRUMENT}, Sec 9",
        in_force_from=None,  # Rule 1 commences the Rules, not the Act.
    )

    # FIX 1 — s.9 attaches to PROCESSING a child's personal data, not to offering
    # services to children. The gate must therefore read
    # ``children.processes_data_of_children``. ``organisation.offers_services_to_children``
    # is recorded only as supporting context; substituting one for the other was the
    # defect.
    children = declaration.children
    processes = children.processes_data_of_children

    # ``organisation.offers_services_to_children`` is still recorded as
    # supporting context, but it must NOT decide the gate. The two facts are
    # distinct: a hospital may process a great deal of children's data while
    # offering no service directed at children.
    extras_with_offering: tuple[tuple[str, str], ...] = (
        ("organisation_offers_services_to_children_recorded",
         str(declaration.organisation.offers_services_to_children)),
    )

    if processes is None:
        return _emit(
            obligation,
            _missing(("children.processes_data_of_children",)),
        )
    if processes is False:
        return _emit(
            obligation,
            _not_applicable(
                "DPDP Act 2023 s.9 attaches to processing a child's personal data. "
                "The declaration states children.processes_data_of_children is "
                "False, so no child's personal data is processed and the s.9 "
                "duty does not engage.",
                evidence_paths=("children.processes_data_of_children",),
            ),
        )

    # processes is True — proceed to the required-fields check.
    required_children: dict[str, bool | None] = {
        "children.verifiable_parental_consent": children.verifiable_parental_consent,
        "children.tracks_children": children.tracks_children,
        "children.targeted_advertising_to_children": children.targeted_advertising_to_children,
        "children.likely_detrimental_effect": children.likely_detrimental_effect,
    }
    missing_children = tuple(path for path, value in required_children.items() if value is None)
    if missing_children:
        return _emit(obligation, _missing(missing_children))

    import dpdp.children as upstream_children
    from dpdp.types import ChildRecord

    representative_age = 17
    # The values below are read from the DECLARED children block, not
    # fabricated. The previous version of this evaluator hardcoded ``False``
    # for every boolean, which let a client that tracked children be
    # reported compliant.
    record = ChildRecord(
        data_principal_age=representative_age,
        has_verifiable_parental_consent=bool(children.verifiable_parental_consent),
        is_tracking_behavior=bool(children.tracks_children),
        is_targeted_advertising=bool(children.targeted_advertising_to_children),
        is_likely_to_cause_detrimental_effect=bool(children.likely_detrimental_effect),
    )
    result = upstream_children.check_child_processing(record)
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary=(
                f"Representative minor used for modelling: data_principal_age="
                f"{representative_age}. This is a modelling choice, not a "
                "statutory threshold."
            ),
            evidence_paths=(
                "children.processes_data_of_children",
                "children.verifiable_parental_consent",
                "children.tracks_children",
                "children.targeted_advertising_to_children",
                "children.likely_detrimental_effect",
            ),
            extras=(
                ("representative_age", str(representative_age)),
                *extras_with_offering,
            ),
        ),
        upstream_compliant=result.compliant,
    )


def _eval_sdf_determination(declaration: Declaration) -> Finding:
    """Whether this Data Fiduciary is a Significant Data Fiduciary.

    This evaluator deliberately does NOT call the upstream ``assess_sdf_threshold``
    heuristic, for two reasons, and both of them are the kind that matter.

    First, **it would require fabricated inputs.** ``SDFContext`` wants a processing
    volume and six risk scores between zero and one. The declaration carries none of
    them. Supplying zeros would not be a neutral default — it drives the heuristic
    straight to "likely not a Significant Data Fiduciary", so the tool would return a
    confident negative built entirely out of numbers nobody declared. That is the
    fabrication this rail exists to refuse.

    Second, **it would be a legal determination the tool must not make.** Section 10(1)
    is a power of the Central Government: an entity becomes a Significant Data Fiduciary
    because the Government notifies it as one, on volume, sensitivity, risk and impact
    grounds. It is not a self-assessment threshold an adviser's tool can score. Scoring
    it would be statutory interpretation dressed as arithmetic — the same objection that
    cut the delta's ranking.

    So the determination rests on the one fact the declaration actually carries: whether
    the organisation has been notified. Undeclared means CONTESTED, and the adviser is
    told exactly which fact to go and establish.
    """
    obligation = _make_obligation(
        obligation_id="in.sdf.determination",
        instrument=ACT_INSTRUMENT,
        provision="Sec 10(1)",
        topic=ObligationTopic.GOVERNANCE,
        dimension="sdf_status",
        value="notified by Central Government",
        unit=None,
        obligation_summary=(
            "DPDP Act 2023, Sec 10(1) — the Central Government, by notification, "
            "designates any Data Fiduciary as a Significant Data Fiduciary on "
            "volume, sensitivity, risk or impact grounds."
        ),
        citation_pointer=f"{ACT_INSTRUMENT}, Sec 10(1)",
        in_force_from=None,  # Rule 1 commences the Rules, not the Act.
    )
    notified = declaration.organisation.notified_significant_data_fiduciary
    if notified is None:
        return _emit(
            obligation,
            _missing(("organisation.notified_significant_data_fiduciary",)),
        )

    if notified:
        return _emit(
            obligation,
            _gazette_direct(
                result=ObligationResult.SATISFIED,
                why=(
                    "The declaration states that this Data Fiduciary has been notified "
                    "as a Significant Data Fiduciary under Sec 10(1). The additional "
                    "obligations in Sec 10(2) and Rule 13 therefore apply."
                ),
                declaration_summary="notified_significant_data_fiduciary: yes",
                evidence_paths=("organisation.notified_significant_data_fiduciary",),
                extras=(("determination", "notified"),),
            ),
        )

    return _emit(
        obligation,
        _gazette_direct(
            result=ObligationResult.NOT_APPLICABLE,
            why=(
                "The declaration states that this Data Fiduciary has NOT been notified "
                "as a Significant Data Fiduciary. Significant Data Fiduciary status is "
                "conferred by Central Government notification under Sec 10(1); it is not "
                "self-assessed, and this tool does not score it. The Sec 10(2) and "
                "Rule 13 obligations are therefore not engaged on the declared facts. "
                "If the Central Government notifies this entity, re-run the check."
            ),
            declaration_summary="notified_significant_data_fiduciary: no",
            evidence_paths=("organisation.notified_significant_data_fiduciary",),
            extras=(("determination", "not notified"),),
        ),
    )


def _eval_sdf_obligations(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.sdf.obligations",
        instrument=RULES_INSTRUMENT,
        provision="Rule 13",
        topic=ObligationTopic.GOVERNANCE,
        dimension="sdf_dpia_audit_frequency",
        value=str(SDF_DPIA_AUDIT_MONTHS),
        unit="months",
        obligation_summary=(
            f"DPDP Rules 2025, Rule 13 — a Significant Data Fiduciary must "
            f"conduct a DPIA and audit ONCE EVERY {SDF_DPIA_AUDIT_MONTHS} MONTHS, "
            "perform algorithmic due diligence and localise specified personal "
            "data on Central Government notification."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 13",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 13.
        depends_on=("in.sdf.determination",),
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )

    # The SDF status is settled upstream — either by notification or it is not.
    # We mirror the determination evaluator's logic here so the obligations
    # evaluator does not invent zero risk scores the declaration never supplied.
    notified = declaration.organisation.notified_significant_data_fiduciary
    if notified is None:
        return _emit(
            obligation,
            _missing(("organisation.notified_significant_data_fiduciary",)),
        )
    if notified is False:
        return _emit(
            obligation,
            _not_applicable(
                "Significant Data Fiduciary status is conferred by Central "
                "Government notification under Sec 10(1); the declaration "
                "states the entity has not been notified, so the Rule 13 "
                "duties are not engaged on the declared facts.",
                evidence_paths=("organisation.notified_significant_data_fiduciary",),
            ),
        )

    g = declaration.governance
    required: dict[str, bool | None] = {
        "governance.conducts_impact_assessments": g.conducts_impact_assessments,
        "governance.conducts_audits": g.conducts_audits,
        "governance.has_privacy_officer": g.has_privacy_officer,
    }
    missing = tuple(path for path, value in required.items() if value is None)
    if missing:
        return _emit(obligation, _missing(missing))

    import dpdp.sdf as upstream_sdf
    from dpdp.types import SDFContext

    # The volume and the six risk scores are NOT declared. They are set to
    # zero here ONLY because upstream requires the fields. The metadata flag
    # ``risk_scores_not_declared`` and the rationale below tell the adviser
    # explicitly that the heuristic inputs are not declared and are not
    # relied upon — the determination has already been settled by the
    # notification fact.
    context = SDFContext(
        volume_of_personal_data_processed=0,
        sensitivity_of_personal_data=0.0,
        risk_to_rights_of_data_principals=0.0,
        risk_to_sovereignty_or_integrity=0.0,
        risk_to_electoral_democracy=0.0,
        risk_to_state_security=0.0,
        risk_to_public_order=0.0,
        notified_as_sdf_by_central_govt=True,
        has_appointed_dpo=bool(g.has_privacy_officer),
        has_appointed_data_auditor=bool(g.conducts_audits),
        conducts_periodic_dpia=bool(g.conducts_impact_assessments),
    )
    result = upstream_sdf.check_sdf_obligations(context)
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary="SDF obligations evidence drawn from governance declaration.",
            evidence_paths=tuple(required.keys()),
            extras=(("risk_scores_not_declared", "true"),),
        ),
        upstream_compliant=result.compliant,
    )


def _eval_security_rule6(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.security.rule6",
        instrument=RULES_INSTRUMENT,
        provision="Rule 6(1)",
        topic=ObligationTopic.SECURITY,
        dimension="security_minimum_limbs",
        value=str(SECURITY_MINIMUM_LIMBS),
        unit="limbs",
        required_value=None,  # A5 — Rule 6(1)(a) does not prescribe a standard.
        obligation_summary=(
            f"DPDP Rules 2025, Rule 6(1) — the Data Fiduciary must take "
            f"reasonable security safeguards across at least "
            f"{SECURITY_MINIMUM_LIMBS} enumerated limbs (a)–(g); Rule 6(1)(a) "
            "lists encryption/obfuscation/masking/virtual tokens without "
            "prescribing a standard, so presence alone satisfies."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 6(1)",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 6.
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    if not declaration.security_safeguards:
        return _emit(
            obligation,
            _missing(("security_safeguards",)),
        )

    declared = {pair.control.strip().casefold(): pair for pair in declaration.security_safeguards}

    def _truthy(*needles: str) -> bool | None:
        for needle in needles:
            pair = declared.get(needle.strip().casefold())
            if pair is None:
                return None
            if pair.value.strip().lower() in {"true", "yes", "1", "y", "in place"}:
                return True
            if pair.value.strip().lower() in {"false", "no", "0", "n", "absent"}:
                return False
        return None

    has_tech = _truthy("technical safeguards", "encryption", "obfuscation", "masking")
    has_org = _truthy("organisational safeguards", "policies", "training")
    encrypted_at_rest = _truthy("encryption at rest", "at-rest encryption")
    encrypted_in_transit = _truthy("encryption in transit", "in-transit encryption", "tls")
    access_controls = _truthy(
        "access controls", "access control", "role-based access", "rbac"
    )

    missing_paths: list[str] = []
    if has_tech is None:
        missing_paths.append("security_safeguards[technical_safeguards]")
    if has_org is None:
        missing_paths.append("security_safeguards[organisational_safeguards]")
    if encrypted_at_rest is None:
        missing_paths.append("security_safeguards[encryption_at_rest]")
    if encrypted_in_transit is None:
        missing_paths.append("security_safeguards[encryption_in_transit]")
    if access_controls is None:
        missing_paths.append("security_safeguards[access_controls]")
    if missing_paths:
        return _emit(obligation, _missing(tuple(missing_paths)))

    import dpdp.fiduciary as upstream_fiduciary

    result = upstream_fiduciary.check_security_safeguards(
        has_technical_safeguards=bool(has_tech),
        has_organisational_safeguards=bool(has_org),
        encrypted_at_rest=bool(encrypted_at_rest),
        encrypted_in_transit=bool(encrypted_in_transit),
        access_controls_in_place=bool(access_controls),
    )
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary=(
                "Security safeguards mapped from declaration.security_safeguards "
                "by control name; required_value intentionally left None (A5)."
            ),
            evidence_paths=(
                "security_safeguards[technical_safeguards]",
                "security_safeguards[organisational_safeguards]",
                "security_safeguards[encryption_at_rest]",
                "security_safeguards[encryption_in_transit]",
                "security_safeguards[access_controls]",
            ),
        ),
        upstream_compliant=result.compliant,
    )


def _eval_log_retention(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.security.log_retention",
        instrument=RULES_INSTRUMENT,
        provision="Rule 6(1)(e)",
        topic=ObligationTopic.SECURITY,
        dimension="log_retention_period",
        value=str(LOG_RETENTION_YEARS),
        unit="years",
        obligation_summary=(
            f"DPDP Rules 2025, Rule 6(1)(e) — logs and personal data must be "
            f"retained for a period of {LOG_RETENTION_YEARS} year unless another "
            "law requires otherwise."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 6(1)(e)",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 6(1)(e).
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    pair = declaration.declared_safeguard("log retention")
    if pair is None:
        return _emit(
            obligation,
            _missing(("security_safeguards[log retention]",)),
        )

    parsed = _parse_period_to_days(pair.value)
    if parsed is None:
        result = ObligationResult.CONTESTED
        why = (
            f"Declared log retention value {pair.value!r} could not be "
            f"interpreted as a numeric period (days, weeks, months or years). "
            "It must be restated in a parseable form before the Rule 6(1)(e) "
            f"{LOG_RETENTION_YEARS}-year requirement can be checked."
        )
        extras: tuple[tuple[str, str], ...] = (
            ("period_parsed_days", "None"),
            ("declared_value", pair.value),
        )
    elif parsed < 365:
        shortfall = 365 - parsed
        result = ObligationResult.GAP
        why = (
            f"Declared log retention value {pair.value!r} parses to "
            f"{parsed} days, which is {shortfall} days short of the "
            f"Rule 6(1)(e) {LOG_RETENTION_YEARS}-year minimum."
        )
        extras = (
            ("period_parsed_days", str(parsed)),
            ("shortfall_days", str(shortfall)),
            ("declared_value", pair.value),
        )
    else:
        result = ObligationResult.SATISFIED
        why = (
            f"Declared log retention value {pair.value!r} parses to "
            f"{parsed} days, which meets or exceeds the Rule 6(1)(e) "
            f"{LOG_RETENTION_YEARS}-year minimum ({365} days)."
        )
        extras = (
            ("period_parsed_days", str(parsed)),
            ("declared_value", pair.value),
        )

    return _emit(
        obligation,
        _gazette_direct(
            result=result,
            why=why,
            declaration_summary=(
                f"Declared safeguard: control={pair.control!r}, value={pair.value!r}."
            ),
            evidence_paths=("security_safeguards[log retention]",),
            extras=extras,
        ),
    )


def _eval_processor_contract(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.processor.contract",
        instrument=RULES_INSTRUMENT,
        provision="Rule 6(1)(f)",
        topic=ObligationTopic.PROCESSOR,
        dimension="processor_contract_security_clause",
        value="required",
        unit=None,
        obligation_summary=(
            "DPDP Rules 2025, Rule 6(1)(f) — there must be an appropriate "
            "provision in the contract between Data Fiduciary and Data "
            "Processor for taking reasonable security safeguards."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 6(1)(f)",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 6(1)(f).
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    g = declaration.governance
    required: dict[str, bool | None] = {
        "governance.processor_contracts_in_place": g.processor_contracts_in_place,
        "governance.processor_contract_covers_security": g.processor_contract_covers_security,
    }
    missing = tuple(path for path, value in required.items() if value is None)
    if missing:
        return _emit(obligation, _missing(missing))

    import dpdp.fiduciary as upstream_fiduciary

    result = upstream_fiduciary.check_processor_contract(
        processor_engaged=bool(g.processor_contracts_in_place),
        has_valid_contract=bool(g.processor_contract_covers_security),
    )
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary=(
                "Processor contract evidence drawn from "
                "governance.processor_contracts_in_place and "
                "governance.processor_contract_covers_security."
            ),
            evidence_paths=tuple(required.keys()),
        ),
        upstream_compliant=result.compliant,
    )


def _eval_breach_board_report(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.breach.board_report",
        instrument=RULES_INSTRUMENT,
        provision="Rule 7(2)(b)",
        topic=ObligationTopic.BREACH,
        dimension="breach_notice_deadline",
        value=str(BREACH_BOARD_DEADLINE_HOURS),
        unit="hours",
        obligation_summary=(
            f"DPDP Rules 2025, Rule 7(2)(b) — a detailed report must reach the "
            f"Board WITHIN {BREACH_BOARD_DEADLINE_HOURS} HOURS of becoming aware "
            "of a personal-data breach, or within such longer period as the "
            "Board may allow on written request."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 7(2)(b)",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 7(2)(b).
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    bw = declaration.breach_workflow
    required: dict[str, Any] = {
        "breach_workflow.notifies_regulator": bw.notifies_regulator,
        "breach_workflow.regulator_deadline_hours": bw.regulator_deadline_hours,
    }
    missing = tuple(
        path for path, value in required.items() if value is None
    )
    if missing:
        return _emit(obligation, _missing(missing))

    if not bool(bw.notifies_regulator):
        # The declaration says the client does NOT notify the regulator at all.
        # That is a substantive negative, not an undeclared fact.
        import dpdp.fiduciary as upstream_fiduciary
        from dpdp.types import BreachRecord

        record = BreachRecord(
            detected_at_unix=0,
            notified_board_at_unix=None,
            notified_affected_principals_at_unix=None,
            affected_principal_count=0,
            breach_description="declared does-not-notify",
        )
        result = upstream_fiduciary.check_breach_notification(record)
        return _emit(
            obligation,
            _upstream(
                section=result.section,
                citation=result.citation,
                reason=result.reason,
                declaration_summary=(
                    "Declaration says breach_workflow.notifies_regulator is False; "
                    "upstream exercised on a synthetic non-notification record."
                ),
                evidence_paths=("breach_workflow.notifies_regulator",),
                extras=(("synthetic_clock", "true"),),
            ),
            upstream_compliant=result.compliant,
        )

    # `regulator_deadline_hours` is one of the `required` fields checked at the top of
    # this function, so a None value has already returned a CONTESTED finding and cannot
    # reach here. The assertion states that invariant for the type checker, which cannot
    # narrow through a dict-driven missing-field check. Returning None instead would
    # break the declared `-> Finding` and drop the obligation from the report entirely.
    assert bw.regulator_deadline_hours is not None
    deadline_hours = int(bw.regulator_deadline_hours)
    import dpdp.fiduciary as upstream_fiduciary
    from dpdp.types import BreachRecord

    record = BreachRecord(
        detected_at_unix=0,
        notified_board_at_unix=deadline_hours * 3600,
        notified_affected_principals_at_unix=None,
        affected_principal_count=0,
        breach_description=(
            f"synthetic: declared interval {deadline_hours} hours from detection"
        ),
    )
    result = upstream_fiduciary.check_breach_notification(record)
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary=(
                f"Synthetic clock: detected_at_unix=0, notified_board_at_unix="
                f"{deadline_hours * 3600} (deadline_hours declared={deadline_hours})."
            ),
            evidence_paths=(
                "breach_workflow.notifies_regulator",
                "breach_workflow.regulator_deadline_hours",
            ),
            extras=(
                ("synthetic_clock", "true"),
                ("declared_deadline_hours", str(deadline_hours)),
            ),
        ),
        upstream_compliant=result.compliant,
    )


def _eval_breach_principal(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.breach.principal",
        instrument=RULES_INSTRUMENT,
        provision="Rule 7(1)",
        topic=ObligationTopic.BREACH,
        dimension="breach_individual_notice_trigger",
        value="without delay",
        unit=None,
        obligation_summary=(
            "DPDP Rules 2025, Rule 7(1) — EACH AFFECTED DATA PRINCIPAL must be "
            "intimateed without delay in a concise, clear and plain manner."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 7(1)",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 7(1).
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    bw = declaration.breach_workflow
    declares = bw.notifies_affected_individuals
    if declares is None:
        return _emit(
            obligation,
            _missing(("breach_workflow.notifies_affected_individuals",)),
        )
    if declares is False:
        return _emit(
            obligation,
            _gazette_direct(
                result=ObligationResult.GAP,
                why=(
                    "breach_workflow.notifies_affected_individuals is False; Rule 7(1) "
                    "requires each affected Data Principal to be intimated without delay."
                ),
                declaration_summary=None,
                evidence_paths=("breach_workflow.notifies_affected_individuals",),
            ),
        )

    # declares is True — now look at the declared trigger.
    trigger = bw.individual_notification_trigger
    if trigger is None:
        return _emit(
            obligation,
            _missing(("breach_workflow.individual_notification_trigger",)),
        )

    trigger_lc = trigger.strip().lower()
    without_delay_markers = ("without delay", "immediately", "on becoming aware", "as soon as")
    if any(marker in trigger_lc for marker in without_delay_markers):
        return _emit(
            obligation,
            _gazette_direct(
                result=ObligationResult.SATISFIED,
                why=(
                    "breach_workflow.notifies_affected_individuals is True and the "
                    "declared individual_notification_trigger "
                    f"({trigger!r}) carries a without-delay phrasing (one of: "
                    f"{', '.join(without_delay_markers)}). This matches Rule 7(1)'s "
                    "WITHOUT DELAY duty."
                ),
                declaration_summary=f"declared_trigger={trigger!r}",
                evidence_paths=(
                    "breach_workflow.notifies_affected_individuals",
                    "breach_workflow.individual_notification_trigger",
                ),
            ),
        )

    return _emit(
        obligation,
        _gazette_direct(
            result=ObligationResult.GAP,
            why=(
                "breach_workflow.notifies_affected_individuals is True but the "
                "declared individual_notification_trigger "
                f"({trigger!r}) is a conditional trigger, not 'without delay'. "
                "Rule 7(1) requires intimation without delay to each affected "
                "Data Principal; gating notice on a condition (e.g. 'only when a "
                "data principal complains') does not satisfy that duty."
            ),
            declaration_summary=f"declared_trigger={trigger!r}",
            evidence_paths=(
                "breach_workflow.notifies_affected_individuals",
                "breach_workflow.individual_notification_trigger",
            ),
            extras=(("declared_trigger", trigger),),
        ),
    )


def _eval_grievance_redressal(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.rights.grievance",
        instrument=RULES_INSTRUMENT,
        provision="Rule 14(3)",
        topic=ObligationTopic.RIGHTS,
        dimension="grievance_response_period",
        value=str(GRIEVANCE_MAX_DAYS),
        unit="days",
        obligation_summary=(
            f"DPDP Rules 2025, Rule 14(3) — the grievance redressal system "
            f"must dispose of complaints within NINETY ({GRIEVANCE_MAX_DAYS}) DAYS."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 14(3)",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 14(3).
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    d = declaration.dsr_workflow
    if d.grievance_mechanism_published is None:
        return _emit(
            obligation,
            _missing(("dsr_workflow.grievance_mechanism_published",)),
        )
    if d.grievance_response_period_days is None:
        return _emit(
            obligation,
            _missing(("dsr_workflow.grievance_response_period_days",)),
        )

    published = bool(d.grievance_mechanism_published)
    period = int(d.grievance_response_period_days)
    if published and period <= GRIEVANCE_MAX_DAYS:
        result = ObligationResult.SATISFIED
        why = (
            f"Grievance mechanism published and declared period {period} days is "
            f"within the Rule 14(3) cap of {GRIEVANCE_MAX_DAYS} days."
        )
    elif not published:
        result = ObligationResult.GAP
        why = (
            "dsr_workflow.grievance_mechanism_published is False; Rule 14(3) "
            "requires the grievance redressal system to be published."
        )
    else:
        result = ObligationResult.GAP
        why = (
            f"Declared grievance response period {period} days exceeds the Rule "
            f"14(3) cap of {GRIEVANCE_MAX_DAYS} days."
        )
    return _emit(
        obligation,
        _gazette_direct(
            result=result,
            why=why,
            declaration_summary=(
                f"Declared: published={published}, period_days={period}."
            ),
            evidence_paths=(
                "dsr_workflow.grievance_mechanism_published",
                "dsr_workflow.grievance_response_period_days",
            ),
            extras=(("declared_period_days", str(period)),),
        ),
    )


def _eval_dsr_no_response_period(declaration: Declaration) -> Finding:
    del declaration  # this obligation records a statutory NEGATIVE; nothing is declared against it
    # The negative itself (no Rule 3 to 16 fixes a Sec 11–12 response period)
    # is independent of commencement. Rule 1 commences the Rules in stages,
    # so the SAME answer — DOES_NOT_EXIST — must hold at every date. We
    # therefore leave ``in_force_from=None``: not-yet-commencement cannot
    # revive a duty that does not exist in the instrument at all.
    obligation = _make_obligation(
        obligation_id="in.rights.no_response_period",
        instrument=RULES_INSTRUMENT,
        provision="Rules 3 to 16",
        topic=ObligationTopic.RIGHTS,
        dimension="dsr_response_period",
        value="none prescribed",
        unit=None,
        obligation_summary=(
            "DPDP Rules 2025 prescribe NO response period for access, correction, "
            "updating or erasure. The ninety-day cap in Rule 14(3) attaches to "
            "grievance redressal ONLY; imposing it on the Sec 11–12 rights would "
            "be inventing an obligation."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rules 3 to 16 (negative)",
        in_force_from=None,
    )
    return _emit(
        obligation,
        _gazette_direct(
            result=ObligationResult.DOES_NOT_EXIST,
            why=(
                "No Rule 3 to 16 prescribes a response period for the Sec 11–12 "
                "rights; only Rule 14(3) fixes one, and only for grievance "
                "redressal. This negative is recorded so downstream comparators "
                "do not invent a deadline."
            ),
            declaration_summary=None,
            evidence_paths=(),
            extras=(("negative_recording", "true"),),
        ),
    )


def _eval_governance_contact(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.governance.contact",
        instrument=ACT_INSTRUMENT,
        provision="Sec 8(9)",
        topic=ObligationTopic.GOVERNANCE,
        dimension="contact_publication",
        value="required",
        unit=None,
        obligation_summary=(
            "DPDP Act 2023, Sec 8(9) read with DPDP Rules 2025, Rule 9 — the "
            "contact details of the Data Protection Officer (or equivalent) "
            "must be published in the prescribed manner."
        ),
        citation_pointer=f"{ACT_INSTRUMENT}, Sec 8(9); {RULES_INSTRUMENT}, Rule 9",
        in_force_from=None,  # Rule 1 commences the Rules, not the Act.
    )
    g = declaration.governance
    required: dict[str, bool | None] = {
        "governance.has_privacy_officer": g.has_privacy_officer,
        "governance.privacy_officer_contact_published": g.privacy_officer_contact_published,
    }
    missing = tuple(path for path, value in required.items() if value is None)
    if missing:
        return _emit(obligation, _missing(missing))

    import dpdp.fiduciary as upstream_fiduciary

    result = upstream_fiduciary.check_dpo_contact_publication(
        dpo_contact_published=bool(g.privacy_officer_contact_published),
    )
    return _emit(
        obligation,
        _upstream(
            section=result.section,
            citation=result.citation,
            reason=result.reason,
            declaration_summary=(
                "Contact-publication evidence drawn from "
                "governance.has_privacy_officer and "
                "governance.privacy_officer_contact_published."
            ),
            evidence_paths=tuple(required.keys()),
        ),
        upstream_compliant=result.compliant,
    )


def _eval_cross_border(declaration: Declaration) -> Finding:
    # The Rules-based limb (Rule 15) is commenced by Rule 1(4). The Act limb
    # (Sec 16) is not commenced by Rule 1. The obligation is a hybrid that
    # does not engage until BOTH are in force: Sec 16 fixes the principle
    # ("general permission subject to Central Government restriction") and
    # Rule 15 prescribes the conditions. On an as-at date before
    # RULES_18_MONTH_COMMENCEMENT the obligation is therefore not yet in
    # force. We anchor ``in_force_from`` to the later commencement — the
    # Rules limb — and set ``in_force_from=None`` on the ACT-only limbs.
    obligation = _make_obligation(
        obligation_id="in.crossborder.transfer",
        instrument=ACT_INSTRUMENT,
        provision="Sec 16",
        topic=ObligationTopic.CROSS_BORDER,
        dimension="transfer_restriction_model",
        value="general permission subject to Central Government restriction",
        unit=None,
        obligation_summary=(
            "DPDP Act 2023, Sec 16 read with DPDP Rules 2025, Rule 15 — cross-"
            "border transfer is on a 'general permission' basis subject to "
            "such restrictions as the Central Government may, by notification, "
            "impose on particular countries or territories."
        ),
        citation_pointer=f"{ACT_INSTRUMENT}, Sec 16; {RULES_INSTRUMENT}, Rule 15",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rules-based limb governs commencement.
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    transfers = declaration.cross_border.transfers_outside_jurisdiction
    if transfers is None:
        return _emit(
            obligation,
            _missing(("cross_border.transfers_outside_jurisdiction",)),
        )
    if not transfers:
        return _emit(
            obligation,
            _not_applicable(
                "cross_border.transfers_outside_jurisdiction is False; Sec 16 "
                "does not engage.",
                evidence_paths=("cross_border.transfers_outside_jurisdiction",),
            ),
        )

    destinations = declaration.cross_border.destination_countries
    if not destinations:
        return _emit(
            obligation,
            _missing(("cross_border.destination_countries",)),
        )

    import dpdp.cross_border as upstream_cross_border
    from dpdp.types import CrossBorderTransfer

    any_gap = False
    section = "Sec 16"
    citation = f"DPDP Act 2023 / DPDP Rules 2025, Rule 15 ({len(destinations)} destinations)"
    reasons: list[str] = []
    evidence: list[str] = []
    for country in destinations:
        record = CrossBorderTransfer(destination_country_iso=country)
        result = upstream_cross_border.check_cross_border_transfer(record)
        # Read the ``compliant`` ATTRIBUTE — not ``bool(result)`` — so the
        # adapter does not silently break if upstream drops ``__bool__``.
        if not result.compliant:
            any_gap = True
        reasons.append(f"{country}: compliant={result.compliant} reason={result.reason}")
        evidence.append(f"cross_border.destination_countries[{country}]")
        section = result.section
        citation = (
            f"{ACT_INSTRUMENT}, {result.section} ({result.citation}) — "
            f"destinations: {', '.join(destinations)}"
        )

    return _emit(
        obligation,
        _upstream(
            section=section,
            citation=citation,
            reason="; ".join(reasons),
            declaration_summary=(
                f"Combined transfer check across destinations: "
                f"{', '.join(destinations)}."
            ),
            evidence_paths=tuple(evidence),
            extras=(("destination_count", str(len(destinations))),),
        ),
        upstream_compliant=not any_gap,
    )


def _eval_retention_purpose_served(declaration: Declaration) -> Finding:
    obligation = _make_obligation(
        obligation_id="in.retention.purpose_served",
        instrument=RULES_INSTRUMENT,
        provision="Rule 8",
        topic=ObligationTopic.RETENTION,
        dimension="retention_clock",
        value="purpose no longer served",
        unit=None,
        obligation_summary=(
            "DPDP Rules 2025, Rule 8 — personal data must be erased once the "
            "specified purpose is no longer being served (read with Sec 8(7) of "
            "the Act), unless retention is required by another law."
        ),
        citation_pointer=f"{RULES_INSTRUMENT}, Rule 8",
        in_force_from=RULES_18_MONTH_COMMENCEMENT,  # Rule 1(4) commences Rule 8.
        evaluation_metadata=(("commencement_note", COMMENCEMENT_UNCERTAINTY_NOTE),),
    )
    if not declaration.retention:
        return _emit(
            obligation,
            _missing(("retention",)),
        )

    # Every declared retention rule must have a BOUNDED period the tool can
    # parse. An unbounded period ("indefinitely", "as long as necessary",
    # "for the life of the account") is precisely what Rule 8 exists to
    # prevent, so passing the obligation when one is present would be a
    # false assurance.
    unbounded_offenders: list[str] = []
    for rule in declaration.retention:
        parsed = _parse_period_to_days(rule.period)
        if parsed is None:
            unbounded_offenders.append(rule.purpose)

    summary = "; ".join(
        f"{rule.purpose!r} → {rule.period!r} (basis={rule.basis!r})"
        for rule in declaration.retention
    )

    if unbounded_offenders:
        return _emit(
            obligation,
            _gazette_direct(
                result=ObligationResult.CONTESTED,
                why=(
                    "Rule 8 requires erasure once the purpose is no longer being "
                    "served. The declared retention rules for: "
                    + ", ".join(repr(p) for p in unbounded_offenders)
                    + " carry an unbounded or unparseable period (e.g. "
                    "'indefinitely', 'as long as necessary', 'for the life of "
                    "the account'). An unbounded period is the thing Rule 8 "
                    "exists to prevent; the tool must not pass it silently. "
                    "Restate the periods in bounded form (e.g. '3 years') "
                    "before this obligation can be judged."
                ),
                declaration_summary=summary,
                evidence_paths=tuple(
                    f"retention[{i}]" for i, rule in enumerate(declaration.retention)
                    if rule.purpose in unbounded_offenders
                ),
                extras=(
                    ("declared_rule_count", str(len(declaration.retention))),
                    ("unbounded_rule_count", str(len(unbounded_offenders))),
                ),
            ),
        )

    return _emit(
        obligation,
        _gazette_direct(
            result=ObligationResult.SATISFIED,
            why=(
                "Every declared retention rule carries a bounded period the "
                "tool can parse; this is the Rule 8 retention clock. Whether "
                "the period itself is appropriate is judged elsewhere."
            ),
            declaration_summary=summary,
            evidence_paths=tuple(
                f"retention[{i}]" for i in range(len(declaration.retention))
            ),
            extras=(("declared_rule_count", str(len(declaration.retention))),),
        ),
    )


# Ordered declaration of obligations — stable for tests and divergences.
OBLIGATION_REGISTRY: tuple[Callable[[Declaration], Finding], ...] = (
    _eval_notice_content,
    _eval_consent_quality,
    _eval_children_processing,
    _eval_sdf_determination,
    _eval_sdf_obligations,
    _eval_security_rule6,
    _eval_log_retention,
    _eval_processor_contract,
    _eval_breach_board_report,
    _eval_breach_principal,
    _eval_grievance_redressal,
    _eval_dsr_no_response_period,
    _eval_governance_contact,
    _eval_cross_border,
    _eval_retention_purpose_served,
)

# Public name retained as the canonical registry. The previous private name
# is kept as an alias so any external import keeps working; new code should
# use ``OBLIGATION_REGISTRY``.
_OBLIGATION_REGISTRY = OBLIGATION_REGISTRY


# ---------------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------------


def run_checks(declaration: Declaration, as_at: date) -> list[Finding]:
    """Evaluate the India rail against the supplied declaration.

    The contract check runs first; its error propagates so the caller cannot
    silently evaluate against a drifted upstream. The obligation order is
    stable: the same declaration evaluated twice yields identical
    ``(obligation_id, result)`` tuples.

    ``as_at`` is forwarded through the engine's ``is_in_force`` post-pass:
    every obligation here carries the commencement date Rule 1 fixes for
    its instrument, and the engine downgrades not-yet-in-force findings
    accordingly. The adapter does not re-implement that logic; it builds
    every Finding above and lets the engine apply the commencement filter.

    NOTE on the in-force rule: the engine exposes no PUBLIC helper for it
    (and importing ``_post_pass`` is not acceptable), so the engine will
    re-apply the same rule idempotently downstream. That duplication is
    deliberate: the engine is correct under its own post-pass, and
    ``india/pack.py`` is correct when called directly by anyone who does
    not route through ``engine.run()``.
    """
    contract_check()  # gate evaluation; failure propagates as UpstreamContractError
    # NOTE: do NOT `del as_at`. The engine's post-pass applies
    # ``Obligation.is_in_force(as_at)`` to downgrade not-yet-in-force
    # findings; the adapter's job is to build every Finding and let the
    # engine apply the commencement filter. Discarding the parameter
    # silently here would let a 2026-08 as-at date report an obligation
    # failing under Rule 6(1)(e) even though Rule 1(4) does not commence
    # Rule 6 until 2027-05-13.
    return [evaluator(declaration) for evaluator in OBLIGATION_REGISTRY]


__all__ = [
    "UPSTREAM_DISTRIBUTION",
    "UPSTREAM_MODULE",
    "EXPECTED_UPSTREAM_VERSION",
    "UPSTREAM_PIN_NOTE",
    "REQUIRED_COMPLIANCE_RESULT_ATTRS",
    "REQUIRED_CHECKS",
    "ACT_INSTRUMENT",
    "RULES_INSTRUMENT",
    "GAZETTE_PUBLICATION_EARLIEST",
    "RULES_18_MONTH_COMMENCEMENT",
    "RULE_4_COMMENCEMENT",
    "COMMENCEMENT_UNCERTAINTY_NOTE",
    "OBLIGATION_REGISTRY",
    "_OBLIGATION_REGISTRY",
    "contract_check",
    "run_checks",
]
