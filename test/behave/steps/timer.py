import time
from typing import List

from behave import given, then

from mycroft.util.process_utils import start_message_bus_client
from mycroft.skills.api import SkillApi
from test.integrationtests.voight_kampff import (
    emit_utterance,
    format_dialog_match_error,
    wait_for_dialog_match,
)


# Setup Skill API connection
bus = start_message_bus_client("TimerTestRunner")
SkillApi.connect_bus(bus)
timer_skill = SkillApi.get("mycroft-timer.mycroftai")

CANCEL_RESPONSES = (
    "no-active-timer",
    "cancel-all",
    "cancelled-single-timer",
    "cancelled-timer-named",
    "cancelled-timer-named-ordinal",
)


@given("an active {duration} timer")
def start_single_timer(context, duration):
    """Clear any active timers and start a single timer for a specified duration."""
    _cancel_all_timers()
    _start_a_timer("set a timer for " + duration)


@given("an active timer named {name}")
def start_single_named_timer(context, name):
    """Clear any active timers and start a single named timer for 90 minutes."""
    _cancel_all_timers()
    _start_a_timer("set a timer for 90 minutes named " + name)


@given("an active timer for {duration} named {name}")
def start_single_named_dialog_timer(context, duration, name):
    """Clear any active timers and start a single named timer for specified duration."""
    _cancel_all_timers()
    _start_a_timer(f"set a timer for {duration} named {name}")


@given("multiple active timers")
def start_multiple_timers(context):
    """Clear any active timers and start multiple timers by duration."""
    _cancel_all_timers()
    for row in context.table:
        _start_a_timer("set a timer for " + row["duration"])


def _start_a_timer(utterance: str):
    """Helper function to start a timer.

    If the number of timers is not incremented, cause the step to error out.
    """
    num_timers_pre_start = timer_skill.get_number_of_active_timers()
    timer_skill._create_single_test_timer(utterance)
    num_timers_post_start = timer_skill.get_number_of_active_timers()
    assert num_timers_post_start - num_timers_pre_start == 1, "Did not start new timer."


@given("no active timers")
def reset_timers(context):
    """Cancel all active timers to test how skill behaves when no timers are set."""
    _cancel_all_timers()


@given("an expired timer")
def let_timer_expire(context):
    """Start a short timer and let it expire to test expiration logic."""
    _cancel_all_timers()
    emit_utterance(context.bus, "set a 3 second timer")
    expected_response = ["started-timer"]
    match_found, speak_messages = wait_for_dialog_match(context.bus, expected_response)
    assert match_found, format_dialog_match_error(expected_response, speak_messages)
    expected_response = ["timer-expired"]
    match_found, speak_messages = wait_for_dialog_match(context.bus, expected_response)
    assert match_found, format_dialog_match_error(expected_response, speak_messages)


def _cancel_all_timers():
    """Cancel all active timers."""
    timer_skill._cancel_all_timers_for_test()
    num_timers = timer_skill.get_number_of_active_timers()
    assert num_timers == 0, "Failed to cancel all timers."


@then('the expired timer should stop beeping')
def then_stop_beeping(context):
    # TODO: Better check!
    import psutil

    for i in range(10):
        if "paplay" not in [p.name() for p in psutil.process_iter()]:
            break
        time.sleep(1)
    else:
        assert False, "Timer is still ringing"
