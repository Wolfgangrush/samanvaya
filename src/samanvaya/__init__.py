"""Offline, declaration-driven privacy conformance across six regulatory regimes.

The tool reads one hand-authored declaration describing an organisation and reports,
against named instruments and provisions, which obligations appear satisfied, which are
unaddressed, and which cannot be resolved on the declared facts. It never connects to a
client's systems, never holds a credential, never reaches the network at runtime, and
never advises. It reports; the advocate advises.

Not legal advice. See `types.DISCLAIMER`.
"""

__version__ = "0.3.0"

#: The artefact counter. ``__version__`` says what the tool is; ``__build__`` says
#: which built copy of it a reader is holding.
#:
#: They are separate because they answer different questions and move at different
#: rates. A client who emails back a PDF three months after a meeting can be asked
#: which build produced it, and the answer has to identify one artefact — not a
#: version string that a dozen rebuilt copies also carry. Build 1 is the 0.1.0 line;
#: build 2 is the first release carrying the house style; build 3 was the intake
#: form; build 4 adds the self-test the build gate runs against the frozen bundle;
#: build 5 puts the author's attribution and this number itself into the About box.
#: Build 3 was never installed anywhere — it is bumped because two different code
#: states must never both claim one build number, which is the whole point of this.
#:
#: It is a literal and never computed at import time. The report embeds it, and a
#: report whose bytes change between two runs of the same input would break the
#: determinism the engine tests hold the whole pipeline to.
__build__ = 5

#: The date build ``__build__`` was cut. Also a literal, for the same reason.
__build_date__ = "2026-08-22"

__all__ = ["__version__", "__build__", "__build_date__"]
