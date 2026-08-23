"""Canadian privacy obligations pack — federal verified, Quebec unsourced.

This is a jurisdictional tree. PIPEDA and SOR/2018-64 were verified
verbatim on laws-lois.justice.gc.ca on 2026-08-19, so the federal
obligations carry their true statutory text. legisquebec.gouv.qc.ca
timed out repeatedly, so every constant under Quebec's Law 25 private
sector statute is unsourced and marked [FACT NEEDED]. Provincial
statutes beyond Quebec are likewise unsourced.

`sub_unit is None` yields ONLY the federal PIPEDA obligations — Quebec
obligations are never emitted at federal level, because Quebec's statute
does not apply to an organisation assessed solely against federal law.
`sub_unit == "CA-QC"` yields ONLY the Quebec obligations. Any other
sub_unit yields nothing, as this pack covers no other province.

Bill C-27 died on the Order Paper in January 2025; PIPEDA remains in
force and is the operative federal private-sector statute assessed here.

The engine enforces that a draft pack can never emit SATISFIED (this
pack is draft because of the unsourced Quebec layer); that enforcement
is not reimplemented here.
"""

from __future__ import annotations

from datetime import date

from samanvaya.engine import evaluate_obligations
from samanvaya.types import (
    Declaration,
    Finding,
    Obligation,
    ObligationResult,
    PackInfo,
    RegimeId,
    SubTopic,
    ObligationTopic,
    fact_needed,
)

PACK_ID: str = "canada"
VERSION: str = "0.1.0"
AS_AT: date = date(2026, 8, 19)
DRAFT_REASON: str = (
    "PIPEDA and SOR/2018-64 verified verbatim on laws-lois.justice.gc.ca "
    "2026-08-19, but legisquebec.gouv.qc.ca timed out repeatedly, so every "
    "Quebec Law 25 constant is unsourced, and provincial statutes beyond "
    "Quebec are unsourced."
)

_FEDERAL_INSTRUMENTS: tuple[str, ...] = (
    "Personal Information Protection and Electronic Documents Act",
    "Breach of Security Safeguards Regulations, SOR/2018-64",
)
_ALL_INSTRUMENTS: tuple[str, ...] = _FEDERAL_INSTRUMENTS + (
    "Act respecting the protection of personal information in the private sector",
)

CA_BREACH_COMMISSIONER: Obligation = Obligation(
    obligation_id="ca.breach.commissioner",
    regime=RegimeId.CANADA,
    sub_unit=None,
    instrument="Personal Information Protection and Electronic Documents Act",
    provision="Section 10.1(1)",
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_report_trigger",
        value="real risk of significant harm",
        unit=None,
    ),
    obligation_summary=(
        "Report to the Privacy Commissioner of Canada any breach of security "
        "safeguards involving personal information under the organisation's "
        "control if it is reasonable in the circumstances to believe that the "
        "breach creates a real risk of significant harm to an individual."
    ),
    citation_pointer="PIPEDA, s.10.1(1)",
)

CA_BREACH_INDIVIDUAL: Obligation = Obligation(
    obligation_id="ca.breach.individual",
    regime=RegimeId.CANADA,
    sub_unit=None,
    instrument="Personal Information Protection and Electronic Documents Act",
    provision="Section 10.1(3)",
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_individual_notice_trigger",
        value="real risk of significant harm",
        unit=None,
    ),
    obligation_summary=(
        "Notify an individual of any breach of security safeguards involving "
        "personal information under the organisation's control if it is "
        "reasonable in the circumstances to believe that the breach creates a "
        "real risk of significant harm to the individual."
    ),
    citation_pointer="PIPEDA, s.10.1(3)",
)

CA_BREACH_RECORDS: Obligation = Obligation(
    obligation_id="ca.breach.records",
    regime=RegimeId.CANADA,
    sub_unit=None,
    instrument="Breach of Security Safeguards Regulations, SOR/2018-64",
    provision="Section 10.3(1) read with SOR/2018-64, s.6",
    topic=ObligationTopic.RECORDS,
    sub_topic=SubTopic(
        dimension="breach_record_retention",
        value="24",
        unit="months",
    ),
    required_value="24",
    obligation_summary=(
        "Maintain a record of every breach of security safeguards involving "
        "personal information under the organisation's control, and retain "
        "that record for 24 months after the day on which the organisation "
        "determines that the breach has occurred."
    ),
    citation_pointer="PIPEDA, s.10.3(1); SOR/2018-64, s.6",
)

