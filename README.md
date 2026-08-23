<div align="center">

**समन्वय · samanvaya — reconciliation**

**Offline multi-jurisdiction privacy conformance. Four regimes, one declaration, no ranking.**

<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"/></a>
<img src="https://img.shields.io/badge/tests-790-brightgreen" alt="790 tests"/>
<img src="https://img.shields.io/badge/coverage-90.8%25-brightgreen" alt="90.8% coverage"/>
<img src="https://img.shields.io/badge/network-none-informational" alt="no network"/>
<img src="https://img.shields.io/badge/rails-1%20sourced%20·%203%20draft-orange" alt="1 sourced, 3 draft"/>

</div>

---

# samanvaya

An adviser reads one hand-authored declaration describing an organisation, and gets back a
local report saying which obligations under four named privacy regimes appear satisfied, which
are unaddressed, and which cannot be resolved on the facts as declared.

It never touches the organisation's systems, networks or data. It reads what a human wrote
down.

## The one thing it does that nothing else does

Four separate compliance reports are four separate compliance reports. What an adviser actually
needs is the sentence that falls out of comparing them:

> *Compliant under Regulation (EU) 2016/679, exposed under the Digital Personal Data Protection
> Act 2023.*

`samanvaya` computes that comparison as a first-class output. Two regimes fixing a child-consent
age of 16 and 18 produce **one** divergence row on the `child_consent_age` dimension, carrying
both positions with their instruments and provisions.

**It does not rank them.** Deciding which regime's standard is the more demanding is statutory
interpretation, and a tool that ranks statutes is giving legal advice. The tool reports the
divergence; the advocate ranks it. There is a test that searches the entire codebase for the
word "strongest" and fails if it appears anywhere.

## Who this is for

### For lawyers and privacy professionals

`samanvaya` is a deterministic, offline comparison engine. The adviser writes down an
organisation's facts in a single declaration file. The tool reads that file and reports, for
each obligation it implements, whether the declared facts appear to satisfy the obligation,
appear to leave it unaddressed, or cannot be resolved on the facts as declared. It produces
Markdown, JSON-lines and a tabular PDF with an optional letterhead naming who prepared it.

It is not a compliance platform, a GRC suite, or a continuous monitoring tool. It does not
scrape, scan, integrate with your stack, or hold your data. It reaches no network. The
obligation sets are hand-coded against named statutes and every constant traces to a primary
text or is marked as unread.

One design decision warrants stating plainly. `samanvaya` reports divergence between regimes
where the same underlying practice is treated differently. **It does not rank them.** Deciding
which statute is the more demanding is statutory interpretation, and that work belongs to the
adviser, not to a tool. The tool's job is to show where the regimes diverge so that judgement
can be exercised in context.

### For founders and operators of small companies

This section is not addressed to you as the operator of the tool. `samanvaya` is not something
you run yourself, and it will not tell you whether your company is compliant. It is a tool your
lawyer or privacy adviser runs, on a file they prepare from a conversation with you about how
your business actually works.

What it does for you, indirectly, is this. When a prospective enterprise customer sends a long
security questionnaire, or an investor's diligence pack asks detailed questions about how you
handle personal data, or you have been told a particular privacy law applies to you — your
adviser can produce a clear written comparison of what you have told them against the
obligations of the named statutes. You read the output together. You see what is addressed,
what is not, and what needs another conversation.

It is offline, so what you tell your adviser stays with your adviser. It is free, so the cost
of that structured picture is the adviser's time, not a software licence.

## When this gets used

**The questionnaire that blocks a deal.** An enterprise procurement team has sent your client a
vendor security questionnaire covering personal-data handling, and the deal will not move until
it is answered. You establish the facts, write the declaration, and run the tool. The output
tells you which items are supported by declared practice, which need evidence, and which cannot
be answered on what the client has told you. You take that gap list back to the client.

**The funding-round diligence list.** The investor's data room asks about applicable privacy
law, safeguards, breach response and data-subject rights. The client has never mapped these.
You take the facts as you understand them, write the declaration, and run it against the regime
the investor will scrutinise plus India where the client offers goods or services to people in
India. The unresolved findings become your diligence worklist.

**The client who read about a penalty.** They want to know where they stand. You decline to
give an off-the-cuff verbal assessment. You record the facts, run the tool, and walk them
through the output as a structured starting point for advice — the basis for the conversation,
not the conclusion of it.

`samanvaya` is **not for a live breach.** An incident in progress is containment, notification
deadlines, regulator liaison and forensics. A static comparison against declared facts is the
wrong instrument for a moving one.

