# 02 — ARCHITECTURE (full record)  ·  Samanvaya Privacy Conformance Tool

**Date:** 2026-08-19 · Long by design. `03-ARCHITECTURE-ESSENTIALS.md` is the version an agent reads every session.

## Tech stack, and why each choice

| layer | choice | why | what it rules out |
|---|---|---|---|
| Language | Python 3.11+ | `dpdp-law-to-code` is Python; the adapter is a thin import, not a foreign-function bridge. Sticking to one runtime eliminates a second compiler/interpreter surface, a second dependency tree, and a second licence-audit surface. The adviser runs `pip install` once. | Any language that would force an FFI to the upstream package (Rust, Go, Node). Any language whose standard library lacks a vetted YAML parser that does not pull in transitive C extensions. |
| Type discipline | `dataclasses(frozen=True)` (stdlib) + `mypy --strict` | Frozen dataclasses make obligation records hashable and immutable — a finding cannot be mutated after the engine emits it. `mypy --strict` catches the class of bug that breaks admissibility of a citation (typo in a regime name, an `Optional` that is silently dereferenced). | Pydantic, attrs, msgspec, beartype. Each adds a runtime dependency and a model philosophy that the upstream package does not share. The shared model must look like the upstream package's model so the adapter is mechanical. |
| Declarative input parsing | `ruamel.yaml` (round-trip) + `json` (stdlib) | Hand-authored input must round-trip: advisers edit, diff, and re-run. `ruamel.yaml` preserves comments and key order so the declaration reads like a document. The pathological case (a trailing comma, a smart quote) fails loudly at parse, not silently at evaluation. | PyYAML's `safe_load` (lossy and uses a C loader that has had CVEs), `pydantic` model parsing (swallows nested errors into one opaque message), schema-first validators (advisers will not write JSON Schema). |
| CLI surface | `argparse` (stdlib), subcommand-per-mode | `argparse` is stdlib, deterministic, and `--help` is the documentation. Subcommands are: `check`, `init`, `validate`, `version`, `cite`. No `click`, no `typer`, no `rich` — colour is a terminal feature, not a textual one. | Any framework that requires runtime introspection of the call site, that injects globals, or that imports a network library on import (the offline test must be a single static check). |
| India engine | `dpdp-law-to-code==<pinned>` consumed via setuptools entry point / direct import | 407 tests already attest the India rail against the statutory text. The adapter imports the upstream `ComplianceResult` and `check_*` functions; it does not monkey-patch, subclass, or shadow them. | Vendoring the upstream code (breaks the MIT licence obligation to preserve the copyright notice and the clean-room posture). Wrapping the upstream CLI in a subprocess (adds a process boundary, loses structured return values, complicates the offline test). |
| Output rendering | Stdout + local file. Markdown for the human artefact; JSON-lines for the machine artefact. | Markdown is the format the adviser reads; JSON-lines is the format a future audit tool can diff. Both are written by the same code path so the human and machine views cannot disagree. | HTML (a browser is a network-adjacent runtime), PDF (requires a renderer with its own CVE history), CSV (loses the nested structure), a templating engine (deterministic output is a requirement, and a templating engine is a place where the wrong thing can be unsaid). |
| Tests | `pytest` (stdlib `unittest` is acceptable) | The upstream package already uses `pytest`; the new test suite plugs in alongside. Property tests for the delta engine use `hypothesis` because the regimes disagree in combinatorially many ways. | Any test runner that requires a daemon, a network round-trip, or a container. |
| Packaging | `pyproject.toml` (PEP 621), `pip install -e .` for dev, `pip install .` for release | The release artefact is a wheel. The development artefact is an editable install. Both are reproducible from the lockfile. | Poetry (its resolver is opinionated and not required); `setup.py` (legacy); Conda (a second package manager that the adviser does not need). |
| Licence | MIT | MIT is compatible with the upstream `dpdp-law-to-code` (MIT). MIT is not copyleft; the tool cannot receive copyleft code. | GPL inbound (would taint the tool). LGPL inbound (would force the tool to ship the source of every dynamically linked LGPL library, which is a documentation burden the adviser does not want). AGPL outbound (would force any network operator of the tool to publish source, which contradicts the offline posture). Closed source (the clean-room posture is the licence's reason for existing). |
| Runtime network posture | Zero. Verified at the syscall level via a `socket` import hook in the test suite. | The PRD is a hard constraint: offline is a requirement, not a preference. The test that fails the build if `socket.socket` is ever instantiated by the tool's own code (excluding the verifier itself) is the architectural enforcement of that constraint. | Any dependency that imports `requests`, `urllib3`, `httpx`, `aiohttp`, `boto3`, `google-cloud-*`, `azure-*`, `kubernetes`, `docker`, `paramiko`, `ldap3`. |

## Components

### 1. CLI driver (`samanvaya.cli`)

- **Responsibility:** Parse argv, locate the declaration file, dispatch to the engine, write the report.
- **Inputs:** `--input <path>`, `--as-at <YYYY-MM-DD>` (optional, default = today), `--format md|jsonl|both`, `--out <path>` (optional, default = current directory), `--regime <list>` (optional, default = all six).
- **Outputs:** Exit code 0 on clean completion (gaps are not errors), exit code 2 on missing/invalid declaration, exit code 3 on `[FACT NEEDED]`, exit code 4 on offline violation detected at runtime. Two local files (or one, depending on `--format`) under `--out`.
- **Who calls it:** The adviser. Nothing else.

### 2. Declaration loader (`samanvaya.declaration`)

- **Responsibility:** Parse YAML or JSON into the `Declaration` model; validate the schema; compute the SHA-256 of the canonicalised form for the report header; reject on any unknown top-level key.
- **Inputs:** Path to a file on the local filesystem.
- **Outputs:** A `Declaration` instance; an `IntegrityError` (subclass of `ValueError`) on bad input.
- **Who calls it:** The CLI driver.

### 3. Jurisdiction resolver (`samanvaya.jurisdiction`)

- **Responsibility:** Expand the declared jurisdictions into the set of (regime, sub_unit) pairs that the engine must evaluate. A declaration that names "United States" without naming states produces (US, `<unspecified>`) and emits a `gap` not a `satisfied`. A declaration that names "California" produces (US, CA) plus the federal sectoral set.
- **Inputs:** A `Declaration.jurisdictions` field.
- **Outputs:** A `JurisdictionTree` — a `dict[regime_id, set[sub_unit_id]]` plus a `completeness` flag per regime.
- **Who calls it:** The engine.

### 4. Regulation pack registry (`samanvaya.packs`)

- **Responsibility:** Discover installed packs, surface their metadata (version, regimes covered, as-at date, completeness flag), refuse to load a pack that is declared `draft: true` for evaluations that require a stable result.
- **Inputs:** Setuptools entry-point group `samanvaya.packs`.
- **Outputs:** A `PackRegistry` mapping regime_id to one or more `PackInfo` records.
- **Who calls it:** The engine.

### 5. Regulation pack (six of them, one per regime)

- **Responsibility:** Translate a `Declaration` and a (regime, sub_unit, as_at) tuple into a list of `Obligation` records; evaluate each; emit findings. Each pack is a separate sub-package shipped as part of the same wheel but addressable by entry point so that, in principle, a third party could publish an independent pack without modifying the core. In v1 the six packs are first-party.
- **Inputs:** `Declaration`, `JurisdictionTree`, `as_at` date.
- **Outputs:** `list[Finding]`.
- **Who calls it:** The engine.

### 6. India adapter (`samanvaya.packs.india.adapter`)

- **Responsibility:** Map `Declaration` into the record types expected by `dpdp-law-to-code`; call the upstream `check_*` functions; map each upstream `ComplianceResult` back into a `Finding` that conforms to the shared obligation model. Idempotent. Read-only against the upstream package.
- **Inputs:** `Declaration`, `as_at` date.
- **Outputs:** `list[Finding]` whose `regime = "IND"`, `sub_unit = None`, `instrument = "Digital Personal Data Protection Act 2023" or "Digital Personal Data Protection Rules 2025"`, `provision` is the section or rule number, and `citation_pointer` is the same pointer the upstream package produces.
- **Who calls it:** The India pack.

### 7. Obligation engine (`samanvaya.engine`)

- **Responsibility:** For each (regime, sub_unit) pair, dispatch to the corresponding pack; collect `Finding` records; compute the per-regime rollup; compute the cross-regime delta; apply the as-at filter against each obligation's `in_force_from` and `in_force_until`.
- **Inputs:** `Declaration`, `JurisdictionTree`, `as_at` date, `PackRegistry`.
- **Outputs:** `EngineResult` carrying per-regime rollups, the cross-regime delta, and the flat list of findings.
- **Who calls it:** The CLI driver.

### 8. Delta computer (`samanvaya.delta`)

- **Responsibility:** Project the obligations down to a comparable key (a `(obligation_topic, sub_topic)` tuple) and across regimes produce a `divergence` record per topic: regimes that impose it, regimes that do not, regimes where the declaration satisfies it, regimes where it is a gap.
- **Inputs:** `list[Finding]`.
- **Outputs:** `list[Divergence]`.
- **Who calls it:** The engine.

### 9. Report renderer (`samanvaya.report`)

- **Responsibility:** Render an `EngineResult` to markdown and/or JSON-lines. Carry the disclaimer on every artefact. Embed the declaration hash and the tool version in the header.
- **Inputs:** `EngineResult`.
- **Outputs:** Two strings (markdown and JSON-lines).
- **Who calls it:** The CLI driver.

### 10. Offline verifier (`samanvaya.offline_check`)

- **Responsibility:** A test-only module imported by the CI test suite that monkey-patches the stdlib `socket` module to refuse any `socket.socket(...)` call originating from the tool's own packages. Also a runtime smoke test that the CLI driver runs as its first action: if any module in the `samanvaya.*` namespace has imported a known-network module, the driver exits with code 4.
- **Inputs:** None at runtime; the dependency graph at module import time.
- **Outputs:** A boolean at runtime; a test failure in CI.
- **Who calls it:** The CLI driver (smoke) and the test suite (enforcement).

### 11. Schema validator (`samanvaya.schema`)

- **Responsibility:** Validate the input declaration against the schema defined by `Declaration` (the dataclass is the schema). Reject unknown keys. Reject values that are not the expected primitive type. Do not validate semantic completeness — that is the engine's job and produces `gap` findings, not parse errors.
- **Inputs:** A parsed YAML/JSON dict.
- **Outputs:** A `Declaration` instance or an `IntegrityError`.
- **Who calls it:** The declaration loader.

## Data models

### `Declaration`

Hand-authored input. Frozen. The fields are the minimum the six regimes need; each field's `Optional[...]` state is itself a finding (an absent `breach_workflow` field is a gap under India, EU, UK, Singapore, Quebec — the engine reports it once per regime, not as a parse error).

| field | type | semantics | why |
|---|---|---|---|
| `schema_version` | `str` | `"1.0"` | Forward compatibility. The loader rejects unknown majors. |
| `organisation` | `Organisation` | The legal person whose obligations are being evaluated. | The tool evaluates one organisation per run. |
| `jurisdictions` | `list[JurisdictionRef]` | The set of (country, sub_unit) pairs the organisation declares itself to operate in. Empty is a parse error; ambiguous is a semantic gap. | Drives the jurisdiction tree. |
| `data_categories` | `list[DataCategory]` | Categories of personal data processed. Each carries an `id` and a `sensitivity` flag. | India's DPDP has no special category; the EU's GDPR does; Singapore's PDPA does not. The sensitivity flag is metadata for the engine; the obligation lives in the pack. |
| `purposes` | `list[Purpose]` | Each purpose has an `id`, a `description`, and a `legal_basis` drawn from a closed enumeration that is per-regime. | The engine does not assume a basis exists in every regime. |
| `recipients` | `list[Recipient]` | Each has a `category` (controller, processor, joint controller, third party) and a `jurisdiction`. | Drives cross-border analysis. |
| `security_safeguards` | `SecuritySafeguards` | Seven booleans/strings, one per India Rule 6(1) item. | The seven minima are the universal backbone of the "protect" pillar across regimes. |
| `consent_mechanism` | `ConsentMechanism` | Describes how consent is obtained, recorded, and withdrawn. | EU, UK, Singapore, Quebec have consent regimes; India has explicit consent; the US is a patchwork. |
| `breach_workflow` | `BreachWorkflow` | Detection, notification clock, regulator, data subjects. | Each regime has a different clock; the engine looks up the clock in the pack. |
| `dsr_workflow` | `DsrWorkflow` | Channels and clocks for data-subject requests. | Regimes disagree on which rights exist and on the clocks. |
| `retention` | `list[RetentionRule]` | Per-purpose retention period and trigger. | India Rule 8, EU storage limitation, Quebec Law 25. |
| `sub_national_units` | `list[SubNationalUnit]` | Explicit state/province names when `country = "US"` or `country = "CA"`. | The jurisdiction tree is built from this. |
| `declaration_author` | `str` | Name and roll of the human who authored the declaration. | The tool is for advisers; the declaration is a human-authored artefact. |

### `Organisation`

| field | type | semantics |
|---|---|---|
| `legal_name` | `str` | The legal person. |
| `legal_form` | `Literal["company","llp","partnership","sole_trader","government","ngo","other"]` | Drives fiduciary/processor classification in some regimes. |
| `incorporation_jurisdiction` | `str` | ISO 3166-1 alpha-2 or sub-national code. |
| `annual_turnover_inr` | `Decimal | None` | India-relevant threshold; the consent-manager net-worth test (Rs. 2 crore) and the Quebec turnover-based penalty both look at financial scale. |
| `employee_count` | `int | None` | Drives some EU/UK controller/processor obligations. |

### `JurisdictionRef`

| field | type | semantics |
|---|---|---|
| `country` | `str` | ISO 3166-1 alpha-2. |
| `sub_unit` | `str | None` | ISO 3166-2 (e.g. `US-CA`, `CA-QC`) or `None`. |
| `role` | `Literal["establishment","targeting","monitoring","other"]` | The GDPR's Article 3 territorial scope vocabulary; reused across regimes. |

### `Obligation` (the central regulation-neutral model)

This is the most important model in the architecture. Every regime compiles down to a list of these. The engine reasons over lists of these. The delta computer keys on `(obligation_topic, sub_topic)`.

| field | type | semantics | why it is needed |
|---|---|---|---|
| `obligation_id` | `str` | Globally unique. Convention: `<regime>:<sub_unit or "FED">:<topic>:<sub_topic>:<ordinal>`. | Stable identity across runs; required for the delta. |
| `regime` | `RegimeId` | One of `IND`, `EU`, `UK`, `US`, `SG`, `CA`. | Routing. |
| `sub_unit` | `str | None` | `None` for non-federations; `US-CA` for California, `CA-QC` for Quebec, etc. | The tree. |
| `instrument` | `str` | The full name of the instrument. Example: `"Regulation (EU) 2016/679"`. Example: `"Digital Personal Data Protection Rules 2025"`. | The citation. |
| `provision` | `str` | The section, article, rule, or schedule number. Example: `"Art. 5(1)(f)"`. Example: `"Rule 6(1)"`. | The citation. |
| `topic` | `ObligationTopic` | A closed enumeration: `LAWFUL_BASIS`, `NOTICE`, `CONSENT`, `RIGHTS_ACCESS`, `RIGHTS_CORRECTION`, `RIGHTS_ERASURE`, `RIGHTS_PORTABILITY`, `RIGHTS_OBJECT`, `RIGHTS_AUTOMATED_DECISION`, `BREACH_NOTIFICATION_AUTHORITY`, `BREACH_NOTIFICATION_SUBJECT`, `SECURITY_SAFEGUARD`, `RETENTION`, `DPIA`, `TRANSFER_INTERNATIONAL`, `DPO`, `RECORDS_OF_PROCESSING`, `CHILDREN`, `VULNERABLE_PERSONS`, `CONSENT_MANAGER`, `SIGNIFICANT_DATA_FIDUCIARY`, `ALGORITHMIC_DUE_DILIGENCE`, `LOCALISATION`, `COOKIES`, `COMPLAINTS`, `OTHER`. | The topic is the row key in the delta. |
| `sub_topic` | `str` | A free-text qualifier within the topic. E.g. `"age_threshold < 18"` under `CHILDREN`. E.g. `"72h"` under `BREACH_NOTIFICATION_AUTHORITY`. | Two regimes can share a topic but disagree on the sub-topic. |
| `obligation_summary` | `str` | One-line human-readable statement of what the obligation requires. | The report row. |
| `in_force_from` | `date | None` | The earliest date on which the obligation is binding. `None` means "in force at the instrument's commencement, looked up in the pack". | The commencement clock. |
| `in_force_until` | `date | None` | The date on which the obligation ceases to be binding (repeal, replacement). `None` means open-ended. | The commencement clock. |
| `declaration_summary` | `str | None` | One-line human-readable statement of what the declaration says about this obligation. | The report row. |
| `result` | `Literal["satisfied","gap","contested","not_applicable","does_not_exist"]` | The engine's verdict. | The empty row. |
| `citation_pointer` | `str` | A pointer the human can verify against the primary source. For India: the same pointer the upstream package emits. For the other regimes: the section number and a short hint to the official source. | The audit trail. |
| `evaluation_metadata` | `dict[str, str]` | Free-form key-value pairs the pack may attach. E.g. `{"deadline_hours": "72"}`, `{"deadline_days": "90"}`. | The pack may need to surface a value the obligation_summary cannot carry. |

The five-value `result` is the critical design. It distinguishes:

- `satisfied` — the declaration meets the obligation.
- `gap` — the obligation exists in this regime, the declaration does not address it.
- `contested` — the obligation exists, the declaration addresses it, but the field is ambiguous or partial and a human must judge.
- `not_applicable` — the obligation exists, but a precondition not met (e.g. the organisation is not a Significant Data Fiduciary, so India's Rule 13 DPIA obligation does not apply).
- `does_not_exist` — the obligation does not exist in this regime. This is the value that lets the delta correctly say "compliant under GDPR, exposed under DPDP" — the GDPR pack does not have a Sensitive Personal Data classification, so it emits `does_not_exist` for the topic, and the delta is informed.

### `Finding`

| field | type | semantics |
|---|---|---|
| `obligation` | `Obligation` | The obligation that was evaluated. |
| `result` | same enum | The verdict. |
| `rationale` | `str` | One or two sentences explaining the verdict. |
| `evidence_paths` | `list[str]` | JSON-pointer-like paths into the declaration that the pack consulted. The adviser can re-check the citation against the declaration. |

### `Divergence` (delta computer output)

| field | type | semantics |
|---|---|---|
| `topic` | `ObligationTopic` | The row. |
| `sub_topic` | `str` | The sub-row. |
| `regimes_with_obligation` | `set[RegimeId]` | The regimes that impose this obligation. |
| `regimes_without_obligation` | `set[RegimeId]` | The regimes that do not. |
| `result_by_regime` | `dict[RegimeId, Literal["satisfied","gap","contested","not_applicable","does_not_exist"]]` | The per-regime verdict. |
| `strongest_obligation` | `str | None` | The `obligation_id` of the regime with the strictest binding version, if a "strictest" notion exists for this topic. |

### `JurisdictionTree`

| field | type | semantics |
|---|---|---|
| `by_regime` | `dict[RegimeId, set[str | None]]` | The set of sub-units per regime. `None` means country-level only. |
| `completeness` | `dict[RegimeId, bool]` | `True` if the sub-unit set is non-empty for federations and there are no `unspecified` placeholders. |
| `unspecified` | `set[RegimeId]` | Regime(s) the declaration named at the country level but not at the sub-unit level. |

### `PackInfo`

| field | type | semantics |
|---|---|---|
| `pack_id` | `str` | Stable identifier (`"samanvaya.packs.india"`). |
| `regime` | `RegimeId` | The regime this pack covers. |
| `version` | `str` | SemVer. |
| `covers_sub_units` | `set[str]` | Sub-units the pack implements. Empty for non-federations. |
| `as_at` | `date` | The last date the pack was reviewed against the primary source. |
| `draft` | `bool` | `True` if the pack is incomplete. The engine refuses to emit a `satisfied` verdict against a draft pack and emits `contested` instead. |
| `obligation_count` | `int` | The number of obligations the pack emits. Sanity-checked against the brief. |

### `EngineResult`

| field | type | semantics |
|---|---|---|
| `declaration_hash` | `str` | SHA-256 of the canonical declaration. |
| `tool_version` | `str` | The version of the tool. |
| `as_at` | `date` | The date the engine evaluated against. |
| `per_regime` | `dict[RegimeId, RegimeRollup]` | Counts and the nested list of findings. |
| `divergences` | `list[Divergence]` | The delta. |
| `disclaimer` | `str` | The fixed string. |

### `RegimeRollup`

| field | type | semantics |
|---|---|---|
| `regime` | `RegimeId` | |
| `sub_units_evaluated` | `set[str]` | |
| `counts` | `dict[str, int]` | Counts per `result` value. |
| `findings` | `list[Finding]` | The nested list. |

### `ComplianceResult` (upstream, from `dpdp-law-to-code`)

Treated as an external type. The adapter reads it; the engine does not import it. Documented here for completeness: per the brief, it carries a statutory citation. The adapter extracts `(instrument, provision, summary, citation_pointer)` and maps the upstream `passed` boolean into the `result` enum (`True` → `satisfied`, `False` → `gap`).

### Value vs reference semantics

All models are frozen dataclasses. They are value types. They are hashed on `(obligation_id, result)` for the engine's own deduplication. They are not stored. The report file is the only persistence. The declaration is read once, parsed once, never written back.

## Data flow

```
                            +-------------------------+
                            |  declaration.yaml       |
                            |  (hand-authored)        |
                            +-----------+-------------+
                                        |
                                        v
                            +-------------------------+
                            |  declaration loader     |
                            |  (parse + validate)     |
                            +-----------+-------------+
                                        |
                                        v
                            +-------------------------+
                            |  Declaration (immutable)|
                            +-----+-------------+-----+
                                  |             |
                                  v             v
                  +-----------------------+   +-----------------------+
                  | jurisdiction resolver |   | offline smoke check   |
                  +-----------+-----------+   +-----------------------+
                              |
                              v
                  +-----------------------+
                  | JurisdictionTree      |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | pack registry         |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | obligation engine     |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | pack.india            |  pack.eu  pack.uk  pack.us  pack.sg  pack.ca
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | India adapter         |---> dpdp-law-to-code (pinned)
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | list[Finding]         |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | delta computer        |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | EngineResult          |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | report renderer       |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  | report.md + report.jsonl|
                  | (local file)          |
                  +-----------------------+
```

The engine never reads the declaration after the loader returns. The packs never read the declaration directly; they receive it as an argument. The India adapter is the only module that talks to the upstream package. The renderer is the only module that writes to disk.

## Boundaries and seams

### Seam 1: the declaration boundary

The Declaration type is the boundary between the human-authored world and the engine. The loader is the only validator. The engine treats any Declaration instance as well-formed. A change to the declaration schema is a major version bump and a new entry in the changelog.

### Seam 2: the pack boundary

A pack is a Python package that exposes a single entry point: `evaluate(declaration: Declaration, as_at: date, sub_unit: str | None) -> list[Finding]`. The engine does not import the pack's internals. The pack returns the shared `Obligation` model. This is the boundary that allows a new regime to be added without touching the core and without the core learning the regime's vocabulary.

### Seam 3: the adapter boundary

The India adapter is the only module that imports `dpdp_law_to_code`. If the upstream package's API changes, only the adapter changes. The engine and the rest of the project continue to use the shared `Obligation` model.

### Seam 4: the renderer boundary

The renderer takes an `EngineResult` and produces two strings. Nothing else writes to disk. A change to the output format is a renderer-only change.

### Seam 5: the offline boundary

The offline verifier is a seam. It is a test that imports the tool's modules and asserts that no module in the `samanvaya.*` namespace has imported a forbidden module. The forbidden list is hard-coded: `socket`, `urllib`, `urllib3`, `requests`, `httpx`, `aiohttp`, `boto3`, `google.cloud`, `azure`, `kubernetes`, `docker`, `paramiko`, `ldap3`, `dns`, `nmap`. The smoke test at CLI startup re-checks this against the imported modules.

### Seam 6: the time boundary

The `as_at` parameter is the only place where a date enters the engine. The engine does not call `datetime.date.today()` anywhere. The packs read `as_at` and apply it to the obligation's `in_force_from` and `in_force_until`. The CLI defaults `as_at` to today but the adviser can override it. Without this seam, the commencement clock could not be tested deterministically.

### Seam 7: the test boundary

The upstream package's 407 tests stay upstream. The new project's test suite does not import the upstream package's tests. The adapter has its own tests that pin the upstream `ComplianceResult` shape against the shared `Obligation` model. The two test suites run independently and attest to different contracts.

## Failure modes considered

| # | failure | detection | mitigation |
|---|---|---|---|
| 1 | Declaration is incomplete (missing fields, empty jurisdictions, no `declaration_author`). | The loader raises `IntegrityError` at parse. The CLI exits with code 2. | The report still carries the disclaimer. The adviser sees a clear list of missing fields. The engine does not silently fill defaults. |
| 2 | Declaration names "United States" without states. | The jurisdiction resolver sets `completeness["US"] = False` and adds `unspecified = {"US"}`. The engine emits a `gap` finding per US obligation with topic `OTHER` and rationale `"Sub-national units not specified."` | The report cannot be interpreted as "the declaration has no US gaps". It can only be interpreted as "the declaration has not yet named its US footprint". |
| 3 | Declaration names "California" but not the federal sectoral layer. | The jurisdiction resolver adds the federal sectoral set to `by_regime["US"]` whenever `sub_unit` includes any US state. The engine evaluates HIPAA / GLBA / COPPA / FERPA only if the declaration carries the relevant `data_categories`. | Sub-national law is binding; the tool does not silently drop it. |
| 4 | Regime pack is out of date against an amendment. | The pack's `as_at` is compared to the current date by the engine. If the difference exceeds the configurable `staleness_threshold_days`, the engine emits a `contested` finding per obligation in the pack with rationale `"Pack is N days past its declared as_at date."` | The adviser is told that the verdict is based on a stale read. The pack's `as_at` is updated by a human review, not by the tool. |
| 5 | User asks for a regime with no pack installed. | The registry returns no `PackInfo`. The engine emits a `gap` finding with topic `OTHER` and rationale `"No pack installed for regime <ID>."` | The tool never silently claims coverage it does not have. |
| 6 | A pack is marked `draft: true`. | The engine refuses to emit `satisfied` for any obligation in that pack; it emits `contested` and the rationale says the pack is draft. | The pack remains visible but its verdicts are not admissible as `satisfied`. |
| 7 | Conflicting obligations across regimes. | The delta computer emits a `Divergence` per topic. The report shows the per-regime verdict side by side. | The tool does not adjudicate. The adviser reads the disagreement. |
| 8 | The upstream `dpdp-law-to-code` changes its `ComplianceResult` shape. | The adapter's tests pin the expected shape. CI fails on any drift. | The adapter is updated; the engine is not. |
| 9 | The upstream `dpdp-law-to-code` is unpublished or unavailable. | The CLI emits a clear error: "Cannot import dpdp_law_to_code. Install with `pip install dpdp-law-to-code==<pinned>`." | The tool does not silently fall back to a re-implementation. (Reimplementing the India rail is banned scope.) |
| 10 | A declaration contains a live credential by mistake. | The schema validator runs a heuristic: any string matching the regexes for AWS access keys, Azure client secrets, GCP service account JSON keys, private-key PEM blocks, or `postgres://`/`mysql://` URIs causes the loader to raise `IntegrityError` with the message "Suspected credential; the declaration must be hand-authored and contain no live credentials." | The tool rejects the input. The adviser edits the declaration. |
| 11 | A declaration names a regulated activity that the tool does not cover. | The pack emits `does_not_exist` for the topic. The delta reports the topic with no regimes imposing it. | The tool does not bluff. |
| 12 | The `--as-at` date is before the instrument's commencement. | The engine filters obligations by `in_force_from`. Obligations not yet in force are emitted with `result = "not_applicable"` (or a new value `"not_yet_in_force"` carried under `evaluation_metadata` and surfaced as a distinct row). | The report can answer both "am I compliant today" and "what bites on 14 May 2027". |
| 13 | The report file already exists at `--out`. | The CLI overwrites by default and refuses with a `--no-clobber` flag. | The adviser chooses. |
| 14 | Theodemarch be damned: the tool is asked to send its output somewhere. | The CLI has no `--send` flag. The output is written to a local path. The renderer does not call any network primitive. The offline verifier confirms this. | The PRD-load-bearing constraint is enforced at the architecture level, not at the policy level. |
| 15 | The architecture seems to need a database connector. | **Out of scope.** This is a banned-scope item and is listed here explicitly: the architecture does not include a database connector. If a future requirement seems to need one, the right answer is to re-model the declaration, not to add the connector. | The architecture's response to "I need to read the client's database" is "add the answer to the declaration and re-run". |
| 16 | The architecture seems to need an LLM to interpret a statute. | **Out of scope.** The conformance path is deterministic. The packs encode obligations as data. If an obligation cannot be encoded as data, the tool emits `[FACT NEEDED: <question>]` and stops, rather than calling an LLM. | The PRD-load-bearing constraint. |
| 17 | The architecture seems to need to scrape the statute at runtime. | **Out of scope.** Statute text is referenced by citation, not loaded at runtime. The packs carry the obligations as static data, reviewed by a human against the primary source. | Offline. |
| 18 | The architecture seems to need a plugin system that loads arbitrary Python from a user-supplied path. | **Out of scope.** The pack boundary is an entry-point, not a runtime import. Entry points are installed packages; the user cannot point the tool at a `.py` file and have it evaluated. | The clean-room posture. |
| 19 | The architecture seems to need to remember the input between runs. | **Out of scope.** No caching. No history. No analytics. The report file is the only artefact. | The no-storage-of-client-data constraint. |
| 20 | The architecture seems to need a hosted web UI. | **Out of scope.** v1 is CLI. The renderer writes a local file. | The no-web-UI constraint. |

## The Obligation Model — detailed

The five-value `result` enum is the most consequential design decision in the architecture. The alternatives are:

- **Two values** (`satisfied`, `gap`): loses the `does_not_exist` distinction, which is the delta's signal that "this regime does not impose this obligation" rather than "this regime imposes it and you have a gap".
- **Three values** (`satisfied`, `gap`, `not_applicable`): collapses `does_not_exist` into `not_applicable`, which is wrong. `not_applicable` means the obligation exists but a precondition is not met (e.g. not a Significant Data Fiduciary). `does_not_exist` means the regime does not have the obligation at all. The delta needs both.
- **Four values** (`satisfied`, `gap`, `not_applicable`, `contested`): drops `does_not_exist`. The delta is then ambiguous: is the absence of an obligation row because the regime does not have it, or because the pack forgot to emit it? The five-value enum resolves the ambiguity by requiring the pack to explicitly emit `does_not_exist` for every topic the pack has decided the regime does not cover.

The pack is responsible for emitting `does_not_exist` for every topic in the closed `ObligationTopic` enumeration that the regime does not impose. This is the discipline that makes the delta correct. A pack that omits an obligation row commits a false negative that the delta cannot detect. The pack's own test suite is the enforcement: it asserts that every pack emits exactly one row per topic per regime (modulo `in_force_until` semantics).

The `obligation_id` is the second-most consequential decision. It is the join key between the engine's output and the delta. It must be stable across runs. The convention is enforced: `<regime>:<sub_unit or "FED">:<topic>:<sub_topic>:<ordinal>`. The `ordinal` is a pack-local counter to disambiguate when the same regime imposes the same topic on the same sub-unit twice (e.g. two breach-notification obligations with different clocks — but the brief only gives India `Rule 7(2)` at 72 hours, so this is a future-proofing measure for the other regimes).

The `sub_topic` field is the third-most consequential decision. It is the field that lets `CHILDREN` survive across regimes that disagree on the age threshold. The engine never needs to know what any threshold *is*; the pack emits one `Obligation` per `(topic, sub_topic)` pair and the delta reports the divergence between them. The `sub_topic` is an opaque string of the form `"age_threshold_<N>"`.

**The thresholds themselves are NOT settled here and MUST NOT be hard-coded from memory.** India is the only one carried by the Verified Facts Brief: the DPDP Act 2023 treats a child as a person **under 18**, with verifiable parental consent, no tracking and no targeted advertising (Rules 10 and 12 govern verifiable consent and exemptions). Every other regime's threshold is an open constant:

- [FACT NEEDED: the age threshold under Regulation (EU) 2016/679 and the extent of member-State derogation, read from the Regulation text.]
- [FACT NEEDED: the age threshold(s) applicable under the US federal sectoral layer and under each covered US State statute, read from each instrument.]
- [FACT NEEDED: the age threshold applicable under Singapore's Personal Data Protection Act 2012, read from the Act and any binding advisory guidelines.]
- [FACT NEEDED: the age threshold applicable under PIPEDA and under Quebec Law 25, read from each instrument.]

Each pack supplies its own threshold from its own primary-source review and records the citation on the obligation. A pack that cannot source its threshold emits `[FACT NEEDED]` and is marked `draft`, so the tool never claims coverage it does not have.

## Jurisdiction as a tree — detailed

The `JurisdictionTree` is a `dict[regime, set[sub_unit | None]]`. For non-federations (EU, UK, Singapore, India), the set is `{None}` — the regime is one node. For the US, the set is the union of the declaration's named states plus `None` for the federal sectoral layer. For Canada, the set is the declaration's named provinces plus `None` for the federal PIPEDA layer.

When the declaration names a country but no sub-units, the engine does not silently treat the country as one node. It emits a `gap` with topic `OTHER` and rationale `"Sub-national units not specified for <country>."`. The `completeness` flag is `False`. The pack still evaluates the federal layer if the architecture defines one (US: HIPAA/GLBA/COPPA/FERPA; Canada: PIPEDA).

Overlapping obligations (federal sectoral + state) are merged into the same `regime` (`US`). A California healthcare provider is subject to both CCPA/CPRA and HIPAA. The pack emits obligations under both. The `sub_unit` field of the obligation is `US-CA` for the California obligation and `None` (or a sentinel like `"FED"`) for the HIPAA obligation. The engine does not double-count: the per-regime rollup counts each obligation once, and the divergence report keys on `(topic, sub_topic, sub_unit)` to surface the per-layer view.

## Regulation packs — detailed

A pack is a Python package that exposes a single entry point. The entry-point group is `samanvaya.packs`. The entry point's name is the regime ID. The entry point's value is the qualified name of the `evaluate` function. The `pyproject.toml` declares the six first-party packs:

```
[project.entry-points.samanvaya.packs]
IND = "samanvaya.packs.india:evaluate"
EU = "samanvaya.packs.eu:evaluate"
UK = "samanvaya.packs.uk:evaluate"
US = "samanvaya.packs.us:evaluate"
SG = "samanvaya.packs.sg:evaluate"
CA = "samanvaya.packs.ca:evaluate"
```

Each pack is independently versioned. The pack's `version` is hard-coded in its `__init__.py` and exposed via `PackInfo`. The engine does not infer versions from the wheel; the pack declares its own version because the obligation is the unit of versioning, not the wheel.

Each pack is independently citable. The `obligation.citation_pointer` is the pointer the adviser verifies against the primary source. The pack's `as_at` is the date the pack was last reviewed. The pack's `draft` flag is the visibility knob.

A new pack can be added without touching the core. A third party can publish a wheel that declares the same entry-point group, install it alongside the core, and the registry will discover it. The third party is responsible for the obligation data; the core remains unchanged.

A draft pack is never silent. The engine refuses to emit `satisfied` against a draft pack. The report carries the `draft` flag visibly. The adviser knows the pack is unfinished.

## The commencement clock — detailed

Each `Obligation` carries `in_force_from` and `in_force_until`. The engine evaluates against an `as_at` date. The evaluation is:

- If `in_force_from` is `None`, look up the instrument's commencement in the pack's instrument table.
- If `as_at < in_force_from`, the obligation is not yet binding. Emit `result = "not_applicable"` and add `evaluation_metadata["in_force_from"] = <date>` so the report carries the future date.
- If `in_force_until` is not `None` and `as_at > in_force_until`, the obligation is no longer binding. Same treatment.
- Otherwise, evaluate normally.

For India, the pack's instrument table records:

- `Digital Personal Data Protection Act 2023` — in force on the date of its commencement notification [FACT NEEDED: exact commencement date of the Act 2023 itself, separately from the Rules].
- `Digital Personal Data Protection Rules 2025` — Rules 1, 2, 17–21 in force on 13 November 2025 (publication); Rule 4 in force on 13 November 2026 (one year after publication); Rules 3, 5–16, 22, 23 in force on 13 May 2027 (eighteen months after publication).

For the UK, the pack's instrument table records the Data (Use and Access) Act 2025 in-force schedule: core changes in force 5 February 2026; phased from June 2025 to June 2026. The pack emits obligations with `in_force_from` set to the actual commencement date of each provision, not to the Royal Assent date (19 June 2025).

For the EU, the GDPR's commencement is fixed (25 May 2018). The pack emits all obligations with `in_force_from = 2018-05-25`.

For the US, each state statute has its own effective date. The pack emits one obligation per (statute, section) with `in_force_from` set to the statute's effective date. The federal sectoral layer has its own dates.

For Singapore, the PDPA 2012 has its original commencement; the 2020 amendment has its own commencement dates. The pack emits obligations with the correct date per provision.

For Canada, PIPEDA's commencement is fixed. Quebec Law 25 has its phased in-force schedule across 2022, 2023, and 2024; the 2026 amendments raise the penalty and require a PIA for every international transfer [FACT NEEDED: exact in-force dates of the 2026 Quebec Law 25 amendments, beyond the brief's statement that the 2026 amendments raised the maximum administrative monetary penalty to the greater of 4% of worldwide turnover or CAD 25 million and now require a documented privacy impact assessment for every transfer of personal information outside Quebec].

## The delta engine — detailed

The delta computer receives the flat list of `Finding`s from the engine. It groups them by `(topic, sub_topic)`. For each group, it produces a `Divergence` carrying:

- `regimes_with_obligation`: the regimes that emitted a row with `result != "does_not_exist"` and the obligation is in force at `as_at`.
- `regimes_without_obligation`: the regimes that emitted `does_not_exist`.
- `result_by_regime`: the per-regime verdict.
- `strongest_obligation`: the obligation whose `evaluation_metadata` most strictly binds the topic. The "strictest" algorithm is topic-specific and lives in the delta computer. For `BREACH_NOTIFICATION_AUTHORITY`, "strictest" is the shortest clock. For `RETENTION`, "strictest" is the shortest retention period. For `CHILDREN`, "strictest" is the highest age threshold. The algorithm is documented per topic in the delta module's docstring; the test suite pins the algorithm against known fixture divergences.

The delta is the artefact that answers the adviser's question: "where does the highest binding standard come from, and where does my declaration fall short of it?" The adviser drafts the memo around the delta. The per-regime rollup is secondary; the delta is the primary output for cross-regime reasoning.

## How `dpdp-law-to-code` is consumed

The India adapter is a single module. It imports the upstream package's `check_*` functions and the `ComplianceResult` type. It does not read the upstream source code. It does not vendor the upstream source code. It does not call the upstream CLI; it calls the upstream functions directly.

The adapter maps the upstream `ComplianceResult` to the shared `Obligation` model:

| upstream field | shared `Obligation` field |
|---|---|
| `section` or `rule` (whichever the upstream package uses) | `provision` |
| `instrument` (the upstream package's string) | `instrument` |
| `summary` (the upstream package's string) | `obligation_summary` |
| `passed` (boolean) | `result` (`True` → `satisfied`, `False` → `gap`) |
| `citation` (the upstream package's pointer) | `citation_pointer` |
| (derived from the called function's name) | `obligation_id`, `topic`, `sub_topic` |

The mapping table is the only place where the upstream vocabulary is translated to the shared vocabulary. The mapping is verified by the adapter's tests, which pin the upstream `ComplianceResult` shape against the shared `Obligation` shape. When the upstream package releases a new version, the adapter's tests run against the new version in CI; if the shape drifts, CI fails.

The adapter does not modify the upstream package. It does not patch the upstream package. It does not subclass the upstream `ComplianceResult`. It consumes the upstream package as a library. The upstream package's 407 tests stay upstream.

If the upstream package is unavailable, the tool fails with a clear error and does not silently fall back. Reimplementing the India rail is banned scope.

## Rejected designs

### Rejected 1: One repo per regime.

**Why rejected:** Six repos means six issue trackers, six licences, six CI pipelines, six release cadences. The adviser installs one tool, not six. The cross-regime delta is a single artefact produced by one engine, not a hand-stitched aggregation of six independent reports. The shared model is the architectural asset; six repos would fragment it. The PRD's "one tool" intent is not negotiable.

### Rejected 2: A single flat rules file (a YAML or JSON file with every obligation per regime).

**Why rejected:** The number of obligations is in the low hundreds across six regimes. A flat file is unreadable, un-diffable, and unreviewable. The obligation data is per-regime Python code that is linted, typed, and unit-tested. The India rail already exists as code, not as data; the adapter must consume it, not bypass it. A flat file would also force the engine to know the per-regime vocabulary, which is the opposite of the shared obligation model.

### Rejected 3: Storing statute text in the repo.

**Why rejected:** Statute text is enormous. The EU's GDPR is ~90 pages; the US state statutes together are thousands of pages. Storing the text in the repo would (a) bloat the wheel, (b) make the licence review harder (the text is government copyright in some jurisdictions and CC0 in others, and the licence review is per-jurisdiction), (c) make the reports cite the text rather than the primary source, which is what the adviser verifies against. The PRD-load-bearing constraint is "every citation must trace to a named instrument and provision"; the tool does not need to carry the text to honour that constraint. The text is referenced by citation and verified by the adviser against the primary source.

### Rejected 4: An LLM deciding conformance at runtime.

**Why rejected:** Determinism is a requirement. An LLM is non-deterministic. An LLM is also a third-party system that receives the declaration (which contains client personal data) over the network, which contradicts the offline constraint. An LLM is also a system that makes a confident wrong answer look indistinguishable from a correct one, which is the worst possible failure mode for a legal-output tool. The PRD says `[FACT NEEDED: <question>]` rather than guess, and the architecture gives the same instruction to the engine. An LLM is the universal `guess`.

### Rejected 5: A plugin system that loads arbitrary Python from a user-supplied path.

**Why rejected:** The clean-room posture. The packs are first-party code in the wheel. The engine verifies the pack's entry point against the registry. A plugin loader that `importlib`s an arbitrary path would let the user point the tool at a copy of Fides, which is Apache-2.0 and permitted to read in isolation, but a copy of Privado, which is LGPL-3.0 and would taint the licence. The plugin path would also be a vector for runtime code execution from an untrusted source, which is a different threat model from "the adviser installs the tool from PyPI". Entry points are installed packages; the user cannot drop a `.py` into a folder and have it evaluated.

### Rejected 6: A web UI in v1.

**Why rejected:** Banned scope. The architecture does not include a web framework; the renderer writes markdown and JSON-lines to a local file. The adviser opens the markdown in their editor.

### Rejected 7: A hosted backend.

**Why rejected:** Banned scope. The architecture runs on the adviser's machine. There is no server. There is no database. There is no multi-tenant routing. The only process is the CLI invocation.

### Rejected 8: Treating the engine as a stateful service.

**Why rejected:** The engine is a function. It takes a Declaration and a date and returns an EngineResult. It does not have a database. It does not have a session. It does not have a cache. The CLI invokes it once per run; the process exits. This is the architectural form of "no storage of client personal data".

### Rejected 9: Reading the declaration from stdin.

**Why rejected:** The declaration is a file the adviser edits, diffs, and re-runs. Stdin is for one-shot inputs. The architecture expects the declaration to be a file the adviser can review before invoking the tool. The CLI accepts `--input <path>` only.

### Rejected 10: A separate Python package per pack.

**Why rejected:** Six packages means six wheels means six releases for every coordinated change. The packs are first-party and ship in one wheel. The entry-point mechanism is the seam that allows a future third-party pack to be installed alongside, but the first-party packs are not separately distributed. This decision is reversible: if a third-party pack ecosystem emerges, the first-party packs can be split into separate wheels without breaking the engine.

### Rejected 11: A rule engine (Drools, CLIPS, jsonLogic, etc.).

**Why rejected:** The obligation model is data, not a rule program. The engine is a dispatcher, not an inference engine. The packs produce obligations; the engine aggregates them; the delta computes divergences. A rule engine would add a DSL, a parser, a runtime, and a debugging surface for a job that the dataclass model already does.

### Rejected 12: A persistent findings store across runs.

**Why rejected:** The no-storage-of-client-data constraint. The report file is the artefact. The next run is a fresh process. There is no "history" feature.

### Rejected 13: Auto-remediation.

**Why rejected:** Banned scope. The engine reports; the adviser remediates. The architecture has no `--fix` mode, no boilerplate-suggestion mode, no `best-effort fill` mode. Gaps are gaps; the adviser writes the memo.

### Rejected 14: A scanner module.

**Why rejected:** Banned scope. The architecture does not include a network scanner, a port scanner, a web crawler, a sitemap parser, a headless browser, or any other discovery primitive. The declaration is the input.

### Rejected 15: Implementation of security controls.

**Why rejected:** Banned scope. The tool checks whether the seven Rule 6(1) minima are declared. It does not generate encryption code, configure KMS, write IAM policies, or run a vulnerability scan. The architecture does not include a code-generation module.

### Rejected 16: Reimplementation of the India rail.

**Why rejected:** Banned scope. The upstream package has 407 tests. Reimplementing forks correctness. The adapter consumes the upstream package; the engine does not know the India rail exists except as a pack.

### Rejected 17: Treating the United States as one regime.

**Why rejected:** Banned scope. The United States is a tree. The pack emits obligations per state and per federal sectoral statute. A declaration that names "United States" without states produces a gap, not a satisfied.

### Rejected 18: Treating Canada as one regime.

**Why rejected:** Banned scope. Canada is a tree. The pack emits obligations under PIPEDA (federal) and under Quebec Law 25 (when the declaration names Quebec). The pack also emits obligations under the other provincial regimes as the tool's coverage is extended [FACT NEEDED: list of other Canadian provincial privacy statutes with personal-information protection regimes comparable to Quebec Law 25 — the brief names only Quebec Law 25 explicitly; the tool must declare what it does and does not cover for the other provinces].

### Rejected 19: Using the names "US GDPR", "Singapore GDPR", or "Canada GDPR".

**Why rejected:** The names do not correspond to any instrument. The architecture uses the correct names everywhere: General Data Protection Regulation for the EU, UK GDPR (as amended by the Data (Use and Access) Act 2025) for the UK, the named state and federal statutes for the US, Personal Data Protection Act 2012 for Singapore, and PIPEDA / Quebec Law 25 for Canada.

### Rejected 20: Reading the declaration's contents after the engine has returned.

**Why rejected:** The engine holds the Declaration in memory only for the duration of the run. The renderer does not read the Declaration; it reads the EngineResult. The report file is the only persistence. The Declaration is garbage-collected when the process exits.

---

## Outstanding facts needed

The following items are required from the Verified Facts Brief or from a subsequent primary-source review before the corresponding obligation can be emitted by the pack. The architecture supports this by emitting `[FACT NEEDED: <question>]` and continuing rather than guessing.

- [FACT NEEDED: exact commencement date of the Digital Personal Data Protection Act 2023 itself, separate from the commencement of the Rules 2025. The brief gives the Rules' phased commencement; the Act's commencement is a separate notification.]
- [FACT NEEDED: exact in-force dates of the 2026 amendments to Quebec Law 25. The brief states the substantive effect (penalty raised to greater of 4% of worldwide turnover or CAD 25 million; PIA required for every international transfer) but does not give the in-force date.]
- [FACT NEEDED: list of Canadian provincial privacy statutes with personal-information protection regimes comparable to Quebec Law 25. The brief names only Quebec Law 25. The CA pack must declare what it covers and what it does not.]
- [FACT NEEDED: full list of US state comprehensive privacy statutes in effect during 2026 with their effective dates. The brief lists 20 states; the number is contested across sources (20 at start of 2026, 23–24 after a mid-2026 legislative wave). The US pack must declare which states it covers and as of what date.]
- [FACT NEEDED: exact in-force schedule of the Data (Use and Access) Act 2025 provisions beyond the brief's statement that the core changes are in force 5 February 2026 and the phasing runs June 2025 to June 2026. The UK pack must enumerate the provisions.]
- [FACT NEEDED: Singapore PDPA 2020 amendment effective date. The brief states the amendment added the Data Breach Notification Obligation and raised the maximum financial penalty to SGD 1 million or 10% of annual turnover in Singapore where turnover exceeds SGD 10 million, but does not give the effective date.]
- [FACT NEEDED: HIPAA, GLBA, COPPA, FERPA effective dates and the exact sections that impose obligations on the categories of data the declaration carries. The brief names the statutes but does not enumerate the provisions.]
- [FACT NEEDED: DPDP Rules 10, 11, 12 verifiable-consent thresholds. The brief refers to "verifiable consent for a child" and "for a person with disability" but does not give the age or disability definitions beyond India's DPDP Act 2023 section 2(1)(t) on children (which the brief does not enumerate). The India adapter must consume these from the upstream package or from the brief; the engine does not need to know them.]

The architecture treats these as gaps, not as guesses. The pack emits `does_not_exist` for the topic until the fact is supplied, and the report carries the `[FACT NEEDED]` line so the adviser sees the open question.