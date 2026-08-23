```markdown
# BMAD-SPEC — Samanvaya Privacy Conformance Tool

**Date:** 2026-08-19
**Owner:** the maintainer
**Builder:** TBD
**Domain agent (if any):** none

## B — BUILD

### Problem
A solo data-protection adviser in India today must read six statutory regimes (DPDP Act 2023 + DPDP Rules 2025; Regulation (EU) 2016/679; UK GDPR as retained and amended by the Data (Use and Access) Act 2025; ~20 US state comprehensive statutes plus HIPAA/GLBA/COPPA/FERPA; Singapore PDPA 2012 as amended 2020; PIPEDA + Quebec Law 25) and, against a single client's self-declared dossier, issue a conformance memo. The existing rail (`dpdp-law-to-code`, 407 tests) covers India only. The adviser cross-references the other five regimes by hand, misses sub-national obligations (CCPA/CPRA, Quebec Law 25), and bills the client for memory plus reading time. The observed failure mode is false negatives: a client passes on a US-only review with no state enumeration, then is exposed under CCPA or Colorado CPA, and the adviser carries the indemnity.

### Solution shape
One offline CLI reads one hand-authored JSON or YAML declaration and, against the six regimes, emits a local Markdown + JSON-lines report in which every finding carries a named instrument, a provision, an obligation summary, a declaration summary, a result (`satisfied` | `gap` | `contested` | `not_applicable` | `does_not_exist`), and a citation pointer. India findings are sourced verbatim from `dpdp-law-to-code`'s `ComplianceResult` via an adapter that runs a contract check on load. The US and Canada are enforced as jurisdictional trees; a declaration naming "US" without sub-units, with `sub_units_complete: false`, yields a single incompleteness notice per country, not per obligation. The delta layer reports divergences across regimes; the advocate ranks them.

### Inputs
- Declaration file: local path · JSON or YAML · one per organisation, hand-authored.
- `dpdp-law-to-code==<pinned>`: PyPI / git install as a library, pinned at install time; upgrade is manual.
- Statute text: cited by reference, not loaded at runtime; offline.
- CLI flags: `--as-at YYYY-MM-DD`, `--regime <id>` (repeatable), `--out <path>`, `--format md|jsonl|both` (default both), `--draft` (declares a draft pack).

### Outputs
- Report file (local): Markdown + JSON-lines from one `EngineResult`. Header carries disclaimer, date, `declaration_hash`, tool version. Per-finding records: `regime`, `sub_unit`, `instrument`, `provision`, `topic`, `sub_topic` (structured `(dimension, value, unit)`), `obligation_summary`, `declaration_summary`, `result`, `citation_pointer`, `evaluation_metadata`, `evidence_paths`. Per-regime rollup: counts of each result. Consolidated report: all rollups + divergences + header.
- Findings to stdout: only on explicit `--stdout`; default is file-only.
- India findings: bit-identical to upstream `ComplianceResult` records; cross-attested by the upstream test suite.

### Components
- CLI: `argparse`; subcommands `check`, `init`, `validate`, `version`, `cite`.
- Loader: JSON or YAML (stdlib `json` + `yaml.safe_load`; `ruamel.yaml` CUT per C3).
- Schema: validates structure; rejects unknown keys; type-checks via frozen dataclasses.
- Jurisdiction resolver: expands country → sub-national tree; honours `sub_units_complete: bool`.
- Pack registry: hardcoded mapping of six first-party packs (C2); no plugin discovery.
- Engine: dispatches packs, applies `as_at`, builds rollups, runs delta.
- India adapter: contract check on load (A7); maps `ComplianceResult` variants to the shared enum; runs through a deterministic `as_at` compatibility boundary.
- Delta: reports divergences only (C1); grouping key `(regime, sub_unit, instrument, topic, dimension)` (A2); groups on `dimension` (A1).
- Report: Markdown + JSON-lines from one `EngineResult`; fixed disclaimer string.
- Offline check: install-time dependency audit belt + runtime `socket` monkey-patch tripwire (P1).

### Banned scope
No database connectors, credentials, scanning, discovery, control implementation, legal advice, hosted SaaS, web UI, client data persistence, copying of other privacy tools' source code, invention of statutory references, auto-remediation, ingestion of client operational artefacts, reimplementation of India rail, jurisdiction flattening, misnaming of instruments, auto-publication of output. (Per PRD §"What it must NOT do".)

### v1 ships (numbered)
1. Declaration schema (JSON + YAML).
2. Six-pack hardcoded registry (India, EU GDPR, UK GDPR, US state + federal sectoral, Singapore PDPA, Canada PIPEDA + Quebec Law 25).
3. India adapter consuming `dpdp-law-to-code` unmodified.
4. Jurisdiction tree for US and Canada with `sub_units_complete` flag.
5. Obligation evaluation with `applies_if` predicates (A4), `required_value` on safeguards (A5), `depends_on` topological order (A6), structured `sub_topic` (A1), `instrument` in grouping key (A2).
6. Delta divergence reporting (no ranking; C1).
7. Markdown + JSON-lines report from one `EngineResult`; fixed disclaimer.
8. Offline check: install-time dependency audit + runtime `socket` tripwire (P1).
9. `--as-at` date control with past/future/commencement handling.
10. CLI subcommands `check`, `init`, `validate`, `version`, `cite`.

### v1 deferred
Web UI, hosted backend, multi-tenant SaaS, client data persistence, third-party pack plugins, rule-engine DSL, LLM-based citation fallback, auto-remediation, security-control scanning, cross-run history DB, separate wheels per regime.

### Build order (each step MUST precede the next)
1. **Declaration schema + frozen dataclasses.** Every subsequent component types against this; building packs first would type-check against guesses.
2. **Jurisdiction resolver (US + Canada trees, `sub_units_complete`).** Packs and the engine cannot decide which sub-units to evaluate without it; A3 is a no-op without this.
3. **Pack contract + shared `Obligation` / `Finding` types** with `applies_if` (A4), `required_value` (A5), `depends_on` (A6), structured `sub_topic` (A1), `instrument` key (A2). The delta depends on the structured `sub_topic` and the `instrument` key being on the wire from day one.
4. **India pack + adapter.** The **only** rail with a verified constant set and an existing tested engine. Comes first because it is the correctness anchor (407 upstream tests) and because the adapter's contract check (A7) sets the pattern for the other five.
5. **EU GDPR pack.** Has the cleanest treaty-instrument structure and the most cited secondary literature; establishes the pattern that US federal sectoral and Singapore will follow.
6. **UK GDPR pack.** Structurally similar to EU GDPR but with the Data (Use and Access) Act 2025 amendments; surfaces the dependency-of-amendments problem that A6 exists to solve.
7. **Singapore PDPA pack.** Non-EU, non-US, single-instrument; exercises the `does_not_exist` path.
8. **US pack (federal sectoral + ~20 states + tree).** Largest scope; tree semantics + federal sectoral applicability + `sub_units_complete` interaction (A3) makes it the riskiest. Built last among the first-party packs because it depends on the jurisdiction tree resolver and the full pack contract.
9. **Canada pack (PIPEDA + Quebec Law 25).** Tree semantics; Quebec Law 25 is sub-national.
10. **Delta divergence layer.** No "strongest" ranking (C1).
11. **Markdown + JSON-lines renderer from one `EngineResult`.**
12. **Offline tripwire + install-time dependency audit** (P1).
13. **CLI dispatch + ship-gate sweep.**

### Test strategy per component (what each test must PROVE)
- **Schema:** rejects unknown keys; rejects malformed JSON/YAML; round-trips a canonical declaration losslessly under stdlib YAML.
- **Jurisdiction resolver:** US "with states X,Y" expands to (US, X), (US, Y); US without states with `sub_units_complete: false` emits ONE incompleteness notice; `sub_units_complete: true` yields `does_not_exist` for absent states; Canada province without Quebec still runs PIPEDA, never Quebec Law 25 unless Quebec is declared.
- **Pack contract:** every finding carries `regime`, `instrument`, `provision`; a draft pack emitting `satisfied` fails the test; an obligation with `in_force_until < as_at` is not emitted as `satisfied`; missing `required_value` does not cause a false gap; present `required_value` mismatched emits `gap`.
- **India adapter (A7):** contract check fails LOUDLY on upstream version mismatch with a named actionable error, never an opaque traceback; one full re-run of `dpdp-law-to-code`'s own test suite (407 tests) passes unmodified against the pinned version; India findings produced by the adapter match upstream `ComplianceResult` records bit-identically.
- **Delta (A1, A2, C1):** two obligations differing only in `value` under the same `dimension` produce ONE divergence row; CCPA + HIPAA on the same hospital produce two distinct obligations under the new grouping key; no "strongest" column appears anywhere.
- **Applies_if (A4):** an obligation with `applies_if` referencing employee_count > N yields `not_applicable` for a small org, `contested` for a missing field, never a silent pass.
- **Depends_on (A6):** "appoint X if SDF" depends on the SDF determination; cycle in dependency graph is a pack-load error, not a runtime surprise; an unresolved dependency yields `contested`.
- **Offline (P1):** install-time audit fails if any required or transitive dependency declares a network capability; runtime `socket.socket` call raises; C-extension bypass is documented as a known limit, not relied on.
- **Report:** every artefact carries the disclaimer; Markdown and JSON-lines derive from one `EngineResult`; no divergent output.

### A1–A7 and C1–C3 as concrete build obligations
- **A1** Structured `sub_topic` is in the `Obligation` dataclass from step 3; delta code in step 10 groups on `dimension`; test proves one-row divergence for `age_threshold_18` vs `age_threshold_16`.
- **A2** `Obligation` carries `instrument`; grouping key in step 10 is `(regime, sub_unit, instrument, topic, dimension)`; test proves CCPA and HIPAA do not merge or duplicate.
- **A3** `Declaration` carries `sub_units_complete: bool`; engine emits one incompleteness notice per country; test proves "US no states, `sub_units_complete: false`" yields one notice, not N.
- **A4** `Obligation.applies_if` evaluated before conformance; missing input → `contested`; test proves threshold obligations.
- **A5** Safeguards are `(control, value)` pairs; obligation may carry `required_value`; DPDP Rule 6(1) obligations carry NO `required_value` because the rule lists encryption/obfuscation/masking/virtual tokens without prescribing a standard.
- **A6** `Obligation.depends_on: list[obligation_id]`; topological eval; cycle is a pack-load error; test proves SDF → DPO appointment order.
- **A7** India adapter runs contract check on load; named actionable error on mismatch; test proves version-bump failure mode.
- **C1** No "strongest obligation" code path exists; test searches the codebase for the token and asserts zero hits.
- **C2** Hardcoded mapping of six packs; no `importlib.metadata.entry_points` for packs; test asserts plugin-discovery code is absent.
- **C3** `ruamel.yaml` is not a dependency; `requirements.txt` and lockfile prove it; stdlib `yaml.safe_load` is used.

## M — MEASURE

### Tests
- [ ] Unit: schema; jurisdiction resolver; pack contract; applies_if; depends_on; delta grouping; structured sub_topic; required_value; offline audit.
- [ ] Integration: India adapter against pinned `dpdp-law-to-code` (re-runs upstream 407 tests); US tree with `sub_units_complete` true/false; Canada province-with/without-Quebec; cycle-as-load-error; upstream version-bump contract failure.
- [ ] Smoke: a fresh-clone run of `check` against a canonical declaration produces a report with the disclaimer in the header, every finding carrying `regime`/`instrument`/`provision`, and India findings bit-identical to upstream `ComplianceResult`.

### Real-usage metrics
- Metric 1: Percentage of findings carrying a citation to a named instrument and provision verified against the Verified Facts Brief. Target: 100%. Measured by a CI check that flags any finding with a `[FACT NEEDED: ...]` marker being a hard fail.
- Metric 2: Percentage of US declarations correctly expanded to sub-national units (or carrying the one-time incompleteness notice). Target: 100%. Measured by scenario tests across the 20 states.
- Metric 3: India-finding divergence from upstream `ComplianceResult` per re-run. Target: zero. Measured by snapshot diff.
- Metric 4: Ratio of obligations that emit `not_applicable` to those that would emit `gap` without `applies_if`. Target: positive. Measured by counting on a synthetic declaration set.

### Observation window
First 10 synthetic declaration runs across the six regimes, plus the upstream `dpdp-law-to-code` test suite re-run, before any user-facing adoption claim is asserted.

## A — ANALYZE

**Closed 2026-08-19** by the maintainer. Code exists; these are
measurements, not estimates.

### What was built

6,663 lines of `src/`, 3,249 lines of tests, thirteen modules and six regulation packs.
**430 tests pass, 0 fail. 91.5% line coverage** (measured with a stdlib tracer; `coverage`
was not installed and this build did not add packages to the maintainer's environment). The only file
at 0% is `__main__.py`, the process entry point, which was smoke-tested directly instead.

### Did the tests prove what they were supposed to prove?

| Component | What the spec said the test must PROVE | Result |
|---|---|---|
| Schema | rejects unknown keys; rejects malformed JSON/YAML; round-trips losslessly | ✅ plus duplicate-YAML-key, NaN, and `!!python/` tag refusal |
| Jurisdiction resolver | US expands per state; one incompleteness notice; Quebec never runs unless declared | ✅ all four scenarios |
| Pack contract | every finding cites instrument + provision; a draft pack emitting `satisfied` fails | ✅ enforced in the engine, not per pack |
| India adapter (A7) | contract check fails LOUDLY with a named error; upstream 407 tests pass unmodified | ✅ **and it fired for real** during the fix pass, catching a mistyped upstream parameter name |
| Delta (A1, A2, C1) | one row for 16-vs-18; CCPA and HIPAA stay distinct; no "strongest" anywhere | ✅ including a codebase-wide token search |
| applies_if (A4) | `not_applicable` for a small org; `contested` for a missing field; never a silent pass | ✅ |
| depends_on (A6) | SDF → officer ordering; cycle is a load error; unresolved dependency → contested | ✅ **falsifier 4 fired for real here** — see below |
| Offline (P1) | install-time audit; runtime tripwire; C-extension limit documented as a known limit | ✅ honestly labelled a tripwire, not a proof |
| Report | disclaimer on every artefact; both renderers from one `EngineResult` | ✅ |

### Real-usage metrics from `M`

| Metric | Target | Measured |
|---|---|---|
| 1 — findings carrying a named instrument and provision | 100% | **100%.** Every finding in every fixture |
| 2 — US declarations correctly expanded, or carrying the one-time notice | 100% | **100%** across the tree fixtures. An unresearched state now emits an explicit unsourced obligation rather than silence |
| 3 — India divergence from upstream `ComplianceResult` | zero | **zero.** Upstream section and citation are carried verbatim into `citation_pointer` and metadata |
| 4 — ratio of `not_applicable` to what would have been `gap` without `applies_if` | positive | **positive.** On the Californian hospital, three of eight federal obligations resolve `not_applicable` on sectoral grounds that would otherwise have been reported as gaps |

### What the design got right, and what it did not

**Right, and it earned its keep:** the A7 contract check caught a real drift mid-build. The
codebase-wide "strongest" search caught a C1 violation still sitting in the scaffold. The
`applies_if` / `contested` distinction is doing the single most useful thing in the tool —
it separates "the client said no" from "the client did not say", and almost every defect
found tonight was a place where that distinction had collapsed.

**Wrong, and worth saying plainly:**

1. **A6 was specified in the wrong place.** Dependency propagation lived inside
   `evaluate_obligations`, and the one pack that matters most — India — does not go through
   it. So the rule was written, tested, and not applied where it counted. Falsifier 4 fired
   on the first real report. A policy that only binds the callers who opt in is not a policy;
   it now runs in the engine's post-pass, which every pack goes through.
2. **"Never fabricate an input" was stated as a principle and then breached three times** in
   the same file that stated it — zero risk-scores for the SDF heuristic, `False` for
   children's tracking and targeted advertising, and a substring test standing in for a
   numeric comparison. Each produced a wrong answer about a client. Principles in docstrings
   do not enforce themselves.
3. **The declaration schema was under-specified for the India rail.** It had nowhere to
   record notice content or children's processing facts, which is *why* the fabrication
   happened. The fix was to extend the schema, not to be more careful.

### Observation window

Ten synthetic declarations across the six regimes, plus the upstream suite re-run. **No
user-facing adoption claim is asserted.** The tool has not been run on a real engagement.

---

## D — DECIDE

**Closed 2026-08-19.**

### Falsifiers — all five executed, in `tests/test_falsifiers.py`

| # | Falsifier | Verdict |
|---|---|---|
| 1 | US tree: CCPA and HIPAA merge, or the incompleteness notice is not emitted once | **PASSED.** Verified on a real rendered report for a Californian hospital |
| 2 | Upstream version bump gives an opaque `TypeError`/`ImportError` | **PASSED**, and demonstrated in the wild: running the CLI without the package on the path produced a named error naming the pin, not a traceback |
| 3 | A dependency emits a network call the install-time audit did not flag | **PASSED** on the evidence available. Honest limit: the runtime guard is a tripwire, and a C extension can bypass it. Not claimed as a proof |
| 4 | An SDF-dependent obligation resolved before the SDF determination | **FIRED, THEN FIXED.** The tool reported a non-SDF as having a gap on the Rule 13 duties. Fixed at the engine level; four regressions guard it |
| 5 | A citation not sourced from the Verified Facts Brief | **PASSED.** Every numeric constant in `src/` was swept and adjudicated one by one. Nine unsourced values are carried as `[FACT NEEDED]`, none as fact |

Falsifier 4 firing is the most useful thing that happened in this build. It was found by
reading the first real report, not by a test — which is itself a finding about how much of
this can be checked mechanically.

### Cut-over criterion — status

**India:** two of the three limbs are met. The upstream 407 tests pass unmodified against the
pin `@da15477`, and the adapter's contract check passes. The third limb — *the adviser has
manually verified, on one real engagement, that the India findings are bit-identical to the
upstream `ComplianceResult` records* — is **the maintainer's, and is not met.** Until it is, the India
output is advisory and the manual cross-reading remains authoritative.

**The other five regimes:** not met, and not close. Each requires the adviser to verify, on
one real engagement per regime, that every citation resolves and that the delta's divergences
match a hand-diff. All five ship `draft`, so none of them can emit `satisfied` at all.

### Decision

**SHIP as code. DO NOT PUBLISH.**

`SHIP` here means what `04` says it means: the code is done, the gates are run, the filter has
converged. It does not mean the tool is authoritative for any regime, and it does not mean
anything leaves this machine.

Specifically **not** decided, and reserved to the maintainer:

1. **The name.** Settled after this section was written: the package is `samanvaya`.
2. **Publication.** The pre-publication review runs first, and that is the maintainer's gate.
3. **Which regimes to source next.** The register in `docs/verified_facts_brief.md` has twenty
   open items. Two of them constrain the tool most: the exact publication date of
   G.S.R. 846(E) — one lookup on the e-Gazette, which currently puts a ±1 day on every India
   commencement date — and the list of US states with a comprehensive statute in effect in
   2026, which has no single official source and must be assembled statute by statute.
4. **Whether the independent green-pass reviewer seat stays vacant.** Tonight's audit was
   cross-model plus the maintainer adjudication. That is not the same thing as a named independent
   reviewer, and the router has recorded that seat as unfilled since a former reviewer seat died on
   2026-08-17. Three of fifteen delegate findings were rejected on evidence, which is roughly
   the false-positive rate to expect from this arrangement.

### Falsifier (≥3, ranked)
1. **If**, on a canonical declaration exercising the US tree (California hospital under both CCPA and HIPAA), the report emits a single merged obligation for CCPA and HIPAA OR fails to emit the one-time US incompleteness notice when `sub_units_complete: false`, **the design is wrong** because A2 and A3 are the only reason the US rail is not a false-positive engine, and a failure here means the delta is lying and the adviser is exposed.
2. **If**, on upgrading `dpdp-law-to-code` by one minor version, the adapter fails with an opaque `TypeError` or `ImportError` instead of a named, actionable error identifying the upstream version, **the design is wrong** because A7 is the contract that prevents the tool from breaking silently on the one rail with verified constants; an opaque failure means the adviser loses the India rail with no recovery path.
3. **If**, on a run with no network connectivity available, the tool completes successfully but a subsequent post-mortem reveals a transitive dependency emitted a network call that the install-time audit did not flag, **the design is wrong** because the offline guarantee is load-bearing for the advocate's fiduciary posture; "almost offline" is operationally and legally the same as "online".
4. **If**, on a declaration that triggers "Appoint DPO if SDF", the report emits `satisfied` or `gap` for the DPO appointment without first resolving the SDF determination, **the design is wrong** because A6's topological order is the only thing preventing oscillation between `contested` outcomes; a false stable answer here is a false negative on the highest-stakes obligation in the DPDP rail.
5. **If**, on any obligation, the report emits a citation whose section number, rule number, date, threshold, or deadline is not sourced from the Verified Facts Brief, **the design is wrong** because invention of statutory references is the malpractice vector the PRD explicitly bans; one guessed citation invalidates the report.

### Cut-over criterion
The tool's report becomes authoritative for the DPDP rail on the day a re-run of `dpdp-law-to-code`'s own 407 tests passes unmodified against the pinned version **and** the adapter's contract check passes **and** the adviser has manually verified, on one real engagement, that the India findings in the consolidated report are bit-identical to the upstream `ComplianceResult` records. For the other five regimes, the report becomes authoritative for a regime only when the adviser has manually verified, on one real engagement per regime, that every finding's citation resolves to the named instrument and provision in the Verified Facts Brief, and that the delta's divergences match the adviser's own hand-diff. Until both conditions hold for a regime, the tool's output for that regime is **advisory**, and the manual cross-reading remains authoritative.
```