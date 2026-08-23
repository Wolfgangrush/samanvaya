# 06 — FILTER  ·  samanvaya

**Date:** 2026-08-19 · Run after the code existed, before anything was called done.
**Run by:** the maintainer, overnight, unattended.

> The maintainer, defining the filter: *"You assess your own work and distill it… Once you have
> built all the 6 files, what happens later? You see the code and restructure it in a way
> that is given in the architecture essentials or architecture.md. Once you do that you
> start to see if there is any mistake in it. If there is, you fix it."*

---

## Pass 1 — read the code against the architecture

`03-ARCHITECTURE-ESSENTIALS.md` component table, checked against the tree as written.

| # | Architecture says | Code actually does | Verdict |
|---|---|---|---|
| 1 | `samanvaya.cli` — parse args, dispatch, write reports | `cli.py`, five subcommands, returns int, never raises | matches |
| 2 | `samanvaya.declaration` — parse and validate one declaration | `declaration.py` — load/load_text/canonical_hash; validation delegated to `schema` | matches |
| 3 | `samanvaya.jurisdiction` — expand country and sub-national trees | `jurisdiction.py` — `resolve()` returning targets, notices, completeness, strays | matches |
| 4 | `samanvaya.packs` — discover installed pack entry points | **C2 cut this.** `registry.py` is a hardcoded mapping of six | matches 03, drifted from 02 |
| 5 | `samanvaya.packs.*` — evaluate declaration, date, jurisdiction | six packs, all `evaluate(declaration, as_at, sub_unit)` | matches |
| 6 | `samanvaya.packs.india.adapter` — map to upstream India checks | `adapter.py` + A7 contract check | matches |
| 7 | `samanvaya.engine` — dispatch packs, apply dates, build rollups | `engine.py` — `evaluate_obligations` + `run` | matches |
| 8 | `samanvaya.delta` — compare obligations and verdicts across regimes | `delta.py` — divergence only, no ranking | matches |
| 9 | `samanvaya.report` — render Markdown + JSON-lines | `report.py`, both from one `EngineResult` | matches |
| 10 | `samanvaya.offline_check` — verify runtime network prohibition | `offline_check.py` — install-time audit + runtime tripwire | matches |
| 11 | `samanvaya.schema` — validate structure; reject unknown keys | `schema.py` | matches |
| 12 | — not in the architecture — | `credentials.py` | **extra, retained — see Pass 2 #1** |
| 13 | `packs/us/federal.py`, `packs/us/states.py`, `packs/canada/federal_quebec.py` | scaffold stubs, unreferenced, full of `NotImplementedError` | **extra, removed** |

## Pass 2 — restructure to match

| # | Change made | Which architecture line it now obeys |
|---|---|---|
| 1 | Extracted the credential firewall out of `declaration.py` into a new `credentials.py`, called from `schema.validate` | PRD banned-scope item 1. It was reachable only via `load()`, so a caller validating an already-parsed dict bypassed it entirely. `validate` is public API; the refusal has to sit at the validation boundary, not the file-reading one |
| 2 | Deleted three unreferenced scaffold modules | 03 names no such components; they were scope that arrived without a decision, and carried stale `[FACT NEEDED]` markers that polluted the count |
| 3 | Replaced `report._to_jsonable`'s hand-enumerated field lists with a generic `dataclasses.fields` walk | 03 "Markdown + JSON-lines derive from one `EngineResult`". A hand-written key list silently drops a new field from the declaration hash, so two materially different declarations hash identically |
| 4 | Moved dependency propagation from `evaluate_obligations` alone into the engine's shared post-pass | A6. The India pack builds Findings directly and never called `evaluate_obligations`, so its `depends_on` edges were being ignored — see Pass 3 #1 |
| 5 | Added `Declaration.notice` and `Declaration.children`, and enriched `ConsentMechanism` | Without them the India rail could not drive the upstream checks without fabricating inputs — see Pass 3 #4 |
| 6 | Made the Canada pack emit an explicit unsourced obligation for an unresearched province | 03 "United States and Canada remain jurisdictional trees". The US pack already did this; two federations behaving differently in the same situation is itself a defect |

### Architecture amended

| # | Architecture amended | Why the code was right and the doc was wrong |
|---|---|---|
| A | `02-ARCHITECTURE.md` entry-point plugin registry | Superseded by C2 in the adjudicated hard-question pass. `03` already records it; `02` remains the historical record and is not authoritative where the two disagree |
| B | `Divergence` as a pairwise `(regime_a, regime_b)` record | Pairwise rows contradict A1's "ONE divergence row": three regimes disagreeing would emit three rows. Changed to one row carrying N `DivergencePosition`s. `03` §Key types is updated by this file |
| C | `03` "Obligation result" table lists five values | Accurate. No change |

