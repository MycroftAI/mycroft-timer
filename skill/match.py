from mycroft.util.log import LOG
from .name_extractor import extract_timer_name
from .util import extract_ordinal, extract_timer_duration, find_timer_name_in_utterance

FUZZY_MATCH_THRESHOLD = 0.7

class TimerMatcher:
    def __init__(self, utterance, timers, regex_path):
        self.utterance = utterance
        self.timers = timers
        self.matches = None
        self.requested_duration, _ = extract_timer_duration(self.utterance)
        self.requested_name = extract_timer_name(self.utterance, regex_path)
        self.requested_ordinal = extract_ordinal(self.utterance)

    def match(self):
        if self.requested_duration is not None or self.requested_name is not None:
            duration_matches = self._match_timers_to_duration()
            name_matches = self._match_timers_to_name()
            if duration_matches and name_matches:
                self.matches = [
                    timer for timer in name_matches if timer in duration_matches
                ]
            elif name_matches:
                self.matches = name_matches
            elif duration_matches:
                self.matches = duration_matches
        if self.requested_ordinal is not None:
            self._match_ordinal()

    def _match_timers_to_duration(self):
        duration_matches = []
        if self.requested_duration is not None:
            for timer in self.timers:
                if self.requested_duration == timer.duration:
                    duration_matches.append(timer)
        LOG.info("Found {} duration matches".format(len(duration_matches)))

        return duration_matches

    def _match_timers_to_name(self):
        name_matches = []
        for timer in self.timers:
            name_found = find_timer_name_in_utterance(
                timer.name, self.utterance, FUZZY_MATCH_THRESHOLD
            )
            if name_found:
                name_matches.append(timer)
        LOG.info("Found {} name matches".format(len(name_matches)))

        return name_matches

    def _match_ordinal(self):
        if self.matches is not None:
            self._filter_matches_by_ordinal()
        else:
            self._match_timers_to_ordinal()

    def _filter_matches_by_ordinal(self):
        for timer in self.matches:
            if self.requested_ordinal == timer.ordinal:
                self.matches = [timer]

    def _match_timers_to_ordinal(self):
        for index, timer in enumerate(self.timers):
            ordinal_match_value = index + 1
            if self.requested_ordinal == ordinal_match_value:
                self.matches = [timer]


def get_timers_matching_utterance(utterance, timers, regex_path):
    matcher = TimerMatcher(utterance, timers, regex_path)
    matcher.match()

    return matcher.matches


def get_timers_matching_reply(reply, timers, regex_path):
    matcher = TimerMatcher(reply, timers, regex_path)
    if matcher.requested_name is None:
        matcher.requested_name = reply
    matcher.match()

    return matcher.matches
