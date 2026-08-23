"""United States privacy obligations pack — federal sectoral partly verified.

This is a jurisdictional tree. COPPA, the HIPAA Breach Notification and
Security Rules, and the GLBA Safeguards Rule were verified verbatim on
ecfr.gov on 2026-08-19, so the federal obligations carry their true
regulatory text. leginfo.legislature.ca.gov timed out, so the CCPA
layer is entirely unsourced, and no official aggregated list of US state
comprehensive privacy statutes in effect in 2026 exists — coverage must
be assembled statute by statute.

`sub_unit is None` yields ONLY the federal sectoral obligations.
`sub_unit == "US-CA"` yields ONLY the California obligations. Any other
well-formed US-XX code yields a SINGLE unsourced-state obligation, so an
unresearched state is REPORTED as unresearched rather than silently
returning nothing: silence would read as a clean bill of health, which
would be worse than an honest gap. Anything not matching US-XX yields
nothing.

Two deliberate accuracy guards, both drawn from the primary text: for
HIPAA breaches of 500 or more individuals the Secretary notice is
CONTEMPORANEOUS with the individual notice — NOT "60 days" as a
delegate's research wrongly asserted — and the GLBA 5,000-consumer
threshold is a PARTIAL exemption from four named paragraphs of
16 CFR 314.4, not a blanket exemption from the Rule.

The engine enforces that a draft pack can never emit SATISFIED; that is
not reimplemented here.
"""

from __future__ import annotations

from datetime import date

from samanvaya.engine import evaluate_obligations
from samanvaya.types import (
    PredicateOp,
    AppliesIf,
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

PACK_ID: str = "us"
VERSION: str = "0.1.0"
AS_AT: date = date(2026, 8, 19)
DRAFT_REASON: str = (
    "COPPA, HIPAA and the GLBA Safeguards Rule verified verbatim on "
    "ecfr.gov 2026-08-19, but leginfo.legislature.ca.gov timed out so CCPA "
    "is unsourced, and no official aggregated list of US state comprehensive "
    "privacy statutes in effect in 2026 exists — it must be assembled "
    "statute by statute."
)

_FEDERAL_INSTRUMENTS: tuple[str, ...] = (
    "Children's Online Privacy Protection Rule, 16 CFR part 312",
    "HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
    "HIPAA Security Rule, 45 CFR part 164 subpart C",
    "Gramm-Leach-Bliley Safeguards Rule, 16 CFR part 314",
)
_ALL_INSTRUMENTS: tuple[str, ...] = _FEDERAL_INSTRUMENTS + (
    "Family Educational Rights and Privacy Act",
    "California Consumer Privacy Act",
)

US_COPPA_AGE: Obligation = Obligation(
    obligation_id="us.coppa.age",
    regime=RegimeId.US,
    sub_unit=None,
    instrument="Children's Online Privacy Protection Rule, 16 CFR part 312",
    provision="16 CFR 312.2",
    topic=ObligationTopic.CHILDREN,
    sub_topic=SubTopic(
        dimension="child_age_threshold",
        value="13",
        unit="years",
    ),
    required_value="13",
    obligation_summary=(
        'COPPA: "Child means an individual under the age of 13." Verifiable '
        "parental consent is required before collecting personal information "
        "from a child."
    ),
    citation_pointer="16 CFR 312.2 (definition of Child); 16 CFR 312.5",
    applies_if=(
        AppliesIf(
            path="organisation.offers_services_to_children",
            op=PredicateOp.TRUTHY,
            value=True,
            description="The operator offers services directed to children.",
        ),
    ),
)

US_HIPAA_BREACH_INDIVIDUAL: Obligation = Obligation(
    obligation_id="us.hipaa.breach.individual",
    regime=RegimeId.US,
    sub_unit=None,
    instrument="HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
    provision="45 CFR 164.404(b)",
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_individual_notice_deadline",
        value="60",
        unit="days",
    ),
    required_value="60",
    obligation_summary=(
        "Notify each individual whose unsecured protected health information "
        "has been breached 'without unreasonable delay and in no case later "
        "than 60 calendar days after discovery of a breach'."
    ),
    citation_pointer="45 CFR 164.404(b)",
    applies_if=(
        AppliesIf(
            path="organisation.is_healthcare_provider",
            op=PredicateOp.TRUTHY,
            value=True,
            description="The organisation is a covered entity as a healthcare provider.",
        ),
    ),
)

US_HIPAA_BREACH_SECRETARY: Obligation = Obligation(
    obligation_id="us.hipaa.breach.secretary",
    regime=RegimeId.US,
    sub_unit=None,
    instrument="HIPAA Breach Notification Rule, 45 CFR part 164 subpart D",
    provision="45 CFR 164.408(b)",
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_regulator_notice_timing",
        value="contemporaneous",
        unit=None,
    ),
    required_value="contemporaneous",
    obligation_summary=(
        "For breaches of unsecured protected health information involving "
        "500 OR MORE individuals, notify the Secretary of Health and Human "
        "Services CONTEMPORANEOUSLY with the individual notice required by "
        "45 CFR 164.404(a). The notice is not deferred by any 60-day period."
    ),
    citation_pointer="45 CFR 164.408(b)",
    evaluation_metadata=(
        (
            "under_500_rule",
            "45 CFR 164.408(c): maintain a log and notify not later than "
            "60 days after the end of each calendar year",
        ),
    ),
    applies_if=(
        AppliesIf(
            path="organisation.is_healthcare_provider",
            op=PredicateOp.TRUTHY,
            value=True,
            description="The organisation is a covered entity as a healthcare provider.",
        ),
    ),
)

