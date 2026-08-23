"""The blank questionnaire — the INPUT document.

It is what an adviser prints or emails to a client a week before the meeting so the
client can write answers on it by hand. The adviser then types those answers into the
application. It must never become a second, smaller copy of the conformance report.

The product already has a conformance report renderer. This is not a variant of it.
The report states findings against declared facts; the questionnaire asks for the facts
and states nothing. A questionnaire carrying a verdict has pre-judged a client before
they have answered. A report carrying blanks is unfinished work on an advocate's
letterhead.

WHAT THE TWO DOCUMENTS SHARE
----------------------------
`BMAD/08` said "the preparer letterhead, and nothing else". As of build 2 they also
share the house style in :mod:`samanvaya.pdf_theme` — the wordmark, the palette, the
fonts, the running head and foot — because two documents from one firm that do not look
related is its own failure.

The boundary that sentence was protecting is unchanged and is now enforced rather than
observed: the house style contains no verdict vocabulary and no colour keyed to a
finding, so there is nothing here to reach for. A test asserts it.

ONE SOURCE
----------
Every question printed comes from :data:`samanvaya.interview.QUESTIONS`. The prompt and
the reason are copied VERBATIM. Re-typing, paraphrasing, reordering or inventing would
let the questionnaire drift from the engine, and the mismatch would only surface on the
day it wasted a meeting.

WHY A YES/NO QUESTION GETS BOXES AND NOT A LINE
-----------------------------------------------
"Not established" is a first-class answer. The engine treats an undeclared fact as
contested and reports it rather than guessing, which is the honest result — but a client
handed an empty rule under a yes/no question will write "yes" or "no", because those are
the only two answers the paper appears to allow. Printing the third box is what makes the
honest answer available to someone who is not going to read a paragraph about it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import cast

from samanvaya.interview import QUESTIONS
from samanvaya.pdf_theme import (
    BRASS,
    INK,
    INK_MUTED,
    INK_SOFT,
    NAVY,
    RULE,
    RULE_SOFT,
    SANS,
    SERIF,
    TINT,
    HouseStylePDF,
    Preparer as Preparer,
    latin1,
)
from samanvaya.report import _check_target

# ``answer_lines`` sizes the ruled writing space to the kind of answer expected. A
# yes/no genuinely is a single line; an integer or a number on a small scale likewise.
# A short free-text string (a legal form, a role title) usually needs two lines so the
# client does not feel squeezed at the margin. A list of recipients, processors or
# safeguards needs several lines because the client will be writing several items by
# hand, often one per line. These are deliberately conservative: cramped questionnaires
# produce cramped answers.
#
# For a ``bool`` the number is a height budget rather than a count of rules: the answer
# is drawn as three boxes on one line, and one line is what it needs.
_ANSWER_LINES: dict[str, int] = {
    "bool": 1,
    "int": 1,
    "float": 1,
    "str": 2,
    "list": 5,
}

#: The three answers offered for a yes/no question. Order matters: the honest answer
#: comes last so it does not read as the suggested one, and it is present so it does
#: not read as unavailable.
_BOOLEAN_CHOICES: tuple[str, str, str] = ("Yes", "No", "Not established")


@dataclasses.dataclass(frozen=True)
class QuestionnaireItem:
    """One question block on the printed page.

    The prompt and the reason are copied VERBATIM from the matching
    :class:`samanvaya.interview.Question`. The questionnaire must not paraphrase the
    prompt, because the adviser is expected to be able to read it aloud to a client
    and have the answer it receives still parse against the engine. The reason is
    copied so the client can answer a refusal with a reason rather than a guess.

    ``number`` is the question's position across the whole document, not within its
    section, so that an adviser and a client on a telephone can both say "question 41".
    """

    path: str
    prompt: str
    why: str
    kind: str
    answer_lines: int
    number: int
    choices: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class QuestionnaireSection:
    """A human-facing heading followed by every question in that block."""

    title: str
    items: tuple[QuestionnaireItem, ...]


COVER_NOTE: str = (
    "This document is a blank questionnaire prepared by the firm named above. It is "
    "not legal advice, and nothing in it is a view about your organisation. The "
    "questions are the facts the firm needs before it can advise you. Write your "
    "answer in the ruled space under each question, or tick a box where boxes are "
    "given. If a question does not apply, or you do not know the answer, leave it "
    "blank or tick 'Not established'. That is a real answer: an undeclared fact is "
    "reported as unresolved rather than guessed at, and a guess is worse than an "
    "unresolved answer. Bring the completed form to the meeting, or email it back, "
    "whichever is easier."
)

#: What to do with the form, for a reader who has been emailed a PDF with no covering
#: message. Three steps, because a numbered list is read and a paragraph is skimmed.
_STEPS: tuple[str, ...] = (
    "Answer what you can. Nobody is expected to know all of it.",
    "Leave anything you are unsure about blank, or tick 'Not established'.",
    "Return the form before the meeting so the time is spent on advice, not intake.",
)

_TITLE: str = "Pre-meeting Questionnaire"
_INTAKE_LABEL: str = "Intake"
_WHY_LABEL: str = "Why we ask"
_STEPS_LABEL: str = "What to do with this form"
_PARTICULARS_LABEL: str = "For completion by"
_PARTICULARS_FIELDS: tuple[str, ...] = ("Client", "Completed by", "Date")
_NOTES_LABEL: str = "Anything else worth telling us"
_NOTES_HINT: str = (
    "Use this space for anything the questions above did not cover."
)
_FOOT_NOTE: str = "Blank answers are accepted"
_EMPTY_SECTION: str = "No questions in this section."

#: Every string this module writes itself, as opposed to the prompts and reasons it
#: quotes verbatim from the question bank. The ban on verdict vocabulary applies to
#: this list, and a test walks it.
AUTHORED_TEXT: tuple[str, ...] = (
    COVER_NOTE,
    _TITLE,
    _INTAKE_LABEL,
    _WHY_LABEL,
    _STEPS_LABEL,
    _PARTICULARS_LABEL,
    _NOTES_LABEL,
    _NOTES_HINT,
    _FOOT_NOTE,
    _EMPTY_SECTION,
    *_STEPS,
    *_PARTICULARS_FIELDS,
    *_BOOLEAN_CHOICES,
)


def questionnaire_sections() -> list[QuestionnaireSection]:
    """Build the in-memory model from :data:`samanvaya.interview.QUESTIONS`.

    The order of sections and the order of items within each section are both taken
    from ``QUESTIONS`` itself. Sections appear in the order they are first
    encountered; items appear in the order in which the interview presents them.
    No question is dropped, none is added, none is rewritten.
    """
    by_section: dict[str, list[QuestionnaireItem]] = {}
    section_order: list[str] = []
    number = 0
    for question in QUESTIONS:
        if question.section not in by_section:
            by_section[question.section] = []
            section_order.append(question.section)
        number += 1
        by_section[question.section].append(
            QuestionnaireItem(
                path=question.path,
                prompt=question.prompt,
                why=question.why,
                kind=question.kind,
                answer_lines=_ANSWER_LINES.get(question.kind, 2),
                number=number,
                choices=_BOOLEAN_CHOICES if question.kind == "bool" else (),
            )
        )
    return [
        QuestionnaireSection(title=title, items=tuple(by_section[title]))
        for title in section_order
    ]


class _QuestionnairePDF(HouseStylePDF):
    """The questionnaire's pages: a cover, then sections of questions.

    A separate class from the report's, deliberately. They inherit the same page
    furniture and share no layout: this one has a gutter for question numbers, ruled
    writing space and answer boxes, and no table renderer at all.
    """

    DOC_TITLE = _TITLE
    FOOT_NOTE = _FOOT_NOTE

    #: Width of the left gutter the question number sits in. The prompt, the reason and
    #: the writing space all align to its right edge, which is what makes a page of
    #: eighty-three questions scannable rather than a wall.
    GUTTER: float = 10.0
    #: Vertical distance between ruled writing lines. Below about 6.5mm an adult's
    #: handwriting collides with the rule above it.
    RULE_GAP: float = 7.0
    BOX: float = 3.4

    @property
    def body_left(self) -> float:
        """The x every question's content aligns to."""
        return self.l_margin + self.GUTTER

    @property
    def body_width(self) -> float:
        """Width available to a question's content, right of the gutter."""
        return self.usable_width - self.GUTTER

    # ----------------------------------------------------------------- cover page

    def render_cover(self) -> None:
        total = sum(len(s.items) for s in questionnaire_sections())
        sections = len(questionnaire_sections())

        self.wordmark(20.0)
        self.set_y(self.get_y() + 18.0)

        self.eyebrow(_INTAKE_LABEL)
        self.set_font(SERIF, "B", 25.0)
        self.ink(NAVY)
        self.cell(0, 12.0, latin1(_TITLE), new_x="LMARGIN", new_y="NEXT")
        self.set_font(SERIF, "I", 11.0)
        self.ink(INK_SOFT)
        self.cell(
            0,
            6.5,
            latin1(f"{total} questions in {sections} sections"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.set_y(self.get_y() + 7.0)

        self._particulars()
        self.set_y(self.get_y() + 7.0)

        self.letterhead_block()
        self.set_y(self.get_y() + 2.0)

        self.eyebrow(_STEPS_LABEL)
        self.set_y(self.get_y() + 1.0)
        for index, step in enumerate(_STEPS, start=1):
            # Re-anchor to the margin every iteration. `multi_cell` leaves the cursor at
            # the RIGHT edge of the cell it just drew, so without this each step started
            # a full column further right than the one above it and the third ran off
            # the paper entirely — text present in the file, absent from the page.
            self.set_x(self.l_margin)
            self.set_font(SANS, "B", 8.6)
            self.ink(BRASS)
            self.cell(6.0, 5.4, latin1(f"{index}"), new_x="RIGHT", new_y="TOP")
            self.set_font(SERIF, "", 9.4)
            self.ink(INK)
            self.multi_cell(self.usable_width - 6.0, 5.4, latin1(step))
        self.set_y(self.get_y() + 5.0)

        self.note_panel(COVER_NOTE, size=8.6)

    def _particulars(self) -> None:
        """Draw the three fill-in fields a returned form has to carry.

        Without them a stack of completed questionnaires on a desk is anonymous, and
        the one fact an adviser needs first — whose answers these are — is the one the
        form does not ask for.
        """
        height = len(_PARTICULARS_FIELDS) * 9.0 + 9.0
        top = self.get_y()
        self.panel(self.l_margin, top, self.usable_width, height, fill=TINT)
        self.hairline(top, colour=NAVY, width=0.5)
        self.set_xy(self.l_margin + 5.0, top + 4.0)
        for field in _PARTICULARS_FIELDS:
            y = self.get_y()
            self.set_x(self.l_margin + 5.0)
            self.set_font(SANS, "", 7.4)
            self.ink(INK_SOFT)
            self.set_char_spacing(0.7)
            self.cell(28.0, 6.0, latin1(field.upper()), new_x="RIGHT", new_y="TOP")
            self.set_char_spacing(0.0)
            self.hairline(
                y + 5.6,
                colour=RULE,
                width=0.2,
                x_from=self.l_margin + 34.0,
                x_to=self.w - self.r_margin - 5.0,
            )
            self.set_xy(self.l_margin + 5.0, y + 9.0)
        self.set_y(top + height)

    # ------------------------------------------------------- sections + questions

    def render_section(self, section: QuestionnaireSection, index: int, total: int) -> None:
        # A heading with nothing under it is a heading at the foot of a page. Reserve
        # the heading plus a first question before committing to this page.
        self.ensure_room(46.0)
        self.eyebrow(f"Section {index} of {total}")
        self.set_font(SERIF, "B", 15.0)
        self.ink(NAVY)
        self.cell(0, 8.0, latin1(section.title), new_x="LMARGIN", new_y="NEXT")
        self.set_font(SANS, "", 7.8)
        self.ink(INK_MUTED)
        count = len(section.items)
        self.cell(
            0,
            4.6,
            latin1(f"{count} question{'s' if count != 1 else ''}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.set_y(self.get_y() + 1.4)
        self.hairline(self.get_y(), colour=BRASS, width=0.6)
        self.set_y(self.get_y() + 5.0)

        if not section.items:
            self.body(_EMPTY_SECTION, size=9.2, colour=INK_SOFT, style="I")
            return
        for item in section.items:
            self._render_item(item)

    def _render_item(self, item: QuestionnaireItem) -> None:
        """Draw one question: number, prompt, reason, answer space.

        A question and its writing space must never split across a page — a client
        looking at four ruled lines with no question above them will either skip them
        or answer the wrong one. The height is measured first and the whole block is
        pushed to the next page if it will not fit.
        """
        prompt_height = self._measure(item.prompt, SERIF, "", 10.4, 5.2)
        why_height = self._measure(item.why, SANS, "I", 8.0, 4.4)
        answer_height = (
            self.RULE_GAP if item.choices else item.answer_lines * self.RULE_GAP
        )
        self.ensure_room(prompt_height + why_height + answer_height + 12.0)

        top = self.get_y()
        self.set_font(SANS, "B", 9.4)
        self.ink(BRASS)
        self.set_xy(self.l_margin, top)
        self.cell(self.GUTTER, 5.4, latin1(str(item.number)), new_x="RIGHT", new_y="TOP")

        self.set_xy(self.body_left, top)
        self.set_font(SERIF, "", 10.4)
        self.ink(INK)
        self.multi_cell(self.body_width, 5.2, latin1(item.prompt))
        self.set_y(self.get_y() + 1.6)

        why_top = self.get_y()
        self.set_xy(self.body_left + 3.0, why_top)
        self.set_font(SANS, "I", 8.0)
        self.ink(INK_SOFT)
        self.multi_cell(self.body_width - 3.0, 4.4, latin1(f"{_WHY_LABEL}: {item.why}"))
        # A brass edge beside the reason, so the eye can tell at a glance which text is
        # the question and which is the explanation for it.
        self.set_draw_color(*BRASS)
        self.set_line_width(0.5)
        self.line(self.body_left, why_top + 0.6, self.body_left, self.get_y() - 0.6)
        self.set_line_width(0.2)

        self.set_y(self.get_y() + 2.6)
        if item.choices:
            self._render_choices(item.choices)
        else:
            self._render_rules(item.answer_lines)
        self.set_y(self.get_y() + 4.0)

    def _render_choices(self, choices: tuple[str, ...]) -> None:
        """Draw one row of tick boxes."""
        y = self.get_y()
        x = self.body_left
        self.set_font(SANS, "", 9.0)
        for choice in choices:
            self.set_draw_color(*RULE)
            self.set_line_width(0.3)
            self.rect(x, y + 0.6, self.BOX, self.BOX)
            self.set_line_width(0.2)
            self.ink(INK)
            self.set_xy(x + self.BOX + 2.0, y)
            width = self.get_string_width(latin1(choice)) + 9.0
            self.cell(width, 5.0, latin1(choice), new_x="RIGHT", new_y="TOP")
            x += self.BOX + 2.0 + width
        self.set_xy(self.l_margin, y + self.RULE_GAP)

    def _render_rules(self, count: int) -> None:
        """Draw ``count`` writing guides in the lightest rule the palette has.

        Light on purpose: a dark rule competes with the client's own handwriting, and
        a form whose lines are heavier than the ink on them reads as a bureaucratic
        object rather than as something a person is meant to write on.
        """
        y = self.get_y()
        for index in range(count):
            self.hairline(
                y + (index + 1) * self.RULE_GAP - 1.5,
                colour=RULE_SOFT,
                width=0.25,
                x_from=self.body_left,
            )
        self.set_xy(self.l_margin, y + count * self.RULE_GAP)

    def render_notes(self) -> None:
        """Close the form with open space.

        Every intake form of this length misses something, and a client who has just
        answered eighty-three questions is the person best placed to say what.
        """
        self.ensure_room(70.0)
        self.set_y(self.get_y() + 4.0)
        self.eyebrow(_NOTES_LABEL)
        self.set_font(SANS, "I", 8.0)
        self.ink(INK_SOFT)
        self.multi_cell(self.usable_width, 4.4, latin1(_NOTES_HINT))
        self.set_y(self.get_y() + 3.0)
        y = self.get_y()
        lines = int((self.content_bottom - y - 4.0) // self.RULE_GAP)
        for index in range(max(lines, 4)):
            self.hairline(
                y + (index + 1) * self.RULE_GAP - 1.5, colour=RULE_SOFT, width=0.25
            )

    # -------------------------------------------------------------------- helpers

    def _measure(
        self, text: str, font: str, style: str, size: float, leading: float
    ) -> float:
        """Return the drawn height of ``text`` wrapped to the body column."""
        self.set_font(font, style, size)
        height = self.multi_cell(
            self.body_width,
            leading,
            latin1(text),
            border=0,
            align="L",
            new_x="RIGHT",
            new_y="TOP",
            dry_run=True,
            output="HEIGHT",
        )
        # See the note in `pdf_report.draw_table`: `dry_run=True` alone returns a BOOL
        # (whether a page break fired), not a height. `output="HEIGHT"` is what makes
        # this a measurement, and the cast names the mode.
        return float(cast(float, height))


def render_questionnaire(out: Path, preparer: Preparer) -> None:
    """Write the blank questionnaire to ``out`` as a PDF.

    The target is validated by :func:`samanvaya.report._check_target`: the parent
    directory must exist and be a real directory; a symlink or an existing
    non-regular file is refused with :class:`ValueError`. The renderer uses only
    the core fonts and makes no network calls.

    The document is a cover page — wordmark, title, the fields a returned form has to
    carry, the letterhead, what to do with it, and the cover note — followed by the
    nine sections. The running head and foot start on the page after the cover.
    """
    _check_target(out)
    pdf = _QuestionnairePDF(preparer)
    pdf.add_page()
    pdf.render_cover()

    sections = questionnaire_sections()
    pdf._chrome = True
    pdf.add_page()
    for index, section in enumerate(sections, start=1):
        pdf.render_section(section, index, len(sections))
    pdf.render_notes()
    pdf.output(str(out))
