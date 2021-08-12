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
"""Logic to extract a timer name from a user request."""
import re
from typing import List

from mycroft.util.log import LOG


class TimerNameExtractor:
    """Attempt to find a name in the an utterance and match it to active timers."""

    def __init__(self, utterance, regex_file_path):
        self.utterance = utterance
        self.regex_file_path = regex_file_path
        self.extracted_name = None

    def extract(self):
        """Attempt to find a timer name in a user request."""
        if self.regex_file_path:
            regex_patterns = self._get_timer_name_search_patterns()
            self._search_for_timer_name(regex_patterns)

    def _get_timer_name_search_patterns(self) -> List[str]:
        """Read a file containing one or more regular expressions to find timer name."""
        regex_patterns = []
        with open(self.regex_file_path) as regex_file:
            for pattern in regex_file.readlines():
                pattern = pattern.strip()
                if pattern and pattern[0] != "#":
                    regex_patterns.append(pattern)

        return regex_patterns

    def _search_for_timer_name(self, regex_patterns: List[str]):
        """Match regular expressions to user request looking for timer name match."""
        for pattern in regex_patterns:
            pattern_match = re.search(pattern, self.utterance)
            if pattern_match:
                self._handle_pattern_match(pattern_match)
                if self.extracted_name is not None:
                    break
        self._log_extraction_result()

    def _handle_pattern_match(self, pattern_match):
        """Extract the timer name from the utterance."""
        try:
            extracted_name = pattern_match.group("Name").strip()
            if extracted_name:
                self.extracted_name = extracted_name
        except IndexError:
            pass

    def _log_extraction_result(self):
        """Log the results of the matching."""
        if self.extracted_name is None:
            LOG.info("No timer name extracted from utterance")
        else:
            LOG.info("Timer name extracted from utterance: " + self.extracted_name)


def extract_timer_name(utterance: str, regex_file_path: str) -> str:
    """Helper function to extract a timer name from an utterance."""
    extractor = TimerNameExtractor(utterance, regex_file_path)
    extractor.extract()

    return extractor.extracted_name
