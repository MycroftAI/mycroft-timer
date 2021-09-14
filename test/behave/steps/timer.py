"""Steps to support the Timer Skill feature files."""
from typing import Any, List

from behave import given, then

from test.integrationtests.voight_kampff import (
    emit_utterance,
    VoightKampffDialogMatcher,
    VoightKampffEventMatcher,
)

CANCEL_RESPONSES = (
    "no-active-timer",
    "cancel-all",
    "cancelled-single-timer",
    "cancelled-timer-named",
    "cancelled-timer-named-ordinal",
)


@given("an active {duration} timer")
def start_single_timer(context: Any, duration: str):
    """Clear any active timers and start a single timer for a specified duration."""
    _cancel_all_timers(context)
    _start_a_timer(
        context, utterance="set a timer for " + duration, response=["started-timer"]
    )


@given("an active timer named {name}")
def start_single_named_timer(context: Any, name: str):
    """Clear any active timers and start a single named timer for 90 minutes."""
    _cancel_all_timers(context)
    _start_a_timer(
        context,
        utterance="set a timer for 90 minutes named " + name,
        response=["started-timer-named"],
    )


@given("an active timer for {duration} named {name}")
def start_single_named_dialog_timer(context: Any, duration: str, name: str):
    """Clear any active timers and start a single named timer for specified duration."""
    _cancel_all_timers(context)
    _start_a_timer(
        context,
        utterance=f"set a timer for {duration} named {name}",
        response=["started-timer-named"],
    )


@given("multiple active timers")
def start_multiple_timers(context: Any):
    """Clear any active timers and start multiple timers by duration."""
    _cancel_all_timers(context)
    for row in context.table:
        _start_a_timer(
            context,
            utterance="set a timer for " + row["duration"],
            response=["started-timer", "started-timer-named"],
        )


def _start_a_timer(context, utterance: str, response: List[str]):
    """Helper function to start a timer.

    If one of the expected responses is not spoken, cause the step to error out.
    """
    emit_utterance(context.bus, utterance)
    dialog_matcher = VoightKampffDialogMatcher(context, response)
    dialog_matcher.match()
    assert dialog_matcher.match_found, dialog_matcher.error_message


@given("no active timers")
def reset_timers(context: Any):
    """Cancel all active timers to test how skill behaves when no timers are set."""
    _cancel_all_timers(context)


@given("an expired timer")
def let_timer_expire(context: Any):
    """Start a short timer and let it expire to test expiration logic."""
    _cancel_all_timers(context)
    emit_utterance(context.bus, "set a 3 second timer")
    expected_response = ["started-timer"]
    dialog_matcher = VoightKampffDialogMatcher(context, expected_response)
    dialog_matcher.match()
    assert dialog_matcher.match_found, dialog_matcher.error_message
    expected_response = ["timer-expired"]
    dialog_matcher = VoightKampffDialogMatcher(context, expected_response)
    dialog_matcher.match()
    assert dialog_matcher.match_found, dialog_matcher.error_message


def _cancel_all_timers(context: Any):
    """Cancel all active timers.

    If one of the expected responses is not spoken, cause the step to error out.
    """
    emit_utterance(context.bus, "cancel all timers")
    dialog_matcher = VoightKampffDialogMatcher(context, CANCEL_RESPONSES)
    dialog_matcher.match()
    assert dialog_matcher.match_found, dialog_matcher.error_message


@then("the expired timer is no longer active")
def check_expired_timer_removal(context: Any):
    """Confirm that expired timers have been cleared when requested."""
    expected_event = "timer.stopped-expired"
    event_matcher = VoightKampffEventMatcher(expected_event, context)
    event_matcher.match()
    assert event_matcher.match_found, event_matcher.error_message