US_HIPAA_SECURITY: Obligation = Obligation(
    obligation_id="us.hipaa.security",
    regime=RegimeId.US,
    sub_unit=None,
    instrument="HIPAA Security Rule, 45 CFR part 164 subpart C",
    provision="45 CFR 164.306",
    topic=ObligationTopic.SECURITY,
    sub_topic=SubTopic(
        dimension="security_rule",
        value="Subpart C",
        unit=None,
    ),
    obligation_summary=(
        "Protect the confidentiality, integrity and availability of "
        "electronic protected health information through the administrative, "
        "physical and technical safeguards of the Security Rule."
    ),
    citation_pointer="45 CFR 164.306",
    applies_if=(
        AppliesIf(
            path="organisation.is_healthcare_provider",
            op=PredicateOp.TRUTHY,
            value=True,
            description="The organisation is a covered entity as a healthcare provider.",
        ),
    ),
)

US_GLBA_SAFEGUARDS: Obligation = Obligation(
    obligation_id="us.glba.safeguards",
    regime=RegimeId.US,
    sub_unit=None,
    instrument="Gramm-Leach-Bliley Safeguards Rule, 16 CFR part 314",
    provision="16 CFR 314.6",
    topic=ObligationTopic.SECURITY,
    sub_topic=SubTopic(
        dimension="safeguards_partial_exemption_threshold",
        value="5000",
        unit="consumers",
    ),
    required_value="5000",
    obligation_summary=(
        "Develop, implement and maintain a comprehensive information "
        "security program. This is a PARTIAL exemption threshold only: "
        "16 CFR 314.4(b)(1), (d)(2), (h) and (i) do NOT apply to financial "
        "institutions that maintain customer information concerning FEWER "
        "THAN FIVE THOUSAND consumers — the remainder of the Rule continues "
        "to apply. It is NOT a blanket exemption from the Safeguards Rule."
    ),
    citation_pointer="16 CFR 314.6 (partial exemption); 16 CFR 314.4",
    applies_if=(
        AppliesIf(
            path="organisation.is_financial_institution",
            op=PredicateOp.TRUTHY,
            value=True,
            description="The organisation is a financial institution.",
        ),
    ),
)

US_FERPA: Obligation = Obligation(
    obligation_id="us.ferpa",
    regime=RegimeId.US,
    sub_unit=None,
    # The instrument NAME is known and correct; only the provision is
    # unsourced, so the fact_needed marker goes in the provision alone.
    instrument="Family Educational Rights and Privacy Act",
    provision=fact_needed(
        "FERPA — what are the operative statutory and CFR provisions?"
    ),
    topic=ObligationTopic.ACCOUNTABILITY,
    sub_topic=SubTopic(
        dimension="ferpa_obligations",
        value=fact_needed(
            "FERPA — what are the operative statutory and CFR provisions?"
        ),
        unit=None,
    ),
    obligation_summary="FERPA obligations for educational institutions; operative provisions unsourced.",
    citation_pointer="Family Educational Rights and Privacy Act (unverified provisions)",
    applies_if=(
        AppliesIf(
            path="organisation.is_educational_institution",
            op=PredicateOp.TRUTHY,
            value=True,
            description="The organisation is an educational institution.",
        ),
    ),
)

_FEDERAL_OBLIGATIONS: tuple[Obligation, ...] = (
    US_COPPA_AGE,
    US_HIPAA_BREACH_INDIVIDUAL,
    US_HIPAA_BREACH_SECRETARY,
    US_HIPAA_SECURITY,
    US_GLBA_SAFEGUARDS,
    US_FERPA,
)

US_CA_APPLICABILITY: Obligation = Obligation(
    obligation_id="us.ca.applicability",
    regime=RegimeId.US,
    sub_unit="US-CA",
    instrument="California Consumer Privacy Act",
    provision=fact_needed(
        "CCPA as amended by CPRA — what is the Civil Code section range, and "
        "what are the three applicability thresholds (annual gross revenue, "
        "consumer/household count, share of revenue from selling or sharing)?"
    ),
    topic=ObligationTopic.ACCOUNTABILITY,
    sub_topic=SubTopic(
        dimension="ccpa_applicability_thresholds",
        value=fact_needed(
            "CCPA as amended by CPRA — what is the Civil Code section range, "
            "and what are the three applicability thresholds (annual gross "
            "revenue, consumer/household count, share of revenue from "
            "selling or sharing)?"
        ),
        unit=None,
    ),
    obligation_summary="CCPA applicability thresholds; unsourced on primary text.",
    citation_pointer="California Civil Code, CCPA provisions (unverified)",
)

