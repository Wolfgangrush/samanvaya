"""Samanvaya conformance engine — type definitions.

Offline privacy-conformance CLI. This file defines the shapes that carry
statutory constants; it never invents them. Reaches no network and persists
nothing.

Includes the architectural anchors:
- A1: Delta groups on `dimension` so regime-specific values produce a single
  divergence row rather than a string mismatch.
- A2: `slot_key` includes `instrument` so two instruments on the same
  sub-unit occupy two slots rather than one.
- A3: `IncompletenessNotice` is emitted once per country, not per obligation;
  `sub_units_complete=True` makes an absent sub-unit does_not_exist.
- A4: An absent or None `applies_if` field yields CONTESTED, never a silent pass.
- A5: A `SafeguardPair` is a control/value pair so security measures compare
  on a single dimension.
- A6: Dependency cycles are pack LOAD errors, never runtime surprises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


DISCLAIMER: str = (
    "This output is a conformance report only and is not legal advice. "
    "It records which obligations under the named instruments appear "
    "satisfied, unaddressed or unresolved against a supplied declaration. "
    "It does not advise, does not predict any regulator's decision, and "
    "creates no lawyer-client relationship. Every finding must be checked "
    "against the primary source cited."
)


FACT_NEEDED_PREFIX: str = "[FACT NEEDED:"


def fact_needed(question: str) -> str:
    """Return a placeholder marker signalling that a constant must be sourced."""
    return f"{FACT_NEEDED_PREFIX} {question}]"


class ObligationResult(str, Enum):
    """Outcome of evaluating an obligation against a declaration."""

    SATISFIED = "satisfied"
    """The supplied declaration appears to meet the obligation on the evidence provided."""

    GAP = "gap"
    """The declaration does not address the obligation; a gap is recorded."""

    CONTESTED = "contested"
    """The declaration is ambiguous or missing a key fact; a human must resolve it."""

    NOT_APPLICABLE = "not_applicable"
    """The obligation does not apply to this organisation on the evidence provided."""

    DOES_NOT_EXIST = "does_not_exist"
    """The instrument or provision does not exist for the declared jurisdiction."""


class RegimeId(str, Enum):
    """Identifier of a regulatory regime.

    Note: "US GDPR", "Singapore GDPR" and "Canada GDPR" are not instruments
    and the names are banned from this module.
    """

    INDIA = "IN"
    EU_GDPR = "EU"
    UK_GDPR = "UK"
    SINGAPORE_PDPA = "SG"
    US = "US"
    CANADA = "CA"


FEDERATED_REGIMES: frozenset[RegimeId] = frozenset({RegimeId.US, RegimeId.CANADA})


class ObligationTopic(str, Enum):
    """Closed cross-regime comparison vocabulary."""

    NOTICE = "notice"
    CONSENT = "consent"
    LAWFUL_BASIS = "lawful_basis"
    CHILDREN = "children"
    SECURITY = "security"
    BREACH = "breach"
    RIGHTS = "rights"
    RETENTION = "retention"
    PROCESSOR = "processor"
    CROSS_BORDER = "cross_border"
    GOVERNANCE = "governance"
    RECORDS = "records"
    ACCOUNTABILITY = "accountability"
    PENALTY = "penalty"


@dataclass(frozen=True)
class SubTopic:
    """A sub-topic expressed as a dimension and a value.

    Delta groups on `dimension` so two regimes fixing different values
    produce ONE divergence row rather than a string mismatch. Opaque
    strings are banned; the dimension must be a named axis.
    """

    dimension: str
    value: str
    unit: str | None = None


@dataclass(frozen=True)
class SafeguardPair:
    """A control and its declared value; pairs compare on a single dimension."""

    control: str
    value: str


class PredicateOp(str, Enum):
    """Supported predicates for `applies_if` clauses."""

    EQ = "=="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    IN = "in"
    CONTAINS = "contains"
    TRUTHY = "truthy"


@dataclass(frozen=True)
class AppliesIf:
    """A gating condition evaluated against a Declaration.

    An absent or None field yields CONTESTED, never a silent pass.
    """

    path: str
    op: PredicateOp
    value: Any
    description: str = ""


@dataclass(frozen=True)
class Obligation:
    """A single regulatory obligation drawn from a pack."""

    obligation_id: str
    regime: RegimeId
    sub_unit: str | None
    instrument: str
    provision: str
    topic: ObligationTopic
    sub_topic: SubTopic
    obligation_summary: str
    citation_pointer: str
    in_force_from: date | None = None
    in_force_until: date | None = None
    applies_if: tuple[AppliesIf, ...] = ()
    required_value: str | None = None
    depends_on: tuple[str, ...] = ()
    evaluation_metadata: tuple[tuple[str, str], ...] = ()

    @property
    def slot_key(self) -> tuple[str, str | None, str, str, str]:
        """Stable identity for slot allocation.

        `instrument` is IN the key so CCPA and HIPAA on one Californian
        hospital stay two slots rather than colliding.
        """
        return (
            self.regime.value,
            self.sub_unit,
            self.instrument,
            self.topic.value,
            self.sub_topic.dimension,
        )

    @property
    def comparison_key(self) -> tuple[str, str]:
        """Cross-regime comparison key: topic and dimension."""
        return (self.topic.value, self.sub_topic.dimension)

    def is_in_force(self, as_at: date) -> bool:
        """Return True if this obligation is in force on `as_at`."""
        if self.in_force_from is not None and as_at < self.in_force_from:
            return False
        if self.in_force_until is not None and as_at > self.in_force_until:
            return False
        return True

    def has_unsourced_constant(self) -> bool:
        """True if FACT_NEEDED_PREFIX appears in any statutory-bearing field."""
        for text in (
            self.provision,
            self.citation_pointer,
            self.obligation_summary,
            self.sub_topic.value,
            self.required_value or "",
        ):
            if FACT_NEEDED_PREFIX in text:
                return True
        # evaluation_metadata is scanned too, but NOT the keys ending in `_note`.
        #
        # The distinction is between an unsourced ASSERTION and a stated CAVEAT, and it
        # decides whether a finding may stand at all. An unsourced assertion — a provision
        # number nobody read, a threshold nobody sourced — cannot support a verdict, so
        # the obligation must resolve to CONTESTED. A caveat is different: the India
        # commencement dates are derived from a Gazette publication date that is itself
        # unsettled by one day, and that uncertainty is recorded in `commencement_note`.
        # Letting it gate the verdict would force every India Rules obligation to
        # CONTESTED and gut the one rail whose substance IS fully sourced, over a question
        # that changes nothing on any date more than a day from commencement.
        #
        # So a caveat is surfaced to the reader — the renderer prints it, and the report
        # carries a commencement notice above the findings — without silencing a finding
        # that is otherwise properly sourced.
        return any(
            FACT_NEEDED_PREFIX in value
            for key, value in self.evaluation_metadata
            if not key.endswith("_note")
        )

    def has_unsourced_caveat(self) -> bool:
        """True if a `*_note` metadata entry records an unsettled fact.

        Separate from :meth:`has_unsourced_constant` on purpose: a caveat qualifies a
        finding, it does not disqualify it. The reader is told; the verdict stands.
        """
        return any(
            FACT_NEEDED_PREFIX in value
            for key, value in self.evaluation_metadata
            if key.endswith("_note")
        )


@dataclass(frozen=True)
class Finding:
    """A single evaluated obligation outcome."""

    obligation: Obligation
    result: ObligationResult
    rationale: str
    declaration_summary: str | None = None
    evidence_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackInfo:
    """Metadata about a loaded obligations pack.

    A draft pack may NEVER emit SATISFIED, because a draft indicates the
    obligations are not yet stable and any satisfied judgment could be
    reversed by a subsequent edit.
    """

    pack_id: str
    regime: RegimeId
    version: str
    covers_sub_units: frozenset[str]
    as_at: date
    draft: bool
    obligation_count: int
    instruments: tuple[str, ...] = ()
    draft_reason: str = ""


@dataclass(frozen=True)
class IncompletenessNotice:
    """Emitted ONCE PER COUNTRY, never once per obligation.

    Aggregation at the country level prevents a noisy notice per gap
    when the underlying problem is jurisdictional coverage.

    ``regime`` is ``None`` when the declaration named a country this tool
    has no sourced obligations for. The tool's whole discipline is that
    an absent regime must never read as a clean bill, so an uncovered
    declared jurisdiction is reported as a notice with no regime rather
    than being silently dropped. Consumers (Markdown, JSON-lines, PDF)
    render the regime column as a dash or ``None declared`` in that case
    and include the country and the human-readable message so the reader
    can see the jurisdiction was declared but not assessed.
    """

    regime: RegimeId | None
    country: str
    message: str


@dataclass(frozen=True)
class RegimeRollup:
    """All findings and notices for a single regime."""

    regime: RegimeId
    pack_info: PackInfo
    findings: tuple[Finding, ...]
    counts: dict[str, int]
    notices: tuple[IncompletenessNotice, ...] = ()


@dataclass(frozen=True)
class DivergencePosition:
    """One regime's position on a divergence dimension."""

    regime: RegimeId
    sub_unit: str | None
    instrument: str
    provision: str
    value: str
    unit: str | None
    result: ObligationResult


