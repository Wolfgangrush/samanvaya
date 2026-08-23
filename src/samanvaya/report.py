"""Markdown and JSON-lines renderers for the conformance engine.

Both renderers derive from ONE :class:`EngineResult`. That is not tidiness: if the
Markdown a client reads and the JSON-lines an auditor reads could ever disagree,
the report has no evidential value at all, and the adviser cannot say which of
the two he stood behind. Every artefact carries the fixed not-legal-advice
disclaimer and the declaration hash, so a report can be tied to the exact
declaration it was produced from.

Reaches no network and persists only the file the caller names — no cache, no
log, no history.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

from samanvaya.types import (
    FACT_NEEDED_PREFIX,
    DISCLAIMER,
    Divergence,
    DivergencePosition,
    EngineResult,
    Finding,
    IncompletenessNotice,
    ObligationResult,
    PackInfo,
    RegimeId,
    RegimeRollup,
)

_FORMAT_MD = "md"
_FORMAT_JSONL = "jsonl"
_FORMAT_BOTH = "both"
_ALLOWED_FORMATS = frozenset({_FORMAT_MD, _FORMAT_JSONL, _FORMAT_BOTH})


def _stable_dumps(payload: dict[str, Any]) -> str:
    """Serialise one record deterministically so rendering is byte-stable."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _unsourced_marker(finding: Finding) -> str | None:
    """Return the FACT NEEDED marker for a finding, if any obligation field carries it."""
    obligation = finding.obligation
    for text in (
        obligation.provision,
        obligation.citation_pointer,
        obligation.obligation_summary,
        obligation.sub_topic.value,
        obligation.required_value or "",
    ):
        if FACT_NEEDED_PREFIX in text:
            return text
    return None


def _render_header_lines(result: EngineResult) -> list[str]:
    """Return the shared markdown header block, written identically by both formats."""
    lines: list[str] = []
    lines.append("# Conformance report")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    lines.append("")
    lines.append(f"- as_at: {result.as_at.isoformat()}")
    lines.append(f"- tool_version: {result.tool_version}")
    lines.append(f"- declaration_hash: {result.declaration_hash}")
    if result.declaration_path is not None:
        lines.append(f"- declaration_path: {result.declaration_path}")
    lines.append("")
    return lines


def _render_notices_section(notices: tuple[IncompletenessNotice, ...]) -> list[str]:
    """Render the Declaration completeness section, if any notices exist.

    A notice with ``regime is None`` represents an uncovered declared
    jurisdiction. The Regime slot is rendered as ``None declared`` so the
    reader can still see which country the notice is about and why it was
    emitted; silently omitting the slot would re-introduce the very bug
    this section exists to prevent.
    """
    if not notices:
        return []
    lines = ["## Declaration completeness", ""]
    for notice in notices:
        regime_label = notice.regime.value if notice.regime is not None else "None declared"
        lines.append(
            f"- {regime_label} / {notice.country}: {notice.message}"
        )
    lines.append("")
    return lines


def _render_divergences_section(divergences: tuple[Divergence, ...]) -> list[str]:
    """Render cross-regime divergences without ranking the positions."""
    if not divergences:
        return []
    lines = [
        "## Cross-regime divergences",
        "",
        "The report records divergence and does not rank it, because ranking "
        "statutes would be legal interpretation.",
        "",
    ]
    for divergence in divergences:
        heading = f"### {divergence.topic.value} — {divergence.dimension}"
        if divergence.unit:
            heading += f" (unit: {divergence.unit})"
        lines.append(heading)
        lines.append("")
        for position in divergence.positions:
            sub_unit = position.sub_unit or ""
            lines.append(
                f"- {position.regime.value} {sub_unit} — "
                f"{position.instrument}, {position.provision}: "
                f"{position.value} {position.unit or ''} "
                f"({position.result.value})".rstrip()
            )
        lines.append("")
    return lines


