"""README source excerpts are bounded prose, not executable markdown or mint facts."""
import base64
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data.surf_nft_readme import decode_readme, repository_reference

FIXTURES = Path(__file__).parents[1] / 'fixtures/surf/nft/readme'
REPO = 'https://github.com/example/collection'
REVISION = 'a' * 40


def test_repository_reference_is_canonical_and_never_downgrades_a_bad_pin():
    assert repository_reference({'url': REPO.upper().replace('HTTPS://GITHUB.COM', 'https://github.com'),
                                 'commit': REVISION.upper()}) == (REPO, REVISION)
    assert repository_reference({'url': REPO}) == (REPO, None)
    for metadata in ({'url': REPO, 'commit': 'main'}, {'url': REPO, 'commit': ''},
                     {'url': REPO + '?token=secret'}, {'url': REPO + '/tree/main'},
                     {'url': 'https://github.com/example/..'},
                     {'url': 'https://github.com@127.0.0.1/example/collection'},
                     {'url': 'https://github.com/example/%2e%2e'},
                     {'url': 'https://github.com/example/collection.git'}):
        with pytest.raises(ValueError):
            repository_reference(metadata)


def test_intro_excerpt_skips_badges_code_html_and_terminal_controls():
    payload = json.loads((FIXTURES / 'intro.json').read_text())
    result = decode_readme(payload, REPO, REVISION)
    assert result == dict(repository_url=REPO, revision=REVISION,
        readme_url=f'{REPO}/blob/{REVISION}/README.md', state='ok',
        text='An onchain art collection with evolving pieces. Built by the swarm.\n\n'
             'Each piece changes with public activity; see the project for context.')


def test_intro_skips_link_navigation_but_keeps_mixed_prose_links():
    payload = json.loads((FIXTURES / 'intro.json').read_text())
    excerpt = decode_readme(payload, REPO, REVISION)['text']
    assert 'How it works' not in excerpt
    assert 'The contract' not in excerpt
    assert 'Evidence' not in excerpt
    assert 'Each piece changes with public activity; see the project for context.' in excerpt


@pytest.mark.parametrize('change', [dict(encoding='utf16'), dict(content='!not base64!'),
    dict(size=True), dict(size=131073), dict(path='../README.md'), dict(type='symlink'),
    dict(content=base64.b64encode(b'\xff').decode()), dict(content='x' * 180000)])
def test_malformed_readme_envelope_is_rejected(change):
    payload = json.loads((FIXTURES / 'intro.json').read_text())
    with pytest.raises(ValueError):
        decode_readme(dict(payload, **change), REPO, REVISION)


def test_empty_or_markup_only_readme_is_missing_and_excerpt_has_a_bound():
    payload = json.loads((FIXTURES / 'intro.json').read_text())
    markup = '# Heading\n\n```sh\nrm -rf /\n```\n\n<script>hidden</script>'
    empty = dict(payload, content=base64.b64encode(markup.encode()).decode(), size=len(markup))
    assert decode_readme(empty, REPO, None)['state'] == 'missing'
    long = 'Long introductory prose. ' * 1000
    result = decode_readme(dict(payload, content=base64.b64encode(long.encode()).decode(),
                                size=len(long)), REPO, None)
    assert len(result['text']) <= 1600
    assert result['readme_url'] == REPO + '/blob/HEAD/README.md'
