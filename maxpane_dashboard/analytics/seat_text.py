"""Pure seat text boundary: redact, clear canaries, remove currency, then cap.

Structured public hashes may survive only under the existing redactor field
allowance. Document callers use no allowance. No validator rule is relaxed.
"""
from __future__ import annotations

from .seat_redact import HEX64_ALLOWED_FIELDS, HEX64_RE, JWT_RE, SK_RE, redact

__all__ = ["TEXT_CAP", "sanitize_text", "sanitize_sentence", "sanitize_tree"]

TEXT_CAP = 4096


def sanitize_text(value: object, field: str | None = None, *, cap: int = TEXT_CAP,
                  flatten: bool = False) -> str:
    """Return bounded text with no value-canary match, including cut boundaries."""
    text = redact(value, field)
    patterns = (SK_RE, JWT_RE) if field in HEX64_ALLOWED_FIELDS else (SK_RE, JWT_RE, HEX64_RE)
    for pattern in patterns:
        text = pattern.sub('[redacted]', text)
    text = text.replace('$', '')
    if flatten:
        text = ' '.join(text.split())
    cap = max(0, cap)
    text = text if len(text) <= cap else text[:max(0, cap - 1)] + ('…' if cap else '')
    # Dollar removal may join token fragments; cutting can break the redactor's
    # sk-ant-[redacted] exception. Replace matches with one safe character so
    # this final pass never exceeds the cap or creates another cut boundary.
    for pattern in patterns:
        text = pattern.sub('…', text)
    return text


def sanitize_sentence(value: object) -> str:
    return sanitize_text(value, cap=160, flatten=True)


def sanitize_tree(value: object, *, field: str | None = None) -> object:
    """Sanitize strings in an already shaped tree; preserve structured hash ids.

    This is not a schema projector: callers must select fields explicitly.
    In particular unexpected secret-named keys still trigger the validator.
    """
    if isinstance(value, dict):
        return {sanitize_text(key) if isinstance(key, str) else key:
                sanitize_tree(item, field=key if isinstance(key, str) else field)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_tree(item, field=field) for item in value]
    return sanitize_text(value, field) if isinstance(value, str) else value