def _render_pack_header(rollup: RegimeRollup) -> list[str]:
    """Render the per-regime heading block, including the DRAFT PACK label."""
    pack_info: PackInfo = rollup.pack_info
    lines: list[str] = []
    if pack_info.draft:
        lines.append(f"**DRAFT PACK** — {pack_info.draft_reason or 'no reason supplied'}")
        lines.append("")
    return lines


def _render_finding_lines(finding: Finding) -> list[str]:
    """Render one finding as a bullet plus indented supporting lines."""
    obligation = finding.obligation
    head = (
        f"- [{finding.result.value}] {obligation.obligation_id} — "
        f"{obligation.instrument}, {obligation.provision}"
    )
    lines: list[str] = [head]
    lines.append(f"  - obligation: {obligation.obligation_summary}")
    lines.append(f"  - rationale: {finding.rationale}")
    if finding.declaration_summary is not None:
        lines.append(f"  - declaration: {finding.declaration_summary}")
    marker = _unsourced_marker(finding)
    if marker is not None:
        lines.append(f"  - {marker}")
    lines.append(f"  - cite: {obligation.citation_pointer}")
    return lines


def _not_yet_in_force(rollup: RegimeRollup, as_at: date) -> tuple[int, str | None]:
    """How many obligations have not commenced by ``as_at``, and the earliest that does.

    Computed from the obligations' ``in_force_from``, not by matching rationale text, so
    a change of wording cannot silently switch the notice off.

    ``as_at`` is the RUN's date, not the pack's. Using ``pack_info.as_at`` would pin the
    answer to the day the pack was authored, so a run dated after commencement would
    still be told the obligations had not arrived — the notice would never clear.
    """
    pending = [
        f.obligation for f in rollup.findings
        if f.result is ObligationResult.NOT_APPLICABLE
        and f.obligation.in_force_from is not None
        and not f.obligation.is_in_force(as_at)
    ]
    if not pending:
        return 0, None
    earliest = min(ob.in_force_from for ob in pending if ob.in_force_from is not None)
    return len(pending), earliest.isoformat()


def _render_regime_section(rollup: RegimeRollup, as_at: date) -> list[str]:
    """Render one regime section: pack info, counts, then findings."""
    pack_info: PackInfo = rollup.pack_info
    lines: list[str] = [f"## {rollup.regime.value}", ""]
    lines.extend(_render_pack_header(rollup))
    lines.append(f"- pack_id: {pack_info.pack_id}")
    lines.append(f"- version: {pack_info.version}")
    lines.append(f"- pack_as_at: {pack_info.as_at.isoformat()}")
    if pack_info.instruments:
        lines.append(f"- instruments: {', '.join(pack_info.instruments)}")
    lines.append("- counts:")
    for key in sorted(rollup.counts):
        lines.append(f"  - {key}: {rollup.counts[key]}")
    lines.append("")

    # A commencement notice goes ABOVE the findings, because that is where a skim-reader
    # meets it. Without it the section reads "not_applicable: 11" and a client concludes
    # they have no duties under this regime. They do — the duties have not arrived yet,
    # and the difference between those two readings is the entire point of the advice.
    pending, earliest = _not_yet_in_force(rollup, as_at)
    if pending:
        lines.append(
            f"> **{pending} obligation(s) in this regime are NOT YET IN FORCE** on the "
            f"as-at date, the earliest commencing {earliest}. They are reported as "
            "`not_applicable` for that reason alone — not because the organisation is "
            "outside their scope. Read each finding's rationale before relying on this."
        )
        lines.append("")
    for finding in rollup.findings:
        lines.extend(_render_finding_lines(finding))
        lines.append("")
    return lines


def _render_markdown(result: EngineResult) -> str:
    """Assemble the markdown body in declaration order."""
    lines: list[str] = []
    lines.extend(_render_header_lines(result))
    lines.extend(_render_notices_section(result.notices))
    lines.extend(_render_divergences_section(result.divergences))
    for regime in RegimeId:
        rollup = result.per_regime.get(regime)
        if rollup is None:
            continue
        lines.extend(_render_regime_section(rollup, result.as_at))
    return "\n".join(lines).rstrip() + "\n"


