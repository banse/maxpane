"""Redactor shared by the PEPEPANE dashboard and the ``imd-dashd`` broker.

Two byte-identical copies of this file exist on purpose: ``maxpane_dashboard/
analytics/seat_redact.py`` (the TUI; imported by ``data/seat_models.py`` and
the seat widgets) and ``imd_dashd/redact.py`` (the root broker, which imports
nothing from ``maxpane_dashboard``).  ``tests/analytics/test_seat_redact.py::
test_redact_copies_are_byte_identical`` keeps them equal, hence the rules for
this file: Python 3.11 syntax, ``re`` as the only import, no reference to
either package.

Every third-party string -- a journal ``MESSAGE``, an API string, a transcript
summary string, an ``imd`` CLI line, an orphan cmdline, an audit
``verify_line`` -- passes :func:`redact` before it is rendered, persisted or
audited (spec §13).

**Step 0 runs before every rule: control characters.**  ``markup_safety.flatten``
is ``" ".join(str(value).split())`` and drops only whitespace; Rich's ``Text``
strips only ``[7, 8, 11, 12, 13]``; Textual writes segment text raw into the
ANSI stream.  So an ``\\x1b]52;c;...\\x07`` (an OSC 52 clipboard write chosen
by a network-selected model inside a ``working:`` sentence) would otherwise
reach the operator's terminal over ssh.  A bare ESC is made *visible* as ``\u241b``
so an attempted escape is seen rather than silently swallowed; every other C0
byte except TAB and LF, DEL, the C1 range and the Unicode bidi/format controls
are removed.  Then the ordered rule table, then the 64-hex rule with its
field-aware allowance.

The 64-hex rule is field-aware because the one secret this design exists to
protect -- the Ed25519 device private key -- is byte-shape-identical to the
public ``deviceKey`` (both 64 hex).  :func:`find_secret` is the canary the
broker and the status-document validator run over whole trees; it detects and
names, :func:`redact` replaces.
"""

from __future__ import annotations

import re

__all__ = [
    "AGENT_SENTENCE_CAP",
    "BIDI_FORMAT_RE",
    "CONTROL_RE",
    "ESC_GLYPH",
    "HEX64_ALLOWED_FIELDS",
    "HEX64_PLACEHOLDER",
    "HEX64_RE",
    "JWT_RE",
    "RULES",
    "SECRET_KEY_RE",
    "SK_RE",
    "find_secret",
    "find_secret_path",
    "redact",
    "redact_agent_sentence",
    "redact_tree",
    "strip_controls",
]

#: ``\u241b`` -- a bare ESC becomes a visible glyph instead of an escape.
ESC_GLYPH = "\u241b"
#: C0 except ``\t`` and ``\n``, DEL, and the C1 range.
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
#: Zero-width and bidi override/isolate controls: U+200B–U+200F, U+202A–U+202E, U+2066–U+2069.
BIDI_FORMAT_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069]")

#: Canary on values (the rules below replace; the canaries only detect).  The
#: negative lookahead keeps the ``sk-ant-[redacted]`` placeholder from being
#: read as a key: ``ant-`` is four class characters, so the plain contract
#: pattern re-matched its own replacement (``sk-ant-x`` -> ``sk-[redacted][redacted]``)
#: and flagged redacted text as a secret.
SK_RE = re.compile(r"sk-(?!ant-\[redacted\])[A-Za-z0-9*_-]{4,}")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}")

#: Applied in this order after step 0 (spec §13).  ``sk-ant-`` precedes ``sk-``
#: so an Anthropic key is not left as ``sk-[redacted]`` with its prefix lost.
RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9*_-]{4,}"), "sk-ant-[redacted]"),
    (SK_RE, "sk-[redacted]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?"), "[jwt]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [redacted]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "[github-token]"),
    (re.compile(r"([?&](?:token|key|sig|signature|secret)=)[^&\s]+"), r"\1[redacted]"),
)
HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b")
HEX64_PLACEHOLDER = "<hex64>"
#: The fields whose value may legitimately be 64 hex.  ``deviceKey`` only after
#: the broker's whoami match (spec §13, projection canary); the status-document
#: validator allows none of them.
HEX64_ALLOWED_FIELDS = frozenset({"submissionHash", "txHash", "deviceKey"})
#: Canary on dict *keys*: a payload that names a secret under its own name.
SECRET_KEY_RE = re.compile(
    r"privateKey|devicePrivateKey|mnemonic|secret|tools\.env|auth\.json", re.IGNORECASE
)
#: The daemon's own cap on a ``working:`` sentence (bundle §3.1), applied again
#: here because API strings and transcript summaries never went through it.
AGENT_SENTENCE_CAP = 160


def strip_controls(text: str) -> str:
    """Step 0: make ESC visible, then drop every other control and bidi code.

    ``\\t`` and ``\\n`` survive (a journal record may carry a tab; the caller
    splits lines).  Order matters: ESC is replaced *before* :data:`CONTROL_RE`
    runs, because ``\\x1b`` lies inside the C0 range that pattern removes.
    """
    out = text.replace("\x1b", ESC_GLYPH)
    out = CONTROL_RE.sub("", out)
    return BIDI_FORMAT_RE.sub("", out)
