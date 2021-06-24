# Copyright 2017 Mycroft AI Inc.
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
"""A skill to set one or more timers for things like a kitchen timer."""
import time
import pickle
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

from adapt.intent import IntentBuilder

from mycroft import MycroftSkill, intent_handler
from mycroft.audio import wait_while_speaking
from mycroft.skills.intent_service import AdaptIntent
from mycroft.messagebus.message import Message
from mycroft.util import play_wav
from mycroft.util.format import pronounce_number, nice_duration, join_list
from mycroft.util.parse import extract_duration
from mycroft.util.time import now_utc, now_local
from .skill import (
    CountdownTimer,
    extract_timer_duration,
    extract_timer_name,
    FaceplateRenderer,
    get_timers_matching_reply,
    get_timers_matching_utterance,
    remove_conjunction,
    TimerDialog
)

ONE_DAY = 86400
MARK_I = 'mycroft_mark_1'
MARK_II = 'mycroft_mark_2'


class TimerValidationException(Exception):
    """This is not really for errors, just a handy way to tidy up the initial checks."""
    pass

class TimerSkill(MycroftSkill):
    def __init__(self):
        """Constructor"""
        super().__init__("TimerSkill")
        self.active_timers = []
        self.sound_file_path = Path(__file__).parent.joinpath('sounds', 'two-beep.wav')
        self.platform = self.config_core["enclosure"].get("platform", "unknown")
        self.mute = False
        self.timer_index = 0
        self.display_group = 0
        self.regex_file_path = self.find_resource('name.rx', 'regex')
        self.all_timers_words = [word.strip() for word in self.translate_list('all')]

    def initialize(self):
        """Initialization steps to execute after the skill is loaded."""
        self.load_timers()
        if self.active_timers:
            self._start_timer_display()
            self._start_expiration_check()
        else:
            self.disable_intent("handle_cancel_timer")
            self.disable_intent("handle_mute_timer")

        # To prevent beeping while listening
        self.add_event('recognizer_loop:record_begin', self.handle_listener_started)
        self.add_event('recognizer_loop:record_end', self.handle_listener_ended)
        self.add_event('speak', self.handle_speak)
        self.add_event(
            'skill.mycrofttimer.verify.cancel', self.handle_verify_stop_timer
        )

    @intent_handler(
        AdaptIntent().require("Start").require("Timer").optionally("Name")
    )
    def handle_start_timer(self, message: Message):
        """Common handler for start_timer intents.

        Args:
            message: Message Bus event information from the intent parser
        """
        self._start_new_timer(message)

    @intent_handler('start.timer.intent')
    def handle_start_timer_padatious(self, message: Message):
        """Handles custom timer start phrases (e.g. "ping me in 5 minutes").

        Args:
            message: Message Bus event information from the intent parser
        """
        self._start_new_timer(message)

    # TODO: REFACTOR - Why is this commented out?
    # Handles custom status phrases eg 'How much time left'
    # @intent_handler('timer.status.intent')
    # def handle_status_timer_padatious(self, message):
    #     self._communicate_timer_status(message)

    @intent_handler(AdaptIntent().require("Query").
                    optionally("Status").require("Timer").optionally("All"))
    def handle_query_status_timer(self, message: Message):
        """Handles timer status requests (e.g. "do I have any timers").

        Args:
            message: Message Bus event information from the intent parser
        """
        self._communicate_timer_status(message)

    @intent_handler(AdaptIntent().optionally("Query").
                    require("Status").one_of("Timer", "Time").
                    optionally("All").optionally("Duration").
                    optionally("Name"))
    def handle_status_timer(self, message: Message):
        """Handles timer status requests (e.g. "timer status", "status of timers").

        Args:
            message: Message Bus event information from the intent parser
        """
        self._communicate_timer_status(message)

    @intent_handler(IntentBuilder("").require("Mute").require("Timer"))
    def handle_mute_timer(self, _):
        """Handles muting the timer's beeping."""
        # TODO: REFACTOR - is this needed in addition to stop timer?
        self.mute = True

    @intent_handler('stop.timer.intent')
    def handle_stop_timer(self, message: Message):
        """Stop the first expired timer in the queue.

        If the timer is beeping, no confirmation is required; treat it like a stop
        button press.  Don't cancel active timers with only "cancel" as utterance

        Args:
            message: Message Bus event information from the intent parser
        """
        timer = self._get_next_timer()
        if timer.expired:
            self.stop()
        elif message.data.get('utterance') != "cancel":
            self._cancel_timers(message)

    @intent_handler(AdaptIntent().require("Cancel").require("Timer")
                    .optionally("Connector").optionally("All"))
    def handle_cancel_timer(self, message):
        """Handles cancelling active timers.

        Args:
            message: Message Bus event information from the intent parser
        """
        self._cancel_timers(message)

    def shutdown(self):
        """Perform any cleanup tasks before skill shuts down."""
        # TODO: REFACTOR - figure out what the below comment means.
        # Clear the timer list, this fixes issues when stop() gets called
        # on shutdown.
        self.cancel_scheduled_event("ShowTimers")
        self.cancel_scheduled_event("ExpirationCheck")
        if len(self.active_timers) > 0:
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self._cancel_timer(timer)

    def _start_new_timer(self, message):
        """Start a new timer as requested by the user.

        Args:
            message: Message Bus event information from the intent parser
        """
        utterance = message.data["utterance"]
        try:
            duration, name = self._validate_requested_timer(utterance)
        except TimerValidationException as exc:
            self.log.info(str(exc))
        else:
            timer = self._build_timer(duration, name)
            self.active_timers.append(timer)
            self.active_timers.sort(key=lambda x: x.expiration)
            if len(self.active_timers) == 1:
                self.enable_intent("handle_mute_timer")
                self.enable_intent("handle_cancel_timer")
                self._start_timer_display()
                self._start_expiration_check()
            self._speak_new_timer(timer)
            self.write_timers()
            # reset the mute flag with a new timer
            self.mute = False

    def _validate_requested_timer(self, utterance: str):
        """Don't create a timer unless the request has the necessary information.

        Args:
            utterance: the text representing the user's request for a timer

        Returns:
            The duration of the timer and the name, if one is specified.

        Raises:
            TimerValidationError when any of the checks do not pass.
        """
        duration, remaining_utterance = self._determine_timer_duration(utterance)
        name = extract_timer_name(remaining_utterance, self.regex_file_path)
        duplicate_timer = self._check_for_duplicate_name(name)
        if duplicate_timer:
            self._handle_duplicate_name_error(duplicate_timer)
        if duration.total_seconds() >= ONE_DAY:
            answer = self.ask_yesno("timer-too-long-alarm-instead")
            if answer == 'yes':
                self._convert_to_alarm(duration)

        return duration, name

    def _determine_timer_duration(self, utterance: str):
        """Interrogate the utterance to determine the duration of the timer.

        If the duration of the timer cannot be determined when interrogating the
        initial utterance, the user will be asked to specify one.

        Args:
            utterance: the text representing the user's request for a timer

        Returns:
            The duration of the timer and the remainder of the utterance after the
            duration has been extracted.

        Raises:
            TimerValidationException when no duration can be determined.
        """
        duration, remaining_utterance = extract_timer_duration(utterance)
        if duration == 1:  # prevent "set one timer" doing 1 sec timer
            duration, remaining_utterance = extract_timer_duration(remaining_utterance)
        if duration is None:
            duration = self._request_duration()
        else:
            conjunction = self.translate("and")
            remaining_utterance = remove_conjunction(conjunction, remaining_utterance)

        return duration, remaining_utterance

    def _request_duration(self) -> timedelta:
        """The utterance did not include a timer duration so ask for one.

        Returns:
            amount of time specified by the user

        Raises:
            TimerValidationException when the user does not supply a duration
        """
        def validate_duration(string):
            """Check that extract_duration returns a valid duration."""
            extracted_duration = None
            extract = extract_duration(string, self.lang)
            if extract is not None:
                extracted_duration = extract[0]
            return extracted_duration is not None

        response = self.get_response('ask-how-long', validator=validate_duration)
        if response is None:
            raise TimerValidationException("No response to request for timer duration.")
        else:
            duration, _ = extract_timer_duration(response)
            if duration is None:
                raise TimerValidationException("No duration specified")

        return duration

    def _check_for_duplicate_name(self, timer_name: str) -> Optional[CountdownTimer]:
        """Determine if the requested timer name is already in use.

        Args:
            timer_name: The name of the newly requested timer

        Returns:
            The timer with the same name as the requested timer or None if there is
            no duplicate.
        """
        duplicate_timer = None
        if timer_name is not None:
            for timer in self.active_timers:
                if timer_name.lower() == timer.name.lower():
                    duplicate_timer = timer

        return duplicate_timer

    def _handle_duplicate_name_error(self, duplicate_timer: CountdownTimer):
        """Communicate the duplicated timer name error to the user.

        Args:
            duplicate_timer: The timer that has the same name as the requested timer.

        Raises:
            TimerValidationError so that no more validations are done.
        """
        time_remaining = duplicate_timer.expiration - now_utc()
        self.speak_dialog(
            'timer-duplicate-name',
            data=dict(
                name=duplicate_timer.name,
                duration=nice_duration(time_remaining)
            )
        )
        raise TimerValidationException("Requested timer name already exists")

    def _convert_to_alarm(self, duration: timedelta):
        """Generate a message bus event to pass the user's request to the alarm skill.

        Args:
            duration: timer duration requested by user

        Raises:
            TimerValidationError indicating that the user's request was converted
            to an alarm.
        """
        # TODO: add name of alarm if available?
        alarm_time = now_local() + duration
        alarm_data = dict(
            date=alarm_time.strftime('%B %d %Y'),
            time=alarm_time.strftime('%I:%M%p')
        )
        phrase = self.translate('set-alarm', alarm_data)
        message = Message(
            "recognizer_loop:utterance", dict(utterances=[phrase], lang="en-us")
        )
        self.bus.emit(message)
        raise TimerValidationException("Timer converted to alarm")

    def _build_timer(self, duration: timedelta, requested_name: str) -> CountdownTimer:
        """Generate a timer object based on the validated user request.

        Args:
            duration: amount of time requested for the timer
            requested_name: name requested for the timer

        Returns:
            Newly generated timer object.
        """
        self.timer_index += 1
        timer = CountdownTimer(duration, requested_name)
        if timer.name is None:
            timer.name = self._assign_timer_name()
        timer.index = self.timer_index
        timer.ordinal = self._calculate_ordinal(timer.duration)

        return timer

    def _assign_timer_name(self) -> str:
        """Assign a name to a timer when the user does not specify one.

        All timers will have a name. If the user does not request one, assign a name
        using the "Timer <unnamed timer number>" convention.

        When there is only one timer active and it is assigned a name, the name
        "Timer" will be used.  If another timer without a requested name is added,
        the timer named "Timer" will have its name changed to "Timer 1" and the new
        timer will be named "Timer 2"

        Returns:
            The name assigned to the timer.
        """
        if self.active_timers:
            max_assigned_number = 0
            for timer in self.active_timers:
                if timer.name == "Timer":
                    timer.name = "Timer 1"
                    max_assigned_number = 1
                elif timer.name.startswith("Timer "):
                    _, name_number = timer.name.split()
                    name_number = int(name_number)
                    if name_number > max_assigned_number:
                        max_assigned_number = name_number
            new_timer_number = max_assigned_number + 1
            timer_name = "Timer " + str(new_timer_number)
        else:
            timer_name = "Timer"

        return timer_name

    def _calculate_ordinal(self, duration: timedelta) -> int:
        """Get ordinal based on existing timer durations.

        Args:
            duration: amount of time requested for the timer

        Returns:
            The ordinal of the new timer based on other active timers with the
            same duration
        """
        timer_count = sum(
            1 for timer in self.active_timers if timer.duration == duration
        )

        return timer_count + 1

    def _speak_new_timer(self, timer: CountdownTimer):
        """Speak a confirmation to the user that the new timer has been added.

        Args:
            timer: new timer requested by the user
        """
        dialog = TimerDialog(timer, self.lang)
        timer_count = len(self.active_timers)
        dialog.build_add_dialog(timer_count)
        self.speak_dialog(dialog.name, dialog.data, wait=True)

    def _communicate_timer_status(self, message: Message):
        """Speak response to the user's request for status of timer(s).

        Args:
            message: Message Bus event information from the intent parser
        """
        if self.active_timers:
            utterance = message.data['utterance']
            matches = self._get_timer_status_matches(utterance)
            if matches is not None:
                self._speak_timer_status_matches(matches)
        else:
            self.speak_dialog("no.active.timer")

    def _get_timer_status_matches(self, utterance: str) -> List[CountdownTimer]:
        """Determine which active timer(s) match the user's status request.

        Args:
            utterance: The user's request for status of timer(s)

        Returns:
            Active timer(s) matching the user's request
        """
        if len(self.active_timers) == 1:
            matches = self.active_timers
        else:
            matches = get_timers_matching_utterance(
                utterance, self.active_timers, self.regex_file_path
            )
            if matches is None:
                matches = self.active_timers

        while matches is not None and len(matches) > 2:
            matches = self._ask_which_timer(matches, question='ask-which-timer')

        return matches

    def _speak_timer_status_matches(self, matches: List[CountdownTimer]):
        """Construct and speak the dialog(s) communicating timer status to the user.

        Args:
            matches: the active timers that matched the user's request for timer status
        """
        if matches:
            number_of_timers = len(matches)
            if number_of_timers > 1:
                speakable_number = pronounce_number(number_of_timers)
                dialog_data = dict(number=speakable_number)
                self.speak_dialog('number-of-timers', dialog_data)
            for timer in matches:
                self._speak_timer_status(timer)
        else:
            self.speak_dialog('timer-not-found')

    def _speak_timer_status(self, timer: CountdownTimer):
        """Speak the status of an individual timer - remaining or elapsed.

        Args:
            timer: timer the status will be communicated for
        """
        # TODO: stop beeping before speaking
        # TODO: speak_dialog should have option to not show mouth
        # For now, just deactivate.  The sleep() is to allow the
        # message to make it across the bus first.
        self.enclosure.deactivate_mouth_events()
        time.sleep(0.25)
        dialog = TimerDialog(timer, self.lang)
        dialog.build_status_dialog()
        self.speak_dialog(dialog.name, dialog.data, wait=True)
        self.enclosure.activate_mouth_events()

    def _cancel_timers(self, message: Message):
        """Handle a user's request to cancel one or more timers.

        Args:
            message: Message Bus event information from the intent parser
        """
        utterance = message.data['utterance']
        cancel_all = (
            any(word in utterance for word in self.all_timers_words)
            or message.data.get('All')
        )
        active_timer_count = len(self.active_timers)

        if not self.active_timers:
            self.gui.remove_page("timer_scalable.qml")
            self.speak_dialog("no-active-timer")
        elif cancel_all:
            self._cancel_all_timers()
        elif active_timer_count == 1:
            self._cancel_single_timer(utterance)
        elif active_timer_count > 1:
            self._determine_which_timer_to_cancel(utterance)
        self.write_timers()
        if not self.active_timers:
            self._reset()

    def _cancel_all_timers(self):
        """Handle a user's request to cancel all active timers."""
        if len(self.active_timers) == 1:
            self.speak_dialog("cancelled-single-timer")
        else:
            self.speak_dialog('cancel-all', data={"count": len(self.active_timers)})
        self.active_timers = list()

    def _cancel_single_timer(self, utterance: str):
        """Cancel the only active timer.

        The cancellation request may contain a timer name or duration.  Don't cancel
        a "chicken" timer when the user asked to cancel a "pasta" timer.  Don't cancel
        a ten minute timer when the user requested to cancel a twenty minute timer.

        Args:
            utterance: The words the user spoke to request timer cancellation.
        """
        timer = self.active_timers[0]
        utterance_mismatch = self._match_cancel_request(utterance)
        if utterance_mismatch:
            reply = self._ask_to_confirm_cancel(timer)
            if reply == 'no':
                timer = None
        if timer is not None:
            self.active_timers.remove(timer)
            self.speak_dialog("cancelled-single-timer")

    def _match_cancel_request(self, utterance: str) -> bool:
        """Determine if the only active timer matches what the user requested.

        Args:
            utterance: The timer cancellation request made by the user.

        Returns:
            An indicator of whether or not a match was found.
        """
        matches = get_timers_matching_utterance(
            utterance, self.active_timers, self.regex_file_path
        )
        match_criteria_in_utterance = matches is not None
        if match_criteria_in_utterance:
            timer_matched_criteria = len(matches) == 1
        else:
            timer_matched_criteria = False

        return match_criteria_in_utterance and not timer_matched_criteria

    def _ask_to_confirm_cancel(self, timer) -> str:
        """If the only active timer does not match the request, confirm cancel request.

        Args:
            timer: The only active timer

        Returns:
            "Yes" or "no" reply from the user.
        """
        dialog = TimerDialog(timer, self.lang)
        dialog.build_cancel_confirm_dialog()
        reply = self.ask_yesno(dialog.name, dialog.data)

        return reply

    def _determine_which_timer_to_cancel(self, utterance: str):
        """Cancel timer(s) based on the user's request.

        Args:
            utterance: The timer cancellation request made by the user.
        """
        matches = get_timers_matching_utterance(
            utterance, self.active_timers, self.regex_file_path
        )
        while matches is not None and len(matches) > 1:
            matches = self._ask_which_timer(matches, question='ask-which-timer-cancel')

        if matches is not None:
            if matches:
                timer = matches[0]
                self.active_timers.remove(timer)
                dialog = TimerDialog(timer, self.lang)
                dialog.build_cancel_dialog()
                self.speak_dialog(dialog.name, dialog.data)
            else:
                self.speak_dialog("timer-not-found")

    def _reset(self):
        """There are no active timers so reset all the stateful things."""
        self.gui.release()
        self._stop_timer_display()
        self._stop_expiration_check()
        self.timer_index = 0
        self.disable_intent("handle_mute_timer")
        self.disable_intent("handle_cancel_timer")
        self.enclosure.eyes_reset()
        self.enclosure.mouth_reset()

    def _ask_which_timer(self, timers: List[CountdownTimer], question: str) -> List[CountdownTimer]:
        """Ask the user to provide more information about the timer(s) requested.

        Args:
            timers: list of timers that needs to be filtered using the answer
            question: name of the dialog file containing the question to be asked

        Returns:
            timers filtered based on the answer to the question.
        """
        filtered_timers = None
        speakable_matches = self._get_speakable_timer_details(timers)
        reply = self.get_response(
            dialog=question,
            data=dict(count=len(timers), names=speakable_matches)
        )
        if reply is not None:
            filtered_timers = get_timers_matching_reply(
                reply, timers, self.regex_file_path
            )

        return filtered_timers

    def _get_speakable_timer_details(self, timers: List[CountdownTimer]) -> str:
        """Get timer list as speakable string.

        Args:
            timers: the timers to be converted

        Returns:
            names of the specified timers to be passed to TTS engine for speaking
        """
        speakable_timer_details = []
        for timer in timers:
            dialog = TimerDialog(timer, self.lang)
            dialog.build_details_dialog()
            speakable_timer_details.append(self.translate(dialog.name, dialog.data))
        timer_names = join_list(speakable_timer_details, self.translate("and"))

        return timer_names

    def handle_listener_started(self, _):
        """Pause scheduled events that would interfere with the device listening."""
        self._pause_scheduled_events()

    def handle_listener_ended(self, _):
        """Resume scheduled events paused when the listener started."""
        self._resume_scheduled_events()

    def handle_speak(self, _):
        """Pause scheduled events while the device speaking."""
        self._pause_scheduled_events()
        wait_while_speaking()
        self._resume_scheduled_events()

    def _pause_scheduled_events(self):
        """Pause scheduled events that interfere with device operations.

        All devices will be beeping if there are one or more expired timers.  Pause
        the beeping so that the device can listen and respond to a user request.

        The Mark I has mouth events that occur during listening and speaking.  Stop
        displaying the timer during these events.
        """
        self._stop_expiration_check()
        if self.platform == MARK_I:
            self._stop_timer_display()

    def _resume_scheduled_events(self):
        """Resume scheduled events that were paused during listening/speaking."""
        self._start_timer_display()
        if self.platform == MARK_I:
            self._start_expiration_check()

    def _start_timer_display(self):
        """Start a event repeating every second tp display the timer on a GUI."""
        self.schedule_repeating_event(
            self.display_timers, None, 1, name="ShowTimer"
        )

    def _stop_timer_display(self):
        """Stop the repeating event that displays the timer on a GUI interface."""
        self.cancel_scheduled_event("ShowTimer")

    def _start_expiration_check(self):
        """Start an even repeating every two seconds to check for expired timers."""
        self.schedule_repeating_event(
            self.check_for_expired_timers, None, 2, name="ExpirationCheck"
        )

    def _stop_expiration_check(self):
        """Stop the repeating event that checks for expired timers."""
        self.cancel_scheduled_event('ExpirationCheck')

    def display_timers(self):
        """Update the device's display to show the status of active timers.

        Runs once a second via a repeating event to keep the information on the display
        accurate.
        """
        if self.gui.connected:
            self._display_timers_on_gui()
        elif self.platform == MARK_I:
            self._display_timers_on_faceplate()

    def _display_timers_on_gui(self):
        """Display active timers on a device that supports the QT GUI framework."""
        timers_to_display = self._select_timers_to_display(display_max=4)
        display_data = [timer.display_data for timer in timers_to_display]
        if timers_to_display:
            self.gui['activeTimers'] = dict(timers=display_data)
            self.gui['activeTimerCount'] = len(timers_to_display)
        if self.platform == MARK_II:
            page = 'timer_mark_ii.qml'
        else:
            page = 'timer_scalable.qml'
        self.gui.show_page(page, override_idle=True)

    def _display_timers_on_faceplate(self):
        """Display one timer on a device that supports and Arduino faceplate."""
        faceplate_user = self.enclosure.display_manager.get_active()
        if not faceplate_user:
            self.enclosure.mouth_reset()
        elif faceplate_user == "TimerSkill":
            previous_display_group = self.display_group
            timers_to_display = self._select_timers_to_display(display_max=1)
            if self.display_group != previous_display_group:
                self.enclosure.mouth_reset()
            if timers_to_display:
                timer_to_display = timers_to_display[0]
                renderer = FaceplateRenderer(self.enclosure, timer_to_display)
                if len(self.active_timers) > 1:
                    renderer.multiple_active_timers = True
                renderer.render()

    def _select_timers_to_display(self, display_max: int) -> List[CountdownTimer]:
        """Determine which timers will populate the display.

        If there are more timers than fit on a screen or faceplate, change which
        timers are displayed every ten seconds.

        Args:
            display_max: maximum number of timers that can be displayed at once

        Returns:
            The timer(s) to be displayed.
        """
        if len(self.active_timers) <= display_max:
            timers_to_display = self.active_timers
        else:
            if not now_utc().second % 10:
                if (self.display_group * display_max) < len(self.active_timers):
                    self.display_group += 1
                else:
                    self.display_group = 1

            start_index = (self.display_group - 1) * display_max
            end_index = self.display_group * display_max
            timers_to_display = self.active_timers[start_index:end_index]

        return timers_to_display

    def check_for_expired_timers(self):
        """Provide a audible and visual indicator when one or more timers expire.

        Runs once every two seconds via a repeating event.
        """
        expired_timers = [timer for timer in self.active_timers if timer.expired]
        if expired_timers:
            play_wav(str(self.sound_file_path))
            if self.platform == MARK_I:
                self._flash_eyes()
            self._speak_expired_timer(expired_timers)

    def _flash_eyes(self):
        """Flash the eyes (if supported) as a visual indicator that a timer expired."""
        if 1 <= now_utc().second % 4 <= 2:
            self.enclosure.eyes_on()
        else:
            self.enclosure.eyes_off()

    def _speak_expired_timer(self, expired_timers):
        """Announce the expiration of any timers not already announced.

        This occurs every two seconds, so only announce one expired timer per pass.
        """
        for timer in expired_timers:
            if not timer.expiration_announced:
                dialog = TimerDialog(timer, self.lang)
                dialog.build_expiration_announcement_dialog(len(self.active_timers))
                self.speak_dialog(dialog.name, dialog.data)
                timer.expiration_announced = True
                break

    def converse(self, utterances, lang="en-us"):
        timer = self._get_next_timer()
        if timer and timer.expiration < now_utc():
            # A timer is going off
            if utterances and self.voc_match(utterances[0], "StopBeeping"):
                # Stop the timer
                self.stop()
                return True  # and consume this phrase

    def stop(self):
        timer = self._get_next_timer()
        now = now_utc()
        if timer and timer.expiration < now:
            # stop the expired timer(s)
            while timer and timer.expiration < now:
                self._cancel_timer(timer)
                timer = self._get_next_timer()
            self.write_timers()   # save to disk
            return True

        elif self.active_timers:
            # This is a little tricky.  We shouldn't initiate dialog
            # during Stop handling (there is confusion between stopping speech
            # and starting new conversations). Instead, we'll just consider
            # this Stop consumed and post a message that will immediately
            # be handled to ask the user if they want to cancel.
            self.bus.emit(Message("skill.mycrofttimer.verify.cancel"))
            return True

        return False

    # This is a little odd. This actually does the work for the Stop button,
    # which prevents blocking during the Stop handler when input from the
    # user is needed.
    def handle_verify_stop_timer(self, _):
        # Confirm cancel of live timers...
        if len(self.active_timers) == 1:
            prompt = 'ask.cancel.running'
        else:
            prompt = 'ask.cancel.running.plural'
        if self.ask_yesno(prompt) == 'yes':
            self.handle_cancel_timer()

    def _get_next_timer(self):
        """Retrieve the next timer set to trigger."""
        next_timer = None
        for timer in self.active_timers:
            if next_timer is None or timer.expiration < next_timer.expiration:
                next_timer = timer
        return next_timer

    def write_timers(self):
        """Save active timers to disk for next timer skill is loaded."""
        self.do_pickle('save_timers', self.active_timers)

    def load_timers(self):
        # Reload any saved timers
        self.active_timers = self.do_unpickle('save_timers', [])

        # Reset index
        self.timer_index = 0
        for timer in self.active_timers:
            if timer.index > self.timer_index:
                self.timer_index = timer.index

    # TODO: Move to somewhere in core that will make this re-usable
    def do_pickle(self, name, data):
        """Serialize the data under the name.

        Args:
            name (string): reference name of the pickled data
            data (any): the data to store
        """

        with self.file_system.open(name, 'wb') as f:
            pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)

    def do_unpickle(self, name, default):
        """Load previously saved data under name.

        Args:
            name (string): reference name of the pickled data
            default (any): default if data isn't found

        Returns:
            (any): Picked data or the default
        """
        try:
            with self.file_system.open(name, 'rb') as f:
                return pickle.load(f)
        except:
            return default

#######
def create_skill():
    return TimerSkill()
