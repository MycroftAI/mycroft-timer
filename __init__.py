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
import re
from datetime import datetime, timedelta
from os.path import join, isfile, abspath, dirname
from num2words import num2words

from adapt.intent import IntentBuilder
from mycroft.audio import wait_while_speaking, is_speaking
from mycroft.messagebus.message import Message
from mycroft.skills.core import (
    MycroftSkill,
    intent_handler,
    intent_file_handler)
from mycroft.util import play_wav
from mycroft.util.format import pronounce_number, nice_duration, join_list
from mycroft.util.parse import extract_number, fuzzy_match, extract_duration
from mycroft.util.time import now_local

try:
    from mycroft.skills.skill_data import to_alnum
except ImportError:
    from mycroft.skills.skill_data import to_letters as to_alnum

from .util.bus import wait_for_message


ONE_HOUR = 3600
ONE_MINUTE = 60


# TESTS
#  0: cancel all timers
#  1: start a timer > 1 minute
#  2: cancel timer
#  3: start a 30 second timer
#  4: cancel timer
#  5: start a 1 hour timer
#  6: start a 20 minute timer
#  7: how much time is left
#  8: start a 1 hour timer
#  9: start a 20 minute timer
# 10: how much time is left > first
# 11: how much time is left on 5 minute timer
# 12: how much is left on the five minute timer
# 13: start a 7 minute timer called lasagna
# 14: how much is left on the lasagna timer
# 15: set a 1 and a half minute timer
# 16: set a timer for 3 hours 45 minutes