@dataclass(frozen=True)
class Divergence:
    """A cross-regime divergence on a single dimension.

    Does NOT rank the positions, because deciding which regime's standard
    is the more demanding one is statutory interpretation, and a tool that
    ranks statutes is giving legal advice.
    """

    topic: ObligationTopic
    dimension: str
    positions: tuple[DivergencePosition, ...]
    unit: str | None = None


@dataclass(frozen=True)
class Organisation:
    """The organisation whose declaration is being evaluated.

    Optional-and-None matters because applies_if must distinguish
    "declared below the threshold" from "not declared at all"; the second
    is CONTESTED, not a pass.
    """

    legal_name: str
    legal_form: str | None = None
    employee_count: int | None = None
    annual_revenue_usd: int | None = None
    consumer_count: int | None = None
    is_public_authority: bool | None = None
    is_healthcare_provider: bool | None = None
    is_financial_institution: bool | None = None
    is_educational_institution: bool | None = None
    offers_services_to_children: bool | None = None
    conducts_large_scale_monitoring: bool | None = None
    processes_special_category_data: bool | None = None
    notified_significant_data_fiduciary: bool | None = None
    share_of_revenue_from_selling_personal_data: float | None = None
    data_categories: tuple[str, ...] = ()
    purposes: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()
    retention: str | None = None


