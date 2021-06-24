import re
from typing import List

from mycroft.util.log import LOG

class TimerNameExtractor:
    def __init__(self, utterance, regex_file_path):
        self.utterance = utterance
        self.regex_file_path = regex_file_path
        self.extracted_name = None

    def extract(self):
        """Get the timer name using regex on an utterance."""
        if self.regex_file_path:
            regex_patterns = self._get_timer_name_search_patterns()
            self._search_for_timer_name(regex_patterns)

    def _get_timer_name_search_patterns(self) -> List[str]:
        regex_patterns = []
        with open(self.regex_file_path) as regex_file:
            for pattern in regex_file.readlines():
                pattern = pattern.strip()
                if pattern and pattern[0] != "#":
                    regex_patterns.append(pattern)

        return regex_patterns

    def _search_for_timer_name(self, regex_patterns: List[str]):
        for pattern in regex_patterns:
            pattern_match = re.search(pattern, self.utterance)
            if pattern_match:
                self._handle_pattern_match(pattern_match)
                if self.extracted_name is not None:
                    break
        self._log_extraction_result()

    def _handle_pattern_match(self, pattern_match):
        try:
            extracted_name = pattern_match.group("Name").strip()
            if extracted_name:
                self.extracted_name = extracted_name
        except IndexError:
            pass

    def _log_extraction_result(self):
        if self.extracted_name is None:
            LOG.info('No timer name extracted from utterance')
        else:
            LOG.info('Timer name extracted from utterance: ' + self.extracted_name)

def extract_timer_name(utterance: str, regex_file_path: str) -> str:
    extractor = TimerNameExtractor(utterance, regex_file_path)
    extractor.extract()

    return extractor.extracted_name