# 03 — ARCHITECTURE ESSENTIALS  ·  Samanvaya Privacy Conformance Tool

**Outline only.** Full record: `02-ARCHITECTURE.md`.

Offline, declaration-driven CLI; one hand-authored declaration against six regulatory regimes; local report.

## Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+; frozen dataclasses; strict mypy |
| YAML | `ruamel.yaml` round-trip |
| JSON | stdlib `json` |
| CLI | `argparse` (`check`, `init`, `validate`, `version`, `cite`) |
| India upstream | `dpdp-law-to-code==<pinned>` as a library |
| Reports | Markdown + JSON-lines from one `EngineResult` |
| Tests | `pytest` + Hypothesis |
| Packs | setuptools entry points |

## Components

| Module | Role |
|---|---|
| `samanvaya.cli` | parse args, dispatch, write reports |
| `samanvaya.declaration` | parse and validate one declaration |
| `samanvaya.jurisdiction` | expand country and sub-national trees |
| `samanvaya.packs` | discover installed pack entry points |
| `samanvaya.packs.*` | evaluate declaration, date, jurisdiction |
| `samanvaya.packs.india.adapter` | map to upstream India checks |
| `samanvaya.engine` | dispatch packs, apply dates, build rollups |
| `samanvaya.delta` | compare obligations and verdicts across regimes |
| `samanvaya.report` | render Markdown + JSON-lines |
| `samanvaya.offline_check` | verify runtime network prohibition |
| `samanvaya.schema` | validate structure; reject unknown keys |

## Key types

| Type | Fields |
|---|---|
| `Declaration` | `schema_version: str`; `organisation: Organisation`; `jurisdictions: list[JurisdictionRef]`; `data_categories: list[DataCategory]`; `purposes: list[Purpose]`; `recipients: list[Recipient]`; `security_safeguards: SecuritySafeguards`; `consent_mechanism: ConsentMechanism`; `breach_workflow: BreachWorkflow`; `dsr_workflow: DsrWorkflow`; `retention: list[RetentionRule]`; `sub_national_units: list[SubNationalUnit]`; `declaration_author: str` |
| `JurisdictionTree` | `by_regime: dict[RegimeId, set[str \| None]]`; `completeness: dict[RegimeId, bool]`; `unspecified: set[RegimeId]` |
| `Obligation` | `obligation_id: str`; `regime: RegimeId`; `sub_unit: str \| None`; `instrument: str`; `provision: str`; `topic: ObligationTopic`; `sub_topic: str`; `obligation_summary: str`; `in_force_from: date \| None`; `in_force_until: date \| None`; `declaration_summary: str \| None`; `result: ObligationResult`; `citation_pointer: str`; `evaluation_metadata: dict[str, str]` |
| `Finding` | `obligation: Obligation`; `result: ObligationResult`; `rationale: str`; `evidence_paths: list[str]` |
| `PackInfo` | `pack_id: str`; `regime: RegimeId`; `version: str`; `covers_sub_units: set[str]`; `as_at: date`; `draft: bool`; `obligation_count: int` |
| `EngineResult` | `declaration_hash: str`; `tool_version: str`; `as_at: date`; `per_regime: dict[RegimeId, RegimeRollup]`; `divergences: list[Divergence]`; `disclaimer: str` |

## Obligation result

| Value | Meaning |
|---|---|
| `satisfied` | declaration meets the obligation |
| `gap` | obligation exists; declaration does not address it |
| `contested` | declaration is ambiguous, partial, or based on incomplete facts |
| `not_applicable` | obligation exists; precondition not met |
| `does_not_exist` | regime does not impose the obligation |

## Flow

```text
declaration file -> loader/schema -> Declaration -> jurisdiction resolver
  -> pack registry -> obligation engine -> India adapter -> regulation packs
  -> Finding[] -> delta computer -> EngineResult
  -> Markdown + JSON-lines -> local report file
```

## Pack contract

```python
evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]
```

- One evaluation entry point per pack.
- Scope = declared regime and jurisdiction only.
- Every obligation cites a named instrument and provision.
- Pack emits `does_not_exist` for covered topics it does not impose.
- Pack applies the supplied `as_at` date.
- A draft pack never emits `satisfied`.
- No read or persist of the declaration beyond the call.

