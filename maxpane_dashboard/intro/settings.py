"""Read-only TOML settings and palettes compatible with the Rust intro."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class Egg:
    input: str
    response: str
    action: str


@dataclass(frozen=True)
class IntroConfig:
    enabled: bool = True
    mode: str = 'first_run'
    tagline: str = 'katakana'
    skip_key: str = 'any'
    rain_duration_ms: int = 3500
    typewriter_speed_ms: int = 45
    color_scheme: str = 'phosphor'
    colors: dict = field(default_factory=dict)
    easter_eggs: tuple[Egg, ...] = ()

    def should_show(self, seen: bool) -> bool:
        return self.enabled and self.mode != 'never' and (self.mode == 'always' or not seen)


def load_config(path: Path) -> IntroConfig:
    if not path.exists():
        return IntroConfig()
    data = tomllib.loads(path.read_text(encoding='utf-8')).get('intro', {})
    if not isinstance(data, dict):
        raise ValueError('[intro] must be a table')
    defaults = IntroConfig()
    values = {}
    for name in ('enabled', 'mode', 'tagline', 'skip_key', 'rain_duration_ms',
                 'typewriter_speed_ms', 'color_scheme'):
        value = data.get(name, getattr(defaults, name))
        if type(value) is not type(getattr(defaults, name)):
            raise ValueError(f'intro.{name} has the wrong type')
        if name.endswith('_ms') and not 0 <= value <= 2**64 - 1:
            raise ValueError(f'intro.{name} must be an unsigned 64-bit integer')
        values[name] = value
    colors = data.get('colors', {})
    if not isinstance(colors, dict) or any(not isinstance(colors[k], str)
            for k in ('text', 'background', 'rain_bright', 'rain_dim', 'logo') if k in colors):
        raise ValueError('intro.colors must contain color strings')
    eggs = data.get('easter_eggs', [])
    if not isinstance(eggs, list) or any(not isinstance(egg, dict) or
            any(not isinstance(egg.get(k), str) for k in ('input', 'response', 'action')) for egg in eggs):
        raise ValueError('intro.easter_eggs must contain input, response and action strings')
    return IntroConfig(**values, colors=colors,
                       easter_eggs=tuple(Egg(**{k: egg[k] for k in ('input', 'response', 'action')}) for egg in eggs))


def palette(config: IntroConfig) -> dict[str, str]:
    background, text, bright, dim = {
        'phosphor': ('#000000', '#33ff33', '#c8ffc8', '#005500'),
        'amber': ('#000000', '#ffb000', '#ffdc96', '#643c00'),
        'c64': ('#40318d', '#6c5eb5', '#a096dc', '#40318d'),
    }.get(config.color_scheme, ('#000000', '#33ff33', '#c8ffc8', '#005500'))
    result = dict(background=background, text=text, rain_bright=bright, rain_dim=dim, logo=text)
    if config.color_scheme == 'custom':
        for name in result:
            value = config.colors.get(name, '')
            if re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                result[name] = value
    return result
