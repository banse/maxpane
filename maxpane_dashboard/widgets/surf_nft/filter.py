"""Primitive filter drafts using the shared four-column native editor."""
from rich.text import Text
from textual.containers import Grid
from textual.message import Message
from textual.widgets import Input, Select

from maxpane_dashboard.widgets.filter_editor import FilterEditorBase, field_id
from maxpane_dashboard.widgets.markup_safety import flatten

# Agreement test binds these literal options to the pure projection contract.
FILTER_DEFAULTS={'chain':'all','stage':'launched','mint':'all','idmd':'all','utility':'all','search':'','sort':'newest'}
FILTER_VALUES={
    'chain':('all','ethereum','robinhood'), 'stage':('launched','building'),
    'mint':('all','open','route-open','closed','not-started','sold-out','ended','paused','unconfigured','auction / delivery',
            'conditional','awaiting-season-end','awaiting-finalization','blank-season','auction-open','unknown'),
    'idmd':('all','yes','conditional','no','unknown'), 'sort':('newest','name'),
}


class NftFilterApplyRequested(Message):
    pass


class NftFilterResetRequested(Message):
    pass


class NftFilterEditor(FilterEditorBase):
    APPLY_MESSAGE=NftFilterApplyRequested
    RESET_MESSAGE=NftFilterResetRequested
    SELECT_OPTIONS={key:tuple(({'all':'All','yes':'IDMD free','no':'No IDMD benefit',
        'route-open':'Any open route','building':'In the making','launched':'Launched',
        'name':'Name A–Z','newest':'Newest first'}.get(value,value.title()),value) for value in options)
        for key,options in FILTER_VALUES.items()}
    SELECT_OPTIONS['utility']=(('All','all'),)
    DEFAULT_CSS='''
    NftFilterEditor .filter-group {margin-bottom: 0; padding-bottom: 1;}
    NftFilterEditor .filter-group Select, NftFilterEditor .filter-group Input {height: 1;}
    '''

    def select_group(self,title,field):
        return self.titled_group(title,Select(self.SELECT_OPTIONS[field],allow_blank=False,
            value=FILTER_DEFAULTS[field],compact=True,id=field_id(field),classes='filter-field'))

    def compose(self):
        yield self.error_line()
        with Grid(classes='filter-groups'):
            for title,field in [('CHAIN','chain'),('STAGE','stage'),('MINT','mint'),('IDMD','idmd'),
                                ('UTILITY','utility'),('SORT','sort')]:
                yield self.select_group(title,field)
            yield self.titled_group('SEARCH',Input(placeholder='Collection, contract or job',compact=True,
                id=field_id('search'),classes='filter-field'))
        yield self.actions()

    def set_utilities(self,kinds):
        values=sorted({kind for kind in kinds if isinstance(kind,str) and kind and kind!='all'})
        self.query_one('#filter-utility',Select).set_options([('All','all')]+[(Text(flatten(kind)),kind) for kind in values])
        self._utility_values={'all',*values}

    def values(self):
        return dict(super().values(),search=self.query_one('#filter-search',Input).value)

    def set_values(self,values):
        for key,default in FILTER_DEFAULTS.items():
            value=values.get(key,default)
            if key=='search':
                self.query_one('#filter-search',Input).value=str(value or '')
            else:
                allowed=getattr(self,'_utility_values',{'all'}) if key=='utility' else FILTER_VALUES[key]
                self.query_one('#'+field_id(key),Select).value=value if value in allowed else default