## Hard invariants

- No network calls, telemetry, or outbound HTTP at runtime.
- No persistence beyond the explicitly written local report file.
- No LLM or other nondeterministic interpreter in the conformance path.
- Every finding carries a citation to a named instrument and provision.
- A draft pack can never emit `satisfied`.
- United States and Canada remain jurisdictional trees; country-only declarations are incomplete.
- `dpdp-law-to-code` is consumed unmodified; India logic is not reimplemented.
- Missing or unsourced facts produce `[FACT NEEDED: ...]`, never guessed citations or constants.
- Reports carry the fixed not-legal-advice disclaimer.
- Security-control implementation, scanning, remediation, and auto-filling remain outside the system.

## Implementation gates

| Gate | Reason |
|---|---|
| Confirm upstream India `ComplianceResult` API + `check_*` signatures | adapter depends on exact shape |
| Map every upstream India result variant to the shared enum | shared enum is fixed |
| Registry validates pack metadata matches `evaluate` implementation | prevent contract bypass |
| Adapter accepts `as_at` only through a deterministic compatibility boundary | upstream date form differs |
| Markdown + JSON-lines derive from one `EngineResult` | prevent divergent output |
| Distinguish missing US/Canada sub-units from inapplicable federal laws | tree semantics |
| Mark India API + US/Canada applicability as explicit gates before v1 | known risk surfaces |

## Hard-question pass — risks to watch

| Category | Items |
|---|---|
| Break risk | upstream India API mismatch; pack-metadata vs evaluation divergence; `as_at` form boundary; renderer divergence; US/Canada federal sectoral applicability; upstream result shape mismatch |
| Edge cases | unknown country codes; duplicate jurisdictions; US state named without country; Canadian province without Quebec while Law 25 must not run; US state with no federal sectoral statute; missing legal form/size/activity; cross-regime legal-basis conflict; conflicting security/breach declarations; duplicate/empty/unparseable purposes; ambiguous retention units; declaration mutation across runs; `--as-at` past/future/commencement; stale pack `as_at`; draft pack + satisfied request; pack omitting topic without `does_not_exist`; two obligations with same topic+sub-topic but different scope; upstream India result outside expected shape; missing/malformed citation pointer; report path collision or unsafe path; interruption before report completion; suspected credentials/keys/connection strings; YAML duplicate keys or unsupported tags; JSON NaN/non-standard values; missing or incompatible CLI options; requested regime not installed; stdout truncation/pipe; forbidden dependency imported after startup checks; pack emitting `satisfied` for obligation not in force; jurisdiction change requiring stable-obligation re-evaluation; non-canonical-YAML hash |
| Over-engineering — cut before v1 | third-party pack loading / arbitrary Python plugins; web UI / hosted backend / DB / cache / analytics / telemetry / report history; LLM-based statute interpretation or citation fallback; rule-engine DSL / custom statutory reasoning language; separate wheels per first-party regime; auto-remediation / best-effort fill / declaration rewriting; runtime statute retrieval or scraping; separate findings store / cross-run comparison DB; security-control generation / scanning / pentesting / discovery; delta comparison layer before core pack contract and citation validation are stable |
---

# Hard-question pass — 2026-08-19

Reviewer: **another delegate model**, deliberately NOT the model that authored 01/02/03 (one delegate model).
Full critique: `BMAD/hard-question-pass-2026-08-19.md`.
Adjudication by the maintainer. **Accepted findings are binding on 02 and on the code.**

## ACCEPTED — design changes required

