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

from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill, intent_handler, intent_file_handler
from mycroft.util.log import LOG
from datetime import datetime, timedelta
from os.path import join, isfile, abspath, dirname
from mycroft.util import play_wav
from mycroft.messagebus.message import Message
from mycroft.util.parse import extractnumber, fuzzy_match
from mycroft.util.format import pronounce_number


# TEST SCRIPT:
#  set a 30 second timer
#  stop (confirms)
#  set a timer for 5 minutes
#  cancel timer                 (TODO: Awkward wording)
#  set a 10 second timer
#  set a timer for 5 minutes
#       wait 10 secs.  first timer fires
#  stop
#       second timer should continue
#  stop
#       should get confirmation (TODO: awkward wording)
#  set a timer for 5 minutes
#  how much is left on the timer
#  set a 7 minute timer
#  how much time is left        (TODO: fails, gives current time instead)
#  how much is left on the timer
#       should ask for which timer
#  number one
#       should say around 4.5 minutes
#  how much is left on the timer
#  the 5 minute timer
#       should say around 4.5 minutes
#  how much is left on the timer
#  the second
#       should say around 6 minutes
#  cancel the timer
#
#
# FAILS:
#  set a 1 and a half minute timer
#  set a timer for 3 hours 45 minutes

# TODO: Temporary while EnclosureAPI.eyes_fill() gets implemented
def enclosure_eyes_fill(percentage):
    import subprocess
    amount = int(round(23.0 * percentage / 100.0))
    subprocess.call('echo "eyes.fill=' + str(amount) + '" > /dev/ttyAMA0', shell=True)


# TODO: Move to mycroft.util.format
def nice_duration(duration, lang="en-us", speech=True):
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
            out += pronounce_number(days)
            out += " days " if days == 1 else " day "
        if hours > 0:
            out += pronounce_number(hours)
            out += " hour " if hours == 1 else " hours "
        if minutes > 0:
            out += pronounce_number(minutes)
            out += " minute " if minutes == 1 else " minutes "
        if seconds > 0:
            out += pronounce_number(seconds)
            out += " second" if seconds == 1 else " seconds"
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
# TODO: add labels for timers, first, second, etc

