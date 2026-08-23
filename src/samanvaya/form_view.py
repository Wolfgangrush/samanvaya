"""The sectioned intake window -- BMAD/08 part B, the view.

An adviser sits with a client for two hours and types answers into this window. The
window is a thin view over :class:`samanvaya.form.IntakeForm`: every answer goes
through ``form.set`` and every count comes from ``form.progress``. The window does
not parse, validate, persist or summarise. It only collects and reflects.

THE RULE THE WINDOW PROTECTS
----------------------------
Three properties are non-negotiable and this module is the only place that can keep
them.

1. Sections are jumpable in any order. A client answers out of order and the
   adviser circles back. A forced linear wizard is the wrong shape for a two-hour
   meeting. Every section is reachable from every other.

2. "Not established" is visible, selectable, and the default. Two boxes make the
   honest answer unavailable, so a client will pick one of two and the engine will
   report an undeclared fact as a confident yes or no. The third option is the only
   thing that keeps the gap/contested distinction honest at the input layer.

3. No inference, no verdicts. The window never fills one answer from another,
   never hides a question because an earlier answer made it look unlikely, and never
   tells the user whether they are compliant. The form gathers; the engine assesses
   downstream.

WHAT IT DOES NOT DO
-------------------
- It does not parse or validate. Parsing and validation live in samanvaya.form
  and are reused verbatim through form.set.
- It does not autosave. Autosave is owned by IntakeForm.autosave and is fired
  from inside form.set.
- It does not assess. The engine runs in another module and on another file, and
  this module never imports it.
"""

from __future__ import annotations

import tkinter
from pathlib import Path
from tkinter import ttk

from samanvaya.form import IntakeForm
from samanvaya.interview import QUESTIONS, Question


AUTHORED_TEXT: tuple[str, ...] = (
    "{answered} of {total} answered",
    "Total progress:",
    "Separate items with commas.",
)


_BOOL_CHOICES: tuple[str, ...] = ("Yes", "No", "Not established")


