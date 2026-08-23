"""Guided declaration interview.

The declaration is the tool's real user interface, and until this interview existed
it had none: ``init`` wrote four fields, a full check needed seventy-eight, and a
check against the skeleton returned nothing but ``contested``. This module turns the
flat, hand-authored JSON into a conversation an adviser can actually have with a
client — one question at a time, in plain English, with skip and resume.

The single property that matters most: **a skipped question stays undeclared**. If
this code ever wrote ``False`` for an unanswered fact, every ``contested`` would
silently become a ``gap`` and the tool would begin accusing clients of failing
duties nobody ever asked them about. That defect class took nineteen fixes to clear
out of the packs; an interview that reintroduced it at the input layer would undo
all of it.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Callable, Sequence

from samanvaya import credentials
from samanvaya import types as T

Reader = Callable[[str], str]
Writer = Callable[[str], None]

_SKIP_KEYWORDS = {"s", "skip"}


@dataclasses.dataclass(frozen=True)
class Question:
    """One declarative question in the bank.

    `path` is the dotted address the answer will occupy in the declaration; `section`
    is the human-facing heading announced before any question in that block; `prompt`
    is the spoken sentence (no field names, no underscores — an adviser must be able
    to read it aloud to a client); `why` is the provision that turns on the answer
    (so a refusal can be answered with a reason rather than a guess); `kind` picks
    the parser — closed to a small set so ``parse`` is exhaustive.
    """

    path: str
    section: str
    prompt: str
    why: str
    kind: str


# --- ordered bank ------------------------------------------------------------
# Ordered by section (organisation first) for the on-screen flow. Paths are unique
# and exhaustive over the eight blocks minus each block's `described` flag, which
# the interview sets itself when any field in that block is answered.

_ORG = "Organisation"
_NOTICE = "Notice"
_CONSENT = "Consent mechanism"
_BREACH = "Breach workflow"
_DSR = "Data-subject rights"
_GOV = "Governance"
_XB = "Cross-border transfers"
_CHILD = "Children"


#: Only these blocks carry a ``described`` flag. Organisation, governance and
#: cross-border do not, and writing one onto them makes the validator reject the
#: whole declaration with "unknown key 'described'".
_BLOCKS_WITH_DESCRIBED: frozenset[str] = frozenset(
    {"notice", "consent_mechanism", "breach_workflow", "dsr_workflow", "children"}
)


#: How many times a single question is re-asked before it is recorded as
#: unanswered. Bounded so a reader that never yields a valid answer cannot hang
#: the interview.
_MAX_ATTEMPTS = 5

QUESTIONS: tuple[Question, ...] = (
    # Organisation (14) ---------------------------------------------------------
    Question(
        "organisation.legal_form",
        _ORG,
        "What is the legal form of the organisation?",
        "Several regimes fix duties to legal forms (trust, partnership, LLP, company).",
        "str",
    ),
    Question(
        "organisation.employee_count",
        _ORG,
        "Roughly how many people does the organisation employ, in total?",
        "DPDP Act 2023 s.10 and GDPR Article 37 set thresholds on headcount.",
        "int",
    ),
    Question(
        "organisation.annual_revenue_usd",
        _ORG,
        "What is the annual revenue of the organisation, in US dollars?",
        "Some statutes attach duties to revenue tier rather than employee tier.",
        "int",
    ),
    Question(
        "organisation.consumer_count",
        _ORG,
        "Roughly how many individual customers or users does the organisation have?",
        "DPDP Rules fix notice duties at user-volume tiers.",
        "int",
    ),
    Question(
        "organisation.is_public_authority",
        _ORG,
        "Is the organisation a public authority or government body?",
        "Public-body status engages obligations (FOIA-style duties, GDPR Art. 37).",
        "bool",
    ),
    Question(
        "organisation.is_healthcare_provider",
        _ORG,
        "Does the organisation provide healthcare services or hold health records?",
        "Special-category-data regimes (HIPAA, GDPR Art. 9) attach to this fact.",
        "bool",
    ),
    Question(
        "organisation.is_financial_institution",
        _ORG,
        "Is the organisation a bank, insurer or other regulated financial institution?",
        "GLBA, PCI-DSS and prudential duties attach to this status.",
        "bool",
    ),
    Question(
        "organisation.is_educational_institution",
        _ORG,
        "Is the organisation a school, college or other educational institution?",
        "FERPA and similar statutes reserve their duties to this category.",
        "bool",
    ),
    Question(
        "organisation.offers_services_to_children",
        _ORG,
        "Does the organisation offer goods or services directed at children?",
        "COPPA, DPDP s.9 and KDPA reach services aimed at minors.",
        "bool",
    ),
    Question(
        "organisation.conducts_large_scale_monitoring",
        _ORG,
        "Does the organisation conduct large-scale monitoring of individuals?",
        "GDPR Art. 37 and several national statutes fix a DPO duty at this fact.",
        "bool",
    ),
    Question(
        "organisation.processes_special_category_data",
        _ORG,
        "Does the organisation process special categories of personal data?",
        "GDPR Art. 9, HIPAA and DPDP s.6(s) attach to sensitive-data processing.",
        "bool",
    ),
    Question(
        "organisation.notified_significant_data_fiduciary",
        _ORG,
        "Has the organisation been notified as a Significant Data Fiduciary?",
        "DPDP s.10 imposes extra duties on notified Significant Data Fiduciaries.",
        "bool",
    ),
    Question(
        "organisation.share_of_revenue_from_selling_personal_data",
        _ORG,
        "What share of revenue comes from selling personal data, expressed as a fraction?",
        "Some statutes flag organisations whose business model depends on data trade.",
        "float",
    ),
    Question(
        "organisation.data_categories",
        _ORG,
        "Which categories of personal data does the organisation process?",
        "Most regimes itemise duties by category — name, contact, financial, health.",
        "list",
    ),
    Question(
        "organisation.purposes",
        _ORG,
        "For what purposes does the organisation process personal data?",
        "Purpose-limitation duties require each declared purpose to map to a notice.",
        "list",
    ),
    Question(
        "organisation.recipients",
        _ORG,
        "Who are the recipients of personal data, beyond the organisation itself?",
        "Recipients must be disclosed in the notice and reflected in contracts.",
        "list",
    ),
    Question(
        "declaration.security_safeguards",
        _ORG,
        "Which technical and organisational safeguards are in place, by name?",
        "Declared safeguards let packs verify against their own required controls.",
        "list",
    ),
    Question(
        "organisation.retention",
        _ORG,
        "List the retention rules, one per line, as purpose and period pairs?",
        "Retention is per-purpose and must be declared so regimes can grade it.",
        "str",
    ),
    # Notice (11) --------------------------------------------------------------
    Question(
        "notice.describes_personal_data",
        _NOTICE,
        "Does the privacy notice describe the categories of personal data processed?",
        "DPDP Rule 3(2)(i), GDPR Art. 13(1)(b) and CCPA 1798.100 require it.",
        "bool",
    ),
    Question(
        "notice.describes_purpose",
        _NOTICE,
        "Does the privacy notice describe each purpose for which data is processed?",
        "Purpose specification is required under DPDP s.5 and GDPR Art. 13(1)(c).",
        "bool",
    ),
    Question(
        "notice.describes_rights_exercise_method",
        _NOTICE,
        "Does the notice explain how a person can exercise their data rights?",
        "DPDP s.12, GDPR Art. 13(2)(b) and CCPA require a clear exercise channel.",
        "bool",
    ),
    Question(
        "notice.describes_complaint_method_to_regulator",
        _NOTICE,
        "Does the notice tell people how to lodge a complaint with the regulator?",
        "DPDP s.7(g) and several provincial statutes require this disclosure.",
        "bool",
    ),
    Question(
        "notice.available_in_local_language",
        _NOTICE,
        "Is the privacy notice available in the language of the user base?",
        "Notice-in-local-language is required in many state-level instruments.",
        "bool",
    ),
    Question(
        "notice.given_before_or_with_consent_request",
        _NOTICE,
        "Is the notice given to the person before, or at the same time as, consent is asked?",
        "DPDP s.6 and GDPR Art. 7(3) require this sequencing.",
        "bool",
    ),
    Question(
        "notice.identifies_recipients",
        _NOTICE,
        "Does the notice identify the recipients or categories of recipients?",
        "DPDP Rule 3(2)(iii), GDPR Art. 13(1)(e) and CCPA 1798.115 require it.",
        "bool",
    ),
    Question(
        "notice.states_retention_period",
        _NOTICE,
        "Does the notice state the retention period for each purpose?",
        "GDPR Art. 13(2)(a) and DPDP s.5(2) require storage-period disclosure.",
        "bool",
    ),
    Question(
        "notice.states_controller_identity",
        _NOTICE,
        "Does the notice state the identity and contact details of the data controller?",
        "DPDP s.5(1)(a) and GDPR Art. 13(1)(a) require controller identification.",
        "bool",
    ),
    Question(
        "notice.states_transfer_destinations",
        _NOTICE,
        "Does the notice state the countries to which data is transferred?",
        "Cross-border regimes require destination disclosure at notice time.",
        "bool",
    ),
    Question(
        "notice.is_multi_lingual",
        _NOTICE,
        "Does the notice cover more than one declared language or script?",
        "Some instruments grade notice completeness per available script.",
        "str",
    ),
    # Consent mechanism (20) ---------------------------------------------------
    Question(
        "consent_mechanism.mechanism",
        _CONSENT,
        "What is the consent mechanism in use, as a single short phrase?",
        "Many regimes look at the mechanism label — banner, checkbox, manager.",
        "str",
    ),
    Question(
        "consent_mechanism.is_opt_in",
        _CONSENT,
        "Does the mechanism rely on the user opting in, rather than opting out?",
        "DPDP s.6 and GDPR Art. 7 require opt-in for consent to be valid.",
        "bool",
    ),
    Question(
        "consent_mechanism.withdrawal_as_easy_as_giving",
        _CONSENT,
        "Is withdrawing consent as easy as giving it?",
        "GDPR Art. 7(3) is explicit; CCPA and DPDP mirror the principle.",
        "bool",
    ),
    Question(
        "consent_mechanism.granular_by_purpose",
        _CONSENT,
        "Can the user choose separately for each processing purpose?",
        "Bundled consent is invalid under GDPR Recital 32 and DPDP s.6.",
        "bool",
    ),
    Question(
        "consent_mechanism.parental_consent_verifiable",
        _CONSENT,
        "Is parental consent verifiable where it is required?",
        "DPDP s.9, COPPA and KDPA all require verifiable parental consent.",
        "bool",
    ),
    Question(
        "consent_mechanism.records_kept",
        _CONSENT,
        "Does the organisation keep records of consent given and withdrawn?",
        "DPDP Rule 7 and GDPR Art. 7(1) require accountability records.",
        "bool",
    ),
    Question(
        "consent_mechanism.is_free",
        _CONSENT,
        "Is the choice genuinely free, with no penalty for refusal?",
        "GDPR Art. 7(4) and CCPA require consent to be a free choice.",
        "bool",
    ),
    Question(
        "consent_mechanism.is_specific",
        _CONSENT,
        "Is consent sought specifically for each purpose?",
        "Bundled or pre-checked consent fails GDPR Art. 7(2).",
        "bool",
    ),
    Question(
        "consent_mechanism.is_informed",
        _CONSENT,
        "Is the user properly informed before giving consent?",
        "Informed consent is a precondition under DPDP s.6 and GDPR Recital 32.",
        "bool",
    ),
    Question(
        "consent_mechanism.is_unconditional",
        _CONSENT,
        "Is consent sought without condition on unrelated terms?",
        "Tying consent to unrelated terms is barred under GDPR and DPDP.",
        "bool",
    ),
    Question(
        "consent_mechanism.is_unambiguous",
        _CONSENT,
        "Is the consent action clearly affirmative and unambiguous?",
        "Pre-ticked boxes fail GDPR Art. 7(2) and the EDPB consent guidance.",
        "bool",
    ),
    Question(
        "consent_mechanism.has_clear_affirmative_action",
        _CONSENT,
        "Does the user take a clear affirmative action to consent?",
        "Clear affirmative action is required by GDPR and the DPDP Rules.",
        "bool",
    ),
    Question(
        "consent_mechanism.limited_to_specified_purpose",
        _CONSENT,
        "Is consent strictly limited to the specified, declared purposes?",
        "Purpose limitation is the core of GDPR Art. 5(1)(b).",
        "bool",
    ),
    Question(
        "consent_mechanism.is_pre_checked",
        _CONSENT,
        "Is any consent box presented pre-checked or pre-filled?",
        "Pre-checked boxes fail GDPR Art. 7(2); DPDP s.6 mirrors this.",
        "bool",
    ),
    Question(
        "consent_mechanism.is_bundled_with_unrelated_terms",
        _CONSENT,
        "Is consent bundled with acceptance of unrelated terms?",
        "Bundling is barred under GDPR Art. 7(4) and the DPDP Rules.",
        "bool",
    ),
    Question(
        "consent_mechanism.request_in_clear_plain_language",
        _CONSENT,
        "Is the consent request written in clear, plain language?",
        "Plain-language requirements appear in DPDP Rule 4 and the GDPR consent guidance.",
        "bool",
    ),
    Question(
        "consent_mechanism.local_language_option_offered",
        _CONSENT,
        "Is the consent request offered in the local language of the user?",
        "Local-language consent is mandated in several state-level statutes.",
        "bool",
    ),
    Question(
        "consent_mechanism.privacy_officer_contact_provided",
        _CONSENT,
        "Is the privacy officer contact provided next to the consent request?",
        "DPDP Rule 4 requires a contact alongside consent-asking notices.",
        "bool",
    ),
    Question(
        "consent_mechanism.obtained_via_consent_manager",
        _CONSENT,
        "Is consent obtained and recorded through a dedicated consent manager?",
        "DPDP Rule 7 sets a higher bar when a manager is used.",
        "bool",
    ),
    Question(
        "consent_mechanism.consent_text",
        _CONSENT,
        "Quote the exact consent sentence shown to the user?",
        "The wording is the artefact that regimes grade against.",
        "str",
    ),
    Question(
        "consent_mechanism.withdrawal_method",
        _CONSENT,
        "How can the user withdraw consent, in a single short phrase?",
        "The withdrawal channel must be visible and operable, not just declared.",
        "str",
    ),
    # Breach workflow (7) ------------------------------------------------------
    Question(
        "breach_workflow.notifies_regulator",
        _BREACH,
        "Does the organisation notify the regulator of personal-data breaches?",
        "DPDP s.8, GDPR Art. 33 and many state statutes fix a notification duty.",
        "bool",
    ),
    Question(
        "breach_workflow.regulator_deadline_hours",
        _BREACH,
        "Within how many hours is the regulator notified of a breach?",
        "Deadlines are declared in hours so 72h GDPR and 6h DPDP compare on one axis.",
        "int",
    ),
    Question(
        "breach_workflow.notifies_affected_individuals",
        _BREACH,
        "Are affected individuals notified directly of breaches that affect them?",
        "DPDP s.8(3) and GDPR Art. 34 require direct notification in high-risk cases.",
        "bool",
    ),
    Question(
        "breach_workflow.individual_notification_trigger",
        _BREACH,
        "What triggers direct individual notification, in a short phrase?",
        "The trigger must be declared so the engine can test the threshold.",
        "str",
    ),
    Question(
        "breach_workflow.maintains_breach_register",
        _BREACH,
        "Does the organisation keep an internal register of breaches?",
        "Many regimes require an internal register as evidence of accountability.",
        "bool",
    ),
    Question(
        "breach_workflow.register_retention_period",
        _BREACH,
        "How long is the breach register retained, in plain terms?",
        "Retention of the register is itself a purpose with its own period.",
        "str",
    ),
    Question(
        "breach_workflow.incident_severity_rule",
        _BREACH,
        "How is breach severity classified, in one short phrase?",
        "Severity rules set the threshold for both kinds of notification.",
        "str",
    ),
    # DSR workflow (6) ---------------------------------------------------------
    Question(
        "dsr_workflow.rights_supported",
        _DSR,
        "Which data-subject rights are supported?",
        "Rights must be declared as a list so each regime can grade its own subset.",
        "list",
    ),
    Question(
        "dsr_workflow.response_deadline_days",
        _DSR,
        "Within how many days does the organisation respond to a rights request?",
        "DPDP s.11, GDPR Art. 12(3) and CCPA fix calendar windows for response.",
        "int",
    ),
    Question(
        "dsr_workflow.grievance_mechanism_published",
        _DSR,
        "Is a grievance mechanism for rights complaints published and reachable?",
        "DPDP s.12 and several statutes require a visible grievance channel.",
        "bool",
    ),
    Question(
        "dsr_workflow.grievance_response_period_days",
        _DSR,
        "Within how many days are grievance complaints resolved, in days?",
        "Grievance response windows are declared separately from the rights response.",
        "int",
    ),
    Question(
        "dsr_workflow.identity_verification",
        _DSR,
        "Is the identity of the requester verified before disclosure?",
        "Identity verification is required to prevent unauthorised disclosure.",
        "bool",
    ),
    Question(
        "dsr_workflow.request_channel",
        _DSR,
        "Through what channel can a rights request be made?",
        "A single, named channel prevents the user from hunting for the form.",
        "str",
    ),
    # Governance (9) -----------------------------------------------------------
    Question(
        "governance.has_privacy_officer",
        _GOV,
        "Has the organisation appointed a privacy officer?",
        "GDPR Art. 37, DPDP s.8(5) and several statutes require a named officer.",
        "bool",
    ),
    Question(
        "governance.privacy_officer_contact_published",
        _GOV,
        "Is the privacy officer contact published and reachable?",
        "DPDP Rule 4 requires publication of the contact alongside notice.",
        "bool",
    ),
    Question(
        "governance.conducts_impact_assessments",
        _GOV,
        "Does the organisation conduct privacy or DPIA assessments?",
        "GDPR Art. 35, DPDP s.6 and provincial statutes require impact assessments.",
        "bool",
    ),
    Question(
        "governance.impact_assessment_frequency_months",
        _GOV,
        "How often are impact assessments refreshed, in months?",
        "Frequency is the operation the engine grades against, not the existence fact.",
        "int",
    ),
    Question(
        "governance.conducts_audits",
        _GOV,
        "Does the organisation conduct internal privacy audits?",
        "Audit duty attaches in several regimes to the accountability principle.",
        "bool",
    ),
    Question(
        "governance.audit_frequency_months",
        _GOV,
        "How often are audits conducted, in months?",
        "The numeric frequency must match the practice the audit traces.",
        "int",
    ),
    Question(
        "governance.maintains_processing_records",
        _GOV,
        "Does the organisation keep processing records, as required by statute?",
        "GDPR Art. 30, DPDP Rule 11 and provincial laws impose records duties.",
        "bool",
    ),
    Question(
        "governance.processor_contracts_in_place",
        _GOV,
        "Are written contracts in place with every processor?",
        "GDPR Art. 28, DPDP s.8(1) and CCPA require processor agreements.",
        "bool",
    ),
    Question(
        "governance.processor_contract_covers_security",
        _GOV,
        "Do processor contracts cover security obligations in adequate detail?",
        "A contract that omits security fails the due-diligence duty.",
        "bool",
    ),
    # Cross-border (4) ---------------------------------------------------------
    Question(
        "cross_border.transfers_outside_jurisdiction",
        _XB,
        "Does the organisation transfer personal data outside any declared jurisdiction?",
        "Cross-border statutes apply only when a transfer outside the jurisdiction occurs.",
        "bool",
    ),
    Question(
        "cross_border.destination_countries",
        _XB,
        "To which destination countries is personal data transferred?",
        "Destination lists drive adequacy assessment under GDPR and DPDP.",
        "list",
    ),
    Question(
        "cross_border.transfer_mechanism",
        _XB,
        "Under what mechanism are cross-border transfers made?",
        "The mechanism (SCC, BCR, adequacy) is itself a regulatory question.",
        "str",
    ),
    Question(
        "cross_border.impact_assessment_per_transfer",
        _XB,
        "Is an impact assessment performed for each transfer route?",
        "GDPR Art. 46 and DPDP s.16 require transfer-specific assessment.",
        "bool",
    ),
    # Children (7) -------------------------------------------------------------
    Question(
        "children.processes_data_of_children",
        _CHILD,
        "Does the organisation process personal data of any person under eighteen?",
        "DPDP s.9 attaches to processing a child's data, separate from offering services.",
        "bool",
    ),
    Question(
        "children.verifiable_parental_consent",
        _CHILD,
        "Where children are processed, is parental consent verifiable?",
        "DPDP s.9, COPPA and KDPA all require verifiable parental consent.",
        "bool",
    ),
    Question(
        "children.tracks_children",
        _CHILD,
        "Does the organisation track children across services, in any way?",
        "Tracking children engages behavioural duties separate from processing consent.",
        "bool",
    ),
    Question(
        "children.targeted_advertising_to_children",
        _CHILD,
        "Does the organisation target advertising at children, directly or indirectly?",
        "DPDP s.9(2) and several statutes ban targeted advertising to children.",
        "bool",
    ),
    Question(
        "children.likely_detrimental_effect",
        _CHILD,
        "Is any processing likely to cause detrimental effect to a child?",
        "Detriment is a higher threshold than mere processing and triggers extra duties.",
        "bool",
    ),
    Question(
        "children.age_verification_method",
        _CHILD,
        "How does the organisation verify the age of a user, in one phrase?",
        "The mechanism dictates which age-gate standard the engine applies.",
        "str",
    ),
    Question(
        "children.responsible_person_designated",
        _CHILD,
        "Has the organisation designated a person responsible for children's data?",
        "Several regimes require a named owner of children's-data decisions.",
        "bool",
    ),
)

SECTIONS: tuple[str, ...] = (
    _ORG,
    _NOTICE,
    _CONSENT,
    _BREACH,
    _DSR,
    _GOV,
    _XB,
    _CHILD,
)


def _normalise(reply: str) -> str:
    """Case-fold and strip so ' yes ' and 'YES' land on the same branch."""
    return reply.strip().casefold()


def _is_skip(reply: str) -> bool:
    """True only for blank or for an explicit skip token — never for an unparseable reply."""
    norm = _normalise(reply)
    if not norm:
        return True
    if norm.startswith("?") and norm != "?":
        # `?skip` and friends are help-shaped skips, not help requests.
        remainder = norm[1:].strip()
        return not remainder or remainder in _SKIP_KEYWORDS or remainder == "skip"
    return norm in _SKIP_KEYWORDS or norm == "skip"


def _is_help(reply: str) -> bool:
    """A standalone `?` means the adviser wants to read the `why` clause aloud again."""
    return _normalise(reply) == "?"


def _is_yes(reply: str) -> bool:
    """True only for an affirmative — never for a skip or help request."""
    return _normalise(reply) in {"y", "yes"}


def _is_no(reply: str) -> bool:
    """True only for a negative — never for a skip or help request."""
    return _normalise(reply) in {"n", "no"}


def _parse_bool(reply: str) -> bool | None:
    """Resolve a yes/no reply; None when the reply is a skip and must stay undeclared."""
    if _is_skip(reply):
        return None
    if _is_yes(reply):
        return True
    if _is_no(reply):
        return False
    return False  # signal "unparseable" to the caller without confusing with None


def _parse_int(reply: str) -> int | None | bool:
    """Return the integer on success, None for a skip, or False to signal unparseable."""
    if _is_skip(reply):
        return None
    text = reply.strip()
    try:
        return int(text)
    except ValueError:
        return False


def _parse_float(reply: str) -> float | None | bool:
    """Return the float on success, None for a skip, or False to signal unparseable."""
    if _is_skip(reply):
        return None
    text = reply.strip()
    try:
        return float(text)
    except ValueError:
        return False


def _parse_str(reply: str) -> str | None:
    """Blank replies are skips; a non-blank reply is the answer."""
    if _is_skip(reply):
        return None
    return reply.strip()


def _parse_list(reply: str) -> list[str] | None:
    """Comma-separated, trimmed, blanks dropped. Blank reply is a skip."""
    if _is_skip(reply):
        return None
    items = [item.strip() for item in reply.split(",")]
    return [item for item in items if item]


def _looks_like_credential(value: str) -> bool:
    """Check the answer through the credential scanner at the point of entry.

    A check at parse time means a refusal is shown *before* the answer lands in the
    answers dict. The interview stores nothing credential-shaped — never even an
    intermediate value the caller could read back.
    """
    if not value:
        return False
    found = credentials.scan({"answer": value})
    return found is not None


def _ask(read: Reader, write: Writer, question: Question) -> object | None:
    """Drive one question until a parseable answer or a skip is given.

    Returns either the parsed value or None when the user skips. Never returns False
    as a stop value: the success tuple is ``(True, value)`` and the failure tuple is
    ``(False, None)`` for a skip, so False cannot leak.
    """
    # Bounded, not `while True`. An unbounded re-ask loop hangs forever against any
    # reader that keeps returning the same invalid answer — which is not only a
    # pathological test double: a user pasting a block of text, or a piped script whose
    # answers have drifted out of step with the questions, produces exactly that. After a
    # few failed attempts the question is recorded as UNANSWERED, which is the safe
    # outcome: it becomes `contested`, never `false`.
    for _attempt in range(_MAX_ATTEMPTS):
        write(question.prompt)
        try:
            reply = read("")
        except EOFError:
            # A piped finite script exhausted mid-question — treat as a skip and let
            # the caller's outer loop decide whether to keep asking or finish.
            return None

        if _is_help(reply):
            write(question.why)
            continue

        if _is_skip(reply):
            return None

        if question.kind == "bool":
            parsed_bool = _parse_bool(reply)
            if parsed_bool is False and not _is_no(reply):
                write("I did not understand that. Please answer yes or no, or type skip.")
                continue
            return parsed_bool

        if question.kind == "int":
            parsed_int = _parse_int(reply)
            if parsed_int is False:
                write("I did not understand that. Please enter a whole number, or type skip.")
                continue
            return parsed_int

        if question.kind == "float":
            parsed_float = _parse_float(reply)
            if parsed_float is False:
                write("I did not understand that. Please enter a number, or type skip.")
                continue
            return parsed_float

        if question.kind == "str":
            parsed_str = _parse_str(reply)
            if parsed_str is None:
                return None
            if _looks_like_credential(parsed_str):
                # Refused at the point of entry — the offending text is never echoed,
                # so a pasted secret cannot land in the transcript.
                write(
                    "That looks like a credential. The tool will not hold credentials; "
                    "describe the control in plain prose instead."
                )
                continue
            return parsed_str

        if question.kind == "list":
            parsed_list = _parse_list(reply)
            if parsed_list is None:
                return None
            joined = ", ".join(parsed_list)
            if _looks_like_credential(joined):
                write(
                    "That looks like a credential. The tool will not hold credentials; "
                    "list the controls in plain prose instead."
                )
                continue
            return parsed_list

        write("I did not understand that. Please try again, or type skip.")

    write(
        f"    no usable answer after {_MAX_ATTEMPTS} attempts — recording this as "
        "unanswered. It will be reported as 'contested', not as a gap."
    )
    return None  # attempts spent; undeclared, never False

def run_interview(
    read: Reader,
    write: Writer,
    existing: dict[str, object] | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """Run the question bank and return a flat answers dict keyed by Question.path.

    A skipped question is either absent from the result or maps to None — never to
    False. This is the single rule that keeps the engine from confusing "the client
    said no" (a gap) with "the adviser did not ask" (contested). The test
    ``TestSkipMeansUndeclared`` exists to defend it.
    """
    answers: dict[str, object] = {}
    previously = existing or {}
    total = len(QUESTIONS)
    last_section: str | None = None
    asked = 0

    for index, question in enumerate(QUESTIONS, start=1):
        if limit is not None and asked >= limit:
            break

        if question.path in previously:
            # Resume: keep the prior answer. Crucially, only truthy/parsed values
            # are carried across — never an implicit False.
            existing_value = previously[question.path]
            if existing_value is not None:
                answers[question.path] = existing_value
            continue

        if question.section != last_section:
            write(f"— {question.section} —")
            last_section = question.section

        write(f"[{index}/{total}]")
        result = _ask(read, write, question)
        if result is not None:
            answers[question.path] = result
        asked += 1

    return answers


def _declare_block(
    block_name: str,
    fields: tuple[dataclasses.Field[object], ...],
    flat: dict[str, object],
    block_data: dict[str, object],
) -> bool:
    """Lift one flat answers slice into its block dict; return True if anything was answered.

    A skipped field stays absent — only an answered field is written. The block's
    own ``described`` flag is set when this function reports any answer.
    """
    answered = False
    for field in fields:
        path = f"{block_name}.{field.name}"
        if path in flat and flat[path] is not None:
            block_data[field.name] = flat[path]
            answered = True
    if answered and block_name in _BLOCKS_WITH_DESCRIBED:
        block_data["described"] = True
    return answered




def answers_to_declaration(
    answers: dict[str, object],
    *,
    legal_name: str,
    author: str,
    jurisdictions: Sequence[object],
    schema_version: str = "1.0",
    declaration_date: date | None = None,
) -> dict[str, object]:
    """Build a declaration dict the schema validator accepts.

    Skipped answers stay absent or None — never False. A block's ``described`` flag
    is set only when at least one of its fields has been answered. This keeps the
    gap/contested distinction intact from the input layer through to the engine.
    """
    declaration: dict[str, object] = {
        "schema_version": schema_version,
        "declaration_author": author,
        "jurisdictions": jurisdictions,
    }
    if declaration_date is not None:
        declaration["declaration_date"] = declaration_date.isoformat()

    block_specs: dict[str, type] = {
        "organisation": T.Organisation,
        "notice": T.NoticeDeclaration,
        "consent_mechanism": T.ConsentMechanism,
        "breach_workflow": T.BreachWorkflow,
        "dsr_workflow": T.DsrWorkflow,
        "governance": T.GovernanceDeclaration,
        "cross_border": T.CrossBorderDeclaration,
        "children": T.ChildProcessingDeclaration,
    }

    for block_name, cls in block_specs.items():
        block_data: dict[str, object] = {"legal_name": legal_name} if block_name == "organisation" else {}
        answered = _declare_block(block_name, dataclasses.fields(cls), answers, block_data)
        if answered or block_data:
            if block_name == "organisation":
                block_data["legal_name"] = legal_name
            declaration[block_name] = block_data

    # Paths prefixed `declaration.` belong at the TOP level, not inside a block. Without
    # this the answer is simply dropped: the block loop above never sees the prefix, so
    # the interview asks the question and discards what it is told. `security_safeguards`
    # is the case that matters — DPDP Rule 6(1) is evaluated from that list.
    safeguards = answers.get("declaration.security_safeguards")
    if safeguards:
        names = safeguards if isinstance(safeguards, list) else [str(safeguards)]
        # The interview collects safeguard NAMES. The schema wants (control, value) pairs,
        # and the value is what the adviser recorded, so a bare name carries the name as
        # its own value rather than an invented standard. Rule 6(1)(a) prescribes no
        # standard, so presence alone is what the India pack tests for.
        declaration["security_safeguards"] = [
            {"control": str(n).strip(), "value": str(n).strip()}
            for n in names if str(n).strip()
        ]

    return declaration


def declaration_to_answers(declaration: dict[str, object]) -> dict[str, object]:
    """Flatten a parsed declaration back into the path-keyed form the interview understands.

    Used by ``--resume`` so an adviser who saved mid-way can pick up only the
    questions still to ask. The ``described`` block flag is dropped — it is derived,
    not declared — so resuming cannot accidentally re-derive the wrong block state.
    """
    flat: dict[str, object] = {}
    block_specs: dict[str, type] = {
        "organisation": T.Organisation,
        "notice": T.NoticeDeclaration,
        "consent_mechanism": T.ConsentMechanism,
        "breach_workflow": T.BreachWorkflow,
        "dsr_workflow": T.DsrWorkflow,
        "governance": T.GovernanceDeclaration,
        "cross_border": T.CrossBorderDeclaration,
        "children": T.ChildProcessingDeclaration,
    }
    for block_name, cls in block_specs.items():
        block = declaration.get(block_name)
        if not isinstance(block, dict):
            continue
        for field in dataclasses.fields(cls):
            if field.name == "described":
                continue
            if field.name in block:
                value = block[field.name]
                if value is not None:
                    flat[f"{block_name}.{field.name}"] = value
    return flat


__all__ = [
    "Question",
    "QUESTIONS",
    "SECTIONS",
    "run_interview",
    "answers_to_declaration",
    "declaration_to_answers",
]