## Pass 3 — now look for mistakes

Found by: **O** = the maintainer running the code, **X** = cross-model audit (each delegate auditing
the half it did not write), **T** = a test written before the code.

| # | Mistake | How found | Fix | Test that now covers it |
|---|---|---|---|---|
| 1 | **Falsifier 4 fired.** A client declaring it was NOT a Significant Data Fiduciary was reported as having a **gap** on the Rule 13 twelve-monthly DPIA and audit. A false accusation on the highest-stakes obligation in the India rail | O — reading the first real report | Dependency propagation moved into the engine post-pass; the India adapter also now refuses at source | `test_falsifiers.py::TestFalsifier4DependencyOrder` |
| 2 | **SDF status decided from seven fabricated zero risk-scores.** The declaration supplies none of them; zeros drive the upstream heuristic straight to "not an SDF" | O | The determination now rests solely on the declared notification fact. s.10(1) is a Government power, not a self-assessment the tool may score | `test_india_adapter.py::TestUndeclaredFactsAreContestedNotGaps` |
| 3 | **Log retention compared by substring.** `"1" in "21 days"` is true, so twenty-one days satisfied the one-year minimum in Rule 6(1)(e) | X (another delegate model) | Real numeric parse; unparseable → CONTESTED. A month is 365/12 so "12 months" is exactly one year | `test_audit_regressions.py::TestLogRetentionIsComparedNumerically` |
| 4 | **Children's tracking and targeted-advertising hardcoded to `False`** and fed to the upstream check. A client that tracks children could be reported compliant | X (another delegate model) | New `ChildProcessingDeclaration`; undeclared → CONTESTED, declared-true → GAP | `TestChildrenInputsAreNotFabricated` |
| 5 | **India commencement ignored.** Rule 1(4) commences Rules 3 and 5–16 eighteen months after publication; the tool evaluated them as binding in 2026 | X (another delegate model) | `in_force_from` per the schedule; the ±1-day publication uncertainty is carried in metadata, never silently resolved | `TestIndiaCommencementIsHonoured` |
| 6 | **Credential firewall missed `my_password=`.** `\b` does not match between `_` and a letter | X (another delegate model) | Anchor on start-of-string or a non-alphanumeric | `TestCredentialFirewallWordBoundary` |
| 7 | **EU pack reported a declared refusal as CONTESTED.** "The client said no" and "the client did not say" both came out contested, so an adviser was never told a client affirmatively fails Article 33(1) | X (another delegate model) | Declared-false → GAP; only `None` → CONTESTED | `TestEuDeclaredFalseIsAGapNotContested` |
| 8 | **`_missing()` computed the missing paths and threw them away.** Every EU contested finding reached the adviser naming no fact to go and ask for | X (another delegate model) | Rationale channel threaded through `evaluate()` | same class |
| 9 | **Notice limb count invented by arithmetic** — `SECURITY_MINIMUM_LIMBS - 1`, deriving a s.5(1) statutory count by subtracting one from an unrelated Rule 6(1) constant | X (another delegate model) | Marked `fact_needed`. The count is not sourced, so it must not be asserted | `TestNoticeLimbCountIsNotDerivedByArithmetic` |
| 10 | **Canada silent on unresearched provinces** while the US pack reported them. Silence reads as a clean bill of health | X (one delegate model) | Mirrors the US unsourced-obligation pattern | `test_canada.py::test_an_unresearched_province_is_reported_not_silently_empty` |
| 11 | **A path guard that compared a value with itself.** `_assert_no_traversal` compared `out.resolve().parent` with `out.resolve().parent` — a tautology dressed as a security control | T | Replaced with checks that can actually fire: symlink, non-regular file, missing parent | `test_report.py::TestWriting` |
| 12 | **C1 violation in the scaffold.** `delta.py` still described the ranking design the hard-question pass CUT | T — the codebase-wide "strongest" test | Rewritten | `test_types.py::test_the_token_strongest_appears_nowhere_in_the_package` |
| 13 | **`bool(result)` instead of `result.compliant`.** Safe today only because the upstream dataclass happens to define `__bool__` — which the contract check does not verify | X (another delegate model) | Read the attribute explicitly | `TestUpstreamComplianceIsReadExplicitly` |
| 14 | **`OBLIGATION_COUNT` computed by a wrong formula** that matched by coincidence, and a docstring promising a load-time check that did not exist | X (another delegate model) | `len(OBLIGATION_REGISTRY)`, docstring corrected | `TestPackMetadataMatchesImplementation` |
| 15 | **Renderer grepped for the literal `"FACT NEEDED"`** instead of importing the shared constant, so it could drift from the engine | X (another delegate model) | Imports `FACT_NEEDED_PREFIX` | `TestRendererSharesTheMarkerConstant` |
| 16 | **Dead statutory constant.** `CONSENT_MANAGER_NET_WORTH_INR` declared, never used — a claim nobody checks | X (another delegate model) | Deleted | `TestNoUnusedStatutoryConstants` |
| 17 | **Import cycle** engine → registry → packs → engine | O | Registry import deferred into `run()` | whole suite imports |
| 18 | **A7 caught a real drift during the fix pass**: `REQUIRED_CHECKS` named a parameter `dpo_contact_publication` where upstream has `dpo_contact_published` | O — the contract check refused to run | Corrected | `TestContractCheckFailsLoudly` |