def _render_jsonl_header(result: EngineResult) -> str:
    """Serialise the first JSONL line, which carries disclaimer and identity."""
    payload: dict[str, Any] = {
        "type": "header",
        "disclaimer": DISCLAIMER,
        "as_at": result.as_at.isoformat(),
        "tool_version": result.tool_version,
        "declaration_hash": result.declaration_hash,
    }
    if result.declaration_path is not None:
        payload["declaration_path"] = result.declaration_path
    return _stable_dumps(payload)


def _render_jsonl_notices(notices: tuple[IncompletenessNotice, ...]) -> list[str]:
    """Serialise one notice per line.

    ``regime`` is emitted as ``null`` when the declaration named a
    jurisdiction the tool does not cover; the JSON-lines consumer still
    sees the country token and the human-readable message so the absence
    is not lost downstream.
    """
    return [
        _stable_dumps(
            {
                "type": "notice",
                "regime": notice.regime.value if notice.regime is not None else None,
                "country": notice.country,
                "message": notice.message,
            }
        )
        for notice in notices
    ]


def _render_jsonl_pack(rollup: RegimeRollup, as_at: date) -> str:
    """Serialise one pack metadata line per regime."""
    pack_info = rollup.pack_info
    payload: dict[str, Any] = {
        "type": "pack",
        "regime": rollup.regime.value,
        "pack_id": pack_info.pack_id,
        "version": pack_info.version,
        "as_at": pack_info.as_at.isoformat(),
        "draft": pack_info.draft,
        "draft_reason": pack_info.draft_reason,
        "instruments": list(pack_info.instruments),
        "counts": dict(rollup.counts),
        # The same fact the markdown surfaces above the findings, so a machine
        # consumer cannot read "not_applicable" without also seeing why.
        "not_yet_in_force": _not_yet_in_force(rollup, as_at)[0],
        "earliest_commencement": _not_yet_in_force(rollup, as_at)[1],
    }
    return _stable_dumps(payload)


def _render_jsonl_finding(finding: Finding) -> str:
    """Serialise one finding line with structured sub_topic."""
    obligation = finding.obligation
    sub_topic_payload: dict[str, Any] = {
        "dimension": obligation.sub_topic.dimension,
        "value": obligation.sub_topic.value,
    }
    if obligation.sub_topic.unit is not None:
        sub_topic_payload["unit"] = obligation.sub_topic.unit
    payload: dict[str, Any] = {
        "type": "finding",
        "regime": obligation.regime.value,
        "sub_unit": obligation.sub_unit,
        "instrument": obligation.instrument,
        "provision": obligation.provision,
        "topic": obligation.topic.value,
        "sub_topic": sub_topic_payload,
        "obligation_summary": obligation.obligation_summary,
        "declaration_summary": finding.declaration_summary,
        "result": finding.result.value,
        "citation_pointer": obligation.citation_pointer,
        "rationale": finding.rationale,
        "obligation_id": obligation.obligation_id,
        "evaluation_metadata": {k: v for k, v in obligation.evaluation_metadata},
        "evidence_paths": list(finding.evidence_paths),
    }
    if obligation.required_value is not None:
        payload["required_value"] = obligation.required_value
    if finding.obligation.has_unsourced_constant():
        marker = _unsourced_marker(finding)
        if marker is not None:
            payload["fact_needed"] = marker
    return _stable_dumps(payload)


def _render_jsonl_divergence(divergence: Divergence) -> str:
    """Serialise one divergence line; positions carry no rank."""
    positions_payload: list[dict[str, Any]] = []
    for position in divergence.positions:
        entry: dict[str, Any] = {
            "regime": position.regime.value,
            "sub_unit": position.sub_unit,
            "instrument": position.instrument,
            "provision": position.provision,
            "value": position.value,
            "unit": position.unit,
            "result": position.result.value,
        }
        positions_payload.append(entry)
    payload: dict[str, Any] = {
        "type": "divergence",
        "topic": divergence.topic.value,
        "dimension": divergence.dimension,
        "positions": positions_payload,
    }
    if divergence.unit is not None:
        payload["unit"] = divergence.unit
    return _stable_dumps(payload)


