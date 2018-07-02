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
from mycroft.util.parse import extractnumber, fuzzy_match
from mycroft.util.format import pronounce_number
import mycroft.client.enclosure.display_manager as DisplayManager

try:
    from mycroft.skills.skill_data import to_alnum
except ImportError:
    from mycroft.skills.skill_data import to_letters as to_alnum


# TEST SCRIPT:
#  set a 30 second timer
#  stop (confirms)
#  set a timer for 5 minutes
#  cancel timer
#  set a 10 seconds timer
#  set a timer for 5 minutes
#       wait 10 secs.  first timer fires
#  stop
#       second timer should continue
#  stop
#       should get confirmationy
#  set a timer for 5 minutes
#  how much is left on the timer
#  set a 7 minute timer
#  how much time is left                     (FAIL: gives current time instead)
#  how much is left on the 5 minute timer
#  how much time is left on the 5 minute timer
#  status of the 5 minute timer
#  status of the 7 minute timer
#  how much is left on the first timer      (FAIL)
#  how much is left on the timer
#  >    asks for which timer
#  number one
#       should say around 4.5 minutes
#  how much is left on the timer
#  the 5 minute timer
#       should say around 4.5 minutes
#  how much is left on the timer
#  the second
#       should say around 6 minutes
#  how much is left on the timer
#  >    asks for which timer
#  all
#
#  set a 5 minute timer called lasagna
#  set a 7 minute timer called broccoli
#  cancel the timer
#       asks which...
#  lasagna
#       confirms that it cancelled the lasagna timer
#
#
# FAILS:
#  set a 1 and a half minute timer
#  set a timer for 3 hours 45 minutes


