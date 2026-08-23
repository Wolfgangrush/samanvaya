"""Entry point for the single-file build.

PyInstaller needs a module to start from. The console script declared in
``pyproject.toml`` is not one, so this file exists purely to give the frozen binary the
same entry point ``samanvaya`` has when installed with pip.
"""

from samanvaya.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
