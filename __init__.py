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

from mycroft.skills.core import MycroftSkill
from mycroft.util.log import LOG
from datetime import datetime, timedelta
from os.path import join, isfile, abspath, dirname
from mycroft.util import play_wav
from mycroft.audio import wait_while_speaking

import json
import time
import uuid
import sys
import dateutil.parser as dparser


def get_time_left_string(time_left, timer_name):
    """ Turn into params into a string for status of timer

        Args:
            time_left (int): seconds
            time_name (str): name of timer

        Return
            speak_string (str): timer string mycroft can speak

    """
    days = time_left // 86400
    hours = time_left // 3600 % 24
    minutes = time_left // 60 % 60
    seconds = time_left % 60

    speak_string = "There is "
    if days > 0:
        time_string = "days" if days == 1 else "day"
        speak_string += "{} {} ".format(days, time_string)
    if hours > 0:
        time_string = "hour" if hours == 1 else "hours"
        speak_string += "{} {} ".format(hours, time_string)
    if minutes > 0:
        time_string = "minute" if minutes == 1 else "minutes"
        speak_string += "{} {} ".format(minutes, time_string)
    if seconds > 0:
        time_string = "second" if seconds == 1 else "seconds"
        speak_string += "{} {} ".format(seconds, time_string)
    speak_string += "left on the {} timer".format(timer_name)

    return speak_string


def parse_to_datetime(duration):
    """ Takes in duration and output datetime

        Args:
            duration (str): string in any time format
                            ex. 1 hour 2 minutes 30 seconds

        Return:
            timer_time (datetime): datetime object with
                                   time now + duration
    """
    parsed_time = dparser.parse(duration, fuzzy=True)
    now = datetime.now()

    seconds = parsed_time.second
    minutes = parsed_time.minute
    hours = parsed_time.hour

    timer_time = now + timedelta(
        hours=hours, minutes=minutes, seconds=seconds)

    return timer_time