#####################################################################


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

        # Threshold score for Fuzzy Logic matching for Timer Name
        self.threshold = 0.7

    def initialize(self):
        self.unpickle()

        # Invoke update_display in one second to allow it to disable the
        # cancel intent, since there are no timers to cancel yet!
        self.schedule_repeating_event(self.update_display,
                                      None, 1, name='ShowTimer')

        # To prevent beeping while listening
        self.is_listening = False
        self.add_event('recognizer_loop:record_begin',
                       self.handle_listener_started)
        self.add_event('recognizer_loop:record_end',
                       self.handle_listener_ended)
        self.add_event('skill.mycrofttimer.verify.cancel',
                       self.handle_verify_stop_timer)

    def pickle(self):
        # Save the timers for reload
        self.do_pickle('save_timers', self.active_timers)

    def unpickle(self):
        # Reload any saved timers
        self.active_timers = self.do_unpickle('save_timers', [])

        # Reset index
        self.timer_index = 0
        for timer in self.active_timers:
            if timer["index"] > self.timer_index:
                self.timer_index = timer["index"]

    # TODO: Implement util.is_listening() to replace this
    def is_not_listening(self):
        self.is_listening = False

    def handle_listener_started(self, message):
        self.is_listening = True

    def handle_listener_ended(self, message):
        if self.beep_process is not None:
            self.bus.on('recognizer_loop:speech.recognition.unknown',
                        self.is_not_listening)
            speak_msg_detected = wait_for_message(self.bus, 'speak')
            self.bus.remove('recognizer_loop:speech.recognition.unknown',
                            self.is_not_listening)
        self.is_not_listening()

    def _extract_duration(self, text):
        """Extract duration in seconds.

        Args:
            text (str): Full request, e.g. "set a 30 second timer"
        Returns:
            (int): Seconds requested, or None
            (str): Remainder of utterance
        """
        if not text:
            return None, None

        # Some STT engines return "30-second timer" not "30 second timer"
        # Deal with that before calling extract_duration().
        # TODO: Fix inside parsers
        utt = text.replace("-", " ")
        duration, str_remainder = extract_duration(utt, self.lang)
        if duration:
            # Remove "  and" left behind from "for 1 hour and 30 minutes"
            # prevents it being interpreted as a name "for  and"
            str_remainder = re.sub(r'\s\sand', '', str_remainder, flags=re.I)
            return duration.total_seconds(), str_remainder

        return None, text

    def _extract_ordinal(self, text):
        """Extract ordinal from text.

        Remove once extract_number supports short ordinal format eg '2nd'
        """
        num = None
        if text is None or len(text) == 0:
            return None

        try:
            num = extract_number(text, self.lang, ordinals=True)
            # attempt to remove extracted ordinal
            spoken_ord = num2words(int(num), to="ordinal", lang=self.lang)
            utt = text.replace(spoken_ord,"")
        except:
            self.log.debug('_extract_ordinal: Error in extract_number method')
            pass
        if not num:
            try:
                # Should be removed if the extract_number() function can
                # parse ordinals already e.g. 1st, 3rd, 69th, etc.
                regex = re.compile(r'\b((?P<Numeral>\d+)(st|nd|rd|th))\b')
                result = re.search(regex, text)
                if result and (result['Numeral']):
                    num = result['Numeral']
                    utt = text.replace(result, "")
            except:
                self.log.debug('_extract_ordinal: Error in regex search')
                pass
        return int(num), utt

    def _get_timer_name(self, utt):
        """Get the timer name using regex on an utterance."""
        self.log.debug("Utterance being searched: " + utt)
        rx_file = self.find_resource('name.rx', 'regex')
        if utt and rx_file:
            with open(rx_file) as f:
                for pat in f.read().splitlines():
                    pat = pat.strip()
                    self.log.debug("Regex pattern: " + pat)
                    if pat and pat[0] == "#":
                        continue
                    res = re.search(pat, utt)
                    if res:
                        try:
                            name = res.group("Name").strip()
                            self.log.debug('Regex name extracted: '
                                           + name)
                            if name and len(name.strip()) > 0:
                                return name
                        except IndexError:
                            pass
        return None

    def _get_next_timer(self):
        """Retrieve the next timer set to trigger."""
        next_timer = None
        for timer in self.active_timers:
            if not next_timer or timer["expires"] < next_timer["expires"]:
                next_timer = timer
        return next_timer

    def _get_ordinal_of_new_timer(self, duration, timers=None):
        """Get ordinal based on existing timer durations."""
        timers = timers or self.active_timers
        timer_count = sum(1 for t in timers if t["duration"] == duration)
        return timer_count + 1

    def _get_speakable_ordinal(self, timer):
        """Get speakable ordinal if other timers exist with same duration."""
        timers = self.active_timers
        ordinal = timer['ordinal']
        duration = timer['duration']
        timer_count = sum(1 for t in timers if t["duration"] == duration)
        if timer_count > 1 or ordinal > 1:
            return num2words(ordinal, to="ordinal", lang=self.lang)
        else:
            return ""

    def _get_speakable_timer_list(self, timer_list):
        """Get timer list as speakable string."""
        speakable_timer_list = []
        for timer in timer_list:
            dialog = 'timer.details'
            if timer['name'] is not None:
                dialog += '.named'
            ordinal = (None if timer['ordinal'] <= 1
                       else self._get_speakable_ordinal(timer))
            if ordinal is not None:
                dialog += '.with.ordinal'
            data = {'ordinal': ordinal,
                    'duration': nice_duration(timer["duration"]),
                    'name': timer['name']}
            speakable_timer_list.append(self.translate(dialog, data))
        names = join_list(speakable_timer_list, self.translate("and"))
        return names

    def _get_timer_matches(self, utt, timers=None, max_results=1,
                           dialog='ask.which.timer', is_response=False):
        """Get list of timers that match based on a user utterance.

            Args:
                utt (str): string spoken by the user
                timers (list): list of timers to match against
                max_results (int): max number of results desired
                dialog (str): name of dialog file used for disambiguation
                is_response (bool): is this being called by get_response
            Returns:
                (str): ["All", "Matched", "No Match Found", or "User Cancelled"]
                (list): list of matched timers
        """
        timers = timers or self.active_timers
        all_words = self.translate_list('all')
        if timers is None or len(timers) == 0:
            self.log.error("Cannot get match. No active timers.")
            return "No Match Found", None
        elif utt and any(i.strip() in utt for i in all_words):
            return "All", None

        extracted_duration = self._extract_duration(utt)
        if extracted_duration:
            duration, utt = extracted_duration
        else:
            duration = extracted_duration

        extracted_ordinal = self._extract_ordinal(utt)
        if extracted_ordinal:
            ordinal, utt = extracted_ordinal
        else:
            ordinal = extracted_ordinal

        timers_have_ordinals = any(t['ordinal'] > 1 for t in timers)
        name = self._get_timer_name(utt)

        if is_response and name is None:
            # Catch direct naming of a timer when asked eg "pasta"
            name = utt

        duration_matches, name_matches = None, None
        if duration:
            duration_matches = [t for t in timers if duration == t['duration']]

        if name:
            name_matches = [t for t in timers if t['name'] and
                            self._fuzzy_match_word_from_phrase(t['name'],
                                                               name,
                                                               self.threshold)
                            ]

        if name or duration:
            if duration_matches and name_matches:
                matches = [t for t in name_matches if duration == t['duration']]
            elif duration_matches or name_matches:
                matches = duration_matches or name_matches
            elif ordinal > 0 and not(duration_matches or name_matches):
                matches = timers
            else:
                return "No Match Found", None
        else:
            matches = timers

        if ordinal and len(matches) > 1:
            for idx, match in enumerate(matches):
                # should instead set to match['index'] if index gets reported
                # in timer description.
                if timers_have_ordinals and duration_matches:
                    ord_to_match = match['ordinal']
                else: 
                    ord_to_match = idx + 1
                if ordinal == ord_to_match:
                    return "Match Found", [match]
        elif len(matches) <= max_results:
            return "Match Found", matches
        elif len(matches) > max_results:
            # TODO additional = the current group eg "5 minute timers"
            additional = ""
            speakable_matches = self._get_speakable_timer_list(matches)
            reply = self.get_response(dialog,
                                      data={"count": len(matches),
                                            "names": speakable_matches,
                                            "additional": additional})
            if reply:
                return self._get_timer_matches(reply,
                                               timers=matches,
                                               dialog=dialog,
                                               max_results=max_results,
                                               is_response=True)
            else:
                return "User Cancelled", None
        return "No Match Found", None

    @staticmethod
    def _fuzzy_match_word_from_phrase(word, phrase, threshold):
        matched = False
        score = 0
        phrase_split = phrase.split(' ')
        word_split_len = len(word.split(' '))

        for i in range(len(phrase_split) - word_split_len, -1, -1):
            phrase_comp = ' '.join(phrase_split[i:i + word_split_len])
            score_curr = fuzzy_match(phrase_comp, word.lower())

            if score_curr > score and score_curr >= threshold:
                score = score_curr
                matched = True

        return matched


    def update_display(self, message):
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
        now = datetime.now()
        flash = False
        for timer in self.active_timers:
            if timer["expires"] < now:
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
            idx = timer["index"]
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
        if timer["expires"] > now:
            # Timer still running
            remaining = (timer["expires"] - now).seconds
            self.render_timer(idx, remaining)
        elif timer.get("is_interval"):
            # Timer has expired but it is an interval
            self._play_beep()
            # reset the timer expiration
            remaining = timer["duration"]
            time_expires = datetime.now() + timedelta(seconds=remaining)
            timer["expires"] = time_expires
            self.render_timer(idx, remaining)
        else:
            # Timer has expired but not been cleared, flash eyes
            overtime = (now - timer["expires"]).seconds
            self.render_timer(idx, -overtime)

            if timer["announced"]:
                # beep again every 10 seconds
                if overtime % self.beep_repeat_period == 0 and not self.mute:
                    self._play_beep()
            else:
                # if only timer, just beep
                if len(self.active_timers) == 1:
                    self._play_beep()
                else:
                    duration = nice_duration(timer["duration"])
                    name = timer['name']
                    speakable_ord = self._get_speakable_ordinal(timer)
                    dialog = 'timer.expired'
                    if name:
                        dialog += '.named'
                    if speakable_ord != "":
                        dialog += '.ordinal'
                    self.speak_dialog(dialog,
                                      data={"duration": duration,
                                            "name": name,
                                            "ordinal": speakable_ord})
                timer["announced"] = True

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

    def _speak_timer(self, timer):
        """Speak the status of an individual timer - remaining or elapsed."""
        # If _speak_timer receives timer = None, it assumes that
        # timer wasn't found, and not there was no active timers
        if timer is None:
            self.speak_dialog("timer.not.found")
            return

        # TODO: speak_dialog should have option to not show mouth
        # For now, just deactiveate.  The sleep() is to allow the
        # message to make it across the bus first.
        self.enclosure.deactivate_mouth_events()
        time.sleep(0.25)

        now = datetime.now()
        duration = nice_duration(timer["duration"])
        name = timer["name"]
        ordinal = timer["ordinal"]

        if timer and timer["expires"] < now:
            # expired, speak how long since it triggered
            time_diff = nice_duration((now - timer["expires"]).seconds)
            dialog = 'time.elapsed'
        else:
            # speak remaining time
            time_diff = nice_duration((timer["expires"] - now).seconds)
            dialog = 'time.remaining'

        if name:
            dialog += '.named'
        speakable_ord = self._get_speakable_ordinal(timer)
        if speakable_ord != "":
            dialog += '.with.ordinal'

        self.speak_dialog(dialog, {"duration": duration,
                                   "name": name,
                                   "time_diff": time_diff,
                                   "ordinal": speakable_ord})
        wait_while_speaking()
        self.enclosure.activate_mouth_events()

    def _speak_timer_status(self, timer_name, has_all):
        """Determine which timers to speak - all or specific timer."""
        # Check if utterance has "All"
        if timer_name is None or has_all:
            for timer in self.active_timers:
                self._speak_timer(timer)
            return
        # Just speak status of given timer
        result, timers = self._get_timer_matches(timer_name)
        if result == "No Match Found":
            self.speak_dialog('timer.not.found')
        return self._speak_timer(timers[0])

    ######################################################################
    # INTENT HANDLERS

    @intent_handler(IntentBuilder("start.timer").require("Timer")
                    .require("Start").optionally("Connector"))
    def handle_start_timer(self, message):
        """Common handler for start_timer intents."""

        def validate_duration(string):
            """Check that extract_duration returns a valid duration."""
            res = extract_duration(string, self.lang)
            return res and res[0]

        utt = message.data["utterance"]
        # GET TIMER DURATION
        secs, utt_remaining = self._extract_duration(utt)
        if secs and secs == 1:  # prevent "set one timer" doing 1 sec timer
            utt_remaining = message.data["utterance"]

        if secs is None: # no duration found, request from user
            req_duration = self.get_response('ask.how.long',
                                             validator=validate_duration)
            secs, _ = self._extract_duration(req_duration)
            if secs is None:
                return  # user cancelled

        # GET TIMER NAME
        if utt_remaining is not None and len(utt_remaining) > 0:
            timer_name = self._get_timer_name(utt_remaining)
            if timer_name:
                if self._check_duplicate_timer_name(timer_name):
                    return # make another timer with a different name
        else:
            timer_name = None

        # SHOULD IT BE AN ALARM?
        # TODO: add name of alarm if available?
        if secs >= 60*60*24:  # 24 hours in seconds
            if self.ask_yesno("timer.too.long.alarm.instead") == 'yes':
                alarm_time = now_local() + timedelta(seconds=secs)
                phrase = self.translate('set.alarm',
                                        {'date': alarm_time.strftime('%B %d %Y'),
                                         'time': alarm_time.strftime('%I:%M%p')})
                self.bus.emit(Message("recognizer_loop:utterance",
                                      {"utterances": [phrase], "lang": "en-us"}))
            return

        # CREATE TIMER
        self.timer_index += 1
        time_expires = datetime.now() + timedelta(seconds=secs)
        timer = {"name": timer_name,
                 "index": self.timer_index,
                 # keep track of ordinal until all timers of that name expire
                 "ordinal": self._get_ordinal_of_new_timer(secs),
                 "duration": secs,
                 "expires": time_expires,
                 "announced": False}
        self.active_timers.append(timer)
        self.log.debug("-------------TIMER-CREATED-------------")
        for key in timer:
            self.log.debug('creating timer: {}: {}'.format(key, timer[key]))
        self.log.debug("---------------------------------------")

        # INFORM USER
        if timer['ordinal'] > 1:
            dialog = 'started.ordinal.timer'
        else:
            dialog = 'started.timer'
        if timer['name'] is not None:
            dialog += '.with.name'

        self.speak_dialog(dialog,
                          data={"duration": nice_duration(timer["duration"]),
                                "name": timer["name"],
                                "ordinal": self._get_speakable_ordinal(timer)})

        # CLEANUP
        self.pickle()
        wait_while_speaking()
        self.enable_intent("handle_mute_timer")
        # Start showing the remaining time on the faceplate
        self.update_display(None)
        # reset the mute flag with a new timer
        self.mute = False

    def _check_duplicate_timer_name(self, name):
        for timer in self.active_timers:
            if timer['name'] and (name.lower() == timer['name'].lower()):
                now = datetime.now()
                time_diff = nice_duration((timer['expires'] - now).seconds)
                self.speak_dialog('timer.duplicate.name',
                                  data={"name": timer["name"],
                                        "duration": time_diff})
                return True
        return False

    @intent_handler('start.interval.timer.intent')
    def handle_start_interval_timer(self, message):
        """ Common handler for start_interval_timer intents
        """
        def validate_duration(string):
            """Check that extract_duration returns a valid duration."""
            res = extract_duration(string, self.lang)
            return res and res[0]

        utt = message.data["utterance"]
        #~~ GET TIMER DURATION
        secs, utt_remaining = self._extract_duration(utt)
        if secs and secs == 1:  # prevent "set one timer" doing 1 sec timer
            utt_remaining = message.data["utterance"]

        if secs == None: # no duration found, request from user
            req_duration = self.get_response('ask.how.long.interval',
                                             validator=validate_duration)
            secs, _ = self._extract_duration(req_duration)
            if secs is None:
                return  # user cancelled

        #~~ GET TIMER NAME
        # START WIP - Not worried about timer names for now
        #if utt_remaining is not None and len(utt_remaining) > 0:
        #    timer_name = self._get_timer_name(utt_remaining)
        #    if timer_name:
        #        if self._check_duplicate_timer_name(timer_name):
        #            return # make another timer with a different name
        #else:
        #    timer_name = None
        timer_name = None
        # END WIP

        #~~ SHOULD IT BE AN ALARM?
        # TODO: add name of alarm if available?
        if secs >= 60*60*24:  # 24 hours in seconds
            if self.ask_yesno("timer.too.long.alarm.instead") == 'yes':
                alarm_time = now_local() + timedelta(seconds=secs)
                phrase = self.translate('set.alarm',
                                        {'date': alarm_time.strftime('%B %d %Y'),
                                         'time': alarm_time.strftime('%I:%M%p')})
                self.bus.emit(Message("recognizer_loop:utterance",
                                      {"utterances": [phrase], "lang": "en-us"}))
            return

        #~~ CREATE TIMER
        self.timer_index += 1
        time_expires = datetime.now() + timedelta(seconds=secs)
        timer = {"name": timer_name,
                 "index": self.timer_index,
                 # keep track of ordinal until all timers of that name expire
                 "ordinal": self._get_ordinal_of_new_timer(secs),
                 "duration": secs,
                 "expires": time_expires,
                 "announced": False,
                 "is_interval":True}
        self.active_timers.append(timer)
        self.log.debug("-------------TIMER-CREATED-------------")
        for key in timer:
            self.log.debug('creating inverval timer: {}: {}'.format(key, timer[key]))
        self.log.debug("---------------------------------------")
        #~~ INFORM USER
        if timer['ordinal'] > 1:
            dialog = 'started.ordinal.interval.timer'
        else:
            dialog = 'started.interval.timer'
        # if timer['name'] is not None:
        #     dialog += '.with.name'

        self.speak_dialog(dialog,
                          data={"duration": nice_duration(timer["duration"]),
                                "name": timer["name"],
                                "ordinal": self._get_speakable_ordinal(timer)})

        #~~ CLEANUP
        self.pickle()
        wait_while_speaking()
        self.enable_intent("handle_mute_timer")
        # Start showing the remaining time on the faceplate
        self.update_display(None)
        # reset the mute flag with a new timer
        self.mute = False

    # Handles custom start phrases eg "ping me in 5 minutes"
    # Also over matches Common Play for "start timer" utterances
    @intent_file_handler('start.interval.timer.intent')
    def handle_start_interval_timer_padatious(self, message):
        self.handle_start_interval_timer(message)

    @intent_file_handler('stop.interval.timer.intent')
    def handle_stop_interval_timer(self, message):
        timer = self._get_next_timer()
        if timer and timer["expires"] < datetime.now():
            # Timer is beeping requiring no confirmation reaction,
            # treat it like a stop button press
            self.stop()
        elif message and message.data.get('utterance') == "cancel":
            # No expired timers to clear
            # Don't cancel active timers with only "cancel" as utterance
            return
        else:
            self.handle_cancel_timer(message)


    # Handles custom start phrases eg "ping me in 5 minutes"
    # Also over matches Common Play for "start timer" utterances
    @intent_file_handler('start.timer.intent')
    def handle_start_timer_padatious(self, message):
        self.handle_start_timer(message)

    # Handles custom status phrases eg 'How much time left'
    @intent_file_handler('timer.status.intent')
    def handle_status_timer_padatious(self, message):
        self.handle_status_timer(message)

    # Handles "do I have any timers" etc
    @intent_handler(IntentBuilder("status.timer.query").require("Query").
                    optionally("Status").require("Timer").optionally("All"))
    def handle_query_status_timer(self, message):
        self.handle_status_timer(message)

    # Handles "timer status", "status of timers" etc
    @intent_handler(IntentBuilder("status.timer").optionally("Query").
                    require("Status").one_of("Timer", "Time").
                    optionally("All").optionally("Duration").
                    optionally("Name"))
    def handle_status_timer(self, message):
        if not self.active_timers:
            self.speak_dialog("no.active.timer")
            return

        utt = message.data["utterance"]

        # If asking about all, or only 1 timer exists then speak
        if len(self.active_timers) == 1:
            timer_matches = self.active_timers
        else:
            # get max 2 matches, unless user explicitly asks for all
            result, timer_matches = self._get_timer_matches(utt, max_results=2)
            if result == "User Cancelled":
                return

        # Speak the relevant dialog
        if timer_matches is None:
            self.speak_dialog('timer.not.found')
        else:
            number_of_timers = len(timer_matches)
            if number_of_timers > 1:
                num = pronounce_number(number_of_timers)
                self.speak_dialog('number.of.timers', {'num': num})
            for timer in timer_matches:
                self._speak_timer(timer)

    @intent_handler(IntentBuilder("").require("Mute").require("Timer"))
    def handle_mute_timer(self, message):
        self.mute = True

    @intent_file_handler('stop.timer.intent')
    def handle_stop_timer(self, message):
        timer = self._get_next_timer()
        if timer and timer["expires"] < datetime.now():
            # Timer is beeping requiring no confirmation reaction,
            # treat it like a stop button press
            self.stop()
        elif message and message.data.get('utterance') == "cancel":
            # No expired timers to clear
            # Don't cancel active timers with only "cancel" as utterance
            return
        else:
            self.handle_cancel_timer(message)

    @intent_handler(IntentBuilder("").require("Cancel").require("Timer")
                    .optionally("Connector").optionally("All"))
    def handle_cancel_timer(self, message=None):
        if message:
            utt = message.data['utterance']
            all_words = self.translate_list('all')
            has_all = any(i.strip() in utt for i in all_words) \
                      or message.data.get('All')
        num_timers = len(self.active_timers)

        if num_timers == 0:
            self.speak_dialog("no.active.timer")

        elif not message or has_all:
            if num_timers == 1:
                # Either "cancel all" or from Stop button
                timer = self._get_next_timer()
                self.speak_dialog("cancelled.single.timer")
            else:
                self.speak_dialog('cancel.all', data={"count": num_timers})

            # get duplicate so we can walk the list
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self.cancel_timer(timer)
            self.pickle()   # save to disk

        elif num_timers == 1:
            # Check if utt included details and it is a mismatch
            # E.g. "Cancel the 5 minute timer" when it's a 7 minute timer
            result, timer = self._get_timer_matches(utt, max_results=1)
            if timer is not None:
                timer = timer[0]
            else:
                # If mismatched confirm to cancel the current timer
                next_timer = self._get_next_timer()
                duration = nice_duration(next_timer["duration"])
                name = next_timer["name"] or duration
                if self.ask_yesno('confirm.timer.to.cancel',
                                  data={"name": name}) == 'yes':
                    timer = next_timer
            if timer is not None:
                self.cancel_timer(timer)
                self.speak_dialog("cancelled.single.timer")
                self.pickle()   # save to disk

        elif num_timers > 1:
            dialog = 'ask.which.timer.cancel'
            result, timer = self._get_timer_matches(utt, dialog=dialog,
                                                    max_results=1)
            if result == "User Cancelled":
                self.log.debug("User cancelled or did not respond")
                return
            if timer:
                timer = timer[0]
                self.cancel_timer(timer)
                duration = nice_duration(timer["duration"])
                name = timer["name"] or duration
                speakable_ord = self._get_speakable_ordinal(timer)
                name = timer["name"]
                dialog = "cancelled.timer"
                if name:
                    dialog += '.named'
                if speakable_ord != "":
                    dialog += '.with.ordinal'
                self.speak_dialog(dialog,
                                  data={"duration": duration,
                                        "name": name,
                                        "ordinal": speakable_ord})
                self.pickle()   # save to disk

            else:
                self.speak_dialog("timer.not.found")

        # NOTE: This allows 'ShowTimer' to continue running, it will clean up
        #       after itself nicely.

    def cancel_timer(self, timer):
        """Actually cancels the given timer."""
        # Cancel given timer
        if timer:
            self.active_timers.remove(timer)
            if len(self.active_timers) == 0:
                self.timer_index = 0  # back to zero timers
            self.enclosure.eyes_on()  # reset just in case

    def shutdown(self):
        # Clear the timer list, this fixes issues when stop() gets called
        # on shutdown.
        if len(self.active_timers) > 0:
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self.cancel_timer(timer)

    def converse(self, utterances, lang="en-us"):
        timer = self._get_next_timer()
        if timer and timer["expires"] < datetime.now():
            # A timer is going off
            if utterances and self.voc_match(utterances[0], "StopBeeping"):
                # Stop the timer
                self.stop()
                return True  # and consume this phrase

    # This is a little odd. This actually does the work for the Stop button,
    # which prevents blocking during the Stop handler when input from the
    # user is needed.
    def handle_verify_stop_timer(self, message):
        # Confirm cancel of live timers...
        prompt = ('ask.cancel.running' if len(self.active_timers) == 1
                  else 'ask.cancel.running.plural')
        if self.ask_yesno(prompt) == 'yes':
            self.handle_cancel_timer()

    def stop(self):
        timer = self._get_next_timer()
        now = datetime.now()
        if timer and timer["expires"] < now:
            # stop the expired timer(s)
            while timer and timer["expires"] < now:
                self.cancel_timer(timer)
                timer = self._get_next_timer()
            self.pickle()   # save to disk
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

    ######################################################################
    # TODO:Move to MycroftSkill

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