# TODO: Move to mycroft.util.format
def nice_duration(self, duration, lang="en-us", speech=True):
    """ Convert duration in seconds to a nice spoken timespan

    Examples:
       duration = 60  ->  "1:00" or "one minute"
       duration = 163  ->  "2:43" or "two minutes forty three seconds"

    Args:
        duration: time, in seconds
        speech (bool): format for speech (True) or display (False)
    Returns:
        str: timespan as a string
    """
    days = duration // 86400
    hours = duration // 3600 % 24
    minutes = duration // 60 % 60
    seconds = duration % 60
    if speech:
        out = ""
        if days > 0:
            if days == 1:   # number 1 has to be adapted to the genus of the
                            #  following noun in some languages
                out += self.translate("say.day")
            else:
                out += pronounce_number(days, lang) + " " + self.translate(
                    "say.days")
            out += " "
        if hours > 0:
            out += " "
            if hours == 1:
                out += self.translate("say.hour")
            else:
                out += pronounce_number(hours, lang) + " " + self.translate(
                    "say.hours")
            out += " "
        if minutes > 0:
            if minutes == 1:
                out += self.translate("say.minute")
            else:
                out += pronounce_number(minutes, lang) + " " + self.translate(
                    "say.minutes")
            out += " "
        if seconds > 0:
            if seconds == 1:
                out += self.translate("say.second")
            else:
                out += pronounce_number(seconds, lang) + " " + self.translate(
                    "say.seconds")
        return out
    else:
        # M:SS, MM:SS, H:MM:SS, Dd H:MM:SS format
        out = ""
        if days > 0:
            out = str(days) + "d "
        if hours > 0:
            out += str(hours) + ":"
        if minutes < 10 and hours > 0:
            out += "0"
        out += str(minutes)+":"
        if seconds < 10:
            out += "0"
        out += str(seconds)
        return out


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

    # TODO: Move to MycroftSkill
    def ask_yesno(self, prompt):
        """
        Read prompt and wait for a yes/no answer

        This automatically deals with translation and common variants,
        such as 'yeah', 'sure', etc.

        Args:
              prompt (str): a dialog id or string to read
        Returns:
              string:  'yes', 'no' or whatever the user response if not
                       one of those, including None
        """
        resp = self.get_response(prompt)
        yes_words = self.translate_list('yes')
        if (resp and any(i.strip() in resp for i in yes_words)):
            return 'yes'

        no_words = self.translate_list('no')
        if (resp and any(i.strip() in resp for i in no_words)):
            return 'no'

        return resp


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

    def pickle(self):
        # Save the timers for reload
        with self.file_system.open('save_timers', 'wb') as f:
            pickle.dump(self.active_timers, f, pickle.HIGHEST_PROTOCOL)

    def unpickle(self):
        # Reload any saved timers
        try:
            with self.file_system.open('save_timers', 'rb') as f:
                self.active_timers = pickle.load(f)
            for timer in self.active_timers:
                if timer["index"] > self.timer_index:
                    self.timer_index = timer["index"]
        except:
            self.active_timers = []

    # TODO: Implement util.is_listening() to replace this
    def handle_listener_started(self, message):
        self.is_listening = True

    def handle_listener_ended(self, message):
        self.is_listening = False

    def _extract_duration(self, text):
        if not text:
            return None

        # return the duration in seconds
        num = extractnumber(text.replace("-", " "), self.lang)
        if not num:
            return None

        unit = 1  # default to secs
        if any(i.strip() in text for i in self.translate_list('second')):
            unit = 1
        elif any(i.strip() in text for i in self.translate_list('minute')):
            unit = 60
        elif any(i.strip() in text for i in self.translate_list('hour')):
            unit = 60*60
        return num*unit

    # Handles 'Start a 30 second timer'
    # TODO: Doesn't handle 'start 1 and a half minute timer'
    @intent_file_handler('start.timer.intent')
    def handle_start_timer(self, message):
        # Extract the requested timer duration
        if 'duration' not in message.data:
            secs = self._extract_duration(message.data["utterance"])
            if secs and secs > 1: # set one timer should not yield a 1 sec timer
                duration = message.data["utterance"]
            else:
                duration = self.get_response('ask.how.long')
                if duration == None:
                    return  # user cancelled
        else:
            duration = message.data["duration"]
        secs = self._extract_duration(duration)
        if not secs:
            self.speak_dialog("tell.me.how.long")
            return

        self.timer_index += 1

        # Name the timer
        timer_name = ""
        if 'name' in message.data:
            # Get a name from request
            timer_name = message.data["name"]
        if not timer_name:
            # Name after the duration, e.g. "30 second timer"
            timer_name = nice_duration(self, secs, lang = self.lang)

        now = datetime.now()
        time_expires = now + timedelta(seconds=secs)
        timer = {"name": timer_name,
                 "index": self.timer_index,
                 "duration": secs,
                 "expires": time_expires,
                 "announced": False}
        self.active_timers.append(timer)

        prompt = "started.timer" if len(self.active_timers) == 1 else "started.another.timer"
        self.speak_dialog(prompt,
                          data={"duration": nice_duration(self, timer[
                                                              "duration"],
                                                          lang=self.lang)})
        self.pickle()
        wait_while_speaking()

        self.enable_intent("handle_cancel_timer")
        self.enable_intent("handle_mute_timer")
        self.enable_intent("handle_status_timer")

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
        num = extractnumber(name)
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
            self.disable_intent("handle_cancel_timer")
            self.disable_intent("handle_mute_timer")
            # self.disable_intent("handle_status_timer")  # TODO: needs Adapt
            self.timer_index = 0  # back to zero timers
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
            if not self.display_idx:
                self.display_idx = 1.0
            else:
                self.display_idx += 0.2
            if self.display_idx-1 > len(self.active_timers):
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
        display_owner = DisplayManager.get_active()
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
            time = str(hours)+":"+str(minutes).zfill(2)+":"+str(seconds).zfill(2)
            pixel_width = len(time)*4 - 2*2 + 6 # account of colons being smaller
        else:
            # convert to m:ss
            time = str(minutes).zfill(2)+":"+str(seconds).zfill(2)
            pixel_width = len(time)*4 - 2 + 6 # account of colons being smaller

        x = (4*8 - pixel_width) // 2  # centers on display
        if expired:
            time = "-"+time
        else:
            time = " "+time

        if idx:
            # If there is an index to show, display at the left
            png = "/opt/mycroft/skills/mycroft-timer/"+str(int(idx))+".png"
            self.enclosure.mouth_display_png(png, x=3, y=2, refresh=False)
            x += 6

        # draw on the display
        for ch in time:
            # deal with some odd characters that can break filesystems
            if ch == ":":
                png = "/opt/mycroft/skills/mycroft-timer/colon.png"
            elif ch == " ":
                png = "/opt/mycroft/skills/mycroft-timer/blank.png"
            elif ch == "-":
                png = "/opt/mycroft/skills/mycroft-timer/dash.png"
            else:
                png = "/opt/mycroft/skills/mycroft-timer/"+ch+".png"

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
                which = self.get_response('ask.which.timer',
                                      data={"count": len(self.active_timers),
                                            "names": names})
                if not which:
                    return  # cancelled inquiry
        else:
            which = intent['duration']

        self._speak_timer_status(which)

    @intent_handler(IntentBuilder("").require("Mute").require("Timer"))
    def handle_mute_timer(self, message):
        self.mute = True

    @intent_handler(IntentBuilder("").require("VerifyCancel").require("Timer"))
    def handle_verify_stop_timer(self, message):
        # Confirm cancel of live timers...
        prompt = 'ask.cancel.running' if len(self.active_timers) == 1 else 'ask.cancel.running.plural'
        if self.ask_yesno(prompt) == 'yes':
            self.handle_cancel_timer()

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
                                data={"count": num_timers})

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
            duration = nice_duration(self, timer["duration"], lang = self.lang)
            self.speak_dialog("cancelled.single.timer",
                              data={"name": timer["name"],
                                    "duration": duration})
            self.pickle()   # save to disk

        elif num_timers > 1:
            which = self.get_response('ask.which.timer.cancel',
                                      data={"count": len(self.active_timers)})
            if not which:
                return  # user Cancelled the Cancel

            # Check if they replied "all", "all timers", "both", etc.
            all_words = self.translate_list('all')
            if (which and any(i.strip() in which for i in all_words)):
                message.data["All"] = "all"
                self.handle_cancel_timer(message)
                return

            timer = self._get_timer(which)
            if timer:
                self.cancel_timer(timer)
                duration = nice_duration(self, timer["duration"],
                                         lang = self.lang)
                self.speak_dialog("cancelled.single.timer",
                                  data={"name": timer["name"],
                                        "duration": duration})
                self.pickle()   # save to disk

        # NOTE: This allows 'ShowTimer' to continue running, it will clean up
        #       after itself nicely.

    def _speak_timer_status(self, timer_name):
        # Look for "All"
        all_words = self.translate_list('all')
        if (timer_name == None or
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
            passed = (now - timer["expires"]).seconds
            self.speak_dialog("time.elapsed",
                              data={"name": name,
                                    "passed_time": nice_duration(self,
                                                                 passed,
                                                                 lang = self.lang)})
        else:
            # speak remaining time
            remaining = (timer["expires"] - now).seconds
            self.speak_dialog("time.remaining",
                              data={"name": name,
                                    "remaining": nice_duration(self,
                                                               remaining,
                                                            lang = self.lang)})
        wait_while_speaking()
        self.enclosure.activate_mouth_events()

    def cancel_timer(self, timer):
        # Cancel given timer
        if timer:
            self.active_timers.remove(timer)
            self.enclosure.eyes_on()  # reset just in case

    @intent_file_handler('stop.timer.intent')
    def handle_stop_timer(self, message):
        """ Wrapper for stop method """
        self.stop()

    def shutdown(self):
        # Clear the timer list, this fixes issues when stop() gets called
        # on shutdown.
        if len(self.active_timers) > 0:
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self.cancel_timer(timer)

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
            self.emitter.emit(Message("recognizer_loop:utterance",
                            {'utterances': ["verify_cancel timer"],
                                'lang': 'en-us'}))
            return True

        return False

    ######################################################################
    ## Audio feedback

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


def create_skill():
    return TimerSkill()
