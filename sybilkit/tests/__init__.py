"""``sybilkit``'s own test suite.

Stdlib-only, like the package it tests.  **No test here opens a socket** — the
same hard rule the maxpane repo runs on: every external payload is a committed
fixture under ``tests/fixtures/``, and WP2's source tests inject a transport
double that raises on use.

Run it from the distribution root::

    cd sybilkit && python3 -m pytest
"""
