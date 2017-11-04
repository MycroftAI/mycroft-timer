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
from mycroft.util import play_mp3
from mycroft.audio import wait_while_speaking

import json
import time
import uuid
import sys
import dateutil.parser as dparser

sys.path.append(abspath(dirname(__file__)))
util = __import__('util')


# TODO: display timer if it's a mark_1 device
# TODO: add labels for timers, first, second, etc
# TODO: add stop timer sound functionality
class TimerSkill(MycroftSkill):
    def __init__(self):
        super(TimerSkill, self).__init__("TimerSkill")
        self.active_timers = []
        self.should_converse = False
        self.intent_context = None
        self.sound_file = join(abspath(dirname(__file__)), 'timerBeep.mp3')

    def initialize(self):
        self.register_intent_file(
            'start.timer.intent', self.handle_start_timer)
        self.register_intent_file(
            'status.timer.intent', self.handle_status_timer)
        self.register_intent_file(
            'cancel.timer.intent', self.handle_cancel_timer)
        self.register_entity_file('duration.entity')
        self.register_entity_file('timervalue.entity')

    def handle_start_timer(self, message):
        """ callback for start timer intent

            Args:
                message (Message): object passed by messagebus
        """
        duration = message.data["duration"]
        timer_time = util.parse_to_datetime(duration)

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
        self.speak("the {} timer is up".format(timer_name))
        wait_while_speaking()
        self.play_timer_sound(repeat=3)

    def speak_timer_status(self, timer_name):
        """ wrapper to speak status of timer

            Args:
                timer_name (str): name of timer in event scheduler
        """
        time_left = self.get_scheduled_event_status(timer_name)
        if time_left is None:
            self.speak("Cannot find any active timers")
        speak_string = util.get_time_left_string(time_left, timer_name)
        self.speak(speak_string)

    def cancel_timer(self, timer_name):
        """ cancel timer through event shceduler

            Args:
                timer_name (str): name of timer in event scheduler
        """
        self.cancel_scheduled_event(timer_name)
        if timer_name in self.active_timers:
            self.active_timers.remove(timer_name)

    def play_timer_sound(self, repeat=0, cancel=False, name=None):
        """ callback for end_timer for scheduled_event()
            recursively calls itself to repeat > 1

            Args:
                repeat (int): for how many times to schedule play sound
                cancel (bool): used to cancel previous event
                name (str): name of event scheduled
        """
        if cancel is True:
            self.cancel_scheduled_event(name)
        if repeat > 0:
            play_mp3(self.sound_file)
            time_to_repeat = util.parse_to_datetime('6 seconds')
            name = "timerskill.playsound.repeat.{}".format(repeat)
            self.schedule_event(
                lambda x=None: self.play_timer_sound((repeat - 1), True, name),
                time_to_repeat, data=name, name=name)

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

    def stop(self):
        pass


def create_skill():
    return TimerSkill()
