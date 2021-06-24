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
"""Utility functions for the timer skill."""
import re
from datetime import timedelta
from typing import Optional, Tuple

from mycroft.util.format import pronounce_number
from mycroft.util.log import LOG
from mycroft.util.parse import extract_duration, extract_number, fuzzy_match

FUZZY_MATCH_THRESHOLD = 0.7


def extract_timer_duration(utterance: str) -> Tuple[Optional[timedelta], Optional[str]]:
    """Extract duration in seconds.

    Args:
        utterance: Full request, e.g. "set a 30 second timer"

    Returns
        Number of seconds requested (or None if no duration was extracted) and remainder
        of utterance
    """
    normalized_utterance = _normalize_utterance(utterance)
    extract_result = extract_duration(normalized_utterance)
    if extract_result is None:
        duration = remaining_utterance = None
    else:
        duration, remaining_utterance = extract_result
    if duration is None:
        LOG.info("No duration found in request")
    else:
        LOG.info("Duration of {} found in request".format(duration))

    return duration, remaining_utterance


def _normalize_utterance(utterance: str) -> str:
    """Make the duration of the timer in the utterance consistent for parsing.

    Some STT engines return "30-second timer" not "30 second timer".

    Args:
        utterance: Full request, e.g. "set a 30 second timer"

    Returns:
        The same utterance with any dashes replaced by spaces.

    """
    # TODO: Fix inside parsers
    return utterance.replace("-", " ")


def remove_conjunction(conjunction: str, utterance: str) -> str:
    """Remove the specified conjunction from the utterance.

    For example, remove the " and" left behind from extracting "1 hour" and "30 minutes"
    from "for 1 hour and 30 minutes".  Leaving it behind can confuse other intent
    parsing logic.

    Args:
        conjunction: translated conjunction (like the word "and") to be
            removed from utterance
        utterance: Full request, e.g. "set a 30 second timer"

    Returns:
        The same utterance with any dashes replaced by spaces.

    """
    pattern = r"\s\s{}".format(conjunction)
    remaining_utterance = re.sub(pattern, "", utterance, flags=re.IGNORECASE)

    return remaining_utterance


def extract_ordinal(utterance: str) -> str:
    """Extract ordinal number from the utterance.

    Args:
        utterance: Full request, e.g. "set a 30 second timer"

    Returns:
        An integer representing the numeric value of the ordinal or None if no ordinal
        is found in the utterance.
    """
    ordinal = None
    extracted_number = extract_number(utterance, ordinals=True)
    if type(extracted_number) == int:
        ordinal = extracted_number

    return ordinal


def find_timer_name_in_utterance(timer_name: str, utterance: str) -> bool:
    """Match a timer name to a name requested in the user request.

    Use "fuzzy matching" to perform the search in case the STT translation is not
    a precise match.

    Args:
        timer_name: name of a timer to match against
        utterance: the user request.

    Returns:
        Whether or not a match was found.
    """
    found = False
    best_score = 0
    utterance_words = utterance.split()
    utterance_word_count = len(utterance_words)
    name_word_count = len(timer_name.split())

    for index in range(utterance_word_count - name_word_count, -1, -1):
        utterance_part = " ".join(utterance_words[index : index + utterance_word_count])
        score = fuzzy_match(utterance_part, timer_name.lower())

        if score > best_score and score >= FUZZY_MATCH_THRESHOLD:
            LOG.info(
                'Timer name "{}" matched with score of {}'.format(timer_name, score)
            )
            best_score = score
            found = True

    return found


def get_speakable_ordinal(ordinal) -> str:
    """Get speakable ordinal if other timers exist with same duration.

    Args:
        ordinal: if more than one timer exists for the same duration, this value will
            indicate if it is the first, second, etc. instance of the duration.

    Returns:
        The ordinal that can be passed to TTS (i.e. "first", "second")
    """
    return pronounce_number(ordinal, ordinals=True)


def format_timedelta(time_delta: timedelta) -> str:
    """Convert number of seconds into a displayable time string.

    Args:
        time_delta: an amount of time to convert to a displayable string.

    Returns:
        the value to display on a device's screen or faceplate.
    """
    hours = abs(time_delta // timedelta(hours=1))
    minutes = abs((time_delta - timedelta(hours=hours)) // timedelta(minutes=1))
    seconds = abs(
        (time_delta - timedelta(hours=hours) - timedelta(minutes=minutes))
        // timedelta(seconds=1)
    )
    if hours:
        time_elements = [str(hours), str(minutes).zfill(2), str(seconds).zfill(2)]
    else:
        time_elements = [str(minutes).zfill(2), str(seconds).zfill(2)]
    formatted_time_delta = ":".join(time_elements)

    return formatted_time_delta
