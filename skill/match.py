# Copyright 2021 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Logic to match one or more timers to a user's request."""
import re
from typing import List, Optional

from mycroft.util.log import LOG
from mycroft.util.parse import fuzzy_match
from .name_extractor import extract_timer_name
from .timer import CountdownTimer
from .util import extract_ordinal, extract_timer_duration

FUZZY_MATCH_THRESHOLD = 0.7


class TimerMatcher:
    """Matches timers to a request made by the user."""

    def __init__(self, utterance: str, timers: List[CountdownTimer], regex_path: str):
        self.utterance = utterance
        self.timers = timers
        self.matches = None
        self.requested_duration, _ = extract_timer_duration(self.utterance)
        self.requested_name = extract_timer_name(self.utterance, regex_path) or utterance
        self.normalized_name = self._get_normalized_name()
        self.requested_ordinal = extract_ordinal(self.utterance)

    def match(self):
        """Main method to perform the matching"""
        name_match = self._match_timer_to_name()
        if name_match:
            self.matches = [name_match]
        else:
            duration_matches = self._match_timers_to_duration()
            if duration_matches:
                self.matches = duration_matches
        if self.requested_ordinal is not None:
            self._match_ordinal()

    def _match_timers_to_duration(self) -> List[CountdownTimer]:
        """If the utterance includes a duration, find timers that match it."""
        duration_matches = []
        if self.requested_duration is not None:
            for timer in self.timers:
                if self.requested_duration == timer.duration:
                    duration_matches.append(timer)
            LOG.info("Found {} duration matches".format(len(duration_matches)))

        return duration_matches

    def _match_timer_to_name(self) -> CountdownTimer:
        """Finds a timer that matches the name requested by the user.

        In a conversation mode, when the user is asked "which timer?" the answer
        can be the name of the timer.  Timers that are not given specific names are
        named "timer x" but the name extractor will only extract "x".  So try to
        prepend the word "timer" to get a match if other matches fail.

        Returns:
            Timer matching the name requested by the user.
        """
        matched_timer = None
        for timer in self.timers:
            match = (
                timer.name == self.utterance
                or timer.name == self.requested_name
                or timer.name == "timer " + str(self.requested_name)
                or timer.name == self.normalized_name
                or timer.name == "timer " + str(self.normalized_name)
            )
            if match:
                matched_timer = timer
                LOG.info(f"Match found for timer name '{matched_timer.name}'")
                break

        return matched_timer

    def _match_ordinal(self):
        """If the utterance includes a ordinal, find timers that match it."""
        if self.matches is not None:
            self._filter_matches_by_ordinal()
        else:
            self._match_timers_to_ordinal()

    def _filter_matches_by_ordinal(self):
        """Examine the timers already filtered by name and/or duration for ordinal."""
        for timer in self.matches:
            if self.requested_ordinal == timer.ordinal:
                self.matches = [timer]
                break

    def _match_timers_to_ordinal(self):
        """No timers have matched to name and/or duration so search all for ordinal."""
        for index, timer in enumerate(self.timers):
            ordinal_match_value = index + 1
            if self.requested_ordinal == ordinal_match_value:
                self.matches = [timer]

    def _get_normalized_name(self) -> str:
        """Replace STT oddities"""
        name = self.requested_name
        name = re.sub(r"\bto\b", "2", name)
        name = re.sub(r"\bfor\b", "4", name)
        return name
