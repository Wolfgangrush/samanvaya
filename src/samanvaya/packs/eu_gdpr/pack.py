"""EU GDPR regulation pack for the offline privacy-conformance tool.

This pack translates the verified Articles of Regulation (EU) 2016/679
(GDPR) into obligations the engine can evaluate against a supplied
declaration.  Every statutory constant used here is quoted verbatim from
the EUR-Lex consolidated text (CELEX 02016R0679-20160504); anything that
cannot be sourced from that primary document is left as a
``fact_needed`` marker rather than guessed.

The pack is ``draft=True``: the core Articles are verified but the
obligation set is not complete and the Article 8(1) Member State
derogations are unsourced.  The engine enforces the rule that a draft
pack must never emit ``SATISFIED``; this module does not work around
that.
"""

from __future__ import annotations

import dataclasses

from datetime import date

from samanvaya.engine import evaluate_obligations
from samanvaya.types import (
    AppliesIf,
    ConsentMechanism,
    Declaration,
    Finding,
    GovernanceDeclaration,
    NoticeDeclaration,
    Obligation,
    ObligationResult,
    ObligationTopic,
    Organisation,
    PackInfo,
    PackLoadError,
    PredicateOp,
    RegimeId,
    SubTopic,
    fact_needed,
)

PACK_ID: str = "eu_gdpr"
INSTRUMENT: str = "Regulation (EU) 2016/679"
VERSION: str = "0.1.0"
AS_AT: date = date(2026, 8, 19)
GDPR_APPLICATION_DATE: date = date(2018, 5, 25)

DRAFT_REASON: str = (
    "Core Articles verified verbatim on EUR-Lex 2026-08-19, but the obligation "
    "set is not complete and the Article 8(1) Member State derogations are not "
    "primary-sourced."
)


def info() -> PackInfo:
    """Return metadata about this pack.

    The obligation count is taken from the module-level tuple so the
    pack cannot drift between the count advertised to the engine and
    the obligations actually exported.
    """
    return PackInfo(
        pack_id=PACK_ID,
        regime=RegimeId.EU_GDPR,
        version=VERSION,
        covers_sub_units=frozenset(),
        as_at=AS_AT,
        draft=True,
        draft_reason=DRAFT_REASON,
        obligation_count=len(_OBLIGATIONS),
        instruments=(INSTRUMENT,),
    )


# Module-level rationale channel: the engine owns Finding construction
# and the evaluator contract is deliberately narrow (it may return only
# an ObligationResult), so the paths a CONTESTED verdict depends on
# cannot travel back through the return value.  ``evaluate()`` reads
# this dict after the engine has run and rewrites the rationale of any
# CONTESTED finding that has recorded paths.  This channel exists
# because the engine owns Finding construction and the evaluator
# contract returns only an ObligationResult.
MISSING_PATHS: dict[str, tuple[str, ...]] = {}


def missing_paths_for(obligation_id: str) -> tuple[str, ...]:
    """Return the declaration paths missing on the most recent evaluation.

    Returns an empty tuple when the obligation was not CONTESTED for a
    missing-declaration reason, or when it has not been evaluated.
    """
    return MISSING_PATHS.get(obligation_id, ())


def evaluate(
    declaration: Declaration, as_at: date, sub_unit: str | None
) -> list[object]:
    """Evaluate the EU GDPR pack against ``declaration``.

    The EU is not modelled as a jurisdictional tree in this tool: any
    non-``None`` ``sub_unit`` is rejected at the top level so the engine
    does not see a phantom member-state obligation.  Per-obligation
    conformance judgements live in :func:`_evaluate_one`; the engine
    owns gating (``applies_if``, ``depends_on``, in-force) and the draft
    downgrade.
    """
    if sub_unit is not None:
        return []
    # Clear per run so one evaluation cannot leak paths into the next.
    MISSING_PATHS.clear()
    findings = evaluate_obligations(
        _OBLIGATIONS,
        declaration,
        as_at,
        _evaluate_one,
        pack_info=info(),
    )
    rewritten: list[object] = []
    for finding in findings:
        # `obligation_id` lives on the Obligation, not on the Finding, and `Finding` is a
        # frozen dataclass — neither `model_copy` nor `_replace` exists on it. Getting
        # either of those wrong fails silently: the rewrite simply never happens and every
        # CONTESTED finding reaches the adviser without naming the fact to go and ask for,
        # which is the whole defect this loop was added to fix.
        if finding.result is ObligationResult.CONTESTED:
            paths = missing_paths_for(finding.obligation.obligation_id)
            if paths:
                rationale = "; ".join(
                    f"{path} was not declared; the obligation cannot be "
                    "judged either way until it is."
                    for path in paths
                )
                finding = dataclasses.replace(finding, rationale=rationale)
        rewritten.append(finding)
    return rewritten


