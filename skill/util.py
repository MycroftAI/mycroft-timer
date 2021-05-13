import re
from typing import Optional, Tuple

from mycroft.util.parse import extract_duration


def _duration(utterance: str, language: str) -> Tuple[Optional[int], str]:
    """Extract duration in seconds.

    :param utterance: Full request, e.g. "set a 30 second timer"
    :param language: Language of the utterance
    :return seconds requested (or None if no duration was extracted) and remainder
        of utterance
    """
    duration = None
    # Some STT engines return "30-second timer" not "30 second timer"
    # Deal with that before calling extract_duration().
    # TODO: Fix inside parsers
    utterance_to_parse = utterance.replace("-", " ")
    extracted_duration, remaining_utterance = extract_duration(utterance_to_parse, language)
    if extracted_duration is not None:
        # Remove " and" left behind from "for 1 hour and 30 minutes"
        # prevents it being interpreted as a name "for  and"
        remaining_utterance = re.sub(r'\s\sand', '', remaining_utterance, flags=re.I)
        duration = extracted_duration.total_seconds()
        if duration == 1:  # prevent "set one timer" doing 1 sec timer
            remaining_utterance = utterance

    return duration, remaining_utterance
