"""Small presentation-only memory for explicitly typed card fields."""
from copy import deepcopy
import re

MISSING = re.compile(r'(?<![\w-])(?:--:--|--|—|-)(?![\w-])')
NUMBER_OR_MISSING = re.compile(
    r'(?<![\w.])(?:--|—|-(?!\d)|[+-]?\d[\d,]*(?:\.\d+)?(?:[eE][+-]?\d+)?[kKMBT]?)(?![\d.,])')


class CardValues:
    def __init__(self):
        self.values = {}
        self.parts = {}

    def clear(self):
        self.values.clear()
        self.parts.clear()

    def retain(self, key, value, *, missing=False):
        if not missing:
            self.values[key] = deepcopy(value)
        return deepcopy(self.values.get(key))

    def field(self, key, value, *, numeric=False, literal=False):
        """Keep observations, including zero/empty; never remember a fallback."""
        if literal:
            return self.retain(key, value)
        if not value:
            self.parts.pop(key, None)
            return self.retain(key, '')
        if not numeric:
            return self.retain(key, value, missing=bool(MISSING.search(value))) or ''
        matches = list(NUMBER_OR_MISSING.finditer(value))
        if not matches:
            return value
        if not any(MISSING.fullmatch(match.group()) for match in matches):
            self.retain(key, value)
        ends = [0] + [match.end() for match in matches]
        template = tuple(value[start:match.start()] for start, match in zip(ends, matches)) + (value[ends[-1]:],)
        old_template, old_parts = self.parts.get(key, (None, []))
        if template != old_template:
            old_parts = [None] * len(matches)
        observed = [old if MISSING.fullmatch(match.group()) else match.group()
                    for match, old in zip(matches, old_parts)]
        self.parts[key] = template, observed
        return ''.join(prefix + (part if part is not None else '0')
                       for prefix, part in zip(template, observed)) + template[-1]
