from datetime import timedelta

from mycroft.util.format import nice_duration
from mycroft.util.time import now_utc


class CountdownTimer:
    _speakable_duration = None

    def __init__(self, duration: timedelta, name: str):
        self.duration = duration
        self.name = name
        self.expiration = now_utc() + duration
        self.index = None
        self.announced = False
        self.ordinal = 0

    @property
    def expired(self):
        return self.expiration < now_utc()

    @property
    def speakable_duration(self):
        if self._speakable_duration is None:
            self._speakable_duration = nice_duration(self.duration)

        return self._speakable_duration
