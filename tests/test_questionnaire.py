"""Acceptance tests for the blank questionnaire.

Authored BEFORE the implementation.

The questionnaire is the INPUT artefact. It exists because the adviser needs something to
put in front of a client — on paper, or emailed a week ahead — and because the window
shipped as a file picker for a file nothing in the product could create.

It is not a small variant of the conformance report and must never become one. The report
states findings against declared facts; the questionnaire asks for the facts and states
nothing. They share the preparer letterhead and nothing else. A questionnaire carrying a
verdict has pre-judged a client before they have answered; a report carrying blanks is
unfinished work on an advocate's letterhead.

The single hardest rule here is ONE SOURCE. Every question printed must come from
`interview.QUESTIONS`, because a questionnaire that drifts from the interview would have the
adviser asking a client questions the engine cannot consume, and the mismatch would only
surface on the day it wasted a meeting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samanvaya.interview import QUESTIONS
from samanvaya.pdf_report import Preparer


@pytest.fixture
def preparer() -> Preparer:
    return Preparer(
        firm="Example & Co, Advocates",
        adviser="A. Adviser",
        email="adviser@example.com",
        phone="+91 00000 00000",
    )


class TestTheContentModel:
    def test_it_returns_one_group_per_section(self) -> None:
        from samanvaya.questionnaire import questionnaire_sections

        sections = questionnaire_sections()
        assert {s.title for s in sections} == {q.section for q in QUESTIONS}

    def test_every_question_appears_exactly_once(self) -> None:
        """Nothing may be dropped: an unasked question becomes an unresolved finding."""
        from samanvaya.questionnaire import questionnaire_sections

        printed = [item.path for s in questionnaire_sections() for item in s.items]
        assert sorted(printed) == sorted(q.path for q in QUESTIONS)
        assert len(printed) == len(set(printed))

    def test_no_question_is_invented(self) -> None:
        """ONE SOURCE. The questionnaire may not ask anything the engine cannot consume."""
        from samanvaya.questionnaire import questionnaire_sections

        known = {q.path for q in QUESTIONS}
        for section in questionnaire_sections():
            for item in section.items:
                assert item.path in known, f"invented question: {item.path}"

    def test_each_item_carries_the_prompt_and_the_reason(self) -> None:
        """The `why` is the point: it tells a founder why an odd question is being asked."""
        from samanvaya.questionnaire import questionnaire_sections

        by_path = {q.path: q for q in QUESTIONS}
        for section in questionnaire_sections():
            for item in section.items:
                source = by_path[item.path]
                assert item.prompt == source.prompt
                assert item.why == source.why
                assert item.why.strip(), f"{item.path} has no reason given"

    def test_sections_keep_the_interview_order(self) -> None:
        from samanvaya.questionnaire import questionnaire_sections

        seen: list[str] = []
        for q in QUESTIONS:
            if q.section not in seen:
                seen.append(q.section)
        assert [s.title for s in questionnaire_sections()] == seen

    def test_writing_space_is_sized_to_the_answer(self) -> None:
        """A yes/no needs a line. A list of recipients needs several."""
        from samanvaya.questionnaire import questionnaire_sections

        by_kind: dict[str, int] = {}
        for section in questionnaire_sections():
            for item in section.items:
                by_kind.setdefault(item.kind, item.answer_lines)
                assert item.answer_lines >= 1, item.path
        assert by_kind.get("list", 0) > by_kind.get("bool", 99), (
            "a list answer is given no more room than a yes/no"
        )

    def test_the_model_is_deterministic(self) -> None:
        from samanvaya.questionnaire import questionnaire_sections

        a = [(s.title, tuple(i.path for i in s.items)) for s in questionnaire_sections()]
        b = [(s.title, tuple(i.path for i in s.items)) for s in questionnaire_sections()]
        assert a == b


class TestItStatesNothing:
    """The questionnaire asks. It does not assess, hint, or conclude."""

    BANNED = (
        "compliant", "non-compliant", "pass", "fail", "at risk", "safe",
        "violation", "breach of law", "you should", "we recommend",
    )

    def test_no_verdict_vocabulary_in_text_the_questionnaire_itself_authors(self) -> None:
        """The ban applies to what this module WRITES, not to what it quotes.

        Corrected after the first run. The original scanned prompt and why text too, and
        was wrong twice over. "safe" matched inside "safeguards" — a plain substring
        accident. And "fail" matched in a question's stated reason: *"Bundled or
        pre-checked consent fails GDPR Art. 7(2)."* That is a statement about the LAW,
        which is precisely what a `why` exists to give the adviser, and the ONE SOURCE
        rule requires it be copied verbatim. The test as written could only have been
        satisfied by paraphrasing the question bank, which is the more important rule.

        What the rule actually protects is narrower and still worth guarding: this
        document must never state a verdict about THIS CLIENT. Section headings and the
        cover note are authored here, so they are held to it. Question text is quoted
        from a vetted bank and is checked for verbatim fidelity elsewhere.
        """
        import re

        from samanvaya.questionnaire import questionnaire_sections

        authored = " ".join(s.title for s in questionnaire_sections()).lower()
        for word in self.BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", authored), (
                f"{word!r} appears in a heading this module authors"
            )

    def test_the_cover_note_says_a_blank_is_a_real_answer(self) -> None:
        """A guessed answer is worse than none: unresolved is the honest verdict."""
        from samanvaya.questionnaire import COVER_NOTE

        lowered = COVER_NOTE.lower()
        assert "unresolved" in lowered or "not established" in lowered
        assert "not legal advice" in lowered

    def test_the_cover_note_does_not_state_a_conclusion(self) -> None:
        """Word boundaries, not substrings: "safeguards" must not trip "safe"."""
        import re

        from samanvaya.questionnaire import COVER_NOTE

        lowered = COVER_NOTE.lower()
        for word in self.BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", lowered), word


class TestRendering:
    def test_it_writes_a_real_pdf(self, preparer: Preparer, tmp_path: Path) -> None:
        from samanvaya.questionnaire import render_questionnaire

        out = tmp_path / "questionnaire.pdf"
        render_questionnaire(out, preparer)
        assert out.read_bytes()[:5] == b"%PDF-"
        assert out.stat().st_size > 5000, "83 questions cannot fit in a tiny file"

    def test_it_writes_without_a_preparer(self, tmp_path: Path) -> None:
        from samanvaya.questionnaire import render_questionnaire

        out = tmp_path / "q.pdf"
        render_questionnaire(out, Preparer())
        assert out.read_bytes()[:5] == b"%PDF-"

    def test_it_runs_to_several_pages(self, preparer: Preparer, tmp_path: Path) -> None:
        """83 questions with room to write cannot honestly fit on one page."""
        from samanvaya.questionnaire import render_questionnaire

        out = tmp_path / "q.pdf"
        render_questionnaire(out, preparer)
        raw = out.read_bytes()
        pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
        assert pages >= 3, f"rendered onto {pages} page(s)"

    def test_it_refuses_to_write_through_a_symlink(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        from samanvaya.questionnaire import render_questionnaire

        elsewhere = tmp_path / "elsewhere.pdf"
        elsewhere.write_bytes(b"original")
        (tmp_path / "q.pdf").symlink_to(elsewhere)
        with pytest.raises((ValueError, OSError)):
            render_questionnaire(tmp_path / "q.pdf", preparer)
        assert elsewhere.read_bytes() == b"original"

    def test_no_network_call_is_made_while_rendering(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        from samanvaya.offline_check import install_tripwire, remove_tripwire
        from samanvaya.questionnaire import render_questionnaire

        install_tripwire()
        try:
            render_questionnaire(tmp_path / "q.pdf", preparer)
        finally:
            remove_tripwire()
        assert (tmp_path / "q.pdf").is_file()


class TestItSharesTheLetterheadAndNothingElse:
    def test_it_uses_the_same_preparer_type_as_the_report(self) -> None:
        """One letterhead store. Two would let the two documents disagree."""
        import inspect

        from samanvaya import questionnaire

        source = inspect.getsource(questionnaire)
        assert "Preparer" in source

    def test_it_does_not_import_the_report_renderer(self) -> None:
        """Separate documents, separate renderers — see BMAD/08.

        Sharing the report's table renderer is how a questionnaire slowly grows verdict
        columns. They may share the letterhead helper; they may not share the layout.
        """
        import inspect

        from samanvaya import questionnaire

        source = inspect.getsource(questionnaire)
        assert "report_tables" not in source
        assert "render_pdf" not in source


class TestItLooksLikeAFirmProducedIt:
    """Added 2026-08-22, after the first questionnaire was read as a client would.

    The verdict on it was "too generic, too black and white". That is not a matter of
    taste on a document going out over an advocate's name: a form that looks like a
    program's default output invites the reader to fill it in with the same care it
    appears to have been made with. These tests hold the parts of "professional" that
    can actually be asserted — colour is present, the pages are numbered and findable,
    the document names itself and the firm, and a yes/no question is a yes/no question
    rather than an empty line the client has to interpret.
    """

    def test_the_document_is_not_black_and_white(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        from tests.pdf_probe import has_non_grey_colour

        from samanvaya.questionnaire import render_questionnaire

        out = tmp_path / "q.pdf"
        render_questionnaire(out, preparer)
        assert has_non_grey_colour(out), "every colour operator is grey"

    def test_it_carries_the_wordmark_and_the_firm(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        from tests.pdf_probe import drawn_text

        from samanvaya.pdf_theme import WORDMARK
        from samanvaya.questionnaire import render_questionnaire

        out = tmp_path / "q.pdf"
        render_questionnaire(out, preparer)
        text = drawn_text(out).replace(" ", "")
        assert WORDMARK.replace(" ", "") in text
        assert "Example&Co" in text

    def test_every_page_after_the_cover_is_numbered(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        """A printed form that loses a page must say so."""
        from tests.pdf_probe import drawn_text

        from samanvaya.questionnaire import render_questionnaire

        out = tmp_path / "q.pdf"
        render_questionnaire(out, preparer)
        text = drawn_text(out)
        assert "Page 2 of" in text, "no page-of-total footer was drawn"

    def test_a_yes_no_question_offers_not_established(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        """An empty rule under a yes/no question asks the client to invent a format.

        "Not established" has to be on the paper because it is a first-class answer to
        the engine — an undeclared fact is reported, not guessed at — and a client who
        is only offered Yes and No will pick one.
        """
        from tests.pdf_probe import drawn_text

        from samanvaya.questionnaire import questionnaire_sections, render_questionnaire

        booleans = [
            item
            for section in questionnaire_sections()
            for item in section.items
            if item.kind == "bool"
        ]
        assert booleans, "the fixture has no yes/no questions to check"
        assert all(item.choices == ("Yes", "No", "Not established") for item in booleans)

        out = tmp_path / "q.pdf"
        render_questionnaire(out, preparer)
        assert "Not established" in drawn_text(out)

    def test_a_free_text_question_offers_no_choices(self) -> None:
        """Choices are for questions that have them. A list question gets ruled space."""
        from samanvaya.questionnaire import questionnaire_sections

        for section in questionnaire_sections():
            for item in section.items:
                if item.kind != "bool":
                    assert item.choices == (), item.path

    def test_the_questions_are_numbered_continuously(self) -> None:
        """A client on the phone says "question 41", not "the one about processors"."""
        from samanvaya.questionnaire import questionnaire_sections

        numbers = [
            item.number for section in questionnaire_sections() for item in section.items
        ]
        assert numbers == list(range(1, len(numbers) + 1))

    def test_the_printed_numbers_reach_the_page(
        self, preparer: Preparer, tmp_path: Path
    ) -> None:
        from tests.pdf_probe import drawn_text

        from samanvaya.questionnaire import questionnaire_sections, render_questionnaire

        out = tmp_path / "q.pdf"
        render_questionnaire(out, preparer)
        text = drawn_text(out)
        total = sum(len(s.items) for s in questionnaire_sections())
        for number in (1, total):
            assert str(number) in text


class TestItStillStatesNothing:
    """The redesign added authored text. All of it is held to the original ban."""

    def test_every_authored_string_is_free_of_verdict_vocabulary(self) -> None:
        import re

        from samanvaya.questionnaire import AUTHORED_TEXT

        assert AUTHORED_TEXT, "no authored strings were declared"
        surface = " ".join(AUTHORED_TEXT).lower()
        for word in TestItStatesNothing.BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", surface), (
                f"{word!r} appears in text this module authors"
            )

    def test_it_cannot_reach_a_verdict_colour(self) -> None:
        """There is no verdict colour in the shared house style to reach for.

        This is the boundary BMAD/08 drew, restated for a build where the two documents
        now share a palette. Sharing the wordmark is what makes them one firm's work;
        sharing a verdict colour is how a questionnaire grows a verdict column.
        """
        import inspect

        from samanvaya import pdf_theme, questionnaire

        assert not hasattr(pdf_theme, "VERDICT_COLOUR")
        source = inspect.getsource(questionnaire)
        assert "_VERDICT" not in source
        assert "from samanvaya.pdf_report import" not in source
