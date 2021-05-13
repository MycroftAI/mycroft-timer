from datetime import timedelta

from mycroft.util.time import now_utc


class CountdownTimer:
    def __init__(self, duration: timedelta, name: str):
        self.duration = duration
        self.name = name
        self.expiration = now_utc() + duration
        self.index = None
        self.announced = False
        self.ordinal = 0