def _missing(obligation_id: str, *paths: str) -> ObligationResult:
    """Return a CONTESTED result naming the missing declaration paths.

    A single helper keeps the rationale wording uniform across all
    obligations so the downstream adviser sees the same phrasing for
    every unresolved fact.  The obligation id is passed explicitly at
    every call site so two interleaved evaluations can never attach one
    obligation's missing paths to another's rationale.  The paths are
    recorded in the module-level ``MISSING_PATHS`` channel because the
    evaluator signature may not carry them back; ``evaluate()`` folds
    them into the finding.
    """
    MISSING_PATHS[obligation_id] = tuple(paths)
    return ObligationResult.CONTESTED


# ---------------------------------------------------------------------------
# Obligation catalogue
# ---------------------------------------------------------------------------
# Each obligation is declared as a tuple then converted to an ``Obligation``
# at module load.  Building them from tuples keeps the catalogue grep-able
# and the verification path obvious: every line carries the Article it
# implements in plain text.


def _make_obligation(
    *,
    obligation_id: str,
    topic: ObligationTopic,
    dimension: str,
    value: str,
    unit: str | None,
    provision: str,
    obligation_summary: str,
    applies_if: tuple[AppliesIf, ...] = (),
    required_value: str | None = None,
    depends_on: tuple[str, ...] = (),
    evaluation_metadata: tuple[tuple[str, str], ...] = (),
) -> Obligation:
    """Construct an ``Obligation`` carrying the standard GDPR headers.

    Every obligation in this pack is in force from
    :data:`GDPR_APPLICATION_DATE` (Article 99(2), the date from which the
    Regulation applies) and cites the instrument by Article in the
    citation pointer.
    """
    return Obligation(
        obligation_id=obligation_id,
        regime=RegimeId.EU_GDPR,
        sub_unit=None,
        instrument=INSTRUMENT,
        provision=provision,
        topic=topic,
        sub_topic=SubTopic(dimension=dimension, value=value, unit=unit),
        obligation_summary=obligation_summary,
        citation_pointer=f"Regulation (EU) 2016/679, {provision}",
        in_force_from=GDPR_APPLICATION_DATE,
        applies_if=applies_if,
        required_value=required_value,
        depends_on=depends_on,
        evaluation_metadata=evaluation_metadata,
    )


