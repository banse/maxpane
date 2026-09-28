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
are removed.  Then the ordered rule table, then the 64-or-more-hex rule with its
field-aware allowance.

The long-hex rule detects lowercase, uppercase, optional ``0x`` prefixes and
word-adjacent runs of at least 64 hex digits. It is field-aware because the one secret this design exists to
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
    "G2_RULES",
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
#: Invisible format controls, including joiners, bidi isolates and Unicode tags (spec §13 G2).
BIDI_FORMAT_RE = re.compile("[\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb\U000e0001\U000e0020-\U000e007f]")

#: Canary on values (the rules below replace; the canaries only detect).  The
#: negative lookahead keeps the ``sk-ant-[redacted]`` placeholder from being
#: read as a key: ``ant-`` is four class characters, so the plain contract
#: pattern re-matched its own replacement (``sk-ant-x`` -> ``sk-[redacted][redacted]``)
#: and flagged redacted text as a secret.
SK_RE = re.compile(r"sk-(?!ant-\[redacted\])[A-Za-z0-9*_-]{4,}")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}")


#: Owner G2 credential rules, also imported by pre-commit content guards. These
#: are replacements, not additions to the projection/status canary.
G2_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[github-token]"),
    (re.compile(r"(?<![A-Za-z0-9_])npm_[A-Za-z0-9]{36}(?![A-Za-z0-9_])"), "[npm-token]"),
    (re.compile(r"(?i)(authorization:[ \t]*basic[ \t]+)(?![ \t]|\[redacted\])[A-Za-z0-9+/=._~-]+"), r"\1[redacted]"),
    (re.compile(r"(?i)(\b(?:set-)?cookie:[ \t]*)(?![ \t]|\[redacted\])[^\r\n]+"), r"\1[redacted]"),
    (re.compile(r"(?i)(\bx-api-key:[ \t]*)(?![ \t]|\[redacted\])[^\s,;]+"), r"\1[redacted]"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)(?!\[redacted\]@)[^/?#\s@\[\]]+@"), r"\1[redacted]@"),
)

#: Applied in this order after step 0 (spec §13).  ``sk-ant-`` precedes ``sk-``
#: so an Anthropic key is not left as ``sk-[redacted]`` with its prefix lost.
RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9*_-]{4,}"), "sk-ant-[redacted]"),
    (SK_RE, "sk-[redacted]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?"), "[jwt]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [redacted]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "[github-token]"),
    (re.compile(r"([?&](?:token|key|sig|signature|secret)=)[^&\s]+"), r"\1[redacted]"),
) + G2_RULES
HEX64_RE = re.compile(r"(?<![0-9A-Fa-f])(?:0x)?[0-9A-Fa-f]{64,}(?![0-9A-Fa-f])")
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


def redact(text: object, field: str | None = None) -> str:
    """Control-strip, then the rule table in order, then the 64-hex rule.

    ``None`` is ``""``; any other object is ``str()``-ed inside its own
    ``try`` so a value whose ``__str__`` raises degrades to ``""`` rather than
    taking a panel or the broker down.  *field* is the dict key the value sat
    under; a 64-hex value survives only when that key is in
    :data:`HEX64_ALLOWED_FIELDS`.
    """
    if text is None:
        return ""
    try:
        out = str(text)
    except Exception:
        return ""
    out = strip_controls(out)
    for pattern, replacement in RULES:
        out = pattern.sub(replacement, out)
    if field not in HEX64_ALLOWED_FIELDS:
        out = HEX64_RE.sub(HEX64_PLACEHOLDER, out)
    return out


def redact_agent_sentence(text: object) -> str:
    """:func:`redact`, then whitespace collapse, then the 160-character cap.

    The two operations the daemon applies to a ``working:`` sentence before
    it logs it (``\\s+`` to one space, ``slice(160)``), so an agent sentence
    that arrived by another road renders like one that came through the log.
    """
    flat = " ".join(redact(text).split())
    return flat[:AGENT_SENTENCE_CAP]


def redact_tree(value: object, *, field: str | None = None) -> object:
    """Recursively :func:`redact` every string in a dict/list tree.

    A dict key is passed as *field* for its value (so ``{"submissionHash":
    <hex64>}`` keeps its hash) and is itself redacted; a list inherits the key
    it hangs under.  Non-string scalars come back unchanged; a tuple comes back
    as a list (JSON has no tuple).
    """
    if isinstance(value, dict):
        out: dict = {}
        for key, item in value.items():
            if isinstance(key, str):
                out[redact(key)] = redact_tree(item, field=key)
            else:
                out[key] = redact_tree(item, field=field)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_tree(item, field=field) for item in value]
    if isinstance(value, str):
        return redact(value, field)
    return value


def find_secret_path(
    value: object,
    *,
    allowed_hex64_fields: frozenset[str] = frozenset(),
    allowed_hex64_paths: frozenset[str] = frozenset(),
    field: str | None = None,
) -> tuple[str, str] | None:
    """First canary hit in a tree as ``(kind, dotted path)``, or ``None``.

    Kinds, in the order checked at each node: ``"key_name"`` (a dict key
    matching :data:`SECRET_KEY_RE`), then for a string value ``"sk"``
    (:data:`SK_RE`), ``"jwt"`` (:data:`JWT_RE`) and ``"hex64"``
    (:data:`HEX64_RE` under a key not in *allowed_hex64_fields*; a list
    inherits its key), unless its exact path is in *allowed_hex64_paths*.
    Path allowances do not propagate to children or array items. The path reads ``tasks.rows[3].hash12``; the root is
    ``""``.  Never raises.
    """
    return _walk(value, allowed_hex64_fields, allowed_hex64_paths, field, "")


def find_secret(
    value: object,
    *,
    allowed_hex64_fields: frozenset[str] = frozenset(),
    allowed_hex64_paths: frozenset[str] = frozenset(),
    field: str | None = None,
) -> str | None:
    """The kind of the first canary hit (see :func:`find_secret_path`), or ``None``."""
    hit = find_secret_path(value, allowed_hex64_fields=allowed_hex64_fields,
                           allowed_hex64_paths=allowed_hex64_paths, field=field)
    return None if hit is None else hit[0]


def _walk(
    value: object, allowed: frozenset[str], allowed_paths: frozenset[str], field: str | None, path: str
) -> tuple[str, str] | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = key if isinstance(key, str) else str(key)
            child = f"{path}.{key_text}" if path else key_text
            if SECRET_KEY_RE.search(key_text):
                return ("key_name", child)
            hit = _walk(item, allowed, allowed_paths, key_text, child)
            if hit is not None:
                return hit
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hit = _walk(item, allowed, allowed_paths, field, f"{path}[{index}]")
            if hit is not None:
                return hit
        return None
    if isinstance(value, str):
        if SK_RE.search(value):
            return ("sk", path)
        if JWT_RE.search(value):
            return ("jwt", path)
        if field not in allowed and path not in allowed_paths and HEX64_RE.search(value):
            return ("hex64", path)
    return None
