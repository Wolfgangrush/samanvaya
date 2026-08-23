# BMAD-SPEC — the house style, and the questionnaire's missing caller

**Date:** 2026-08-22
**Owner:** the maintainer
**Build:** 0.2.0, build 2
**Amends:** `08-BMAD-SPEC-intake.md` §"THE GOVERNING DISTINCTION", one clause only.

**Process note, stated rather than hidden:** this document was written *after* the build,
not before it. BMAD's rule is the plan first, and this was a design pass on two existing
renderers rather than a new component, so it ran as a TDD cycle with the acceptance tests
first and the spec written up at the end. Read it as a record of what was decided and why,
not as a gate that was passed.

## Why this exists

The maintainer read the first questionnaire the way a client would and the verdict was
"too generic, too black and white — same with the report".

That is not a matter of taste on these two documents. One goes to a client as an annexure
to legal advice; the other goes out over an advocate's name a week before a meeting. A
deliverable that looks unconsidered invites the reader to treat its contents the same way,
and the contents are the whole product. Both were drawn in a single core font, pure black
on pure white, every table cell boxed — the look a program has when nobody has decided how
it should look.

## A — the house style

### Solution shape
`src/samanvaya/pdf_theme.py`. A module rather than a habit, because a habit drifts between
two renderers and a module cannot. Both documents subclass `HouseStylePDF`.

### Ships
1. **A palette**: a deep navy primary, a single brass accent, and neutrals. Two colours
   plus neutrals is a palette; a third is decoration competing with content.
2. **Paired core fonts**: a serif for anything read in sentences, a sans for the system
   layer that labels and frames it, a monospace for a hash compared character by
   character. No font is embedded — see "Banned".
3. **Page furniture**: cover page, running head, running foot with `Page N of M`, section
   eyebrows, hairline rules, tinted panels, letterhead block.
4. **One sanitiser.** There were two, one per renderer, and they disagreed: the report
   mapped `U+00B7` and the questionnaire did not, so the same middle dot survived one
   document and became a substitution mark in the other.
5. **One `Preparer`.** Moved here from `pdf_report` and re-exported, so the module that
   holds the shared letterhead is named for what it is. Every existing import still works.

### The amendment to BMAD/08
`08` said the two documents share *"exactly one thing: the preparer letterhead"*. They now
also share the house style. Two documents from one firm that do not look related is its own
failure, and it is the failure this build was opened to fix.

The boundary that sentence was protecting is **unchanged**, and is now enforced instead of
observed: the house style contains **no verdict vocabulary and no colour keyed to a
finding**. Those live in `pdf_report`, the only place in the product where a finding
exists. The questionnaire cannot reach a verdict colour because there is not one to reach.
`tests/test_pdf_theme.py` and `tests/test_questionnaire.py` both assert it.

### Banned
- **No embedded font.** An embedded typeface is a redistribution licence to audit inside a
  tool a lawyer hands to clients, and the single-file binary would carry it. The
  professional register is bought with typography, colour and space instead. If the
  Devanagari wordmark is ever wanted on the page, it needs a licensed font first —
  silently substituting question marks is not the compromise.
- **No new dependency.** fpdf2 and the standard library.
- **No network, no image, no remote asset.** Unchanged from `04`.

## B — colour, and the hazard it introduced

Colour was added to end the black-and-white look. Adding colour to a document that reports
legal findings creates a hazard the black-and-white version did not have: a reader can take
a hue as the message, and the one message this tool refuses to send is that an unresolved
finding is a failure.

Three rules answer it. Each is a test, not a convention.

1. **The verdict word is always printed.** Colour repeats what the word says and never
   replaces it. A monochrome printout and a colour-blind reader lose decoration and no
   information.
2. **No verdict is drawn in a red hue** (asserted against the 345°–15° band). A gap is an
   obligation the declared facts leave unaddressed. It is not an alarm, and red would
   report an assessment this tool does not make.
3. **Unresolved is the least saturated of the three.** A neutral slate, quieter than a gap,
   because an unresolved finding is a fact not supplied rather than a finding against the
   client.

Every colour carrying text is held to a WCAG 2.1 contrast floor against the paper — 4.5:1
at normal size, 3:1 at 14pt bold or larger. An objective standard rather than taste, and
what makes the palette survive a bad office printer.

**And no tally by verdict, anywhere.** The cover states what the run was — as-at date,
jurisdictions, obligations examined, tool build, declaration hash. A count of satisfied
obligations beside a count of gaps is a score, and a score invites the comparison between
jurisdictions this tool exists to refuse.

## C — "How to read this report"

A page before the first table, explaining the five verdict words in plain English.

It is not decoration. The five words look like ordinary English and are not. "Unresolved"
reads as a criticism to anyone who has not been told otherwise, and the whole tool exists
to stop that reading. It is now stated once, plainly, before any table — including the
sentence *"This is not a finding against the client"*, which is asserted by a test.

## D — the questionnaire's missing caller

`render_questionnaire` shipped with **no call site anywhere**: no CLI subcommand, no menu
item, no button. Not a hidden feature — dead code. The only way to produce the document an
adviser is supposed to send a client was to import the module at a Python prompt.

This is the defect `08` was written to correct, one layer down. The window shipped as a
file picker for a file nothing could create; the questionnaire shipped as a renderer
nothing could reach.

**The deferral rule, applied again:** an item may be deferred only if it is possible to
name who does that job in the meantime. For both of these the answer was nobody, which
means neither was a deferral. Both were holes.

### Ships
1. `samanvaya questionnaire --out FILE`, with the same letterhead flags and the same
   fallback to the saved profile as the report.
2. **File → Blank Questionnaire (PDF)** and a button beside Generate. It takes no
   declaration, because it is the document that produces one.
3. The credential firewall runs on the letterhead **before** anything is written, so a
   refused run leaves no file behind.

## E — what the tests hold, that the old ones could not

The content-model tests assert what the tool DECIDED. They are silent on what the reader
SEES, and this build found two defects in that gap:

- **The margin-overrun guard.** `multi_cell` leaves the cursor at the RIGHT edge of the
  cell it drew. The questionnaire's three-step list re-measured its width from there, so
  each step started a full column further right and the third ran clean off the paper.
  Every test passed. The text was in the file and absent from the page. A spy on `cell`
  and `multi_cell` now asserts that no draw call is asked to reach past the right margin,
  in either document.
- **The widget smoke test.** On 2026-08-20 a build shipped that died on launch with
  `AttributeError: module 'tkinter.ttk' has no attribute 'Menu'` while all 589 tests
  passed, because not one constructed a widget. The launch gate added in response proves
  the window OPENS and never clicks anything. One test now builds the real window, clicks
  the new button, and requires a file on disk. It skips where there is no display.

Both are the same lesson arriving through different doors, and it is the lesson the row
geometry tests learned first: **proving the model is not proving the artefact.**

## F — cut-over criterion

`08`'s criterion stands and is still unmet: intake is done when the maintainer produces a
conformance report for a real engagement **without ever opening a JSON file or a terminal**.
`08` part B — the sectioned interview inside the window — remains unbuilt, and until it
lands the questionnaire can be handed out but its answers still have to be typed in through
the CLI.

This build makes both documents fit to send. It does not close `08` part B.