@dataclass(frozen=True)
class JurisdictionRef:
    """A country's declared jurisdiction footprint.

    `sub_units_complete=True` makes an absent sub-unit DOES_NOT_EXIST
    rather than a gap, so an organisation triggering only a federal
    statute need not enumerate fifty states to prove a negative.
    """

    country: str
    sub_units: tuple[str, ...] = ()
    sub_units_complete: bool = False


@dataclass(frozen=True)
class RetentionRule:
    """A retention declaration for a specific purpose."""

    purpose: str
    period: str
    basis: str | None = None


@dataclass(frozen=True)
class ConsentMechanism:
    """Declarations about the consent mechanism in use."""

    described: bool = False
    mechanism: str | None = None
    is_opt_in: bool | None = None
    withdrawal_as_easy_as_giving: bool | None = None
    granular_by_purpose: bool | None = None
    parental_consent_verifiable: bool | None = None
    records_kept: bool | None = None
    is_free: bool | None = None
    is_specific: bool | None = None
    is_informed: bool | None = None
    is_unconditional: bool | None = None
    is_unambiguous: bool | None = None
    has_clear_affirmative_action: bool | None = None
    limited_to_specified_purpose: bool | None = None
    is_pre_checked: bool | None = None
    is_bundled_with_unrelated_terms: bool | None = None
    request_in_clear_plain_language: bool | None = None
    local_language_option_offered: bool | None = None
    privacy_officer_contact_provided: bool | None = None
    obtained_via_consent_manager: bool | None = None
    consent_text: str | None = None
    withdrawal_method: str | None = None


