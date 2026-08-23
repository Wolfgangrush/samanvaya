"""United Kingdom GDPR obligations pack — DRAFT, nothing verified.

Why this pack is entirely unsourced: on 2026-08-19 every request to
legislation.gov.uk returned HTTP 202 with an empty body — the HTML
rendering, the XML representation and the data API alike. No UK provision
could be read on primary source, so no section number, deadline, age or
commencement date in this pack is verified.

A delegate's research reported candidate values for the child consent age,
the breach notification deadline and the data subject rights response
period. That research has deliberately NOT been entered into the code. A
research lead is not a source: it tells us where to look, not what the
statute says. Every statutory constant below is therefore a
[FACT NEEDED] marker, and every obligation will resolve to CONTESTED
until someone reads the primary text and fills the marker in.

The engine enforces that a draft pack can never emit SATISFIED; this pack
does not reimplement or work around that.

This pack concerns the UK GDPR, the Data Protection Act 2018 and the
Data (Use and Access) Act 2025 — instruments of the United Kingdom only.
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

PACK_ID: str = "uk_gdpr"
VERSION: str = "0.1.0"
AS_AT: date = date(2026, 8, 19)
DRAFT_REASON: str = (
    "legislation.gov.uk returned HTTP 202 with an empty body on every request on "
    "2026-08-19 — HTML, XML and data API — so no UK provision could be read on "
    "primary source."
)

_INSTRUMENTS: tuple[str, ...] = (
    "UK GDPR",
    "Data Protection Act 2018",
    "Data (Use and Access) Act 2025",
)

UK_CHILDREN_AGE: Obligation = Obligation(
    obligation_id="uk.children.age",
    regime=RegimeId.UK_GDPR,
    sub_unit=None,
    instrument="Data Protection Act 2018",
    provision=fact_needed(
        "Data Protection Act 2018 s.9 — what age does the UK fix for a child's "
        "consent to information society services?"
    ),
    topic=ObligationTopic.CHILDREN,
    sub_topic=SubTopic(
        dimension="child_consent_age",
        value=fact_needed(
            "Data Protection Act 2018 s.9 — what age does the UK fix for a "
            "child's consent to information society services?"
        ),
        unit="years",
    ),
    obligation_summary="Child consent age under the Data Protection Act 2018; the statutory age is unsourced.",
    citation_pointer="Data Protection Act 2018, section 9 (unverified)",
)

UK_BREACH_AUTHORITY: Obligation = Obligation(
    obligation_id="uk.breach.authority",
    regime=RegimeId.UK_GDPR,
    sub_unit=None,
    instrument="UK GDPR",
    provision=fact_needed(
        "UK GDPR as retained and amended — what is the deadline to notify the "
        "Information Commissioner of a personal data breach?"
    ),
    topic=ObligationTopic.BREACH,
    sub_topic=SubTopic(
        dimension="breach_notice_deadline",
        value=fact_needed(
            "UK GDPR as retained and amended — what is the deadline to notify "
            "the Information Commissioner of a personal data breach?"
        ),
        unit="hours",
    ),
    obligation_summary="Deadline to notify the Information Commissioner of a personal data breach; unsourced.",
    citation_pointer="UK GDPR breach notification article (unverified)",
)

UK_RIGHTS_DEADLINE: Obligation = Obligation(
    obligation_id="uk.rights.deadline",
    regime=RegimeId.UK_GDPR,
    sub_unit=None,
    instrument="UK GDPR",
    provision=fact_needed(
        "UK GDPR as amended by the Data (Use and Access) Act 2025 — what is "
        "the response period, and how does the 'stop the clock' provision "
        "for clarifying requests operate?"
    ),
    topic=ObligationTopic.RIGHTS,
    sub_topic=SubTopic(
        dimension="dsr_response_period",
        value=fact_needed(
            "UK GDPR as amended by the Data (Use and Access) Act 2025 — what "
            "is the response period, and how does the 'stop the clock' "
            "provision for clarifying requests operate?"
        ),
        unit="days",
    ),
    obligation_summary="Data subject rights response period, including any stop-the-clock provision; unsourced.",
    citation_pointer="UK GDPR data subject rights articles, as amended by DUAA 2025 (unverified)",
)

UK_DUAA_COMMENCEMENT: Obligation = Obligation(
    obligation_id="uk.duaa.commencement",
    regime=RegimeId.UK_GDPR,
    sub_unit=None,
    instrument="Data (Use and Access) Act 2025",
    provision=fact_needed(
        "Data (Use and Access) Act 2025 — official citation, Royal Assent "
        "date and phased commencement schedule?"
    ),
    topic=ObligationTopic.GOVERNANCE,
    sub_topic=SubTopic(
        dimension="duaa_commencement",
        value=fact_needed(
            "Data (Use and Access) Act 2025 — official citation, Royal "
            "Assent date and phased commencement schedule?"
        ),
        unit=None,
    ),
    obligation_summary="Commencement status of the Data (Use and Access) Act 2025; unsourced.",
    citation_pointer="Data (Use and Access) Act 2025 commencement provisions (unverified)",
)

OBLIGATIONS: tuple[Obligation, ...] = (
    UK_CHILDREN_AGE,
    UK_BREACH_AUTHORITY,
    UK_RIGHTS_DEADLINE,
    UK_DUAA_COMMENCEMENT,
)


def info() -> PackInfo:
    """Return pack metadata for the engine and the report header."""
    return PackInfo(
        pack_id=PACK_ID,
        regime=RegimeId.UK_GDPR,
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

    The FACT NEEDED check is deliberately the FIRST branch so that an
    unsourced constant can never be forgotten on a per-obligation basis:
    an obligation carrying an unverified statutory constant must always
    resolve to CONTESTED, whatever the declaration says.
    """
    if obligation.has_unsourced_constant():
        return ObligationResult.CONTESTED
    # Every obligation in this pack is unsourced, so this branch is
    # unreachable until a constant is sourced; it is retained for shape.
    return ObligationResult.CONTESTED


def evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]:
    """Evaluate all UK obligations, delegating scheduling to the engine."""
    return evaluate_obligations(
        OBLIGATIONS,
        declaration,
        as_at,
        _evaluate_one,
        pack_info=info(),
    )
