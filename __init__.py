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

from adapt.intent import IntentBuilder
from mycroft.skills.core import (
    MycroftSkill,
    intent_handler,
    intent_file_handler)
from mycroft.util.log import LOG
from mycroft.audio import wait_while_speaking, is_speaking
from datetime import datetime, timedelta
from os.path import join, isfile, abspath, dirname
from mycroft.util import play_wav
from mycroft.messagebus.message import Message
from mycroft.util.parse import extract_number, fuzzy_match, extract_duration
from mycroft.util.format import pronounce_number, nice_duration
from mycroft.util.time import now_local

try:
    from mycroft.skills.skill_data import to_alnum
except ImportError:
    from mycroft.skills.skill_data import to_letters as to_alnum

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
        # self.sound_file = join(abspath(dirname(__file__)), 'timerBeep.wav')
        self.beep_repeat_period = 10
        self.sound_file = join(abspath(dirname(__file__)), 'twoBeep.wav')
        self.beep_repeat_period = 5

        self.displaying_timer = None
        self.beep_process = None
        self.mute = False
        self.timer_index = 0
        self.display_idx = None

    def initialize(self):
        self.register_entity_file('duration.entity')
        self.register_entity_file('timervalue.entity')
        self.register_entity_file('all.entity')

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
    def handle_listener_started(self, message):
        self.is_listening = True

    def handle_listener_ended(self, message):
        self.is_listening = False

    def _extract_duration(self, text):
        """ Extract duration in seconds
        Args:
            text (str): Full request, e.g. "set a 30 second timer"
        Returns:
            (int): Seconds requested, or None
        """
        if not text:
            return None

        # Some STT engines return "30-second timer" instead of
        # "30 second timer".  Deal with that before calling
        # extract_duration().
        # TODO: Fix inside parsers
        utt = text.replace("-", " ")
 
        dur_remainder = extract_duration(utt, self.lang)
        if dur_remainder and dur_remainder[0]:
            return dur_remainder[0].total_seconds()
        return None

    # Handles 'Start a 30 second timer'
    @intent_file_handler('start.timer.intent')
    def handle_start_timer(self, message):
        # Extract the requested timer duration
        if 'duration' not in message.data:
            secs = self._extract_duration(message.data["utterance"])
            if secs and secs > 1:  # prevent "set one timer" doing 1 sec timer
                duration = message.data["utterance"]
            else:
                duration = self.get_response('ask.how.long')
                if duration is None:
                    return  # user cancelled
        else:
            duration = message.data["duration"]
        secs = self._extract_duration(duration)
        if not secs:
            self.speak_dialog("tell.me.how.long")
            return
        if secs >= 60*60*24:  # 24 hours in seconds
            if self.ask_yesno("timer.too.long.alarm.instead") == 'نعم':
                alarm_time = now_local() + timedelta(seconds=secs)

                # TODO: Test this under another language.  I think this will work...
                phrase = "وضع منبه " + alarm_time.strftime("%B %d %Y at %I:%M%p")
                self.bus.emit(Message("recognizer_loop:utterance",
                                      {"utterances": [phrase], "lang": "en-us"}))
            return

        self.timer_index += 1

        # Name the timer
        timer_name = ""
        if 'name' in message.data:
            # Get a name from request
            timer_name = message.data["name"]
        if not timer_name:
            # Name after the duration, e.g. "30 second timer"
            timer_name = nice_duration(secs)

        now = datetime.now()
        time_expires = now + timedelta(seconds=secs)
        timer = {"name": timer_name,
                 "index": self.timer_index,
                 "duration": secs,
                 "expires": time_expires,
                 "announced": False}
        self.active_timers.append(timer)

        prompt = ("started.timer" if len(self.active_timers) == 1
                  else "started.another.timer")
        self.speak_dialog(prompt,
                          data={"duration": nice_duration(timer["duration"])})
        self.pickle()
        wait_while_speaking()

        self.enable_intent("handle_mute_timer")

        # Start showing the remaining time on the faceplate
        self.update_display(None)

        # reset the mute flag with a new timer
        self.mute = False

    def _get_next_timer(self):
        # Retrieve the next timer set to trigger
        next = None
        for timer in self.active_timers:
            if not next or timer["expires"] < next["expires"]:
                next = timer
        return next

    def _get_timer(self, name):
        # Referenced it by duration? "the 5 minute timer"
        secs = self._extract_duration(name)
        if secs:
            for timer in self.active_timers:
                if timer["duration"] == secs:
                    return timer

        # Referenced by index?  "The first", "number three"
        num = extract_number(name)
        if num:
            for timer in self.active_timers:
                if timer["index"] == num:
                    return timer

        # Referenced by name (fuzzy matched)?
        timer = None
        best = 0.5  # minimum threshold for a match
        for t in self.active_timers:
            score = fuzzy_match(name, t["name"])
            if score > best:
                best = score
                timer = t
        if timer:
            return timer

        return None

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
            # This code will display each timer for 5 passes
            # of this screen update (5 seconds), then move on
            # to display the next timer.
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

        # Check if the display frequency is set correctly for the
        # closest timer...
        if timer != self.displaying_timer:
            self.cancel_scheduled_event('ShowTimer')
            self.schedule_repeating_event(self.update_display,
                                          None, 1,
                                          name='ShowTimer')
            self.displaying_timer = timer

        # Calc remaining time and show using faceplate
        if (timer["expires"] > now):
            # Timer still running
            remaining = (timer["expires"] - now).seconds
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
                    self.speak_dialog("timer.expired",
                                      data={"name": timer["name"]})

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

        hours = seconds // (60*60)  # hours
        rem = seconds % (60*60)
        minutes = rem // 60  # minutes
        seconds = rem % 60
        if hours > 0:
            # convert to h:mm:ss
            time = (str(hours) + ":"+str(minutes).zfill(2) +
                    ":"+str(seconds).zfill(2))
            # account of colons being smaller
            pixel_width = len(time)*4 - 2*2 + 6
        else:
            # convert to m:ss
            time = str(minutes).zfill(2)+":"+str(seconds).zfill(2)
            # account of colons being smaller
            pixel_width = len(time)*4 - 2 + 6

        x = (4*8 - pixel_width) // 2  # centers on display
        if expired:
            time = "-"+time
        else:
            time = " "+time

        if idx:
            # If there is an index to show, display at the left
            png = join(abspath(dirname(__file__)), str(int(idx))+".png")
            self.enclosure.mouth_display_png(png, x=3, y=2, refresh=False)
            x += 6

        # draw on the display
        for ch in time:
            # deal with some odd characters that can break filesystems
            if ch == ":":
                png = "colon.png"
            elif ch == " ":
                png = "blank.png"
            elif ch == "-":
                png = "negative.png"
            else:
                png = ch+".png"

            png = join(abspath(dirname(__file__)), png)
            self.enclosure.mouth_display_png(png, x=x, y=2, refresh=False)
            if ch == ':':
                x += 2
            else:
                x += 4

    # Handles 'How much time left'
    @intent_file_handler('status.timer.intent')
    def handle_status_timer(self, message):
        intent = message.data
        if not self.active_timers:
            self.speak_dialog("no.active.timer")
        elif len(self.active_timers) == 1:
            self._speak_timer_status(None)
        else:
            self._multiple_timer_status(intent)

    def _multiple_timer_status(self, intent):
        """ Determines which timer to speak about

            Args:
                intent (dict): data from Message object
        """
        if 'duration' not in intent.keys():
            if len(self.active_timers) < 3:
                which = None  # indicates ALL
            else:
                names = ""
                for timer in self.active_timers:
                    names += ". " + timer["name"]
                cnt = len(self.active_timers)
                which = self.get_response('ask.which.timer',
                                          data={"count": pronounce_number(cnt, self.lang),
                                                "names": names})
                if not which:
                    return  # cancelled inquiry
        else:
            which = intent['duration']

        self._speak_timer_status(which)

    @intent_handler(IntentBuilder("").require("Mute"))
    def handle_mute_timer(self, message):
        self.mute = True
        self.speak("تم كتم صوت الموقت")

    # This is a little odd. This actually does the work for the Stop button,
    # which prevents blocking during the Stop handler when input from the
    # user is needed.
    def handle_verify_stop_timer(self, message):
        # Confirm cancel of live timers...
        prompt = ('ask.cancel.running' if len(self.active_timers) == 1
                  else 'ask.cancel.running.plural')
        if self.ask_yesno(prompt) == 'نعم':
            self.handle_cancel_timer()

    @intent_file_handler('stop.timer.intent')
    def handle_stop_timer(self, message):
        self.log.info("handle_stop_timer")
        timer = self._get_next_timer()
        if timer and timer["expires"] < datetime.now():
            # Timer is beeping requiring no confirmation reaction,
            # treat it like a stop button press
            self.stop()
            self.speak("تم إيقاف الموقت")
        else:
            utt = message.data["utterance"]
            all_words = self.translate_list('all')
            if (any(i.strip() in utt for i in all_words)):
                message.data["All"] = all_words[0]
            self.handle_cancel_timer(message)

    @intent_handler(IntentBuilder("").require("Cancel").require("Timer").
                    optionally("All"))
    def handle_cancel_timer(self, message=None):
        num_timers = len(self.active_timers)
        if num_timers == 0:
            self.speak_dialog("no.active.timer")
            return

        if not message or 'All' in message.data:
            # Either "cancel all" or from Stop button
            if num_timers == 1:
                timer = self._get_next_timer()
                self.speak_dialog("cancelled.single.timer",
                                  data={"name": timer["name"]})
            else:
                self.speak_dialog('cancel.all',
                                  data={"count": pronounce_number(num_timers, self.lang)})

            # get duplicate so we can walk the list
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self.cancel_timer(timer)
            self.pickle()   # save to disk

        elif num_timers == 1:
            # TODO: Cancel if there is a spoken name and it is a mismatch?
            # E.g. "Cancel the 5 minute timer" when it's a 7 minute timer
            timer = self._get_next_timer()
            self.cancel_timer(timer)
            duration = nice_duration(timer["duration"])
            self.speak_dialog("cancelled.single.timer",
                              data={"name": timer["name"],
                                    "duration": duration})
            self.pickle()   # save to disk

        elif num_timers > 1:
            which = self.get_response('ask.which.timer.cancel',
                                      data={"count": pronounce_number(len(self.active_timers), self.lang)})
            if not which:
                return  # user Cancelled the Cancel

            # Check if they replied "all", "all timers", "both", etc.
            all_words = self.translate_list('all')
            if (which and any(i.strip() in which for i in all_words)):
                message.data["All"] = all_words[0]
                self.handle_cancel_timer(message)
                return

            timer = self._get_timer(which)
            if timer:
                self.cancel_timer(timer)
                duration = nice_duration(timer["duration"])
                self.speak_dialog("cancelled.single.timer",
                                  data={"name": timer["name"],
                                        "duration": duration})
                self.pickle()   # save to disk

        # NOTE: This allows 'ShowTimer' to continue running, it will clean up
        #       after itself nicely.

    def _speak_timer_status(self, timer_name):
        # Look for "All"
        all_words = self.translate_list('all')
        if (timer_name is None or
                (any(i.strip() in timer_name for i in all_words))):
            for timer in self.active_timers:
                self._speak_timer(timer)
            return

        # Just speak status of given timer
        timer = self._get_timer(timer_name)
        return self._speak_timer(timer)

    def _speak_timer(self, timer):
        if timer is None:
            self.speak_dialog("no.active.timer")
            return

        # TODO: speak_dialog should have option to not show mouth
        # For now, just deactiveate.  The sleep() is to allow the
        # message to make it across the bus first.
        self.enclosure.deactivate_mouth_events()
        time.sleep(0.25)

        now = datetime.now()
        name = timer["name"]

        if timer and timer["expires"] < now:
            # expired, speak how long since it triggered
            passed = nice_duration((now - timer["expires"]).seconds)
            self.speak_dialog("time.elapsed",
                              data={"name": name,
                                    "passed_time": passed})
        else:
            # speak remaining time
            remaining = nice_duration((timer["expires"] - now).seconds)
            self.speak_dialog("time.remaining",
                              data={"name": name,
                                    "remaining": remaining})
        wait_while_speaking()
        self.enclosure.activate_mouth_events()

    def cancel_timer(self, timer):
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
            if self.voc_match(utterances[0], "StopBeeping"):
                # Stop the timer
                self.stop()
                return True  # and consume this phrase

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
            # This is a little tricky.  We shouldn't initiate
            # dialog during Stop handling (there is confusion
            # between stopping speech and starting new conversations).
            # Instead, we'll just consider this Stop consumed and
            # post a message that will immediately be handled to
            # ask the user if they want to cancel.
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
        """Serialize the data under the name

        Args:
            name (string): reference name of the pickled data
            data (any): the data to store
        """

        with self.file_system.open(name, 'wb') as f:
            pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)

    def do_unpickle(self, name, default):
        """Load previously saved data under name

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