CA_PRINCIPLES: Obligation = Obligation(
    obligation_id="ca.principles",
    regime=RegimeId.CANADA,
    sub_unit=None,
    instrument="Personal Information Protection and Electronic Documents Act",
    provision="Schedule 1",
    topic=ObligationTopic.ACCOUNTABILITY,
    sub_topic=SubTopic(
        dimension="fair_information_principles",
        value="10",
        unit="principles",
    ),
    required_value="10",
    obligation_summary=(
        "Schedule 1 sets out the National Standard of Canada CAN/CSA-Q830-96, "
        "comprising ten principles of fair information practice, with "
        "Principle 1 (Accountability) at clause 4.1 requiring an organisation "
        "to designate an individual accountable for compliance."
    ),
    citation_pointer="PIPEDA, Schedule 1, clause 4.1",
)

_FEDERAL_OBLIGATIONS: tuple[Obligation, ...] = (
    CA_BREACH_COMMISSIONER,
    CA_BREACH_INDIVIDUAL,
    CA_BREACH_RECORDS,
    CA_PRINCIPLES,
)

CA_QC_PIA: Obligation = Obligation(
    obligation_id="ca.qc.pia",
    regime=RegimeId.CANADA,
    sub_unit="CA-QC",
    instrument="Act respecting the protection of personal information in the private sector",
    provision=fact_needed(
        "Quebec private sector Act — which section requires a privacy impact "
        "assessment before communicating personal information outside Quebec?"
    ),
    topic=ObligationTopic.GOVERNANCE,
    sub_topic=SubTopic(
        dimension="pia_for_transfer_outside_quebec",
        value=fact_needed(
            "Quebec private sector Act — which section requires a privacy "
            "impact assessment before communicating personal information "
            "outside Quebec?"
        ),
        unit=None,
    ),
    obligation_summary="Privacy impact assessment before communicating personal information outside Quebec; section unsourced.",
    citation_pointer="Quebec private sector Act, PIA provision (unverified)",
)

CA_QC_CHILDREN: Obligation = Obligation(
    obligation_id="ca.qc.children",
    regime=RegimeId.CANADA,
    sub_unit="CA-QC",
    instrument="Act respecting the protection of personal information in the private sector",
    provision=fact_needed(
        "Quebec private sector Act — below what age is parental consent required?"
    ),
    topic=ObligationTopic.CHILDREN,
    sub_topic=SubTopic(
        dimension="child_consent_age",
        value=fact_needed(
            "Quebec private sector Act — below what age is parental consent "
            "required?"
        ),
        unit="years",
    ),
    obligation_summary="Age below which parental consent is required under the Quebec private sector Act; unsourced.",
    citation_pointer="Quebec private sector Act, minor consent provision (unverified)",
)

CA_QC_OFFICER: Obligation = Obligation(
    obligation_id="ca.qc.officer",
    regime=RegimeId.CANADA,
    sub_unit="CA-QC",
    instrument="Act respecting the protection of personal information in the private sector",
    provision=fact_needed(
        "Quebec private sector Act — which section provides for the person in "
        "charge of the protection of personal information?"
    ),
    topic=ObligationTopic.GOVERNANCE,
    sub_topic=SubTopic(
        dimension="person_in_charge",
        value=fact_needed(
            "Quebec private sector Act — which section provides for the "
            "person in charge of the protection of personal information?"
        ),
        unit=None,
    ),
    obligation_summary="Person in charge of the protection of personal information; section unsourced.",
    citation_pointer="Quebec private sector Act, person in charge provision (unverified)",
)

CA_QC_PENALTY: Obligation = Obligation(
    obligation_id="ca.qc.penalty",
    regime=RegimeId.CANADA,
    sub_unit="CA-QC",
    instrument="Act respecting the protection of personal information in the private sector",
    provision=fact_needed(
        "Quebec private sector Act — which sections fix the maximum "
        "administrative monetary penalty and the maximum penal fine, and at "
        "what amounts?"
    ),
    topic=ObligationTopic.PENALTY,
    sub_topic=SubTopic(
        dimension="maximum_penalty",
        value=fact_needed(
            "Quebec private sector Act — which sections fix the maximum "
            "administrative monetary penalty and the maximum penal fine, and "
            "at what amounts?"
        ),
        unit=None,
    ),
    obligation_summary="Maximum administrative monetary penalty and penal fine under the Quebec private sector Act; unsourced.",
    citation_pointer="Quebec private sector Act, penalty provisions (unverified)",
)

_QUEBEC_OBLIGATIONS: tuple[Obligation, ...] = (
    CA_QC_PIA,
    CA_QC_CHILDREN,
    CA_QC_OFFICER,
    CA_QC_PENALTY,
)


