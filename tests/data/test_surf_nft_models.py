"""Frozen primitive contract and pure-projection boundaries."""
import ast
import importlib
import json
from pathlib import Path


def test_flat_contract_and_filter_defaults_are_exact():
    models=importlib.import_module('maxpane_dashboard.data.surf_nft_models')
    assert models.NFT_KEYS==('nft_rows','nft_build_rows','nft_summary','nft_selected','nft_readme','nft_sources','nft_coverage','as_of')
    assert models.NFT_WIDGET_SIGNATURES['NftSummary'] == ('nft_readme',)
    assert models.NFT_SUMMARY_FIELDS==('deployed','building','mint_open','idmd_free','conditional','chains','mint_known','idmd_known','partial','observed_at')
    assert models.NFT_FILTER_DEFAULTS=={'chain':'all','stage':'launched','mint':'all','idmd':'all','utility':'all','search':'','sort':'newest'}


def test_normalized_fixture_and_projection_obey_exact_contract():
    models=importlib.import_module('maxpane_dashboard.data.surf_nft_models')
    nft=importlib.import_module('maxpane_dashboard.analytics.surf_nft')
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/surf/nft/projection.json').read_text())
    rows=[nft.normalize_record(raw) for raw in fixture['records']]
    for row in rows:
        assert tuple(row)==models.NFT_ROW_FIELDS
    raw=dict(nft_rows=rows,nft_build_rows=[],nft_summary={},nft_selected=None,nft_sources={},nft_coverage={},as_of=1)
    result=nft.project_snapshot(raw)
    assert tuple(result)==models.NFT_KEYS
    assert tuple(result['nft_summary'])==models.NFT_SUMMARY_FIELDS
    assert nft.FILTER_DEFAULTS==models.NFT_FILTER_DEFAULTS
    assert nft.FILTER_VALUES==models.NFT_FILTER_VALUES


def test_projection_has_only_standard_library_imports():
    nft=importlib.import_module('maxpane_dashboard.analytics.surf_nft')
    source=ast.parse(Path(nft.__file__).read_text())
    imports=[]
    for node in ast.walk(source):
        if isinstance(node,ast.Import): imports.extend(alias.name for alias in node.names)
        if isinstance(node,ast.ImportFrom): imports.append(node.module or '')
    assert all(name.split('.')[0] in {'__future__','copy','datetime','math','re'} for name in imports)
