# BMAD-SPEC — intake: the sectioned interview and the questionnaire

**Date:** 2026-08-22
**Owner:** the maintainer
**Discipline:** the maintainer owns every acceptance test and the verify.
**Supersedes:** `07-BMAD-SPEC-desktop-app.md` §"v1 deferred" item 5, which was wrong.

## Why this exists

The window shipped as a file picker for a file nothing in the application could create. The
adviser was asked to supply a declaration — an 83-field JSON document — and nothing anywhere
in the product would produce one. The 83 questions existed the whole time, in the CLI, unused
by the surface the user actually opens.

This was known. `agents/felix/.../2026-08-18-...` recorded *"the tool currently has no real
user interface, since nobody hand-fills a 78-field JSON"* four days before the window shipped
without it, and the spec that shipped it listed declaration authoring under "v1 deferred".

**The deferral rule, corrected:** an item may be deferred only if it is possible to name who
or what does that job in the meantime. For declaration authoring the answer was nobody, which
means it was never a deferral — it was a hole.

## THE GOVERNING DISTINCTION — input and output are different documents

The maintainer's instruction, 2026-08-22: *"the input part of the app and the output part of
the app will be different.. the report will be different."*

This is the design's spine and neither surface may drift into the other:

| | **The questionnaire** | **The conformance report** |
|---|---|---|
| Purpose | Gather facts | State findings against declared facts |
| Audience | The client, or the adviser taking notes | The client, as an annexure to advice |
| Contains | Questions, the reason for each, blank space | Verdicts, instruments, provisions |
| Never contains | A verdict, a finding, an opinion | A blank, a question, an invitation |
| When | Before the engagement | After the engine has run |

They share exactly one thing: **the preparer letterhead**. Nothing else.

> **AMENDED 2026-08-22 (build 2) — see `09-BMAD-SPEC-house-style.md`.** They now also share
> the HOUSE STYLE: the wordmark, the palette, the fonts, the running head and foot. Two
> documents from one firm that do not look related is its own failure. The boundary this
> paragraph was protecting is unchanged and is now *enforced* rather than observed — the
> shared module carries no verdict vocabulary and no colour keyed to a finding, so the
> questionnaire cannot reach one. Two renderers, two layouts, one letterhead: still true. Two renderers, two
layouts, two sets of rules. A questionnaire that hints at a verdict has pre-judged the
client; a report with blanks in it is unfinished work on an advocate's letterhead.

## A — the questionnaire PDF

### Solution shape
The application renders every question in `interview.QUESTIONS` as a blank questionnaire on
the preparer's letterhead. The adviser emails it before the meeting or prints it for the room.

> **AMENDED 2026-08-22 (build 2).** Item A shipped as a renderer with **no caller** — no CLI
> subcommand, no menu item, no button. Dead code, not a hidden feature. It is now reachable
> as `samanvaya questionnaire --out FILE` and as **File > Blank Questionnaire (PDF)** in the
> window. The deferral rule in the section above applies to this too, and gives the same
> answer: nobody was doing that job, so it was never a deferral.

### Ships
1. Grouped under the nine section headings, in `QUESTIONS` order.
2. Each question shows its `prompt` and, beneath it in a lighter register, its `why`. The
   `why` is the whole point: it tells a founder why an odd question is being asked, and it
   tells the adviser what turns on the answer.
3. Ruled writing space sized to the question kind — a yes/no needs a line, a list needs five.
4. Letterhead from the same `Preparer` the report uses. Never a second letterhead store.
5. A cover note stating what the document is, that it is not advice, and that a blank answer
   is a legitimate answer that will be reported as unresolved rather than guessed at.
6. Offline, deterministic, fpdf2, core fonts — the same constraints as the report.

### Banned
- Any verdict vocabulary. The existing AST test applies here too.
- Any question not present in `interview.QUESTIONS`. **One source.** If the questionnaire and
  the form could drift, the adviser would be asking questions the engine cannot consume.

## B — the sectioned interview in the window

> **BUILT 2026-08-22 (build 3).** `src/samanvaya/form.py` (headless model) +
> `src/samanvaya/form_view.py` (the window), reachable as **File > New Intake Form** and
> the button beside Generate. Built against acceptance tests authored here first and
> committed before any implementation. §D below is STILL NOT MET —
> it is met by a person, not a test; see `10-BMAD-SPEC-intake-part-b.md`.

### Solution shape
Nine pages, one per section, every question in a section visible at once with its `why`
beside it. The adviser moves between sections freely, because a client answers out of order
and the adviser circles back. Produces the declaration JSON the engine already reads.

### Ships
1. Section navigation, jumpable in any order — not a forced linear wizard.
2. Per-question widget by `kind`: `bool` as Yes / No / **Not established**, `int` and `float`
   as validated entries, `str` as an entry, `list` as comma-separated with a hint.
3. **"Not established" is a first-class answer and the default.** It is not a blank. The
   engine treats an undeclared fact as `contested`, which is the honest verdict, and the
   form must never coerce a guess to fill a field.
4. Per-section progress ("12 of 17 answered") and a total.
5. **Autosave to a working file after every change.** A two-hour client meeting must survive
   a crash, a battery, or a closed lid.
6. Resume: reopen a part-finished declaration and continue.
7. Save produces a declaration the engine loads without complaint; the same credential
   firewall that guards the letterhead guards every free-text answer.
8. A jurisdictions step, since the declaration needs countries and `QUESTIONS` does not cover
   them.

### Banned
- No new dependency. Tkinter only.
- No inference. The form never fills one answer from another, never defaults a statutory
  fact to a convenient value, and never hides a question because an earlier answer made it
  seem unlikely.
- No verdicts. The form gathers; it does not assess.

## Build order
1. Acceptance tests for A, authored by the maintainer, failing.
2. A implemented, green, and a real questionnaire opened and read.
3. Acceptance tests for B, failing.
4. B implemented, green.
5. The whole loop run once by hand: interview → save → generate → report.

## D — cut-over criterion
Intake is done when the maintainer produces a conformance report for a real engagement
**without ever opening a JSON file or a terminal**. Until that has happened once, this is
built but not proven.