## Status — read this before relying on any output

One rail has every constant read verbatim from a primary source. Three are partial. Two
regimes that used to appear here have been removed.

| Rail | Instruments | Constants | Pack |
|---|---|---|---|
| **India** | DPDP Act 2023 · DPDP Rules 2025 (G.S.R. 846(E)) | **every constant verbatim from the Gazette** | **sourced** |
| **EU** | Regulation (EU) 2016/679 | verbatim from EUR-Lex (CELEX 02016R0679) | **draft** — core Articles verified, obligation set incomplete |
| **United States** | COPPA · HIPAA · GLBA Safeguards | federal sectoral verbatim from eCFR; **state law not covered** | **draft** |
| **Canada** | PIPEDA · SOR/2018-64 | federal verbatim from Justice Laws; **Quebec not covered** | **draft** |

### What was removed, and why

The **United Kingdom** and **Singapore** packs were withdrawn on 20 August 2026. Every
obligation in each was a placeholder: `legislation.gov.uk` answered every request — HTML, XML
and its data API, across three clients and eight retries — with HTTP 202 and a zero-length
body, and `sso.agc.gov.sg` served only its site shell. Neither statute was ever read.

Carrying them was worse than not covering them. An unsourced constant forces its obligation to
`contested`, and a `contested` row renders in a client-facing PDF as a line reading, in full,
`[FACT NEEDED: which section imposes the data breach notification obligation?]`. That is a
document advertising that the work was not done. The packs are parked, not deleted, in
[`unsourced-packs/`](unsourced-packs/), with a note on what un-parking them requires.

**Declaring a regime this tool does not cover is reported, never ignored.** Name Great Britain,
Singapore, Brazil or anywhere else without a pack and the report carries an explicit notice:
*"GB was declared as a jurisdiction but this tool has no sourced obligations for it, so GB was
NOT ASSESSED. Its absence from the findings above is not a finding."* Silence about a declared
jurisdiction reads as a clean bill, and this tool does not let an absence pass for a finding.

### On draft packs and unsourced constants

A **draft pack can never emit `satisfied`.** That is enforced in the engine, not left to each
pack's good behaviour. Where a constant could not be read on a primary source it is carried as
`[FACT NEEDED: <the question>]`, the obligation resolves to `contested`, and the marker travels
all the way into the report. **Nothing is guessed.** Open questions are registered in
[`docs/verified_facts_brief.md`](docs/verified_facts_brief.md).

### One date, stated precisely

India's DPDP Rules 2025 were made by notification **G.S.R. 846(E), dated 13 November 2025**.
Rule 1 commences the Rules in three phases, each anchored to *the date of publication in the
Official Gazette*:

- Rules 1, 2 and 17 to 21 — on publication
- Rule 4 (Consent Manager registration) — **one year** after publication
- Rules 3, 5 to 16, 22 and 23 — **eighteen months** after publication

The notification does not state its own publication date, and that date is not the same event
as the date the notification bears. This tool therefore prints the rule and the notification
date rather than a computed commencement date, and records the residual uncertainty on the
finding rather than resolving it silently.

## Install

**As an application** — this is what an adviser wants. The window is the product surface;
the command line remains for anyone who prefers it.

```bash
./build-app.sh      # builds, signs, and refuses to finish unless every surface works
./install-app.sh    # installs to /Applications and re-tests the installed copy
```

`build-app.sh` runs two gates. The **launch gate** starts the binary and requires it to
still be running six seconds later — added after a build shipped that died instantly on
`AttributeError: module 'tkinter.ttk' has no attribute 'Menu'` while every test passed,
because no test built a widget. The **self-test gate** then asks the signed bundle to
construct every surface it has — main window, menu bar, intake form, and both PDF
renderers — and fails the build if any is broken. "PyInstaller exited 0" is a statement
about PyInstaller; "the app opened" is a statement about one instant. Neither is a
statement about the intake form still working after it was frozen.

`install-app.sh` installs from the **signed stage copy, never `dist/`**: `~/Desktop` sits
under a cloud file provider that stamps extended attributes onto everything inside it,
which breaks code signatures — so `dist/` is a convenience copy that cannot be re-signed
in place. The installer checks the bundle identifier before removing any existing install,
quits a running copy first, and re-runs the self-test against what actually landed in
`/Applications`.

**As a library or a command-line tool:**

```bash
pip install .
```

Two runtime dependencies, both deliberate:

- **PyYAML** — declarations may be written in YAML.
- **[dpdp-law-to-code](https://github.com/Wolfgangrush/dpdp-law-to-code)** — the India rail is
  not reimplemented here. It is consumed unmodified at a pinned commit, and its own 407 tests
  are what attest the India findings.

## Use

```bash
samanvaya interview --out declaration.json # 83 plain-English questions; the usual way in
                                           # (or open the app: File > New Intake Form)
samanvaya validate declaration.json        # structure + credential firewall
samanvaya check declaration.json --as-at 2027-12-01 --out report
samanvaya questionnaire --out questionnaire.pdf  # the blank form, to send before the meeting
samanvaya cite                             # every pack, version, draft status, instruments
```

`init` still exists and writes a bare four-field skeleton, but `interview` is what you
want: a full check draws on **83 declarable facts**, and a check against the four-field
skeleton returns nothing but `contested` — correctly, and uselessly.

### The interview

It asks the questions an adviser asks in a discovery meeting, in plain English, each one
naming the provision that turns on it. Answer `y` / `n`, `s` to skip, or `?` to be told
why the question is being asked.

**Skipping is safe, and that is the point.** A skipped question stays *undeclared*. It is
never recorded as "no". The tool reports it as `contested` — a note that the adviser must
go and ask — and never as a `gap`, which is an accusation that the client fails a duty.
Losing that distinction is the single most dangerous thing this tool could do, so the
interview is built around preserving it: `--resume` picks up a part-finished declaration
and asks only what is still unanswered.

### Worked examples

[`examples/`](examples/) holds five filled declarations — an Indian SaaS company, an
EU/UK retailer, a Californian hospital sitting under both state and federal law, a
Canadian fintech operating in Quebec, and one that is almost entirely unanswered to show
that a half-finished declaration is a legitimate starting point rather than an error.

```bash
samanvaya check examples/03-us-california-hospital.json --as-at 2027-12-01 --out report
```

`check` writes `report.md` and `report.jsonl`. Findings go to the file, **not** to the terminal —
they are client material, and stdout lingers in shell history and screen-shares. `--stdout` is
opt-in.

`--as-at` matters more than it looks. Statutes commence on dates. DPDP Rule 1(4) does not bring
Rules 3 and 5 to 16 into force until eighteen months after publication of G.S.R. 846(E), so a run
dated in 2026 correctly reports most of the DPDP Rules as *not yet in force* — and says so
prominently, above the findings, so a reader cannot mistake "not yet arrived" for "does not
apply".

## What a finding looks like

Verbatim, from a declaration stating a 96-hour regulator deadline, run at `--as-at 2027-12-01`:

```
- [gap] in.breach.board_report — Digital Personal Data Protection Rules 2025, Rule 7(2)(b)
  - obligation: DPDP Rules 2025, Rule 7(2)(b) — a detailed report must reach the Board
    within 72 HOURS of becoming aware of the breach.
  - rationale: Upstream Sec 8(6) returned compliant=False: Board not notified within
    72hr of detection — Sec 8(6) intimation requirement
  - cite: Digital Personal Data Protection Rules 2025, Rule 7(2)(b)
          [upstream: Sec 8(6) (DPDP Act 2023, Sec 8(6))]
```

Two citations, because they answer different questions. This tool's `provision` names the
provision fixing the constant being reported — Rule 7(2)(b) for the seventy-two hours — while the
upstream engine cites the section imposing the underlying duty, Sec 8(6). Neither replaces the
other, so the pointer carries both and the reader can trace the finding back to the exact
upstream result.

Five verdicts, and the distinctions between them are the product:

| | |
|---|---|
| `satisfied` | the declaration meets the obligation |
| `gap` | the obligation applies and the declaration does not meet it |
| `contested` | **the declaration does not say.** Not a pass, not an accusation |
| `not_applicable` | the obligation exists but its precondition is not met, or it is not yet in force |
| `does_not_exist` | the regime does not impose this obligation at all |

`contested` versus `gap` is the line the tool works hardest to hold. "The client said no" and
"the client did not say" are different findings, and only the first is a failure. Reporting the
second as a gap is a false accusation against a client, and most of the defects found while
building this were places where that distinction had quietly collapsed.

## What it will not do

The banned scope is in [`BMAD/01-PRD.md`](BMAD/01-PRD.md) and it is load-bearing, not
aspirational. In particular:

- **No connections and no credentials.** The declaration is a file. A declaration containing
  anything credential-shaped — a connection string, an AWS key, a PEM header, a secret-looking
  assignment — is **refused**, and the error names the JSON path without echoing the value.
  Holding a client's credential would make the author a Data Processor in his own right.
- **No network at runtime.** Verified two ways: an install-time dependency audit that fails
  closed on any package it does not recognise, and a runtime `socket` guard. The guard is
  labelled a **tripwire, not a proof** — a C extension can bypass it, and pretending otherwise
  would invite reliance.
- **No persistence.** No cache, no history, no log, no telemetry. The report file you name is
  the only thing written.
- **No scanning, no discovery, no control implementation, no auto-remediation.**
- **No legal advice.** Every artefact carries the disclaimer in [`NOTICE`](NOTICE).

## Design notes worth knowing

**Jurisdiction is a tree, not a list.** The United States and Canada have binding sub-national
law. A declaration naming "United States" with no states, and not asserting the list is complete,
gets **one** incompleteness notice for the country — not one per obligation. An unresearched
state or province is *reported* as unresearched rather than omitted, because an absent section
reads as a clean bill of health.

**The upstream India engine is consumed, not copied.** The adapter runs a contract check on load
that verifies the upstream version, the `ComplianceResult` shape and every required `check_*`
signature. On a mismatch it fails with a named, actionable error identifying the pinned version —
never an opaque traceback at the moment a finding is needed.

**Clean room.** No other privacy tool's source was read. Every check traces to a section or rule
of a named instrument.

## The two documents

They are different documents and neither may drift into the other. The **questionnaire**
asks for facts and states nothing; the **report** states findings against declared facts
and contains no blanks. They share the preparer letterhead and the house style
([`pdf_theme.py`](src/samanvaya/pdf_theme.py)) — and nothing about findings, which is
enforced by test rather than observed by convention.

```bash
samanvaya questionnaire --out questionnaire.pdf   # before the meeting
samanvaya check declaration.json --as-at 2027-12-01 --out report --format pdf   # after
```

Both are reachable from the window as well: **File > Blank Questionnaire (PDF)**, and the
Generate button.

Colour was added in build 2 and carries one rule, tested three ways: **the verdict word is
always printed, and colour only ever repeats it.** No verdict is drawn in a red hue, and
`Unresolved` is the quietest of the three, because an unresolved finding is a fact not
supplied rather than a finding against the client. The report reads identically in black
and white. See [`BMAD/09-BMAD-SPEC-house-style.md`](BMAD/09-BMAD-SPEC-house-style.md).

## Tests

```bash
uv run --extra dev python -m pytest -q
```

`--extra dev` is load-bearing: `pytest` lives in the `dev` extra, and the runtime
dependencies alone (`fpdf`, among others) are what `test_cli`, `test_pdf_report` and
`test_questionnaire` import. A bare system `python3 -m pytest` fails to collect those
three with `ModuleNotFoundError: No module named 'fpdf'`. That is a missing
environment, not a broken suite.

790 tests, 90.8% line coverage. [`tests/test_falsifiers.py`](tests/test_falsifiers.py) executes
the five conditions that would prove the design wrong, stated in
[`BMAD/04-BMAD-SPEC.md`](BMAD/04-BMAD-SPEC.md) before the code existed. One of them
— an obligation being resolved before the determination it depends on — **fired for real** during
the build, and its regression tests are why it is in that file.

## Repository map

| | |
|---|---|
| `BMAD/` | the design record: requirements, architecture, spec, and the convergence filter |
| `src/samanvaya/pdf_theme.py` | the house style both client-facing documents are drawn in |
| `docs/verified_facts_brief.md` | every statutory constant, its source, and the register of what is still unsourced |
| `docs/CSO_AUDIT_20260819.md` | security audit |
| `docs/BUILD-NOTES.md` | how it was built, and every defect found |
| `src/samanvaya/packs/` | one pack per regime |
| `examples/` | five worked declarations, and what each one exercises |

## Licence

MIT. See [`LICENSE`](LICENSE).

## Acknowledgements

The India rail rests entirely on
[`dpdp-law-to-code`](https://github.com/Wolfgangrush/dpdp-law-to-code) and its 407 tests. Statute
text was read from the issuing authorities directly: the Gazette of India Extraordinary for
G.S.R. 846(E), EUR-Lex for Regulation (EU) 2016/679, Justice Laws Canada for PIPEDA and
SOR/2018-64, and eCFR for the US federal sectoral rules.

---

*This software produces a conformance report. It is not legal advice, it does not predict any
regulator's or court's decision, and it creates no lawyer-client relationship. Every finding must
be checked against the primary source cited before it is relied upon.*