def _render_jsonl(result: EngineResult) -> str:
    """Assemble the JSONL body in declaration order, byte-stable."""
    lines: list[str] = [_render_jsonl_header(result)]
    lines.extend(_render_jsonl_notices(result.notices))
    for regime in RegimeId:
        rollup = result.per_regime.get(regime)
        if rollup is None:
            continue
        lines.append(_render_jsonl_pack(rollup, result.as_at))
    for finding in result.all_findings:
        lines.append(_render_jsonl_finding(finding))
    for divergence in result.divergences:
        lines.append(_render_jsonl_divergence(divergence))
    return "\n".join(lines) + "\n"


def render(result: EngineResult, fmt: str) -> str:
    """Render the engine output as Markdown or JSON-lines.

    Both renderings derive from the SAME ``EngineResult`` and must never be
    able to disagree: if the Markdown a client reads and the JSON-lines an
    auditor reads could differ, the report has no evidential value and the
    adviser cannot say which one he stood behind.
    """
    if fmt == _FORMAT_MD:
        return _render_markdown(result)
    if fmt == _FORMAT_JSONL:
        return _render_jsonl(result)
    raise ValueError(f"unknown render format: {fmt!r}")


def _check_target(path: Path) -> None:
    """Refuse a target this tool must not write to.

    What is deliberately NOT refused: a ``..`` segment. The adviser chose the output
    path, and rejecting relative navigation would only stop the person who typed it on
    purpose. An earlier version of this function compared a path's resolved parent with
    its own resolved parent and raised on inequality — a tautology that could never fire,
    dressed as a security control. False assurance is worse than none, so it is gone.

    What IS refused, and why each one matters for a file holding client findings:

    * the parent directory does not exist — this tool creates no directories, because
      silently materialising a path is how a report ends up somewhere nobody looks;
    * the parent is not a directory;
    * the target already exists and is not a regular file — a directory, a device, or a
      FIFO;
    * the target is a symbolic link. A planted symlink is the one way a caller-supplied
      path can redirect client personal data somewhere the adviser did not choose, and
      following it would be the tool's own fault rather than the adviser's.
    """
    parent = path.parent
    if not parent.exists():
        raise ValueError(f"refusing to write: directory does not exist: {parent}")
    if not parent.is_dir():
        raise ValueError(f"refusing to write: not a directory: {parent}")
    if path.is_symlink():
        raise ValueError(f"refusing to write through a symbolic link: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"refusing to overwrite a non-regular file: {path}")


def write(result: EngineResult, out: Path, fmt: str = "both") -> None:
    """Persist the rendered report to disk.

    The supplied path is a STEM: ``md`` writes ``<stem>.md``, ``jsonl`` writes
    ``<stem>.jsonl``, ``both`` writes both. No cache, no log, no history —
    only the report files the caller named are written.
    """
    if fmt not in _ALLOWED_FORMATS:
        raise ValueError(f"unknown render format: {fmt!r}")
    parent = out.parent
    targets: list[tuple[Path, str]] = []
    if fmt in (_FORMAT_MD, _FORMAT_BOTH):
        targets.append((parent / (out.name + ".md"), _render_markdown(result)))
    if fmt in (_FORMAT_JSONL, _FORMAT_BOTH):
        targets.append((parent / (out.name + ".jsonl"), _render_jsonl(result)))

    # Check every target BEFORE writing any of them, so a rejected second file cannot
    # leave a half-written report behind that reads as complete.
    for path, _text in targets:
        _check_target(path)
    for path, text in targets:
        path.write_text(text, encoding="utf-8")


__all__ = ["render", "write"]


# Defensive: silence unused-import warnings under strict-mypy without runtime cost.
_ = (ObligationResult, DivergencePosition)