class TimerSkill(MycroftSkill):
    def __init__(self):
        super(TimerSkill, self).__init__("TimerSkill")
        self.active_timers = []
        self.sound_file = join(abspath(dirname(__file__)), 'timerBeep.wav')
        try:
            self.eyes_fill = self.enclosure.eyes_fill
        except:
            self.eyes_fill = enclosure_eyes_fill
        self.displaying_timer = None
        self.beep_process = None
        self.display_text = None
        self.mute = False

    def initialize(self):
        self.register_entity_file('duration.entity')
        self.register_entity_file('timervalue.entity')
        self.register_entity_file('all.entity')

        # Invoke update_display in one second to allow it to disable the
        # cancel intent, since there are no timers to cancel yet!
        self.schedule_repeating_event(self.update_display,
                                      None, 1, name='ShowTimer')

    # Handles 'Start a 30 second timer'
    # TODO: Doesn't handle 'start 1 and a half minute timer'
    @intent_file_handler('start.timer.intent')
    def handle_start_timer(self, message):
        duration = message.data["duration"]

        # Name the timer
        # TODO: Get a name from request
        # ????: Name sequentially, e.g. "Timer 1", "Timer 2"?
        timer_name = duration

        # Extract the requested timer duration
        num = extractnumber(duration)
        unit = 1  # default to secs
        if any(i.strip() in duration for i in self.translate_list('second')):
            unit = 1
        elif any(i.strip() in duration for i in self.translate_list('minute')):
            unit = 60
        elif any(i.strip() in duration for i in self.translate_list('hour')):
            unit = 60*60

        now = datetime.now()
        time_expires = now + timedelta(seconds=num*unit)
        timer = {"name": timer_name,
                 "duration": num*unit,
                 "expires": time_expires}
        self.active_timers.append(timer)

        self.speak_dialog("started.timer",
                          data={"duration": nice_duration(timer["duration"])})

        # Start showing the remaining time on the faceplate
        self.update_display(None)
        self.enable_intent("handle_cancel_timer")
        self.enable_intent("handle_mute_timer")
        self.enable_intent("handle_status_timer")

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
        # Retrieve the next timer set to trigger
        for timer in self.active_timers:
            if timer["name"] == name:
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
            self.disable_intent("handle_status_timer")  # TODO: Change to Adapt for this
            self.enclosure.eyes_reset()
            self._stop_beep()
            self._clear_display()
            return

        # Check if the display frequency is set correctly for the
        # closest timer...
        if timer != self.displaying_timer:
            self.cancel_scheduled_event('ShowTimer')
            # Create a callback with appropriate frequency
            freq = timer["duration"]/100.0
            if freq < 1:
                freq = 1
            self.schedule_repeating_event(self.update_display,
                                          None, freq,
                                          name='ShowTimer')
            self.displaying_timer = timer

        # Calc remaining time and show using faceplate
        now = datetime.now()

        if (timer["expires"] > now):
            # Timer still running
            remaining = (timer["expires"] - now).seconds
            dur = timer["duration"]
            self.eyes_fill(int(remaining*100.0/dur))
        else:
            # Timer has expired but not been cleared, flash eyes
            overtime = (now - timer["expires"]).seconds
            if overtime % 2 == 0:
                self.enclosure.eyes_off()
            else:
                self.enclosure.eyes_on()

            # beep every 10 seconds
            if overtime % 10 == 0 and not self.mute:
                self._play_beep()

            # Show the expired time.  This naturally "flashes"
            self._show(nice_duration(overtime, speech=False))

    # Handles 'How much time left'
    @intent_file_handler('status.timer.intent')
    def handle_status_timer(self, message):
        intent = message.data
        if not self.active_timers:
            self.speak_dialog("no.active.timer")
        elif len(self.active_timers) == 1:
            self._speak_timer_status(self.active_timers[0]["name"])
        else:
            self._multiple_timer_status(intent)

    def _multiple_timer_status(self, intent):
        """ determines which timer to speak the status of

            Args:
                intent (dict): data from Message object
        """
        if 'duration' not in intent.keys():
            which = self.get_response('ask.which.timer',
                                      data={"count": len(self.active_timers)})
            if not which:
                return

            num = extractnumber(which)
            if num and num-1 < len(self.active_timers):
                timer = self.active_timers[int(num-1)]
            else:
                timer = None
                best = 0.5  # minimum threshold for a match
                for t in self.active_timers:
                    if fuzzy_match(which, t["name"]) > best:
                        best = fuzzy_match(which, t["name"])
                        timer = t
            if timer:
                self._speak_timer_status(timer["name"])
        else:
            duration = intent['duration']
            timer_name = duration
            self._speak_timer_status(timer_name)

    @intent_handler(IntentBuilder("").require("Mute").require("Timer"))
    def handle_mute_timer(self, message):
        self.mute = True

    @intent_handler(IntentBuilder("").require("Cancel").require("Timer").optionally("All"))
    def handle_cancel_timer(self, message):
        num_timers = len(self.active_timers)
        if num_timers == 0:
            self.speak_dialog("no.active.timer")
            return

        intent = message.data
        if 'All' in intent:
            self.speak_dialog('cancel.all')
            # get duplicate so we can walk the list
            active_timers = list(self.active_timers)
            for timer in active_timers:
                self.cancel_timer(timer["name"])

        elif num_timers == 1:
            timer = self._get_next_timer()
            self.cancel_timer(timer["name"])
            self.speak_dialog("cancelled.single.timer",
                              data={"duration": nice_duration(timer["duration"])})

        elif num_timers > 1:
            which = self.get_response('ask.which.timer.cancel',
                                      data={"count": len(self.active_timers)})
            if not which:
                return

            # Check if they replied "all", "all timers", "both", etc.
            all_words = self.translate_list('all')
            if (which and any(i.strip() in which for i in all_words)):
                self.speak_dialog('cancel.all')
                # get duplicate so we can walk the list
                active_timers = list(self.active_timers)
                for timer in active_timers:
                    self.cancel_timer(timer["name"])
                return

            num = extractnumber(which)
            if num and num-1 < len(self.active_timers):
                timer = self.active_timers[int(num-1)]
            else:
                timer = None
                best = 0.5  # minimum threshold for a match
                for t in self.active_timers:
                    if fuzzy_match(which, t["name"]) > best:
                        best = fuzzy_match(which, t["name"])
                        timer = t
            if timer:
                self.cancel_timer(timer["name"])
                self.speak_dialog("cancelled.single.timer",
                                  data={"duration": nice_duration(timer["duration"])})

        # NOTE: This allows 'ShowTimer' to continue running, it will clean up
        #       after itself nicely.

    def _speak_timer_status(self, timer_name):
        # Speak status of given timer
        timer = self._get_timer(timer_name)
        if timer is None:
            self.speak_dialog("no.active.timer")
        else:
            now = datetime.now()
            remaining = (timer["expires"] - now).seconds
            self.speak(nice_duration(remaining))

    def cancel_timer(self, timer_name):
        # Cancel given timer
        timer = None
        for t in self.active_timers:
            if t["name"] == timer_name:
                timer = t
                break
        if timer:
            self.active_timers.remove(timer)

    @intent_file_handler('stop.intent')
    def _stop(self, message):
        """ Wrapper for stop method """
        self.stop()

    def stop(self):
        timer = self._get_next_timer()
        now = datetime.now()
        if timer and timer["expires"] < now:
            # stop the expired timer(s)
            while timer and timer["expires"] < now:
                self.cancel_timer(timer["name"])
                timer = self._get_next_timer()
            return True

        elif self.active_timers:
            # Confirm cancel of live timers...
            if len(self.active_timers) > 1:
                confirm = self.get_response('ask.cancel.running')
            else:
                confirm = self.get_response('ask.cancel.running.plural')
            yes_words = self.translate_list('yes')
            if (confirm and any(i.strip() in confirm for i in yes_words)):
                # Cancel all timers
                while timer:
                    self.cancel_timer(timer["name"])
                    timer = self._get_next_timer()
                self.speak_dialog("cancel.all")
                return True

        return False

    def _clear_display(self):
        self.enclosure.mouth_reset()
        self.display_text = None

    def _show(self, str, force=False):
        # NOTE: On the Mark 1, the display clears before writing.
        #       This make it look like it 'flashes', which is OK
        if str != self.display_text:
            self.enclosure.mouth_text(str)
            self.display_text = str

    def _play_beep(self):
        # Play the beep sound
        if not self._is_playing_beep():
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