class IntakeWindow:
    """The sectioned Tk intake window over an :class:`IntakeForm`.

    Constructing the window does not enter the main loop. Construction builds the
    widget tree and wires every control to ``self.write`` so a click and a test
    travel the same path. The caller owns the main loop and the root window.
    """

    form: IntakeForm
    section_names: tuple[str, ...]
    current_section: str

    def __init__(
        self,
        root: tkinter.Tk | tkinter.Misc,
        form: IntakeForm,
    ) -> None:
        """Build every page of the window over the supplied model."""
        self.form = form
        self._root = root

        self._question_by_path: dict[str, Question] = {q.path: q for q in QUESTIONS}
        self._widgets: dict[str, tkinter.Misc] = {}
        self._error_labels: dict[str, tkinter.StringVar] = {}
        self._section_frames: dict[str, ttk.Frame] = {}
        self._section_progress_vars: dict[str, tkinter.StringVar] = {}

        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        self._notebook = ttk.Notebook(outer)
        self._notebook.grid(row=0, column=0, sticky="nsew")

        self.section_names = self.form.sections()
        for title in self.section_names:
            self._build_section(title)

        ttk.Separator(outer, orient="horizontal").grid(
            row=1, column=0, sticky="ew", pady=(8, 4)
        )
        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)

        ttk.Label(footer, text="Total progress:").grid(row=0, column=0, sticky="w")
        self._total_var = tkinter.StringVar()
        ttk.Label(footer, textvariable=self._total_var).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        self.current_section = self.section_names[0]
        self.show_section(self.current_section)
        self._refresh_progress()

    def show_section(self, title: str) -> None:
        """Show the section named ``title``. Raises ``KeyError`` if unknown."""
        if title not in self._section_frames:
            raise KeyError(title)
        self._notebook.select(self._section_frames[title])  # type: ignore[no-untyped-call]
        self.current_section = title

    def widget_for(self, path: str) -> object:
        """Return the widget bound to the question at ``path``, or ``None``."""
        return self._widgets.get(path)

    def choices_for(self, path: str) -> tuple[str, ...]:
        """Return the user-facing options for the question at ``path``."""
        question = self._question_by_path.get(path)
        if question is None:
            return ()
        if question.kind == "bool":
            return _BOOL_CHOICES
        return ()

    def prompt_for(self, path: str) -> str:
        """Return the bank prompt for the question at ``path``."""
        return self._question_by_path[path].prompt

    def why_for(self, path: str) -> str:
        """Return the bank reason for the question at ``path``."""
        return self._question_by_path[path].why

    def write(self, path: str, raw: str) -> str | None:
        """Commit ``raw`` as the answer at ``path``."""
        message = self.form.set(path, raw)
        error_var = self._error_labels.get(path)
        if error_var is not None:
            error_var.set(message or "")
        if message is None:
            self._refresh_progress()
        return message

    def progress_text(self, title: str) -> str:
        """Return the live progress text for the section named ``title``."""
        progress = self.form.progress(title)
        return f"{progress.answered} of {progress.total} answered"

    def total_text(self) -> str:
        """Return the live progress text across all sections."""
        progress = self.form.total_progress()
        return f"{progress.answered} of {progress.total} answered"

    def save_to(self, path: Path) -> str | None:
        """Save the declaration to ``path``. Returns an error message or ``None``."""
        try:
            self.form.save(path)
        except ValueError as exc:
            return str(exc)
        return None

    def _build_section(self, title: str) -> None:
        """Construct one scrollable tab for the section named ``title``."""
        outer = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(outer, text=title)
        self._section_frames[title] = outer

        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text=title, font="TkHeadingFont").grid(
            row=0, column=0, sticky="w"
        )

        progress_var = tkinter.StringVar()
        self._section_progress_vars[title] = progress_var
        ttk.Label(header, textvariable=progress_var).grid(
            row=0, column=1, sticky="e"
        )

        canvas = tkinter.Canvas(outer, borderwidth=0, highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        body = ttk.Frame(canvas)
        body.columnconfigure(0, weight=1)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_canvas_resize(event: tkinter.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def _on_body_resize(event: tkinter.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", _on_canvas_resize)
        body.bind("<Configure>", _on_body_resize)

        for index, question in enumerate(self.form.questions_in(title)):
            self._build_question_row(body, index, question)

    def _build_question_row(
        self,
        parent: tkinter.Misc,
        index: int,
        question: Question,
    ) -> None:
        """Build one question's prompt, why, control and error label."""
        path = question.path

        row = ttk.Frame(parent)
        row.grid(row=index, column=0, sticky="ew", pady=(0, 12))
        row.columnconfigure(0, weight=1)

        ttk.Label(
            row,
            text=question.prompt,
            wraplength=600,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        # The `why` is what the adviser reads aloud when the client asks
        # "why are you asking me that", so it is shown beneath the prompt in
        # a lighter register.
        tkinter.Label(
            row,
            text=question.why,
            wraplength=600,
            justify="left",
            fg="grey",
        ).grid(row=1, column=0, sticky="w", pady=(0, 4))

        error_var = tkinter.StringVar()
        self._error_labels[path] = error_var

        if question.kind == "bool":
            control = self._build_bool_control(row, question)
        else:
            control = self._build_text_control(row, question)

        self._widgets[path] = control
        control.grid(row=2, column=0, sticky="ew")

        # The error label sits below the control so a refusal is read next
        # to the question that was refused, never in a dialog that loses
        # the user's place.
        tkinter.Label(
            row,
            textvariable=error_var,
            wraplength=600,
            justify="left",
            fg="red",
        ).grid(row=3, column=0, sticky="w", pady=(2, 0))

    def _build_bool_control(
        self, parent: tkinter.Misc, question: Question
    ) -> ttk.Frame:
        """Build the three-radio control for a bool question.

        "Not established" is the default and is always selectable. Two boxes
        make the honest answer unavailable, so a client offered only Yes and
        No will pick one, and the engine reports an undeclared fact as a
        confident yes or no. The third choice is the only thing that keeps
        the gap/contested distinction honest at the input layer.
        """
        path = question.path
        frame = ttk.Frame(parent)
        var = tkinter.StringVar(value="Not established")

        for label in _BOOL_CHOICES:
            def _select(p: str = path, v: str = label) -> None:
                self.write(p, v)
            ttk.Radiobutton(
                frame,
                text=label,
                value=label,
                variable=var,
                command=_select,
            ).pack(side="left", padx=(0, 12))

        return frame

    def _build_text_control(
        self, parent: tkinter.Misc, question: Question
    ) -> ttk.Frame:
        """Build the single-line entry for a text/number/list question.

        Every keystroke commits through ``self.write`` so a click and a test
        travel the same path; a list answer carries a comma hint because
        nothing else tells the user how to enter one.
        """
        path = question.path
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)

        var = tkinter.StringVar()

        def _on_change(*args: str) -> None:
            self.write(path, var.get())

        var.trace_add("write", _on_change)

        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=0, column=0, sticky="ew")

        if question.kind == "list":
            ttk.Label(
                frame,
                text="Separate items with commas.",
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        return frame

    def _refresh_progress(self) -> None:
        """Update every progress label after a write or a section switch."""
        for title, var in self._section_progress_vars.items():
            var.set(self.progress_text(title))
        self._total_var.set(self.total_text())
