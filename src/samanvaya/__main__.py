"""Package entry point so `python -m samanvaya` works as well as the console script.

Kept to one line of behaviour on purpose: the entry point should be a way in, not a
second place where argument handling can drift from `cli.main`.
"""

from samanvaya.cli import main

raise SystemExit(main())
