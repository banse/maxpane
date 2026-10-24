"""Presentation fallbacks retain observations, never their own default zeros."""
from maxpane_dashboard.widgets.card_values import CardValues


def test_numeric_parts_keep_observations_and_accept_real_zero():
    values = CardValues()
    assert values.field('coverage', '--/-- known', numeric=True) == '0/0 known'
    assert values.field('coverage', '5/12 known', numeric=True) == '5/12 known'
    assert values.field('coverage', '--/20 known', numeric=True) == '5/20 known'
    assert values.field('coverage', '0/-- known', numeric=True) == '0/20 known'
    assert values.field('coverage', '--/-- known', numeric=True) == '0/20 known'
    assert values.field('price', '$--', numeric=True) == '$0'
    assert values.field('price', '$-2.5', numeric=True) == '$-2.5'
    assert values.field('price', '$--', numeric=True) == '$-2.5'


def test_text_missing_is_blank_or_last_read_and_clear_drops_history():
    values = CardValues()
    assert values.field('version', '--') == ''
    assert values.field('version', '2.1.299') == '2.1.299'
    assert values.field('version', '—') == '2.1.299'
    assert values.field('date', 'paired --') == ''
    assert values.field('date', 'paired 09-20') == 'paired 09-20'
    assert values.field('date', 'paired --') == 'paired 09-20'
    values.clear()
    assert values.field('version', '--') == ''
    assert values.field('count', '--', numeric=True) == '0'


def test_formats_and_empty_observations_do_not_reuse_incompatible_values():
    values = CardValues()
    values.field('rate', '3 ETH', numeric=True)
    assert values.field('rate', '-- IMD', numeric=True) == '0 IMD'
    values.field('date', 'worked 12:31')
    values.field('date', '')
    assert values.field('date', 'worked --:--') == ''
    assert values.field('literal', 'A — B --flag -7', literal=True) == 'A — B --flag -7'