_OBLIGATIONS: tuple[Obligation, ...] = (
    _make_obligation(
        obligation_id="eu.notice.content",
        topic=ObligationTopic.NOTICE,
        dimension="notice_content",
        value="required",
        unit=None,
        provision="Article 13",
        obligation_summary=(
            "Article 13 requires the controller to provide the data subject "
            "with information about the controller's identity, the purposes "
            "of processing, the categories of personal data, the recipients, "
            "and the retention period at the point of collection."
        ),
    ),
    _make_obligation(
        obligation_id="eu.lawful_basis",
        topic=ObligationTopic.LAWFUL_BASIS,
        dimension="lawful_basis_required",
        value="at least one of six",
        unit=None,
        provision="Article 6",
        obligation_summary=(
            "Article 6 requires that processing have at least one lawful "
            "basis from the six listed in Article 6(1). A declared consent "
            "mechanism that actually identifies a basis is the minimum "
            "evidence the pack needs to assess whether any basis has been "
            "recorded; declared purposes alone are not a lawful basis."
        ),
    ),
    _make_obligation(
        obligation_id="eu.principles",
        topic=ObligationTopic.ACCOUNTABILITY,
        dimension="processing_principles",
        value="6",
        unit="principles",
        provision="Article 5",
        obligation_summary=(
            "Article 5(1) sets out six principles relating to processing of "
            "personal data, at points (a) to (f). Accountability is not a seventh "
            "principle in the text: Article 5(2) separately makes the controller "
            "responsible for, and able to demonstrate compliance with, paragraph 1. "
            "Counting it as a seventh principle is a common gloss that this pack "
            "does not adopt. Maintaining processing records is the evidence that "
            "the controller can discharge the Article 5(2) duty."
        ),
    ),
    _make_obligation(
        obligation_id="eu.children.age",
        topic=ObligationTopic.CHILDREN,
        dimension="child_consent_age",
        value="16",
        unit="years",
        provision="Article 8(1)",
        obligation_summary=(
            "Article 8(1) fixes the age of lawful consent for information "
            "society services directly offered to a child at 16 years. "
            "Member States may legislate a lower age, provided it is not "
            "below 13 years. The duty is decided by whether the controller "
            "can verify parental consent."
        ),
        applies_if=(
            AppliesIf(
                path="organisation.offers_services_to_children",
                op=PredicateOp.TRUTHY,
                value=True,
                description="Article 8(1) only applies where services are "
                "offered directly to a child.",
            ),
        ),
        evaluation_metadata=(
            (
                "member_state_derogation",
                fact_needed(
                    "which Member States have lowered the Article 8(1) age, "
                    "and to what age?"
                ),
            ),
        ),
    ),
    _make_obligation(
        obligation_id="eu.security.measures",
        topic=ObligationTopic.SECURITY,
        dimension="security_standard",
        value="appropriate to the risk",
        unit=None,
        provision="Article 32(1)",
        obligation_summary=(
            "Article 32(1) requires appropriate technical and organisational "
            "measures to ensure a level of security appropriate to the risk, "
            "listing pseudonymisation and encryption as examples 'including "
            "interalia as appropriate'. The provision does not prescribe a "
            "single standard; the pack treats the mere presence of declared "
            "safeguards as the minimum evidence of compliance."
        ),
    ),
    _make_obligation(
        obligation_id="eu.breach.authority",
        topic=ObligationTopic.BREACH,
        dimension="breach_notice_deadline",
        value="72",
        unit="hours",
        provision="Article 33(1)",
        obligation_summary=(
            "Article 33(1) requires notification to the supervisory "
            "authority without undue delay and, where feasible, not later "
            "than 72 hours after having become aware of a breach."
        ),
    ),
    _make_obligation(
        obligation_id="eu.breach.subject",
        topic=ObligationTopic.BREACH,
        dimension="breach_individual_notice_trigger",
        value="high risk",
        unit=None,
        provision="Article 34(1)",
        obligation_summary=(
            "Article 34(1) requires the controller to communicate a breach "
            "to the data subject without undue delay where the breach is "
            "likely to result in a high risk to the rights and freedoms of "
            "natural persons."
        ),
    ),
    _make_obligation(
        obligation_id="eu.rights.deadline",
        topic=ObligationTopic.RIGHTS,
        dimension="dsr_response_period",
        value="1",
        unit="months",
        provision="Article 12(3)",
        obligation_summary=(
            "Article 12(3) requires the controller to respond to a data "
            "subject request without undue delay and in any event within "
            "one month of receipt, extensible by two further months where "
            "necessary. The pack compares one month as 30 days; this is a "
            "modelling approximation, not a statutory equivalence."
        ),
        evaluation_metadata=(
            ("extension", "two further months"),
            (
                "month_to_days_note",
                "one month is compared as 30 days; the Regulation says one month",
            ),
        ),
    ),
    _make_obligation(
        obligation_id="eu.records.ropa",
        topic=ObligationTopic.RECORDS,
        dimension="records_threshold",
        value="250",
        unit="persons",
        provision="Article 30(5)",
        obligation_summary=(
            "Article 30(5) relieves an enterprise or organisation employing "
            "fewer than 250 persons of the records obligation only "
            "conditionally: the derogation is defeated where the processing "
            "is likely to result in a risk to the rights and freedoms of "
            "data subjects, is not occasional, or includes Article 9(1) "
            "special categories or Article 10 data. An organisation below "
            "the 250 threshold therefore cannot assume it is relieved; the "
            "carve-outs must be checked first. At or above 250 employees "
            "the records duty applies outright."
        ),
        # No applies_if: Article 30(5) is not a simple employee-count
        # gate — the derogation below 250 is conditional — so the pack
        # owns the engagement logic in ``_evaluate_one``.
        evaluation_metadata=(
            (
                "derogation_carve_outs",
                "risk|not occasional|Article 9(1) or Article 10",
            ),
        ),
    ),
    _make_obligation(
        obligation_id="eu.processor_contract",
        topic=ObligationTopic.PROCESSOR,
        dimension="processor_contract",
        value="required",
        unit=None,
        provision="Article 28(3)",
        obligation_summary=(
            "Article 28(3) requires processing by a processor to be "
            "governed by a contract or other legal act setting out the "
            "subject matter, duration, nature and purpose of processing, "
            "the obligations of the processor and the rights of the "
            "controller."
        ),
    ),
    _make_obligation(
        obligation_id="eu.governance.dpia",
        topic=ObligationTopic.GOVERNANCE,
        dimension="dpia_trigger",
        value="high risk",
        unit=None,
        provision="Article 35(1)",
        obligation_summary=(
            "Article 35(1) requires the controller to carry out a data "
            "protection impact assessment prior to processing where it is "
            "likely to result in a high risk to the rights and freedoms of "
            "natural persons."
        ),
        applies_if=(
            AppliesIf(
                path="organisation.conducts_large_scale_monitoring",
                op=PredicateOp.TRUTHY,
                value=True,
                description="Article 35(1) and Article 37(1)(b) both engage "
                "on large-scale monitoring of data subjects.",
            ),
        ),
    ),
    _make_obligation(
        obligation_id="eu.governance.dpo",
        topic=ObligationTopic.GOVERNANCE,
        dimension="dpo_trigger",
        value="public authority, large-scale monitoring, or large-scale special categories",
        unit=None,
        provision="Article 37(1)",
        obligation_summary=(
            "Article 37(1) requires the designation of a data protection "
            "officer where (a) processing is by a public authority or "
            "body, (b) core activities consist of regular and systematic "
            "monitoring of data subjects on a large scale, or (c) core "
            "activities consist of large-scale processing of Article 9(1) "
            "special categories of data."
        ),
        # No applies_if: Article 37(1) has three alternative triggers and
        # encoding them as ANDed predicates would be wrong.  See
        # ``_evaluate_one`` for the engagement logic.
    ),
    _make_obligation(
        obligation_id="eu.crossborder",
        topic=ObligationTopic.CROSS_BORDER,
        dimension="transfer_basis",
        value="adequacy, safeguards or derogation",
        unit=None,
        provision="Article 44",
        obligation_summary=(
            "Article 44 establishes the general principle that any "
            "transfer of personal data to a third country or "
            "international organisation requires an adequacy decision, "
            "appropriate safeguards, or one of the derogations in "
            "Article 49."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Per-obligation conformance judgement
# ---------------------------------------------------------------------------


def _evaluate_one(
    obligation: Obligation, declaration: Declaration
) -> ObligationResult:
    """Return the conformance judgement for a single obligation.

    The engine owns gating (``applies_if``, ``depends_on``, in-force and
    the draft downgrade); this function answers only the narrow
    question ``does the declaration, on its face, address this duty?``
    Any explanatory text that the adviser needs is carried on the
    obligation itself in ``obligation_summary`` and
    ``evaluation_metadata``.
    """
    org: Organisation = declaration.organisation
    consent: ConsentMechanism = declaration.consent_mechanism
    governance: GovernanceDeclaration = declaration.governance
    notice: NoticeDeclaration = declaration.notice

    ob_id = obligation.obligation_id

    if ob_id == "eu.notice.content":
        # Article 13 lists five items we look for; if any of them is not
        # declared the result is CONTESTED, not a silent pass.  A limb
        # declared False is an affirmative failure: GAP.
        missing: list[str] = []
        failed: list[str] = []
        for path, value in (
            ("notice.described", notice.described),
            ("notice.describes_purpose", notice.describes_purpose),
            ("notice.describes_personal_data", notice.describes_personal_data),
            ("notice.identifies_recipients", notice.identifies_recipients),
            ("notice.states_retention_period", notice.states_retention_period),
            ("notice.states_controller_identity", notice.states_controller_identity),
        ):
            if value is None:
                missing.append(path)
            elif value is False:
                failed.append(path)
        if missing:
            return _missing(ob_id, *missing)
        if failed:
            return ObligationResult.GAP
        return ObligationResult.SATISFIED

    if ob_id == "eu.lawful_basis":
        # Article 6 requires an identified lawful basis.  Bare declared
        # purposes must NEVER satisfy this obligation: "we have purposes"
        # is not a lawful basis, and recording it as such would hand out
        # a false clean bill once the pack leaves draft.
        if consent.described is True:
            if consent.mechanism:
                return ObligationResult.SATISFIED
            # Described but no mechanism identified: the basis itself is
            # still not declared.
            return _missing(
                ob_id, "consent_mechanism.described",
                "consent_mechanism.mechanism",
            )
        if consent.described is False:
            return ObligationResult.GAP
        return _missing(
            ob_id, "consent_mechanism.described",
            "consent_mechanism.mechanism",
        )

    if ob_id == "eu.principles":
        # Article 5(2) accountability is shown through processing
        # records; the Article 5(1) principles themselves are not separately
        # checkable from a declaration.
        if governance.maintains_processing_records is True:
            return ObligationResult.SATISFIED
        if governance.maintains_processing_records is False:
            return ObligationResult.GAP
        return _missing(ob_id, "governance.maintains_processing_records")

    if ob_id == "eu.children.age":
        # The engine has already gated on offers_services_to_children.
        # Here we only decide whether parental consent is verifiable.
        if consent.parental_consent_verifiable is True:
            return ObligationResult.SATISFIED
        if consent.parental_consent_verifiable is False:
            return ObligationResult.GAP
        return _missing(ob_id, "consent_mechanism.parental_consent_verifiable")

    if ob_id == "eu.security.measures":
        # Article 32(1) lists pseudonymisation and encryption as
        # examples, not as the only acceptable measures; the duty is to
        # apply measures appropriate to the risk.  Presence of any
        # declared safeguard is the minimum evidence.  An empty tuple
        # means nothing was declared: CONTESTED, not GAP — absence of a
        # declaration is not a declared absence.
        if declaration.security_safeguards:
            return ObligationResult.SATISFIED
        return _missing(ob_id, "security_safeguards")

    if ob_id == "eu.breach.authority":
        bwf = declaration.breach_workflow
        if bwf.notifies_regulator is None:
            return _missing(ob_id, "breach_workflow.notifies_regulator")
        if bwf.notifies_regulator is False:
            return ObligationResult.GAP
        if bwf.regulator_deadline_hours is None:
            return _missing(ob_id, "breach_workflow.regulator_deadline_hours")
        if bwf.regulator_deadline_hours > 72:
            return ObligationResult.GAP
        return ObligationResult.SATISFIED

    if ob_id == "eu.breach.subject":
        value = declaration.breach_workflow.notifies_affected_individuals
        if value is None:
            return _missing(ob_id, "breach_workflow.notifies_affected_individuals")
        if value is False:
            return ObligationResult.GAP
        return ObligationResult.SATISFIED

    if ob_id == "eu.rights.deadline":
        dsr = declaration.dsr_workflow
        if dsr.described is not True:
            if dsr.described is False:
                return ObligationResult.GAP
            return _missing(ob_id, "dsr_workflow.described")
        if dsr.response_deadline_days is None:
            return _missing(ob_id, "dsr_workflow.response_deadline_days")
        if dsr.response_deadline_days > 30:
            # One month is modelled as 30 days; see the note on the
            # obligation's evaluation_metadata.
            return ObligationResult.GAP
        return ObligationResult.SATISFIED

    if ob_id == "eu.records.ropa":
        # Article 30(5) is not a simple employee-count gate.  The
        # derogation below 250 is defeated where the processing is
        # likely to result in a risk to the rights and freedoms of data
        # subjects, is not occasional, or includes Article 9(1) special
        # categories or Article 10 data.  The tool must not certify a
        # derogation on facts it never asked for.

        def _decide_records() -> ObligationResult:
            if governance.maintains_processing_records is True:
                return ObligationResult.SATISFIED
            if governance.maintains_processing_records is False:
                return ObligationResult.GAP
            return _missing(ob_id, "governance.maintains_processing_records")

        if org.employee_count is None:
            return _missing(ob_id, "organisation.employee_count")

        if org.employee_count >= 250:
            # The derogation does not reach here; the duty applies.
            return _decide_records()

        # Below 250 the derogation MIGHT apply; test the carve-outs.
        if org.processes_special_category_data is True:
            # Article 9(1)/Article 10 carve-out defeats the derogation;
            # the duty applies.
            return _decide_records()
        if org.processes_special_category_data is None:
            # The derogation cannot be relied on without this fact.
            return _missing(
                ob_id, "organisation.processes_special_category_data"
            )
        # The special-category carve-out is out of the way, but the
        # other two carve-outs (risk to rights and freedoms, and
        # not-occasional processing) are not declarable from this
        # schema.  DO NOT return NOT_APPLICABLE: the tool must not
        # certify a derogation on facts it never asked for.
        MISSING_PATHS[ob_id] = (
            fact_needed(
                "does the processing involve Article 9(1) special "
                "categories or Article 10 data?"
            ),
            fact_needed(
                "is any processing likely to result in a risk to the "
                "rights and freedoms of data subjects?"
            ),
            fact_needed(
                "is any processing other than occasional?"
            ),
        )
        return ObligationResult.CONTESTED

    if ob_id == "eu.processor_contract":
        if governance.processor_contracts_in_place is True:
            return ObligationResult.SATISFIED
        if governance.processor_contracts_in_place is False:
            return ObligationResult.GAP
        return _missing(ob_id, "governance.processor_contracts_in_place")

    if ob_id == "eu.governance.dpia":
        if governance.conducts_impact_assessments is True:
            return ObligationResult.SATISFIED
        if governance.conducts_impact_assessments is False:
            return ObligationResult.GAP
        return _missing(ob_id, "governance.conducts_impact_assessments")

    if ob_id == "eu.governance.dpo":
        # Article 37(1) has three alternative triggers: the duty is
        # engaged if ANY of them is true, not all.  Encoding this as an
        # ANDed ``applies_if`` would mis-state the law, so the pack
        # owns the engagement logic here.
        public_authority = org.is_public_authority
        monitoring = org.conducts_large_scale_monitoring
        special_cat = org.processes_special_category_data

        declared = [
            public_authority is not None,
            monitoring is not None,
            special_cat is not None,
        ]
        if not any(declared):
            return _missing(
                ob_id,
                "organisation.is_public_authority",
                "organisation.conducts_large_scale_monitoring",
                "organisation.processes_special_category_data",
            )

        values = [public_authority, monitoring, special_cat]
        declared_false = [
            v is False for v in values if v is not None
        ]
        if declared_false and not any(v is True for v in values if v is not None):
            return ObligationResult.NOT_APPLICABLE

        if public_authority is None:
            return _missing(ob_id, "organisation.is_public_authority")
        if monitoring is None:
            return _missing(ob_id, "organisation.conducts_large_scale_monitoring")
        if special_cat is None:
            return _missing(ob_id, "organisation.processes_special_category_data")

        if governance.has_privacy_officer is True:
            return ObligationResult.SATISFIED
        if governance.has_privacy_officer is False:
            return ObligationResult.GAP
        return _missing(ob_id, "governance.has_privacy_officer")

    if ob_id == "eu.crossborder":
        xb = declaration.cross_border
        if xb.transfers_outside_jurisdiction is False:
            return ObligationResult.NOT_APPLICABLE
        if xb.transfers_outside_jurisdiction is None:
            return _missing(ob_id, "cross_border.transfers_outside_jurisdiction")
        if xb.transfer_mechanism:
            return ObligationResult.SATISFIED
        return _missing(ob_id, "cross_border.transfer_mechanism")

    # An unrecognised obligation id is a bug in the pack, not a gap in
    # the client's facts; it must not surface as a data-quality
    # CONTESTED finding.
    raise PackLoadError(
        f"eu_gdpr pack: unknown obligation_id {ob_id!r} in evaluator"
    )


__all__ = [
    "PACK_ID",
    "INSTRUMENT",
    "VERSION",
    "AS_AT",
    "GDPR_APPLICATION_DATE",
    "DRAFT_REASON",
    "MISSING_PATHS",
    "info",
    "evaluate",
    "missing_paths_for",
]
