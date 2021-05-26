import re
from datetime import timedelta
from typing import Optional, Tuple

from num2words import num2words

from mycroft.util.log import LOG
from mycroft.util.parse import extract_duration, extract_number, fuzzy_match


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
        LOG.info("No duration found in request")
    else:
        duration, remaining_utterance = extract_result
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
    pattern = r'\s\s{}'.format(conjunction)
    remaining_utterance = re.sub(pattern, '', utterance, flags=re.IGNORECASE)

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

def find_timer_name_in_utterance(timer_name, utterance, threshold):
    found = False
    best_score = 0
    utterance_words = utterance.split()
    utterance_word_count = len(utterance_words)
    name_word_count = len(timer_name.split())

    for index in range(utterance_word_count - name_word_count, -1, -1):
        utterance_part = ' '.join(utterance_words[index:index + utterance_word_count])
        score = fuzzy_match(utterance_part, timer_name.lower())

        if score > best_score and score >= threshold:
            LOG.info(
                "Timer name \"{}\" matched with score of {}".format(timer_name, score)
            )
            best_score = score
            found = True

    return found

def get_speakable_ordinal(timer, language):
    """Get speakable ordinal if other timers exist with same duration."""
    return num2words(timer.ordinal, to="ordinal", lang=language)