@dataclass(frozen=True)
class BreachWorkflow:
    """Declarations about the breach response workflow.

    Deadlines are declared in HOURS so instruments fixing different
    deadlines compare on one dimension.
    """

    described: bool = False
    notifies_regulator: bool | None = None
    regulator_deadline_hours: int | None = None
    notifies_affected_individuals: bool | None = None
    individual_notification_trigger: str | None = None
    maintains_breach_register: bool | None = None
    register_retention_period: str | None = None
    incident_severity_rule: str | None = None


@dataclass(frozen=True)
class DsrWorkflow:
    """Declarations about data-subject rights handling."""

    described: bool = False
    rights_supported: tuple[str, ...] = ()
    response_deadline_days: int | None = None
    grievance_mechanism_published: bool | None = None
    grievance_response_period_days: int | None = None
    identity_verification: bool | None = None
    request_channel: str | None = None


@dataclass(frozen=True)
class GovernanceDeclaration:
    """Declarations about governance positioning."""

    has_privacy_officer: bool | None = None
    privacy_officer_contact_published: bool | None = None
    conducts_impact_assessments: bool | None = None
    impact_assessment_frequency_months: int | None = None
    conducts_audits: bool | None = None
    audit_frequency_months: int | None = None
    maintains_processing_records: bool | None = None
    processor_contracts_in_place: bool | None = None
    processor_contract_covers_security: bool | None = None


@dataclass(frozen=True)
class CrossBorderDeclaration:
    """Declarations about cross-border transfers."""

    transfers_outside_jurisdiction: bool | None = None
    destination_countries: tuple[str, ...] = ()
    transfer_mechanism: str | None = None
    impact_assessment_per_transfer: bool | None = None


@dataclass(frozen=True)
class NoticeDeclaration:
    """What the declared privacy notice contains.

    Notice content is a checkable obligation in every one of the six regimes — DPDP
    Act 2023 s.5(1) and DPDP Rule 3 in India, Articles 13 and 14 of the GDPR in the
    EU — so the declaration has to carry it or the whole notice rail collapses to
    "cannot say". Every field defaults to ``None`` meaning *not declared*, which
    resolves to ``CONTESTED`` and tells the adviser exactly what to go back and ask
    the client.
    """

    described: bool = False
    describes_personal_data: bool | None = None
    describes_purpose: bool | None = None
    describes_rights_exercise_method: bool | None = None
    describes_complaint_method_to_regulator: bool | None = None
    available_in_local_language: bool | None = None
    given_before_or_with_consent_request: bool | None = None
    identifies_recipients: bool | None = None
    states_retention_period: bool | None = None
    states_controller_identity: bool | None = None
    states_transfer_destinations: bool | None = None
    is_multi_lingual: str | None = None


@dataclass(frozen=True)
class ChildProcessingDeclaration:
    """What the organisation declares about processing children's personal data.

    This block exists because of a defect the cross-model audit found on 2026-08-19: the
    India adapter was hard-coding ``is_tracking_behavior=False`` and
    ``is_targeted_advertising=False`` into the upstream check, because the declaration had
    nowhere to record them. A client that tracked children could therefore be reported as
    compliant. Fabricating an input and reporting the result as a finding is the single
    worst thing a conformance tool can do, so the facts now have to be declared.

    Every field defaults to ``None`` meaning *not declared*, which resolves to
    ``CONTESTED`` and tells the adviser precisely what to go back and ask.
    """

    described: bool = False
    processes_data_of_children: bool | None = None
    """Whether the organisation processes any personal data of a person under eighteen.

    Distinct from ``organisation.offers_services_to_children``, and the distinction is the
    whole point. DPDP Act 2023 s.9 attaches to PROCESSING a child's personal data, not to
    offering services to children. A hospital, a school's back office or an ad platform may
    process a great deal of children's data while offering no service directed at children,
    and gating s.9 on the offering alone told exactly that organisation the duty did not
    engage — a clean bill on the wrong scope.
    """
    verifiable_parental_consent: bool | None = None
    tracks_children: bool | None = None
    targeted_advertising_to_children: bool | None = None
    likely_detrimental_effect: bool | None = None
    age_verification_method: str | None = None
    responsible_person_designated: bool | None = None