# TODO: display timer if it's a mark_1 device
# TODO: add labels for timers, first, second, etc
# TODO: add stop timer sound functionality
class TimerSkill(MycroftSkill):
    def __init__(self):
        super(TimerSkill, self).__init__("TimerSkill")
        self.active_timers = []
        self.should_converse = False
        self.intent_context = None
        self.stop_notify = False
        self.allow_notify = False
        self.sound_file = join(abspath(dirname(__file__)), 'timerBeep.wav')

    def initialize(self):
        self.register_intent_file(
            'start.timer.intent', self.handle_start_timer)
        self.register_intent_file(
            'status.timer.intent', self.handle_status_timer)
        self.register_intent_file(
            'cancel.timer.intent', self.handle_cancel_timer)
        self.register_intent_file('stop.intent', self._stop)
        self.register_entity_file('duration.entity')
        self.register_entity_file('timervalue.entity')

    def handle_start_timer(self, message):
        """ callback for start timer intent

            Args:
                message (Message): object passed by messagebus
        """
        duration = message.data["duration"]
        timer_time = parse_to_datetime(duration)

        timer_name = duration

        self.active_timers.append(timer_name)
        self.speak("okay. {} starting now".format(duration))
        self.schedule_event(
            self._handle_end_timer, timer_time,
            data=timer_name, name=timer_name)

    def handle_status_timer(self, message):
        """ callback for timer status intent

            Args:
                message (Message): object passed by messagebus
        """
        intent = message.data
        amt_of_timer = len(self.active_timers)
        if amt_of_timer == 0:
            self.speak("Cannot find any active timers")
        elif amt_of_timer == 1:
            timer_name = self.active_timers[0]
            self.speak_timer_status(timer_name)
        elif amt_of_timer > 1:
            self.multiple_timer_status(intent, amt_of_timer)

    def multiple_timer_status(self, intent, amt_of_timer):
        """ determines which timer to speak the status of

            Args:
                intent (dict): data from Message object
        """
        if 'duration' not in intent.keys():
            self.should_converse = True
            # let converse knows how to handle utterances
            self.intent_context = 'status.timer.intent'
            # when setting expect_respose = True, let's mycroft activate
            # listening mode right after speak
            mult_str = "You have {} active timers. ".format(amt_of_timer)
            for i in range(len(self.active_timers)):
                mult_str += "the {} timer, ".format(self.active_timers[i])
                if (i + 2) == len(self.active_timers):
                    mult_str += "and "
                if ((i + 1) == len(self.active_timers)):
                    mult_str += "."
            mult_str += "Which one were you referring to?"
            self.speak(mult_str, expect_response=True)
        else:
            duration = intent['duration']
            timer_name = duration
            self.speak_timer_status(timer_name)

    def handle_cancel_timer(self, message):
        """ callback for cancel intent

            Args:
                message (Message): object passed by messagebus
        """
        intent = message.data
        if 'all' in intent:
            active_timers = list(self.active_timers)
            self.speak_dialog('cancel.all')
            for timers in active_timers:
                self.cancel_timer(timers)
            return

        amt_of_timer = len(self.active_timers)
        if amt_of_timer == 0:
            self.speak("Cannot find any active timers")
        elif amt_of_timer == 1:
            timer_name = self.active_timers[0]
            self.cancel_timer(timer_name)
            self.speak("Okay. {} is canceled".format(timer_name))
        elif amt_of_timer > 1:
            if 'timervalue' not in intent.keys():
                self.should_converse = True
                self.intent_context = 'cancel.timer.intent'
                self.speak("You have {} active timers, ".format(amt_of_timer) +
                           "which one's should I cancel?",
                           expect_response=True)
            else:
                timer_value = intent['timervalue']
                timer_name = duration
                self.cancel_timer(timer_name)
                self.speak("Okay. {} is canceled".format(timer_name))

    def _handle_end_timer(self, message):
        """ callback for start timer scheduled_event()

            Args:
                message (Message): object passed by messagebus
        """
        timer_name = message.data
        self.cancel_timer(timer_name)
        self.notify_process = play_wav(self.sound_file)
        self.notify_process.wait()
        self.speak("the {} timer is up".format(timer_name),
                   expect_response=True)
        wait_while_speaking()
        self.notify()

    def speak_timer_status(self, timer_name):
        """ wrapper to speak status of timer

            Args:
                timer_name (str): name of timer in event scheduler
        """
        time_left = self.get_scheduled_event_status(timer_name)
        if time_left is None:
            self.speak("Cannot find any active timers")
        speak_string = get_time_left_string(time_left, timer_name)
        self.speak(speak_string)

    def cancel_timer(self, timer_name):
        """ cancel timer through event shceduler

            Args:
                timer_name (str): name of timer in event scheduler
        """
        self.cancel_scheduled_event(timer_name)
        if timer_name in self.active_timers:
            self.active_timers.remove(timer_name)

    def notify(self, repeat=360):
        """ recursively calls it's self to play alarm sound

            Args:
                repeat (int): number of times it'll call itself
                              each repeat is about 10 seconds
        """
        if hasattr(self, 'notify_event_name'):
            self.cancel_scheduled_event(self.notify_event_name)

        self.allow_notify = True
        self.notify_process = play_wav(self.sound_file)
        if self.stop_notify is False:
            if repeat > 0:
                time_to_repeat = parse_to_datetime('6 seconds')
                self.notify_event_name = \
                    "timerskill.playsound.repeat.{}".format(repeat)
                self.schedule_event(
                    lambda x=None: self.notify(repeat - 1), time_to_repeat,
                    data=self.notify_event_name, name=self.notify_event_name)
            else:
                self.reset_notify()
        if self.stop_notify is True:
            self.reset_notify()

    def reset_notify(self):
        self.allow_notify = False
        self.stop_notify = False

    def reset_converse(self):
        """ set converse to false and empty intent_context """
        self.should_converse = False
        self.intent_context = None

    def converse(self, utterances, lang='en-us'):
        """ overrides MycroftSkill converse method. when return value is True,
            any utterances after will be sent through the conveerse method
            to be handled.

            Args:
                utterances (str): utterances said to mycroft
                lang (str): languge of utterance (currently not used)
        """
        if self.intent_context == 'status.timer.intent':
            utt = utterances[0]
            found_timer = False
            for timer in self.active_timers:
                if timer in utt:
                    self.speak_timer_status(timer)
                    found_timer = True
                    self.reset_converse()
                    return True
            if found_timer is False:
                self.speak("Cannot find any timer named {}".format(utt))
                self.reset_converse()
                return True
        elif self.intent_context == 'cancel.timer.intent':
            utt = utterances[0]
            found_timer = False
            for timer in self.active_timers:
                if timer in utt:
                    self.cancel_timer(timer)
                    self.speak("Okay. {} is canceled".format(timer))
                    self.reset_converse()
                    return True
            if found_timer is False:
                self.speak("Cannot find any timer named {}".format(utt))
                self.reset_converse()
                return True
        return self.should_converse

    def _stop(self, message):
        """ Wrapper for stop method """
        self.stop()

    def stop(self):
        if self.allow_notify is True:
            self.stop_notify = True
            self.allow_notify = False
            self.cancel_scheduled_event(self.notify_event_name)
            self.notify_process.kill()


def create_skill():
    return TimerSkill()