US_CA_RIGHTS: Obligation = Obligation(
    obligation_id="us.ca.rights",
    regime=RegimeId.US,
    sub_unit="US-CA",
    instrument="California Consumer Privacy Act",
    provision=fact_needed(
        "CCPA as amended by CPRA — which Civil Code sections confer the "
        "consumer rights?"
    ),
    topic=ObligationTopic.RIGHTS,
    sub_topic=SubTopic(
        dimension="consumer_rights",
        value=fact_needed(
            "CCPA as amended by CPRA — which Civil Code sections confer the "
            "consumer rights?"
        ),
        unit=None,
    ),
    obligation_summary="CCPA consumer rights provisions; unsourced on primary text.",
    citation_pointer="California Civil Code, CCPA consumer rights (unverified)",
)

_CALIFORNIA_OBLIGATIONS: tuple[Obligation, ...] = (
    US_CA_APPLICABILITY,
    US_CA_RIGHTS,
)


def info() -> PackInfo:
    """Return pack metadata for the engine and the report header."""
    return PackInfo(
        pack_id=PACK_ID,
        regime=RegimeId.US,
        version=VERSION,
        covers_sub_units=frozenset({"US-CA"}),
        as_at=AS_AT,
        draft=True,
        obligation_count=len(_FEDERAL_OBLIGATIONS) + len(_CALIFORNIA_OBLIGATIONS),
        instruments=_ALL_INSTRUMENTS,
        draft_reason=DRAFT_REASON,
    )


def _bool_flag(flag: bool | None) -> ObligationResult:
    """Map an optional boolean declaration to a conformance judgement.

    ``None`` is CONTESTED, never a silent pass, because a fact the
    declaration omits is a fact still to be asked about.
    """
    if flag is None:
        return ObligationResult.CONTESTED
    if flag is True:
        return ObligationResult.SATISFIED
    return ObligationResult.GAP


def _evaluate_one(obligation: Obligation, declaration: Declaration) -> ObligationResult:
    """Judge one obligation against the declaration.

    The FACT NEEDED check is the FIRST branch so an unsourced constant
    always yields CONTESTED and cannot be forgotten per-obligation.
    """
    if obligation.has_unsourced_constant():
        return ObligationResult.CONTESTED

    if obligation.obligation_id == "us.coppa.age":
        return _bool_flag(declaration.consent_mechanism.parental_consent_verifiable)
    if obligation.obligation_id == "us.hipaa.breach.individual":
        return _bool_flag(declaration.breach_workflow.notifies_affected_individuals)
    if obligation.obligation_id == "us.hipaa.breach.secretary":
        return _bool_flag(declaration.breach_workflow.notifies_regulator)
    if obligation.obligation_id in ("us.hipaa.security", "us.glba.safeguards"):
        if len(declaration.security_safeguards) > 0:
            return ObligationResult.SATISFIED
        return ObligationResult.GAP
    return ObligationResult.CONTESTED


def evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]:
    """Evaluate the obligations applicable to `sub_unit` only.

    An unresearched US-XX state is reported as unresearched via a single
    FACT NEEDED obligation rather than returning nothing, because silence
    would read as a clean bill of health. This is the single most
    important behaviour in this pack.
    """
    if sub_unit is None:
        obligations: tuple[Obligation, ...] = _FEDERAL_OBLIGATIONS
        return evaluate_obligations(
            obligations, declaration, as_at, _evaluate_one, pack_info=info()
        )
    if sub_unit == "US-CA":
        return evaluate_obligations(
            _CALIFORNIA_OBLIGATIONS,
            declaration,
            as_at,
            _evaluate_one,
            pack_info=info(),
        )
    if len(sub_unit) == 5 and sub_unit.startswith("US-") and sub_unit[3:].isalpha():
        unsourced_state: Obligation = Obligation(
            obligation_id=f"us.{sub_unit.lower()}.unsourced",
            regime=RegimeId.US,
            sub_unit=sub_unit,
            instrument="Unidentified state comprehensive privacy statute",
            provision=fact_needed(
                f"which comprehensive privacy statute is in effect in "
                f"{sub_unit} during 2026, what is its citation and effective "
                f"date?"
            ),
            topic=ObligationTopic.ACCOUNTABILITY,
            sub_topic=SubTopic(
                dimension="state_statute_identified",
                value=fact_needed(
                    f"which comprehensive privacy statute is in effect in "
                    f"{sub_unit} during 2026, what is its citation and "
                    f"effective date?"
                ),
                unit=None,
            ),
            obligation_summary=(
                f"{sub_unit}: no comprehensive privacy statute has been "
                "researched for this state. This finding is deliberately "
                "emitted so the unresearched state is reported rather than "
                "silently omitted."
            ),
            citation_pointer=f"{sub_unit} state statutes (unresearched)",
        )
        return evaluate_obligations(
            (unsourced_state,), declaration, as_at, _evaluate_one, pack_info=info()
        )
    return []