@dataclass(frozen=True)
class Declaration:
    """The full supplied declaration of an organisation."""

    schema_version: str
    organisation: Organisation
    jurisdictions: tuple[JurisdictionRef, ...]
    declaration_author: str
    data_categories: tuple[str, ...] = ()
    purposes: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()
    security_safeguards: tuple[SafeguardPair, ...] = ()
    notice: NoticeDeclaration = field(default_factory=NoticeDeclaration)
    children: ChildProcessingDeclaration = field(default_factory=ChildProcessingDeclaration)
    consent_mechanism: ConsentMechanism = field(default_factory=ConsentMechanism)
    breach_workflow: BreachWorkflow = field(default_factory=BreachWorkflow)
    dsr_workflow: DsrWorkflow = field(default_factory=DsrWorkflow)
    governance: GovernanceDeclaration = field(default_factory=GovernanceDeclaration)
    cross_border: CrossBorderDeclaration = field(default_factory=CrossBorderDeclaration)
    retention: tuple[RetentionRule, ...] = ()
    declaration_date: date | None = None

    def declared_safeguard(self, control: str) -> SafeguardPair | None:
        """Return the first safeguard matching `control` case-insensitively on stripped name."""
        target = control.strip().casefold()
        for pair in self.security_safeguards:
            if pair.control.strip().casefold() == target:
                return pair
        return None


@dataclass(frozen=True)
class EngineResult:
    """The full output of the conformance engine."""

    declaration_hash: str
    tool_version: str
    as_at: date
    per_regime: dict[RegimeId, RegimeRollup]
    divergences: tuple[Divergence, ...]
    notices: tuple[IncompletenessNotice, ...] = ()
    disclaimer: str = DISCLAIMER
    declaration_path: str | None = None

    @property
    def all_findings(self) -> tuple[Finding, ...]:
        """Concatenate findings across regimes in declaration iteration order."""
        collected: list[Finding] = []
        for regime in RegimeId:
            rollup = self.per_regime.get(regime)
            if rollup is None:
                continue
            collected.extend(rollup.findings)
        return tuple(collected)


class PackLoadError(Exception):
    """Raised when a pack cannot be loaded (including dependency cycles)."""


class UpstreamContractError(Exception):
    """Pin mismatch against an upstream dependency.

    Carries the upstream version so the failure is actionable rather than
    an opaque traceback.
    """

    def __init__(self, upstream_version: str, expected: str, message: str = "") -> None:
        self.upstream_version = upstream_version
        self.expected = expected
        super().__init__(message or f"upstream {upstream_version} != expected {expected}")


class DeclarationError(Exception):
    """Raised when a supplied declaration is malformed or incomplete."""


__all__ = sorted(
    [
        "DISCLAIMER",
        "FACT_NEEDED_PREFIX",
        "fact_needed",
        "ObligationResult",
        "RegimeId",
        "FEDERATED_REGIMES",
        "NoticeDeclaration",
        "ObligationTopic",
        "SubTopic",
        "SafeguardPair",
        "PredicateOp",
        "AppliesIf",
        "Obligation",
        "Finding",
        "PackInfo",
        "IncompletenessNotice",
        "RegimeRollup",
        "DivergencePosition",
        "Divergence",
        "Organisation",
        "JurisdictionRef",
        "RetentionRule",
        "ChildProcessingDeclaration",
        "ConsentMechanism",
        "BreachWorkflow",
        "DsrWorkflow",
        "GovernanceDeclaration",
        "CrossBorderDeclaration",
        "Declaration",
        "EngineResult",
        "PackLoadError",
        "UpstreamContractError",
        "DeclarationError",
    ]
)
