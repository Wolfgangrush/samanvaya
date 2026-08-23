# How this was built, and everything that was wrong with it

Written 2026-08-19. This is the engineering record: what the process was, what it caught, and
what it missed until something else caught it. It is kept because the defect list is more useful
than the design document — a design says what was intended, a defect list says what actually
happens when you build it.

## Result

| | |
|---|---|
| Tests | **507 passed, 0 failed** |
| Coverage | **91.1%** line coverage (stdlib tracer; `coverage` was not installed and this build added no packages to the machine it ran on) |
| Upstream cross-attestation | **407 passed** unmodified against the pinned `dpdp-law-to-code` commit |
| Code | 28 files in `src/`, 21 in `tests/` |
| Unsourced-constant markers | 41, every one deliberate, all 20 open questions registered in `verified_facts_brief.md` |
| Ranking vocabulary, plugin discovery, `ruamel`, `NotImplementedError`, dynamic import | 0 of each |

## Method

The plan was written before the code: requirements, architecture, a spec naming five
falsifiers, and a scaffold — all in `../BMAD/`. Then the code. Then a convergence pass
(`../BMAD/06-FILTER.md`) that drags the code back onto the architecture. Then the ship gates.

Two rules did most of the work:

**Acceptance tests were never delegated.** Implementation was; the tests that judge it were not.
A model that writes both the code and its test writes a test that agrees with the code.

**Every statutory constant was verified on the primary text** — the instrument downloaded from
the issuing authority and the provision extracted by string search, with no language model
between the statute and the file. Research assistants proposed constants; none was admitted on
that basis. One of them reported the HIPAA deadline for breaches affecting 500 or more
individuals as "60 calendar days". The rule says the Secretary is notified **contemporaneously**
with the individual notice; the 60 days belongs to a different provision, and separately to an
annual filing. That correction is now recorded inline in the US pack, because the next person to
read it will have the same wrong number in their head.

**A numeric-constant sweep ran on every generated file.** This exists because a citation-pattern
check does not catch a bare number: a model once invented an age threshold of "10" and attributed
it to a facts brief, and a grep for citation shapes passed it clean. Ages, days, hours, months,
years, percentages, currency and CFR/section references are swept separately and adjudicated one
at a time.

## Two adversarial audits

Each reviewer audited only the half it had not written. The first audit returned fifteen
findings: **twelve real, three rejected on evidence.** The second, run after a rename and before
the first push, returned nine: **seven real, two rejected.** Roughly a fifth of what came back
was wrong, which is the error rate to plan for.

The rejections are recorded at the foot of `../tests/test_audit_regressions.py` with reasons, so
nobody re-litigates them. One is worth repeating because both reviewers raised it: an auditor
claimed the ninety-day grievance rule imposes no publication duty. It does — the rule reads
"shall prominently publish on its website or app". The sentence is syntactically incomplete as
printed in the Gazette, which is a drafting infelicity in the instrument and not a transcription
error here.

## The defects

Nineteen in total, itemised with severity and covering test in `../BMAD/06-FILTER.md` Pass 3.
The pattern is worth stating plainly: **almost every one was a false clean bill or a false
accusation.** Not a crash, not a wrong type — a wrong answer about a client, delivered
confidently.

**The ones found by running the code, not by testing it:**

1. **An obligation resolved before the determination it depends on.** An organisation declaring
   it was *not* a Significant Data Fiduciary was reported as having a **gap** on the twelve-monthly
   assessment duty — accused of failing a duty that did not reach it, on the highest-stakes
   obligation in the India rail. The dependency rule was implemented inside one evaluation
   helper, and the one pack that mattered most did not call it. Found by reading the first real
   report.
2. **Eleven of fifteen India obligations reading `not_applicable`** on a 2026 date, correctly,
   because most of the Rules do not commence until 2027 — but with the reason buried eleven
   rationales deep while the summary said only `not_applicable: 11`. A client skimming that
   concludes they have no duties. They do; the duties have not arrived. The report now carries a
   commencement notice above the findings.

**The ones an adversarial reviewer found and the tests did not:**

3. **A rule with a documented condition that the code never evaluated.** The records-of-processing
   derogation is defeated where processing involves special categories, is not occasional, or is
   likely to result in a risk. The pack cited all three carve-outs in its metadata and gated on
   the headcount alone, so a 200-person organisation processing special-category data was told it
   owed no records duty.
4. **A boolean read, a qualifier ignored.** A client declaring it notifies affected individuals
   "only when a data principal complains" was reported **satisfied** against a *without delay*
   duty — the schema carried the trigger field, and the evaluator never looked at it.
5. **A duty gated on the wrong fact.** The children's-data obligation attaches to *processing* a
   child's personal data; it was gated on *offering services to children*. A hospital or a school
   back office — which processes a great deal and offers nothing child-facing — was told the duty
   did not engage.
6. **Commencement ignored entirely**, so clients were reported as failing duties that had not
   commenced.
7. **Fabricated inputs, three times, in the file whose own docstring forbade fabrication** —
   zero-valued risk scores fed to a threshold heuristic, `False` hardcoded for children's tracking
   and targeted advertising, and a substring test standing in for a numeric comparison, so
   `"1" in "21 days"` made twenty-one days satisfy a one-year minimum.
8. **A credential firewall that missed `my_password=`** — `\b` does not match between `_` and a
   letter, because both are word characters.
9. **A statutory count invented by arithmetic** — a limb count derived by subtracting one from an
   unrelated constant.
10. **A lawful-basis duty satisfied by listing purposes.** Having processing purposes is not
    having a lawful basis.

**And the ones that were dead code pretending to be controls:**

11. A path guard that compared a value with itself — a tautology that could never fire, dressed
    as a security check. False assurance is worse than none.
12. A metadata field the unsourced-constant check could not see, so an obligation whose in-force
    date rested on an unsettled publication date reported itself as fully sourced.

## What changed in the design as a result

**The engine enforces the invariants; packs are not trusted to.** In-force filtering, dependency
propagation, the draft downgrade, and the refusal to let an unsourced constant support a verdict
all run in one post-pass that every pack goes through. Each was, at some point in this build,
implemented in a place a pack could bypass — and one did.

**An unsourced *assertion* is distinguished from a stated *caveat*.** An assertion nobody sourced
cannot support a verdict, so the finding becomes `contested`. A caveat qualifies a finding without
disqualifying it. Collapsing the two forced every India obligation to `contested` over a one-day
question about a publication date, and gutted the one rail whose substance is fully sourced.

**Undeclared is not the same as declared-absent, anywhere.** Most of the defects above are one
instance of this. "The client said no" is a gap; "the client did not say" is contested; and a
tool that conflates them either accuses a client falsely or clears them falsely.

## Known limits

- The runtime network guard is a **tripwire, not a proof**. A C extension can open a socket
  without going through it. The real assurance is the install-time dependency audit, which fails
  closed on any package it does not recognise.
- The cut-over criterion is **unmet on every rail**. Two of its three limbs hold for India — the
  upstream suite passes unmodified and the adapter's contract check passes — but the third
  requires a human to verify the output on one real engagement, and that has not happened.
- Four of six rails ship `draft` because their constants could not be read on a primary source.
  A draft pack can never emit `satisfied`.
