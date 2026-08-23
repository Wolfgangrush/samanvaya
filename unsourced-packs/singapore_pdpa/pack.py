"""Singapore Personal Data Protection Act 2012 obligations pack — DRAFT, nothing verified.

Why this pack is entirely unsourced: on 2026-08-19 sso.agc.gov.sg returned
only its site shell, not the text of the Act, so no provision of the PDPA
could be read on primary source. Every section number and threshold below
is therefore a [FACT NEEDED] marker, and every obligation resolves to
CONTESTED until the primary text is read.

The PDPA is a Singaporean statute and is NOT a GDPR. It must never be
described as one, and none of its obligations should be mapped onto GDPR
articles. Its 2020 amendment added a Data Breach Notification Obligation;
the commencement of that amendment is itself unsourced on primary text
tonight, so even the existence-in-force of the breach obligations is
contested rather than asserted.

The engine enforces that a draft pack can never emit SATISFIED; this pack
does not reimplement or work around that.
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

PACK_ID: str = "singapore_pdpa"
VERSION: str = "0.1.0"
AS_AT: date = date(2026, 8, 19)
DRAFT_REASON: str = (
    "sso.agc.gov.sg returned only its site shell, not the text of the Act, "
    "on 2026-08-19."
)

_INSTRUMENTS: tuple[str, ...] = ("Personal Data Protection Act 2012",)

SG_BREACH_COMMISSION: Obligation = Obligation(
    obligation_id="sg.breach.commission",
    regime=RegimeId.SINGAPORE_PDPA,
    sub_unit=None,
    instrument="Personal Data Protection Act 2012",
    provision=fact_needed(
        "PDPA 2012 — which section imposes the data breach notification "
        "obligation and what is the deadline to notify the Commission?"
    ),
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_notice_deadline",
        value=fact_needed(
            "PDPA 2012 — which section imposes the data breach notification "
            "obligation and what is the deadline to notify the Commission?"
        ),
        unit="days",
    ),
    obligation_summary="Data breach notification to the Personal Data Protection Commission; section and deadline unsourced.",
    citation_pointer="Personal Data Protection Act 2012, breach notification provisions (unverified)",
)

SG_BREACH_INDIVIDUAL: Obligation = Obligation(
    obligation_id="sg.breach.individual",
    regime=RegimeId.SINGAPORE_PDPA,
    sub_unit=None,
    instrument="Personal Data Protection Act 2012",
    provision=fact_needed(
        "PDPA 2012 — which section requires notification to affected "
        "individuals, and on what trigger?"
    ),
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_individual_notice_trigger",
        value=fact_needed(
            "PDPA 2012 — which section requires notification to affected "
            "individuals, and on what trigger?"
        ),
        unit=None,
    ),
    obligation_summary="Notification of affected individuals on data breach; section and trigger unsourced.",
    citation_pointer="Personal Data Protection Act 2012, individual notification provisions (unverified)",
)

SG_GOVERNANCE_DPO: Obligation = Obligation(
    obligation_id="sg.governance.dpo",
    regime=RegimeId.SINGAPORE_PDPA,
    sub_unit=None,
    instrument="Personal Data Protection Act 2012",
    provision=fact_needed(
        "PDPA 2012 — which section requires the appointment of a data "
        "protection officer?"
    ),
    topic=ObligationTopic.GOVERNANCE,
    sub_topic=SubTopic(
        dimension="dpo_requirement",
        value=fact_needed(
            "PDPA 2012 — which section requires the appointment of a data "
            "protection officer?"
        ),
        unit=None,
    ),
    obligation_summary="Data protection officer appointment requirement; section unsourced.",
    citation_pointer="Personal Data Protection Act 2012, data protection officer provisions (unverified)",
)

SG_CONSENT: Obligation = Obligation(
    obligation_id="sg.consent",
    regime=RegimeId.SINGAPORE_PDPA,
    sub_unit=None,
    instrument="Personal Data Protection Act 2012",
    provision=fact_needed(
        "PDPA 2012 — which sections impose the Consent Obligation?"
    ),
    topic=ObligationTopic.CONSENT,
    sub_topic=SubTopic(
        dimension="consent_obligation",
        value=fact_needed(
            "PDPA 2012 — which sections impose the Consent Obligation?"
        ),
        unit=None,
    ),
    obligation_summary="Consent Obligation under the PDPA; sections unsourced.",
    citation_pointer="Personal Data Protection Act 2012, consent provisions (unverified)",
)

OBLIGATIONS: tuple[Obligation, ...] = (
    SG_BREACH_COMMISSION,
    SG_BREACH_INDIVIDUAL,
    SG_GOVERNANCE_DPO,
    SG_CONSENT,
)


def info() -> PackInfo:
    """Return pack metadata for the engine and the report header."""
    return PackInfo(
        pack_id=PACK_ID,
        regime=RegimeId.SINGAPORE_PDPA,
        version=VERSION,
        covers_sub_units=frozenset(),
        as_at=AS_AT,
        draft=True,
        obligation_count=len(OBLIGATIONS),
        instruments=_INSTRUMENTS,
        draft_reason=DRAFT_REASON,
    )


def _evaluate_one(obligation: Obligation, declaration: Declaration) -> ObligationResult:
    """Judge one obligation against the declaration.

    The FACT NEEDED check is the FIRST branch by construction: an
    unsourced constant must always resolve to CONTESTED regardless of
    what the declaration says, and placing it here means it cannot be
    forgotten per-obligation.
    """
    if obligation.has_unsourced_constant():
        return ObligationResult.CONTESTED
    return ObligationResult.CONTESTED


def evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]:
    """Evaluate all Singapore PDPA obligations, delegating scheduling to the engine."""
    return evaluate_obligations(
        OBLIGATIONS,
        declaration,
        as_at,
        _evaluate_one,
        pack_info=info(),
    )
