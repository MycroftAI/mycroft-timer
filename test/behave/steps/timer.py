from threading import Event
import time
from typing import List

from behave import given, then

from test.integrationtests.voight_kampff import (
    emit_utterance,
    format_dialog_match_error,
    wait_for_dialog_match,
    then_wait
)

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
    _cancel_all_timers(context)
    _start_a_timer(
        context.bus, utterance="set a timer for " + duration, response=["started-timer"]
    )


@given("an active timer named {name}")
def start_single_named_timer(context, name):
    """Clear any active timers and start a single named timer for 90 minutes."""
    _cancel_all_timers(context)
    _start_a_timer(
        context.bus,
        utterance="set a timer for 90 minutes named " + name,
        response=["started-timer-named"],
    )


@given("an active timer for {duration} named {name}")
def start_single_named_dialog_timer(context, duration, name):
    """Clear any active timers and start a single named timer for specified duration."""
    _cancel_all_timers(context)
    _start_a_timer(
        context.bus,
        utterance=f"set a timer for {duration} named {name}",
        response=["started-timer-named"],
    )


@given("multiple active timers")
def start_multiple_timers(context):
    """Clear any active timers and start multiple timers by duration."""
    _cancel_all_timers(context)
    for row in context.table:
        _start_a_timer(
            context.bus,
            utterance="set a timer for " + row["duration"],
            response=["started-timer", "started-timer-named"],
        )


def _start_a_timer(bus, utterance: str, response: List[str]):
    """Helper function to start a timer.

    If one of the expected responses is not spoken, cause the step to error out.
    """
    emit_utterance(bus, utterance)
    match_found, speak_messages = wait_for_dialog_match(bus, response)
    assert match_found, format_dialog_match_error(response, speak_messages)


@given("no active timers")
def reset_timers(context):
    """Cancel all active timers to test how skill behaves when no timers are set."""
    _cancel_all_timers(context)


def _cancel_all_timers(context):
    """Cancel all active timers.

    If one of the expected responses is not spoken, cause the step to error out.
    """
    emit_utterance(context.bus, "cancel all timers")
    match_found, speak_messages = wait_for_dialog_match(context.bus, CANCEL_RESPONSES)
    assert match_found, format_dialog_match_error(CANCEL_RESPONSES, speak_messages)


@given("a timer is expired")
def let_timer_expire(context):
    """Start a short timer and let it expire to test expiration logic."""
    emit_utterance(context.bus, "set a 3 second timer")
    expected_response = ["started-timer"]
    match_found, speak_messages = wait_for_dialog_match(context.bus, expected_response)
    assert match_found, format_dialog_match_error(expected_response, speak_messages)
    time.sleep(4)


@then('"mycroft-timer" should stop beeping')
def then_stop_beeping(context):
    """Listen on the bus for beep requests and ensure it stops."""
    played_beeps = 0
    failed_event = Event()
    def count_played_beeps(_):
        nonlocal played_beeps
        nonlocal failed_event
        played_beeps += 1
        if played_beeps >= 2:
            failed_event.set()

    context.bus.on("skill.timer.play_beep", count_played_beeps)
    failed_event.wait(timeout=5.0)
    context.bus.remove("skill.timer.play_beep", count_played_beeps)
    if failed_event.is_set():
        assert false, "The beeping didn't stop"
