"""Bounded GitHub README provenance and plain introductory source excerpts."""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata

MAX_README_BYTES = 131_072
MAX_EXCERPT_CHARS = 1600
_REPOSITORY = re.compile(r'https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})')
_COMMIT = re.compile(r'[0-9a-fA-F]{40}')


def repository_reference(metadata):
    """Validate before any network use; a broken pin cannot become HEAD."""
    if not isinstance(metadata, dict) or not isinstance(metadata.get('url'), str):
        raise ValueError('invalid repository metadata')
    match = _REPOSITORY.fullmatch(metadata['url'])
    if not match or match[2] in ('.', '..') or match[2].lower().endswith('.git'):
        raise ValueError('invalid canonical GitHub repository')
    revision = metadata.get('commit')
    if revision is not None and (not isinstance(revision, str) or not _COMMIT.fullmatch(revision)):
        raise ValueError('invalid pinned README revision')
    return metadata['url'].lower(), revision.lower() if revision else None


def _excerpt(markdown):
    # Strip complete terminal escape sequences before removing remaining controls.
    markdown = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]', '', markdown)
    markdown = ''.join(char for char in markdown if char in '\n\t' or unicodedata.category(char) not in ('Cc', 'Cf'))
    markdown = re.sub(r'<!--.*?(?:-->|$)|<(script|style)\b[^>]*>.*?(?:</\1\s*>|$)', '', markdown,
                      flags=re.IGNORECASE | re.DOTALL)
    paragraphs, current, fence = [], [], None
    for line in markdown.splitlines():
        stripped = line.strip()
        marker = re.match(r'(`{3,}|~{3,})', stripped)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence is not None:
            continue
        if re.match(r'#{1,6}\s', stripped):
            if current or paragraphs:
                break
            continue
        if not stripped:
            if current:
                paragraphs.append(' '.join(current))
                current = []
            if len(paragraphs) == 3:
                break
            continue
        if (line.startswith(('    ', '\t')) or stripped.startswith(('<', '|', '>'))
                or re.match(r'(?:[-*+]\s|\d+\.\s|\[[^]]+\]:|[-=]{3,}$)', stripped)):
            continue
        navigation, links = re.subn(r'\[[^]]+\]\([^\s)]+\)', '', stripped)
        if links >= 2 and not navigation.strip(' \t·|•/—–-:'):
            continue
        stripped = re.sub(r'!?\[!\[[^]]*\]\([^)]*\)\]\([^)]*\)|!\[[^]]*\]\([^)]*\)', '', stripped)
        stripped = re.sub(r'\[([^]]+)\]\([^)]*\)|\[([^]]+)\]\[[^]]*\]', lambda m: m[1] or m[2], stripped)
        stripped = re.sub(r'<[^>]*>', '', stripped)
        stripped = re.sub(r'[*_`~]', '', stripped)
        stripped = ' '.join(stripped.split())
        if stripped:
            current.append(stripped)
    if current:
        paragraphs.append(' '.join(current))
    text = '\n\n'.join(paragraphs)
    if len(text) > MAX_EXCERPT_CHARS:
        text = text[:MAX_EXCERPT_CHARS - 1].rsplit(' ', 1)[0] + '…'
    return text or None


def decode_readme(payload, repository_url, revision):
    """Ignore provider URLs; only a validated root file can supply text."""
    if (not isinstance(payload, dict) or payload.get('type') != 'file'
            or payload.get('path') != 'README.md' or payload.get('encoding') != 'base64'
            or type(payload.get('size')) is not int or not 0 <= payload['size'] <= MAX_README_BYTES
            or not isinstance(payload.get('content'), str)
            or len(payload['content']) > (MAX_README_BYTES * 4 // 3 + 8) * 1.05):
        raise ValueError('invalid README envelope')
    try:
        decoded = base64.b64decode(''.join(payload['content'].split()), validate=True)
        if len(decoded) > MAX_README_BYTES or len(decoded) != payload['size']:
            raise ValueError('README size mismatch')
        text = _excerpt(decoded.decode('utf-8'))
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError('malformed README content') from exc
    return dict(repository_url=repository_url, readme_url=f'{repository_url}/blob/{revision or "HEAD"}/README.md',
                revision=revision, text=text, state='ok' if text else 'missing')
