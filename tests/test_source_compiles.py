"""Guard: the whole tree must parse under the target Python.

This exists because `except A, B:` (Python-2 syntax) shipped to `main` five
separate times and spread into newly written modules. It is a hard SyntaxError
on Python 3, so the affected modules cannot import at all and every view inside
them is dead at runtime.

CI already runs `compileall`, but a red CI check only helps if merges are
blocked on it. Encoding the same guarantee as a test means the failure also
surfaces locally in `pytest`, where authors actually look.
"""

from __future__ import annotations

import compileall
import io
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
# `services` and `contracts` are the FastAPI strangler tree and its shared
# schemas. They were outside this gate while being the one part of the codebase
# nobody runs locally — precisely where the syntax drift this test exists for
# would survive longest. Missing targets are skipped below, so listing
# `contracts` before it exists is safe.
TARGETS = ("apps", "config", "contracts", "jobs", "services", "tests", "manage.py")


def test_all_sources_compile() -> None:
    """Every tracked Python file parses; no legacy Python-2 syntax survives."""
    buffer = io.StringIO()
    original_stdout, sys.stdout = sys.stdout, buffer
    try:
        ok = True
        for target in TARGETS:
            path = REPO_ROOT / target
            if not path.exists():
                continue
            if path.is_file():
                ok &= bool(compileall.compile_file(path, quiet=2, force=True))
            else:
                ok &= bool(
                    compileall.compile_dir(
                        path, quiet=2, force=True, rx=__import__("re").compile(r"migrations")
                    )
                )
    finally:
        sys.stdout = original_stdout

    assert ok, (
        "Python sources failed to compile. Most likely cause: Python-2 style\n"
        "`except A, B:` — it must be written `except (A, B):` on Python 3.\n\n"
        f"{buffer.getvalue()}"
    )