| # | Finding | Change required |
|---|---|---|
| A1 | `sub_topic` opaque strings do not compare. `age_threshold_18` vs `age_threshold_16` are distinct strings, so the delta emits string-mismatch noise instead of one CHILDREN divergence. | `sub_topic` becomes a **structured value**: `(dimension, value, unit)`. The delta groups on `dimension` and reports differing `value`s as ONE divergence row. Opaque strings are banned. |
| A2 | `instrument` missing from the grouping key. A California hospital under both CCPA (`US-CA`) and HIPAA (federal) produces two obligations with `regime="US"` that either merge and lose the distinction, or duplicate ambiguously. | Grouping key becomes `(regime, sub_unit, instrument, topic, dimension)`. `instrument` is promoted to a first-class key field. |
| A3 | US/Canada federal-only false positive. An org triggering only HIPAA, with no CCPA-state presence, declares "US" with no states and is flagged as an incomplete `gap` — forcing it to enumerate 50 states to prove a negative. | The declaration gains an explicit **`sub_units_complete: bool`**. When true, absence of a state is `does_not_exist`, not `gap`. When false or absent, the engine emits the incompleteness notice **once per country**, never per obligation. |
| A4 | Obligations lack applicability thresholds. Nothing can express "applies only if employee_count > N" or "only to high-risk processing", so the engine cannot emit `not_applicable` for a small entity. | `Obligation` gains **`applies_if`** — a declarative predicate over Declaration fields. Evaluated before conformance. Missing input for a predicate yields `contested`, never a silent pass. |
| A5 | Safeguard *values* cannot be compared. "Encryption: Yes" against a rule demanding a named algorithm collapses to a boolean. | Safeguard declarations become `(control, value)` pairs, and an obligation may carry a `required_value`. Comparison is value-aware. Where the statute names no specific value — as with DPDP Rule 6(1)(a), which lists encryption, obfuscation, masking or virtual tokens without prescribing a standard — the obligation carries **no** `required_value` and presence alone satisfies. Do not invent a standard the instrument does not state. |
| A6 | No chained evaluation. "Appoint X if you are a Significant Data Fiduciary" depends on the outcome of the SDF determination; the engine cannot order them, so the finding oscillates. | Obligations gain **`depends_on: list[obligation_id]`**. The engine evaluates in dependency order (topological). A cycle is a pack-load error, not a runtime surprise. An unresolved dependency yields `contested`. |
| A7 | Upstream adapter fails with an opaque `TypeError`/`ImportError` if `dpdp-law-to-code` changes its `ComplianceResult` shape or a `check_*` signature. | The adapter runs a **contract check on load** — verifying the expected attributes and signatures — and on mismatch fails with a named, actionable error identifying the upstream version. Never an opaque traceback. |

## ACCEPTED — cuts (over-engineering)

| # | Cut | Reason |
|---|---|---|
| C1 | **"Strongest obligation" ranking is DELETED from the delta.** | another delegate model's strongest point, and it is a *legal* one: deciding which regime's standard is "strongest" is statutory interpretation. A tool that ranks standards is giving legal advice. The delta **reports divergence**; the advocate ranks it. |
| C2 | **Entry-point plugin registry replaced by a hardcoded mapping of the six first-party packs.** | Third-party packs are rejected scope for v1. A dynamic discovery mechanism for a fixed set of six is indirection without benefit. `draft` and `as_at` survive as pack attributes; only the discovery machinery goes. |
| C3 | **`ruamel.yaml` dropped for stdlib parsing.** | Round-trip fidelity exists to preserve comments on write-back. The tool never writes back — it is explicitly banned from patching the declaration. A heavy dependency for a capability the PRD forbids using. |

## PARTIALLY ACCEPTED

| # | Finding | Ruling |
|---|---|---|
| P1 | The runtime `socket` monkey-patch is fragile and does not stop a C-extension bypassing it. | **Correct that it is not a guarantee; wrong that it should go.** It is retained as a cheap smoke test, and demoted from "proof" to "tripwire" in the wording. The actual assurance moves to **install-time**: a dependency audit asserting no direct or transitive dependency requires network access. Belt and braces, honestly labelled. |

## REJECTED

| # | Finding | Why rejected |
|---|---|---|
| R1 | Cut the DeltaComputer entirely; emit six independent rollups and let a human diff them. | **The cross-regime delta IS the product.** "Compliant under Regulation (EU) 2016/679, exposed under the DPDP Act 2023" is the single thing no incumbent ships and the reason this repo exists. Emitting six disconnected rollups makes it a worse version of tools that already exist. The *ranking* inside the delta is legal interpretation and is cut (C1); the *divergence reporting* is the deliverable and stays. |

## Consequence

`02-ARCHITECTURE.md` is now **superseded on seven points (A1–A7) and three cuts (C1–C3)** by this
section. Where 02 and this section disagree, **this section wins** and 02 must be amended during
the build. `06-FILTER` will sweep for exactly this divergence.
