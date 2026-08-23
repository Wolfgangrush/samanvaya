"""Samanvaya conformance engine — evaluation and roll-up.

Offline privacy-conformance CLI. This module is the single place where the
policy ordering of an evaluation is enforced: dependency ordering before any
evaluation, in-force filtering, applicability gating, conformance, and the
draft downgrade. Packs may build their own ``Finding`` objects, so ``run``
re-applies the in-force and draft rules as a deliberate post-pass — a pack
that builds findings by hand must not be able to bypass policy that every
pack using ``evaluate_obligations`` is subject to.

Why the ordering matters:

- A6: ``depends_on`` is resolved in topological order and cycles are pack
  LOAD errors, discovered before a single obligation is evaluated. A false
  stable answer on a dependent obligation is the highest-cost failure the
  adviser carries indemnity for.
- A4: a missing input to ``applies_if`` is CONTESTED, never a silent pass
  and never a gap, because "not declared" is not "compliant".
- A3: incompleteness notices are attached once per country to the result,
  not repeated per obligation.

No network, no file I/O, no clock reads, no randomness: the same
declaration and as-at date must always produce identical output.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from types import ModuleType
from typing import Any

from samanvaya import __version__
from samanvaya.declaration import canonical_hash
from samanvaya.jurisdiction import resolve
from samanvaya.types import (
    DISCLAIMER,
    AppliesIf,
    Declaration,
    Divergence,
    EngineResult,
    Finding,
    IncompletenessNotice,
    Obligation,
    ObligationResult,
    PackInfo,
    PredicateOp,
    RegimeId,
    RegimeRollup,
)

__all__ = ["evaluate_obligations", "run"]


def _topological_order(obligations: Sequence[Obligation]) -> list[Obligation]:
    """Return obligations in dependency order, preserving input order among peers.

    Raises PackLoadError naming every obligation in a cycle BEFORE any
    evaluation happens, because a partial run followed by an explosion is
    exactly the runtime surprise A6 exists to prevent.
    """
    by_id: dict[str, Obligation] = {}
    for obligation in obligations:
        if obligation.obligation_id in by_id:
            raise ValueError(
                f"duplicate obligation_id {obligation_id_of(obligation)!r} in pack"
            )
        by_id[obligation.obligation_id] = obligation

    # Dependency edges point from prerequisite to dependent.
    dependents: dict[str, list[str]] = {oid: [] for oid in by_id}
    in_degree: dict[str, int] = {oid: 0 for oid in by_id}
    for obligation in obligations:
        for dep in obligation.depends_on:
            if dep in by_id:
                dependents[dep].append(obligation.obligation_id)
                in_degree[obligation.obligation_id] += 1

    # Kahn's algorithm with an input-ordered ready list so output is
    # deterministic regardless of dictionary ordering.
    ready: list[str] = [o.obligation_id for o in obligations if in_degree[o.obligation_id] == 0]
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for follower in dependents[current]:
            in_degree[follower] -= 1
            if in_degree[follower] == 0:
                ready.append(follower)

    if len(ordered) != len(by_id):
        # Whatever never became ready is either in or downstream of a cycle;
        # every such obligation is named so the pack author can fix the pack.
        stuck = sorted(set(by_id) - set(ordered))
        raise_cycle_error(stuck, by_id)
    return [by_id[oid] for oid in ordered]


def obligation_id_of(obligation: Obligation) -> str:
    """Return an obligation's id (kept tiny for readable error messages)."""
    return obligation.obligation_id


def raise_cycle_error(stuck: Sequence[str], by_id: dict[str, Obligation]) -> None:
    """Raise a PackLoadError naming the obligations locked in a dependency cycle."""
    names = ", ".join(sorted(stuck))
    raise PackLoadErrorFor(f"dependency cycle in pack involving: {names}")


def PackLoadErrorFor(message: str) -> Exception:  # noqa: N802 - reads as a constructor
    """Build a PackLoadError; isolated so the import stays at module top."""
    from samanvaya.types import PackLoadError

    return PackLoadError(message)


