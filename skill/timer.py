from datetime import timedelta

from mycroft.util.format import nice_duration
from mycroft.util.time import now_utc
from .util import format_timedelta


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

    @property
    def time_remaining(self):
        if self.expired:
            formatted_timedelta = None
        else:
            time_remaining = self.expiration - now_utc()
            formatted_timedelta = format_timedelta(time_remaining)

        return formatted_timedelta

    @property
    def percent_remaining(self):
        if self.expired:
            percent_remaining = None
        else:
            time_remaining = self.expiration - now_utc()
            percent_remaining = (
                time_remaining.total_seconds() / self.duration.total_seconds()
            )

        return percent_remaining

    @property
    def time_since_expiration(self):
        if self.expired:
            time_since_expiration = now_utc() - self.expiration
            formatted_timedelta = "-" + format_timedelta(time_since_expiration)
        else:
            formatted_timedelta = None

        return formatted_timedelta

    @property
    def display_data(self):
        return dict(
            expired=self.expired,
            percentRemaining=self.percent_remaining,
            timerName=self.name,
            timeDelta=self.time_remaining or self.time_since_expiration
        )