**Audit findings that did NOT survive verification** are recorded, with reasons, at the foot
of `tests/test_audit_regressions.py`, so nobody re-litigates them. Three of the fifteen
delegate findings were rejected on evidence.

## Pass 4 — banned-scope sweep

| # | Banned item | Present in code? | Removed / deferred to |
|---|---|---|---|
| 1 | Database connectors | No — and actively refused | firewall + `TestCredentialRefusal` |
| 2 | Credentials, secrets, API keys | No — refused at `validate()` | `credentials.py` |
| 3 | Network scanning / port scanning | No | — |
| 4 | Discovery by crawling or probing | No | — |
| 5 | Implementation or testing of security controls | No. Rule 6(1) minima are checked as DECLARED items only | — |
| 6 | Legal advice | No. Disclaimer on every artefact; C1 ranking absent | `TestNoRanking` |
| 7 | Hosted multi-tenant SaaS | No | — |
| 8 | Web UI | No | — |
| 9 | Storage of client personal data | No. The named report file is the only write | `test_nothing_else_is_written` |
| 10 | Copying another privacy tool's source | No. Clean room; no such source was read | — |
| 11 | Invention of statutory references | **Swept.** Every numeric constant in `src/` adjudicated against the Verified Facts Brief | `TestFalsifier5NoInventedCitations` |
| 12 | Auto-remediation | No | — |
| 13 | Ingestion of client logs / HR records | No | — |
| 14 | Reimplementation of the India rail | No. `dpdp-law-to-code` consumed unmodified at pin `@da15477` | upstream 407 tests re-run |
| 15 | Jurisdiction flattening | No. US and Canada are trees | `TestFalsifier1UsTreeSemantics` |
| 16 | "US GDPR" / "Singapore GDPR" / "Canada GDPR" | Only in the docstring saying they are not instruments | `test_no_finding_names_an_instrument_that_does_not_exist` |
| 17 | Auto-publication of output | No. `write()` writes a local file and nothing else | — |

---

## Exit criteria

- [x] Every component in the architecture maps to code, and every module maps back. Three
      orphaned scaffold modules removed; one addition (`credentials.py`) is justified above.
- [x] `03-ARCHITECTURE-ESSENTIALS.md` still describes the code, with the `Divergence` shape
      amendment recorded at Pass 2 #B.
- [x] Nothing from the banned-scope list survives.
- [x] Suite green — **430 passed, 0 failed** — and every Pass-3 fix has a test that would
      catch it returning.

## Verdict

- [x] **CONVERGED.**
- [ ] ANOTHER PASS NEEDED

One qualification, which is a limit on the *product* and not on the convergence: four of the
six rails ship `draft` because their constants could not be primary-sourced tonight — the UK
because `legislation.gov.uk` returned HTTP 202 with an empty body to every request, Singapore
because `sso.agc.gov.sg` served only its site shell, Quebec because `legisquebec.gouv.qc.ca`
timed out, and California because `leginfo.legislature.ca.gov` timed out. That is the design
behaving correctly: an unsourced constant becomes `[FACT NEEDED]` and its pack cannot emit
`satisfied`. It is tracked in `docs/verified_facts_brief.md`, not hidden here.

---

*Where this sits: `00`–`05` are written before code. `06` is written after it. Together they
are the loop — plan, build, then drag the build back onto the plan.*