def _resolve_path(declaration: Declaration, path: str) -> tuple[bool, Any]:
    """Walk a dotted path by getattr; return (resolved, value).

    A missing segment or a None value resolves to (False, None) so the
    caller can record CONTESTED naming the full path — never a silent pass.
    """
    current: Any = declaration
    for segment in path.split("."):
        try:
            current = getattr(current, segment)
        except AttributeError:
            return False, None
        if current is None:
            return False, None
    return True, current


def _apply_predicate(declaration: Declaration, predicate: AppliesIf) -> tuple[ObligationResult | bool, str]:
    """Evaluate one predicate.

    Returns either ``False`` (obligation does not apply, with a rationale),
    or an ObligationResult of CONTESTED (missing fact or incomparable types)
    with a rationale naming the path.
    """
    resolved, value = _resolve_path(declaration, predicate.path)
    if not resolved:
        return (
            ObligationResult.CONTESTED,
            f"applicability input {predicate.path!r} is not declared; "
            "the fact is needed before applicability can be decided",
        )
    op = predicate.op
    try:
        if op is PredicateOp.EQ:
            holds = value == predicate.value
        elif op is PredicateOp.NE:
            holds = value != predicate.value
        elif op is PredicateOp.GT:
            holds = value > predicate.value
        elif op is PredicateOp.GTE:
            holds = value >= predicate.value
        elif op is PredicateOp.LT:
            holds = value < predicate.value
        elif op is PredicateOp.LTE:
            holds = value <= predicate.value
        elif op is PredicateOp.IN:
            holds = value in predicate.value
        elif op is PredicateOp.CONTAINS:
            holds = predicate.value in value
        elif op is PredicateOp.TRUTHY:
            holds = bool(value)
        else:  # pragma: no cover - closed enum
            return (
                ObligationResult.CONTESTED,
                f"unsupported predicate operator {op!r} on {predicate.path!r}",
            )
    except TypeError:
        return (
            ObligationResult.CONTESTED,
            f"applicability input {predicate.path!r} ({value!r}) cannot be "
            f"compared with {op.value} {predicate.value!r}",
        )
    if holds:
        return True, ""
    label = predicate.description or f"{predicate.path} {op.value} {predicate.value!r}"
    return False, f"obligation does not apply: gating condition failed ({label})"


def _in_force_finding(obligation: Obligation) -> Finding:
    """Build a NOT_APPLICABLE finding naming the in-force window."""
    window = []
    if obligation.in_force_from is not None:
        window.append(f"in force from {obligation.in_force_from.isoformat()}")
    if obligation.in_force_until is not None:
        window.append(f"in force until {obligation.in_force_until.isoformat()}")
    detail = "; ".join(window) or "no in-force window recorded"
    return Finding(
        obligation=obligation,
        result=ObligationResult.NOT_APPLICABLE,
        rationale=f"not in force on the as-at date: {detail}",
    )


