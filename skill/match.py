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
        self.requested_name = self._extract_timer_name(regex_path)
        self.requested_ordinal = extract_ordinal(self.utterance)

    def _extract_timer_name(self, regex_path) -> Optional[str]:
        """Attempts to extract a timer name from an utterance.

        If the regex name matching logic returns no matches, it might be
        a cancel timer request.  In this case, make another attempt to find the
        timer name in the utterance by removing the first word ("cancel" or some
        variation) then the second word ("timer").

        Args:
            regex_path: The file system path to a file containing regular expressions
                used to find a timer name in the utterance.

        Returns:
            a matched timer name or None if no match found
        """
        timer_name = extract_timer_name(self.utterance, regex_path)
        if timer_name is None:
            # Attempt to extract a name from a "cancel timer" utterance
            words = self.utterance.split()
            possible_name = " ".join(words[1:])
            if possible_name in [timer.name for timer in self.timers]:
                timer_name = possible_name
            else:
                possible_name = " ".join(words[2:])
                if possible_name in [timer.name for timer in self.timers]:
                    timer_name = possible_name
            if timer_name is not None:
                LOG.info(f"Extracted timer name \"{timer_name}\" from utterance")

        return timer_name

    def match(self):
        """Main method to perform the matching"""
        if self.requested_duration is not None or self.requested_name is not None:
            duration_matches = self._match_timers_to_duration()
            name_matches = self._match_timers_to_name()
            print(name_matches)
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

    def _match_timers_to_duration(self) -> List[CountdownTimer]:
        """If the utterance includes a duration, find timers that match it."""
        duration_matches = []
        if self.requested_duration is not None:
            for timer in self.timers:
                if self.requested_duration == timer.duration:
                    duration_matches.append(timer)
            LOG.info("Found {} duration matches".format(len(duration_matches)))

        return duration_matches

    def _match_timers_to_name(self) -> List[CountdownTimer]:
        """If the utterance includes a timer name, find timers that match it."""
        name_matches = []
        if self.requested_name is not None:
            best_score = 0
            for timer in self.timers:
                score = fuzzy_match(self.requested_name, timer.name.lower())
                if score == 1.0:
                    name_matches = [timer]
                    break
                elif score >= FUZZY_MATCH_THRESHOLD and score > best_score:
                    name_matches.insert(0, timer)
            LOG.info("Found {} name matches".format(len(name_matches)))

        return name_matches

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


def get_timers_matching_utterance(
    utterance: str, timers: List[CountdownTimer], regex_path: str
) -> List[CountdownTimer]:
    """Match timers to an utterance that matched a timer intent."""
    matcher = TimerMatcher(utterance, timers, regex_path)
    matcher.match()

    return matcher.matches


def get_timers_matching_reply(
    reply: str, timers: List[CountdownTimer], regex_path: str
) -> List[CountdownTimer]:
    """Match timers to a reply for clarification of which timers to select."""
    matcher = TimerMatcher(reply, timers, regex_path)
    if matcher.requested_name is None:
        matcher.requested_name = reply
    matcher.match()

    return matcher.matches
