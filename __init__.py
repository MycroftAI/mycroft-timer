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

import time
import pickle
from datetime import datetime, timedelta
from os.path import join, abspath, dirname
from typing import List, Optional, Tuple

from adapt.intent import IntentBuilder
from mycroft import MycroftSkill, intent_handler
from mycroft.audio import is_speaking
from mycroft.skills.intent_service import AdaptIntent
from mycroft.messagebus.message import Message
from mycroft.util import play_wav
from mycroft.util.format import pronounce_number, nice_duration, join_list
from mycroft.util.parse import extract_duration
from mycroft.util.time import now_utc, now_local

try:
    from mycroft.skills.skill_data import to_alnum
except ImportError:
    from mycroft.skills.skill_data import to_letters as to_alnum

from .skill import (
    CountdownTimer,
    extract_timer_duration,
    extract_timer_name,
    get_speakable_ordinal,
    get_timers_matching_reply,
    get_timers_matching_utterance,
    remove_conjunction,
    TimerDialog
)
from .util.bus import wait_for_message

ONE_DAY = 86400
ONE_HOUR = 3600
ONE_MINUTE = 60
BACKGROUND_COLORS = ('#22A7F0', '#40DBB0', '#BDC3C7', '#4DE0FF')


class TimerValidationException(Exception):
    """This is not really for errors, just a handy way to tidy up the initial checks."""
    pass