def info() -> PackInfo:
    """Return pack metadata for the engine and the report header."""
    return PackInfo(
        pack_id=PACK_ID,
        regime=RegimeId.CANADA,
        version=VERSION,
        covers_sub_units=frozenset({"CA-QC"}),
        as_at=AS_AT,
        draft=True,
        obligation_count=len(_FEDERAL_OBLIGATIONS) + len(_QUEBEC_OBLIGATIONS),
        instruments=_ALL_INSTRUMENTS,
        draft_reason=DRAFT_REASON,
    )


def _bool_flag(flag: bool | None) -> ObligationResult:
    """Map an optional boolean declaration to a conformance judgement.

    ``None`` means the declaration is silent, which is CONTESTED rather
    than a pass: an undeclared fact is not a compliant one.
    """
    if flag is None:
        return ObligationResult.CONTESTED
    if flag is True:
        return ObligationResult.SATISFIED
    return ObligationResult.GAP


def _evaluate_one(obligation: Obligation, declaration: Declaration) -> ObligationResult:
    """Judge one obligation against the declaration.

    The FACT NEEDED check is the FIRST branch so an unsourced constant
    always yields CONTESTED and can never be forgotten per-obligation.
    """
    if obligation.has_unsourced_constant():
        return ObligationResult.CONTESTED

    if obligation.obligation_id == "ca.breach.commissioner":
        return _bool_flag(declaration.breach_workflow.notifies_regulator)
    if obligation.obligation_id == "ca.breach.individual":
        return _bool_flag(declaration.breach_workflow.notifies_affected_individuals)
    if obligation.obligation_id == "ca.breach.records":
        return _bool_flag(declaration.breach_workflow.maintains_breach_register)
    if obligation.obligation_id == "ca.principles":
        return _bool_flag(declaration.governance.has_privacy_officer)
    return ObligationResult.CONTESTED


def _unsourced_province(sub_unit: str) -> Obligation:
    """An explicit "nothing has been researched here" obligation for a province.

    Carries a FACT NEEDED marker in both the provision and the compared value, so the
    engine resolves it to CONTESTED, the delta excludes it from comparison rather than
    manufacturing a divergence against a placeholder, and the reader still sees a row
    telling them the province was not covered.
    """
    question = (
        f"which private-sector privacy statute applies in {sub_unit}, what is its "
        "citation, and has it been declared substantially similar to PIPEDA?"
    )
    return Obligation(
        obligation_id=f"ca.{sub_unit.lower()}.unsourced",
        regime=RegimeId.CANADA,
        sub_unit=sub_unit,
        instrument="Unidentified provincial private-sector privacy statute",
        provision=fact_needed(question),
        topic=ObligationTopic.ACCOUNTABILITY,
        sub_topic=SubTopic(
            dimension="provincial_statute_identified",
            value=fact_needed(question),
            unit=None,
        ),
        obligation_summary=(
            f"{sub_unit}: no provincial private-sector privacy statute has been "
            "researched for this province. This finding is emitted deliberately so "
            "that the province is reported as uncovered rather than omitted, because "
            "an omitted section reads as a clean bill of health. PIPEDA still applies "
            "federally and is evaluated separately."
        ),
        citation_pointer=fact_needed(question),
    )


def evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]:
    """Evaluate the obligations applicable to `sub_unit` only.

    The jurisdictional tree is enforced here by selecting the obligation
    set BEFORE delegating to the engine, which owns applies_if,
    depends_on, in-force handling and the draft downgrade.
    """
    if sub_unit is None:
        obligations: tuple[Obligation, ...] = _FEDERAL_OBLIGATIONS
    elif sub_unit == "CA-QC":
        obligations = _QUEBEC_OBLIGATIONS
    elif len(sub_unit) == 5 and sub_unit.startswith("CA-") and sub_unit[3:].isalpha():
        # An unresearched province is REPORTED as unresearched, never answered with
        # silence. Alberta and British Columbia each have their own private-sector
        # privacy statute, and others may follow; this pack has researched none of them.
        # Returning an empty list would leave the province out of the report entirely,
        # and an absent section reads to a client as a clean bill of health.
        #
        # This mirrors the US pack, which already does exactly this for an unresearched
        # state. Two federations behaving differently in the same situation is itself a
        # defect: the adviser would have to remember which pack is silent and which is
        # explicit. The safer of the two behaviours wins.
        obligations = (_unsourced_province(sub_unit),)
    else:
        return []
    return evaluate_obligations(
        obligations,
        declaration,
        as_at,
        _evaluate_one,
        pack_info=info(),
    )
