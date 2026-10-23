"""Intro state machine: injected clock, no terminal or filesystem access."""
from .settings import IntroConfig, Egg

LINES = ('Wake up, Pepe...', 'The Swarm has you...', 'Follow the white frog.', 'Lock in, Pepe.')
DEFAULT_EGGS = (
    Egg('morpheus', "I can only show you the door. You're the one that has to walk through it.", 'retry'),
    Egg('vitalik', "The merge is complete. Are you ready to see what's next?", 'proceed'),
    Egg('gm', "gm Pepe. Let's go.", 'proceed'),
    Egg('wagmi', "We're all gonna make it. Starting up...", 'proceed'),
    Egg('ngmi', 'Not with that attitude. Try again.', 'retry'),
    Egg('satoshi', 'Chancellor on brink of second bailout for banks.', 'proceed'),
)


class IntroSequence:
    def __init__(self, config: IntroConfig, *, clock):
        self.config, self.clock = config, clock
        self.accepted = False
        self.delays = [[config.typewriter_speed_ms / 1000 *
                        (2 if line.endswith('...') and i >= len(line) - 3 else 1)
                        for i in range(len(line))] for line in LINES]
        self.typewriter_duration = sum(map(sum, self.delays)) + 4 * 1.2 + 3 * 1.2 + 1.5
        self.enter('typewriter')

    def enter(self, stage, at=None):
        self.stage = stage
        self.started = self.clock() if at is None else at
        self.result = None
        self.buffer, self.response = '', None
        self.response_action, self.response_until = '', 0.0

    @property
    def elapsed(self):
        return max(0, self.clock() - self.started)

    @property
    def blink(self):
        return int(self.elapsed / .53) % 2 == 0

    def typewriter_text(self):
        t = self.elapsed
        for index, (line, delays) in enumerate(zip(LINES, self.delays)):
            duration = sum(delays)
            if t < duration:
                count, due = 0, 0.0
                for delay in delays:
                    due += delay
                    if t + 1e-9 >= due:
                        count += 1
                return line[:count], line, True
            if t < duration + 1.2:
                return line, line, False
            blank = 1.5 if index == len(LINES) - 1 else 1.2
            if t < duration + 1.2 + blank:
                return '', '', False
            t -= duration + 1.2 + blank
        return '', '', False

    def finish(self, result):
        self.result = result
        self.stage = 'done' if result == 'dashboard' else 'exit'

    def tick(self):
        if self.result is not None:
            return
        if self.stage == 'typewriter' and self.elapsed >= self.typewriter_duration:
            self.enter('prompt', self.started + self.typewriter_duration)
        elif self.stage == 'prompt' and self.response is not None and self.clock() >= self.response_until:
            if self.response_action == 'proceed':
                self.enter('rain', self.response_until)
            elif self.response_action == 'exit':
                self.finish('exit')
            else:
                self.enter('prompt', self.response_until)
        elif self.stage == 'rain':
            duration = self.config.rain_duration_ms / 1000 + 4
            if self.elapsed >= duration:
                self.enter('logo', self.started + duration)

    def respond(self, message, action, delay=1.0):
        self.response, self.response_action = message, action
        self.response_until = self.clock() + delay

    def key(self, key, character=None, *, kind='press'):
        if kind != 'press' or self.result is not None:
            return
        if key in ('ctrl+c', 'ctrl+shift+c'):
            self.finish('interrupt')
            return
        skip = self.config.skip_key
        if (skip == 'any' and self.stage not in ('prompt', 'logo') or
                skip in ('any', 'esc') and key == 'escape'):
            self.finish('dashboard')
            return
        if self.stage == 'logo' and self.elapsed >= 3:
            self.finish('dashboard')
        elif self.stage == 'prompt' and self.response is None:
            if key == 'backspace':
                self.buffer = self.buffer[:-1]
            elif key == 'enter':
                if not self.buffer or self.buffer.lower() == 'y':
                    self.accepted = self.buffer.lower() == 'y'
                    self.respond('locking in...', 'proceed', .8)
                elif self.buffer.lower() == 'n':
                    self.respond('Maybe next time, Pepe.', 'exit')
                else:
                    egg = next((e for e in (*self.config.easter_eggs, *DEFAULT_EGGS)
                                if e.input.lower() == self.buffer.lower()), None)
                    self.respond(egg.response if egg else 'There is no spoon. Try again.',
                                 egg.action if egg else 'retry')
            elif character and character.isprintable():
                if character.lower() == 'y' and not self.buffer:
                    self.accepted = True
                    self.respond('locking in...', 'proceed', .8)
                else:
                    self.buffer = (self.buffer + character)[:64]
