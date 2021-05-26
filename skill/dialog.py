from mycroft.util.format import nice_duration
from mycroft.util.time import now_utc
from .util import get_speakable_ordinal

SINGLE_UNNAMED_TIMER_NAME = "Timer"

class TimerDialog:
    def __init__(self, timer, language):
        self.timer = timer
        self.language = language
        self.name = None
        self.data = None

    def build_add_dialog(self, timer_count):
        self.name = "started-timer"
        self.data = dict(duration=self.timer.speakable_duration)
        if timer_count > 1:
            self.name += "-named"
            self.data.update(name=self.timer.name)
            self._check_for_ordinal()

    def build_status_dialog(self):
        now = now_utc()
        if self.timer.expired:
            self.name = 'time-elapsed'
            time_since_expiration = now - self.timer.expiration
            self.data = dict(time_diff=nice_duration(time_since_expiration.seconds))
        else:
            self.name = 'time-remaining'
            time_until_expiration = self.timer.expiration - now
            self.data = dict(time_diff=nice_duration(time_until_expiration.seconds))
        self._check_for_named_timer()
        self._check_for_ordinal()
        self.data.update(duration=self.timer.speakable_duration)

    def build_details_dialog(self):
        self.name = 'timer-details'
        self.data = dict(duration=self.timer.speakable_duration)
        self._check_for_named_timer()
        self._check_for_ordinal()

    def build_cancel_dialog(self):
        self.name = "cancelled-timer"
        self.data = dict(duration=self.timer.speakable_duration)
        self._check_for_named_timer()
        self._check_for_ordinal()

    def build_cancel_confirm_dialog(self):
        self.name = 'confirm-timer-to-cancel'
        timer_name = self.timer.name or self.timer.speakable_duration
        self.data = dict(name=timer_name)

    def _check_for_named_timer(self):
        if self.timer.name != SINGLE_UNNAMED_TIMER_NAME:
            self.name += '-named'
            self.data.update(name=self.timer.name)

    def _check_for_ordinal(self):
        if self.timer.ordinal > 1:
            self.name += '-ordinal'
            speakable_ordinal = get_speakable_ordinal(self.timer, self.language)
            self.data.update(ordinal=speakable_ordinal)