class TimerSkill(MycroftSkill):
    def __init__(self):
        super(TimerSkill, self).__init__("TimerSkill")
        self.active_timers = []
        self.beep_repeat_period = 10
        self.sound_file = join(abspath(dirname(__file__)), 'snd',
                               'twoBeep.wav')
        self.beep_repeat_period = 5

        self.displaying_timer = None
        self.beep_process = None
        self.mute = False
        self.timer_index = 0
        self.display_idx = None
        self.regex_file_path = self.find_resource('name.rx', 'regex')

        # Threshold score for Fuzzy Logic matching for Timer Name
        self.threshold = 0.7
        self.screen_showing = False
        self.all_timers_words = [word.strip() for word in self.translate_list('all')]

    def initialize(self):
        self.load_timers()

        # Invoke update_display in one second to allow it to disable the
        # cancel intent, since there are no timers to cancel yet!
        if not self.gui.connected:
            self.schedule_repeating_event(self.update_display,
                                          None, 1, name='ShowTimer')

        # To prevent beeping while listening
        self.is_listening = False
        self.add_event('recognizer_loop:record_begin', self.handle_listener_started)
        self.add_event('recognizer_loop:record_end', self.handle_listener_ended)
        self.add_event(
            'skill.mycrofttimer.verify.cancel', self.handle_verify_stop_timer)
        self.gui.register_handler(
            'skill.mycrofttimer.expiredtimer', self.handle_expired_timer
        )

    @intent_handler(
        AdaptIntent().require("Start").require("Timer").optionally("Name")
    )
    def handle_start_timer(self, message):
        """Common handler for start_timer intents."""
        self._start_new_timer(message)

    # Handles custom start phrases eg "ping me in 5 minutes"
    # Also over matches Common Play for "start timer" utterances
    # @intent_handler('start.timer.intent')
    # def handle_start_timer_padatious(self, message):
    #     print(message.data)
    #     self._start_new_timer(message)

    # Handles custom status phrases eg 'How much time left'
    @intent_handler('timer.status.intent')
    def handle_status_timer_padatious(self, message):
        self._communicate_timer_status(message)

    # Handles "do I have any timers" etc
    @intent_handler(AdaptIntent().require("Query").
                    optionally("Status").require("Timer").optionally("All"))
    def handle_query_status_timer(self, message):
        self._communicate_timer_status(message)

    @intent_handler(AdaptIntent().optionally("Query").
                    require("Status").one_of("Timer", "Time").
                    optionally("All").optionally("Duration").
                    optionally("Name"))
    def handle_status_timer(self, message):
        # Handles "timer status", "status of timers" etc.
        self._communicate_timer_status(message)

    @intent_handler(IntentBuilder("").require("Mute").require("Timer"))
    def handle_mute_timer(self, _):
        self.mute = True

    @intent_handler('stop.timer.intent')
    def handle_stop_timer(self, message):
        """Stop the first expired timer in the queue.

        If the timer is beeping, no confirmation is required; treat it like a stop
        button press.  Don't cancel active timers with only "cancel" as utterance

        Args:
            message:

        Returns:

        """
        timer = self._get_next_timer()
        if timer.expired:
            self.stop()
        elif message.data.get('utterance') != "cancel":
            self._cancel_timers(message)

    @intent_handler(AdaptIntent().require("Cancel").require("Timer")
                    .optionally("Connector").optionally("All"))
    def handle_cancel_timer(self, message):
        self._cancel_timers(message)

    def _start_new_timer(self, message):
        """Start a new timer as requested by the user.

        Args:
            message: Message from the intent parser containing information about
                the request
        """
        utterance = message.data["utterance"]
        try:
            duration, name = self._validate_requested_timer(utterance)
        except TimerValidationException as exc:
            self.log.info(str(exc))
        else:
            timer = self._add_timer(duration, name)
            # self._display_timer(timer)
            self._speak_new_timer(timer)
            self.write_timers()
            self.enable_intent("handle_mute_timer")
            # Start showing the remaining time on the faceplate
            # if not self.gui.connected:
            #     self.update_display(None)
            # reset the mute flag with a new timer
            self.mute = False

    def _validate_requested_timer(self, utterance):
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
            answer = self.ask_yesno("timer.too.long.alarm.instead")
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
            remaining_utterance = remove_conjunction(conjunction, utterance)

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
        duplicate_timer = None
        if timer_name is not None:
            for timer in self.active_timers:
                if timer_name.lower() == timer.name.lower():
                    duplicate_timer = timer

        return duplicate_timer

    def _handle_duplicate_name_error(self, duplicate_timer):
        time_remaining = duplicate_timer.expiration - now_utc()
        self.speak_dialog(
            'timer-duplicate-name',
            data=dict(
                name=duplicate_timer.name,
                duration=nice_duration(time_remaining)
            )
        )
        raise TimerValidationException("Requested timer name already exists")

    def _convert_to_alarm(self, duration):
        # SHOULD IT BE AN ALARM?
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

    def _add_timer(self, duration: timedelta, name: str) -> CountdownTimer:
        self.timer_index += 1
        timer = CountdownTimer(duration, name)
        if timer.name is None:
            timer.name = self._assign_timer_name()
        timer.index = self.timer_index
        timer.ordinal = self._calculate_ordinal(timer.duration)
        self.active_timers.append(timer)
        self.active_timers.sort(key=lambda x: x.expiration)

        return timer

    def _assign_timer_name(self):
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
        """Get ordinal based on existing timer durations."""
        timer_count = sum(
            1 for timer in self.active_timers if timer.duration == duration
        )

        return timer_count + 1

    def _display_timer(self, timer):
        if self.gui.connected:
            if self.timer_index is None or self.timer_index == 1:
                timer_id = 1
            else:
                timer_id = self.timer_index

            now = datetime.now()
            remaining = (timer.expiration - now).seconds
            ct = self._build_timer_display(timer_id, timer, remaining)
            self.render_qt_timer(ct)
            self.screen_showing = True

    def _speak_new_timer(self, timer):
        # INFORM USER
        dialog = TimerDialog(timer, self.lang)
        timer_count = len(self.active_timers)
        dialog.build_add_dialog(timer_count)
        self.speak_dialog(dialog.name, dialog.data, wait=True)

    def _communicate_timer_status(self, message):
        if self.active_timers:
            utterance = message.data['utterance']
            matches = self._get_timer_status_matches(utterance)
            if matches is not None:
                self._speak_timer_status_matches(matches)
        else:
            self.speak_dialog("no.active.timer")

    def _get_timer_status_matches(self, utterance):
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

    def _speak_timer_status_matches(self, matches):
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

    def _speak_timer_status(self, timer):
        """Speak the status of an individual timer - remaining or elapsed."""
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
        utterance = message.data['utterance']
        cancel_all = (
            any(word in utterance for word in self.all_timers_words)
            or message.data.get('All')
        )
        active_timer_count = len(self.active_timers)

        if not self.active_timers:
            self.gui.remove_page("timer.qml")
            self.speak_dialog("no-active-timer")
        elif cancel_all:
            self._cancel_all_timers()
        elif active_timer_count == 1:
            self._cancel_single_timer(utterance)
        elif active_timer_count > 1:
            self._determine_which_timer_to_cancel(utterance)
        self.write_timers()

    def _cancel_all_timers(self):
        if len(self.active_timers) == 1:
            self.speak_dialog("cancelled-single-timer")
        else:
            self.gui.remove_page("timer.qml")
            self.gui["cancelAllTimers"] = True
            self.speak_dialog('cancel-all', data={"count": len(self.active_timers)})

        # duplicate active timers so we can walk a static list
        active_timers = list(self.active_timers)
        for timer in active_timers:
            self.cancel_timer(timer)

    def _cancel_single_timer(self, utterance):
        # Check if utt included details and it is a mismatch
        # E.g. "Cancel the 5 minute timer" when it's a 7 minute timer
        timer = self.active_timers[0]
        utterance_mismatch = self._match_cancel_request(utterance)
        if utterance_mismatch:
            reply = self._ask_to_confirm_cancel(timer)
            if reply == 'no':
                timer = None
        if timer is not None:
            self.cancel_timer(timer)
            self.speak_dialog("cancelled-single-timer")

    def _match_cancel_request(self, utterance):
        matches = get_timers_matching_utterance(
            utterance, self.active_timers, self.regex_file_path
        )
        match_criteria_in_utterance = matches is not None
        timer_matched_criteria = len(matches) == 1

        return match_criteria_in_utterance and not timer_matched_criteria

    def _ask_to_confirm_cancel(self, timer):
        # If mismatched confirm to cancel the current timer
        dialog = TimerDialog(timer, self.lang)
        dialog.build_cancel_confirm_dialog()
        reply = self.ask_yesno(dialog.name, dialog.data)

        return reply

    def _determine_which_timer_to_cancel(self, utterance):
        matches = get_timers_matching_utterance(
            utterance, self.active_timers, self.regex_file_path
        )
        while matches is not None and len(matches) > 1:
            matches = self._ask_which_timer(matches, question='ask-which-timer-cancel')

        if matches is not None:
            if matches:
                timer = matches[0]
                self.cancel_timer(timer)
                dialog = TimerDialog(timer, self.lang)
                dialog.build_cancel_dialog()
                self.speak_dialog(dialog.name, dialog.data)
            else:
                self.speak_dialog("timer-not-found")

    def cancel_timer(self, timer):
        """Actually cancels the given timer."""
        self.gui["remove_timer"] = {"index": timer.index, "duration": timer.duration}
        self.active_timers.remove(timer)
        if not self.active_timers:
            if self.screen_showing:
                self.gui.release()
                self.screen_showing = False
            self.timer_index = 0
            self.enclosure.eyes_on()  # reset just in case

    def _ask_which_timer(self, timers, question):
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

    def _get_speakable_timer_details(self, timers):
        """Get timer list as speakable string."""
        speakable_timer_details = []
        for timer in timers:
            dialog = TimerDialog(timer, self.lang)
            dialog.build_details_dialog()
            speakable_timer_details.append(self.translate(dialog.name, dialog.data))
        timer_names = join_list(speakable_timer_details, self.translate("and"))

        return timer_names

    def handle_expired_timer(self, message):
        #if only timer, just beep
        if len(self.active_timers) == 1:
            self._play_beep()
        else:
            duration = nice_duration(message.data["duration"])
            name = message.data['name']
            timer = {"name": message.data['name'],
                 "index": message.data['index'],
                 "ordinal": message.data['ordinal'],
                 "duration": message.data['duration'],
                 "announced": message.data['announced']}
            speakable_ord = get_speakable_ordinal(timer, self.lang)
            dialog = 'timer.expired'
            if name:
                dialog += '.named'
            if speakable_ord != "":
                dialog += '.ordinal'
            self.speak_dialog(dialog,
                                data={"duration": duration,
                                    "name": name,
                                    "ordinal": speakable_ord})

    # TODO: Implement util.is_listening() to replace this
    def is_not_listening(self):
        self.is_listening = False

    def handle_listener_started(self, _):
        self.is_listening = True

    def handle_listener_ended(self, _):
        if self.beep_process is not None:
            self.bus.on('recognizer_loop:speech.recognition.unknown',
                        self.is_not_listening)
            speak_msg_detected = wait_for_message(self.bus, 'speak')
            self.bus.remove('recognizer_loop:speech.recognition.unknown',
                            self.is_not_listening)
        self.is_not_listening()

    def _get_next_timer(self):
        """Retrieve the next timer set to trigger."""
        next_timer = None
        for timer in self.active_timers:
            if next_timer is None or timer.expiration < next_timer.expiration:
                next_timer = timer
        return next_timer

    def update_display(self, _):
        # Get the next triggering timer
        timer = self._get_next_timer()
        if not timer:
            # No active timers, clean up
            self.cancel_scheduled_event('ShowTimer')
            self.displaying_timer = None
            self.disable_intent("handle_mute_timer")
            self._stop_beep()
            self.enclosure.eyes_reset()
            self.enclosure.mouth_reset()
            return

        # Check if there is an expired timer
        now = now_utc()
        flash = False
        for timer in self.active_timers:
            if timer.expiration < now_utc():
                flash = True
                break
        if flash:
            if now.second % 2 == 1:
                self.enclosure.eyes_on()
            else:
                self.enclosure.eyes_off()

        if is_speaking():
            # Don't overwrite mouth visemes
            return

        if len(self.active_timers) > 1:
            # This code will display each timer for 5 passes of this
            # screen update (5 seconds), then move on to display next timer.
            if not self.display_idx:
                self.display_idx = 1.0
            else:
                self.display_idx += 0.2
            if int(self.display_idx-1) >= len(self.active_timers):
                self.display_idx = 1.0

            timer = self.active_timers[int(self.display_idx)-1]
            idx = timer.index
        else:
            if self.display_idx:
                self.enclosure.mouth_reset()
            self.display_idx = None
            idx = None

        # Check if the display frequency is set correctly for closest timer.
        if timer != self.displaying_timer:
            self.cancel_scheduled_event('ShowTimer')
            self.schedule_repeating_event(self.update_display,
                                          None, 1,
                                          name='ShowTimer')
            self.displaying_timer = timer

        # Calc remaining time and show using faceplate
        if timer.expiration > now:
            # Timer still running
            remaining = (timer.expiration - now).seconds
            self.render_timer(idx, remaining)
        else:
            # Timer has expired but not been cleared, flash eyes
            overtime = (now - timer.expiration).seconds
            self.render_timer(idx, overtime)

            if timer.announced:
                # beep again every 10 seconds
                if overtime % self.beep_repeat_period == 0 and not self.mute:
                    self._play_beep()
            else:
                # if only timer, just beep
                if len(self.active_timers) == 1:
                    self._play_beep()
                else:
                    duration = nice_duration(timer.duration)
                    name = timer.name
                    speakable_ord = get_speakable_ordinal(timer, self.lang)
                    dialog = 'timer.expired'
                    if name:
                        dialog += '.named'
                    if speakable_ord != "":
                        dialog += '.ordinal'
                    self.speak_dialog(dialog,
                                      data={"duration": duration,
                                            "name": name,
                                            "ordinal": speakable_ord})
                timer.announced = True

    def render_qt_timer(self, ct):
        self.gui["remove_timer"] = ""
        self.gui["cancelAllTimers"] = False
        self.gui['timer_data'] = ct

        if not self.screen_showing:
            self.gui.show_page('timer.qml', override_idle=True)
            self.screen_showing = True

    def render_timer(self, idx, seconds):
        display_owner = self.enclosure.display_manager.get_active()
        if display_owner == "":
            self.enclosure.mouth_reset()  # clear any leftover bits
        elif display_owner != "TimerSkill":
            return

        # convert seconds to m:ss or h:mm:ss
        if seconds <= 0:
            expired = True
            seconds *= -1
        else:
            expired = False

        remaining_time = self._build_time_remaining_string(seconds)
        if seconds > ONE_HOUR:
            # account of colons being smaller
            pixel_width = len(remaining_time)*4 - 2*2 + 6
        else:
            # account of colons being smaller
            pixel_width = len(remaining_time)*4 - 2 + 6

        x = (4*8 - pixel_width) // 2  # centers on display
        if expired:
            remaining_time = "-" + remaining_time
        else:
            remaining_time = " " + remaining_time

        if idx:
            # If there is an index to show, display at the left
            png = join(abspath(dirname(__file__)), "anim",
                       str(int(idx))+".png")
            self.enclosure.mouth_display_png(png, x=3, y=2, refresh=False)
            x += 6

        # draw on the display
        for ch in remaining_time:
            # deal with some odd characters that can break filesystems
            if ch == ":":
                png = "colon.png"
            elif ch == " ":
                png = "blank.png"
            elif ch == "-":
                png = "negative.png"
            else:
                png = ch+".png"

            png = join(abspath(dirname(__file__)), 'anim',  png)
            self.enclosure.mouth_display_png(png, x=x, y=2, refresh=False)
            if ch == ':':
                x += 2
            else:
                x += 4

    @staticmethod
    def _build_time_remaining_string(remaining_seconds):
        """Convert number of seconds into a displayable time string."""
        hours = abs(remaining_seconds) // ONE_HOUR
        hours_remainder = abs(remaining_seconds) % ONE_HOUR
        minutes = hours_remainder // ONE_MINUTE
        seconds = hours_remainder % ONE_MINUTE
        if hours:
            # convert to H:MM:SS
            remaining_time = [
                str(hours),
                str(minutes).zfill(2),
                str(seconds).zfill(2)
            ]
        else:
            # convert to MM:SS
            remaining_time = [
                str(minutes).zfill(2),
                str(seconds).zfill(2)
            ]

        return ':'.join(remaining_time)

    def shutdown(self):
        # Clear the timer list, this fixes issues when stop() gets called
        # on shutdown.
        if len(self.active_timers) > 0:
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self.cancel_timer(timer)

    def converse(self, utterances, lang="en-us"):
        timer = self._get_next_timer()
        if timer and timer.expiration < now_utc():
            # A timer is going off
            if utterances and self.voc_match(utterances[0], "StopBeeping"):
                # Stop the timer
                self.stop()
                return True  # and consume this phrase

    # This is a little odd. This actually does the work for the Stop button,
    # which prevents blocking during the Stop handler when input from the
    # user is needed.
    def handle_verify_stop_timer(self, _):
        # Confirm cancel of live timers...
        prompt = ('ask.cancel.running' if len(self.active_timers) == 1
                  else 'ask.cancel.running.plural')
        if self.ask_yesno(prompt) == 'yes':
            self.handle_cancel_timer()

    def stop(self):
        timer = self._get_next_timer()
        now = now_utc()
        if timer and timer.expiration < now:
            # stop the expired timer(s)
            while timer and timer.expiration < now:
                self.cancel_timer(timer)
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

    ######################################################################
    # Audio feedback

    def _play_beep(self):
        # Play the beep sound
        if not self._is_playing_beep() and not self.is_listening:
            self.beep_process = play_wav(self.sound_file)

    def _is_playing_beep(self):
        # Check if the WAV is still playing
        if self.beep_process:
            self.beep_process.poll()
            if self.beep_process.returncode:
                # The playback has ended
                self.beep_process = None

    def _stop_beep(self):
        if self._is_playing_beep():
            self.beep_process.kill()
            self.beep_process = None
            
    def _build_timer_display(self, idx, timer, remaining_time):
        color_idx = 0 if idx is None else idx % 4 - 1
        elapsed_time = timer.duration - remaining_time
        remaining_time_display = self._build_time_remaining_string(
            remaining_time
        )
        if datetime.now() > timer.expiration:
            percent_elapsed = 1
            remaining_time_display = '-' + remaining_time_display
            timer_expd = True
        else:
            percent_elapsed = elapsed_time / timer.duration
            timer_expd = False
            
        remain_time_in_ms = remaining_time * 1000
        
        timer_id = idx or 1
        if timer.name:
            timer_name = timer.name.capitalize()
        else:
            if idx is None or idx == 1:
                timer_name = 'Timer'
            else:
                timer_name = 'Timer ' + str(idx)
            
        timer_duration = timer.duration
        timer_data = {"timer_color": BACKGROUND_COLORS[color_idx], "timer_name": timer_name, "time_remaining": remain_time_in_ms, "timer_duration": timer_duration, "timer_id": timer_id, "timer_ordinal": timer.ordinal, "timer_announced": timer.announced, "timer_index": timer.index}
        
        return timer_data

    def write_timers(self):
        # Save the timers for reload
        self.do_pickle('save_timers', self.active_timers)

    def load_timers(self):
        # Reload any saved timers
        self.active_timers = self.do_unpickle('save_timers', [])

        # Reset index
        self.timer_index = 0
        for timer in self.active_timers:
            if timer.index > self.timer_index:
                self.timer_index = timer.index

    # TODO: Move to MycroftSkill
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


def create_skill():
    return TimerSkill()