def _propagate_dependencies(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    """A6, applied to findings a pack built by hand.

    This exists because of a real defect, and the defect is worth recording. The India
    pack constructs its Findings directly against the upstream engine rather than through
    ``evaluate_obligations``, so its ``depends_on`` edges were never honoured. The result
    was that an organisation which declared it had NOT been notified as a Significant Data
    Fiduciary — making ``in.sdf.determination`` ``not_applicable`` — was still reported as
    having a **gap** on ``in.sdf.obligations``, the twelve-monthly DPIA and audit under
    Rule 13.

    That is a false accusation against the client on the highest-stakes obligation in the
    India rail, and it is exactly the failure the specification's fourth falsifier names.
    Enforcing the rule only inside ``evaluate_obligations`` was not enough, because the
    one pack that matters most does not go through it.

    Findings are walked in dependency order so a chain resolves in a single pass, and each
    verdict is read from the live map rather than the incoming one.
    """
    by_id: dict[str, ObligationResult] = {
        f.obligation.obligation_id: f.result for f in findings
    }
    ordered = _topological_order([f.obligation for f in findings])
    position = {ob.obligation_id: i for i, ob in enumerate(ordered)}
    walk = sorted(findings, key=lambda f: position.get(f.obligation.obligation_id, 0))

    resolved: dict[str, Finding] = {}
    for finding in walk:
        obligation = finding.obligation
        if not obligation.depends_on:
            resolved[obligation.obligation_id] = finding
            continue

        outcome: ObligationResult | None = None
        why = ""
        for dep in obligation.depends_on:
            dep_result = by_id.get(dep)
            if dep_result is None:
                outcome, why = (
                    ObligationResult.CONTESTED,
                    f"depends on {dep!r}, which this pack did not evaluate, so the "
                    "precondition could not be resolved",
                )
                break
            if dep_result is ObligationResult.SATISFIED:
                continue
            if dep_result in (
                ObligationResult.NOT_APPLICABLE,
                ObligationResult.DOES_NOT_EXIST,
            ):
                outcome, why = (
                    ObligationResult.NOT_APPLICABLE,
                    f"its precondition {dep!r} resolved to {dep_result.value}, so this "
                    "obligation is not engaged on the declared facts",
                )
                break
            outcome, why = (
                ObligationResult.CONTESTED,
                f"its precondition {dep!r} resolved to {dep_result.value}, so this "
                "obligation cannot be judged either way until that is settled",
            )
            break

        if outcome is None or finding.result is outcome:
            resolved[obligation.obligation_id] = finding
            by_id[obligation.obligation_id] = finding.result
            continue

        adjusted_finding = Finding(
            obligation=obligation,
            result=outcome,
            rationale=f"{why}. Original verdict was {finding.result.value}: {finding.rationale}",
            declaration_summary=finding.declaration_summary,
            evidence_paths=finding.evidence_paths,
        )
        resolved[obligation.obligation_id] = adjusted_finding
        by_id[obligation.obligation_id] = outcome

    # Restore the pack's own emission order; only the verdicts have changed.
    return tuple(resolved[f.obligation.obligation_id] for f in findings)


def _post_pass(findings: Sequence[Finding], as_at: date, pack_info: PackInfo | None) -> tuple[Finding, ...]:
    """Re-apply the in-force rule, dependency propagation and the draft downgrade.

    Deliberate belt-and-braces: a pack that builds Findings by hand rather than through
    ``evaluate_obligations`` must not be able to bypass the policy that binds every pack.
    Each step is idempotent, so running it over findings that already went through
    ``evaluate_obligations`` changes nothing.
    """
    findings = _propagate_dependencies(findings)
    adjusted: list[Finding] = []
    for finding in findings:
        # An obligation resting on an unsourced constant cannot support a verdict, so it
        # never reaches the adviser as `satisfied` or `gap`. This is enforced HERE rather
        # than trusted to each pack, because it is the rule that keeps a guessed section
        # number from ever becoming an accusation — or an absolution — against a client.
        #
        # A `*_note` caveat is deliberately excluded from this test (see
        # Obligation.has_unsourced_caveat): a caveat qualifies a finding, it does not
        # disqualify it.
        if (
            finding.obligation.has_unsourced_constant()
            and finding.result in (ObligationResult.SATISFIED, ObligationResult.GAP)
        ):
            adjusted.append(
                Finding(
                    obligation=finding.obligation,
                    result=ObligationResult.CONTESTED,
                    rationale=(
                        "downgraded: this obligation rests on a constant that could not be "
                        "sourced on a primary text, so it cannot be judged either way. "
                        f"Original verdict was {finding.result.value}: {finding.rationale}"
                    ),
                    declaration_summary=finding.declaration_summary,
                    evidence_paths=finding.evidence_paths,
                )
            )
            continue
        obligation = finding.obligation
        if not obligation.is_in_force(as_at) and finding.result is not ObligationResult.NOT_APPLICABLE:
            adjusted.append(_in_force_finding(obligation))
            continue
        if (
            pack_info is not None
            and pack_info.draft
            and finding.result is ObligationResult.SATISFIED
        ):
            reason = pack_info.draft_reason.strip() or "reason not stated"
            adjusted.append(
                Finding(
                    obligation=obligation,
                    result=ObligationResult.CONTESTED,
                    rationale=(
                        f"downgraded because the pack is a draft ({reason}); "
                        "constants are not yet primary-sourced so no "
                        "'satisfied' finding may be emitted"
                    ),
                )
            )
            continue
        adjusted.append(finding)
    return tuple(adjusted)


def evaluate_obligations(
    obligations: Sequence[Obligation],
    declaration: Declaration,
    as_at: date,
    evaluator: Callable[[Obligation, Declaration], ObligationResult],
    pack_info: PackInfo | None = None,
) -> list[Finding]:
    """Evaluate a pack's obligations against a declaration.

    The order of operations is policy, not convenience: topological ordering
    and cycle detection first (A6), then in-force, then dependency
    propagation, then applicability gating (A4), then conformance, then the
    draft downgrade. Never raises for bad declaration data; such data
    resolves to CONTESTED with a rationale explaining what is missing.
    """
    ordered = _topological_order(obligations)
    results: dict[str, ObligationResult] = {}
    findings: list[Finding] = []

    for obligation in ordered:
        oid = obligation.obligation_id

        # b) In force.
        if not obligation.is_in_force(as_at):
            finding = _in_force_finding(obligation)
            results[oid] = finding.result
            findings.append(finding)
            continue

        # c) Dependency propagation.
        short_circuit: tuple[ObligationResult, str] | None = None
        for dep_id in obligation.depends_on:
            if dep_id not in results:
                short_circuit = (
                    ObligationResult.CONTESTED,
                    f"dependency {dep_id!r} is not present in this obligation set",
                )
                break
            dep_result = results[dep_id]
            if dep_result is ObligationResult.SATISFIED:
                continue
            if dep_result in (ObligationResult.NOT_APPLICABLE, ObligationResult.DOES_NOT_EXIST):
                short_circuit = (
                    ObligationResult.NOT_APPLICABLE,
                    f"dependency {dep_id!r} is {dep_result.value}, "
                    "so this obligation does not apply",
                )
            else:
                short_circuit = (
                    ObligationResult.CONTESTED,
                    f"dependency {dep_id!r} is {dep_result.value}, "
                    "so this obligation cannot be resolved",
                )
            break

        if short_circuit is not None:
            result, rationale = short_circuit
            results[oid] = result
            findings.append(Finding(obligation=obligation, result=result, rationale=rationale))
            continue

        # d) Applicability gating.
        if obligation.applies_if:
            applies = True
            for predicate in obligation.applies_if:
                outcome, rationale = _apply_predicate(declaration, predicate)
                if outcome is ObligationResult.CONTESTED:
                    applies = False
                    results[oid] = outcome
                    findings.append(Finding(obligation=obligation, result=outcome, rationale=rationale))
                    break
                if outcome is False:
                    applies = False
                    results[oid] = ObligationResult.NOT_APPLICABLE
                    findings.append(
                        Finding(
                            obligation=obligation,
                            result=ObligationResult.NOT_APPLICABLE,
                            rationale=rationale,
                        )
                    )
                    break
            if not applies:
                continue

        # e) Conformance.
        result = evaluator(obligation, declaration)
        rationale = f"evaluated against the declaration on {as_at.isoformat()}"

        # f) Draft downgrade — a draft pack must never tick a box.
        if pack_info is not None and pack_info.draft and result is ObligationResult.SATISFIED:
            reason = pack_info.draft_reason.strip() or "reason not stated"
            result = ObligationResult.CONTESTED
            rationale = (
                f"downgraded because the pack is a draft ({reason}); "
                "constants are not yet primary-sourced so no "
                "'satisfied' finding may be emitted"
            )

        results[oid] = result
        findings.append(Finding(obligation=obligation, result=result, rationale=rationale))

    return findings


def _counts(findings: Sequence[Finding]) -> dict[str, int]:
    """Count findings by result value, including zero entries for unused results.

    Zero entries matter so downstream consumers can index ``counts``
    without defensive ``.get`` calls, and so
    ``sum(counts.values()) == len(findings)`` always holds.
    """
    counts: dict[str, int] = {result.value: 0 for result in ObligationResult}
    for finding in findings:
        counts[finding.result.value] += 1
    return counts


def run(
    declaration: Declaration,
    as_at: date,
    regimes: Sequence[RegimeId] | None = None,
) -> EngineResult:
    """Run every applicable pack against the declaration and roll up the result.

    Deterministic by construction: no clock reads, no randomness, and every
    collection that could leak set-iteration order is sorted before use.
    """
    resolution = resolve(declaration)
    resolved_regimes: set[RegimeId] = {regime for regime, _sub_unit in resolution.targets}
    if regimes is not None:
        resolved_regimes &= set(regimes)

    # Sorted by RegimeId declaration order for a stable output sequence.
    ordered_regimes = [r for r in RegimeId if r in resolved_regimes]

    per_regime: dict[RegimeId, RegimeRollup] = {}
    all_notices: list[IncompletenessNotice] = list(resolution.notices)

    # The declaration named one or more countries the resolver could not
    # map to any sourced pack. The resolver already keeps the tokens in
    # ``unknown_countries`` with the explicit contract that they are never
    # silently dropped, but nothing downstream was reading it. Emit one
    # regime-less notice per uncovered country BEFORE the per-regime loop
    # so a declaration naming an unsupported jurisdiction never suppresses
    # the rest of the run: the run still walks every regime it CAN cover,
    # and the reader is told plainly that the named country went
    # unassessed. Sorted by the declared token for determinism.
    for token in sorted(resolution.unknown_countries):
        all_notices.append(
            IncompletenessNotice(
                regime=None,
                country=token,
                message=(
                    f"{token} was declared as a jurisdiction but this tool "
                    f"has no sourced obligations for it, so {token} was NOT "
                    f"ASSESSED. Its absence from the findings above is not a finding."
                ),
            )
        )

    for regime in ordered_regimes:
        # Imported here, not at module scope, to break a genuine import cycle: the
        # registry imports the six packs, and every pack imports `evaluate_obligations`
        # from this module. Deferring the lookup to call time is the smallest fix that
        # keeps the registry a plain hardcoded mapping (C2) rather than a lazy loader.
        from samanvaya.registry import get as get_pack

        from samanvaya.packs.contract import PackProtocol

        pack: PackProtocol = get_pack(regime)
        pack_info = pack.info()
        findings: list[Finding] = []
        for target_regime, sub_unit in sorted(resolution.targets, key=lambda t: t[1] or ""):
            if target_regime is not regime:
                continue
            findings.extend(pack.evaluate(declaration, as_at, sub_unit))
        # Belt-and-braces post-pass (see module docstring): a pack that
        # builds Findings by hand cannot bypass the in-force rule or the
        # draft downgrade.
        findings = list(_post_pass(findings, as_at, pack_info))
        rollup_notices = tuple(n for n in resolution.notices if n.regime is regime)
        per_regime[regime] = RegimeRollup(
            regime=regime,
            pack_info=pack_info,
            findings=tuple(findings),
            counts=_counts(findings),
            notices=rollup_notices,
        )

    # Delta is optional at runtime so the engine works before it lands.
    try:
        from samanvaya.delta import compute as compute_divergences

        divergences: tuple[Divergence, ...] = compute_divergences(per_regime)
    except ImportError:
        divergences = ()

    return EngineResult(
        declaration_hash=canonical_hash(declaration),
        tool_version=__version__,
        as_at=as_at,
        per_regime=per_regime,
        divergences=divergences,
        notices=tuple(all_notices),
        disclaimer=DISCLAIMER,
    )
