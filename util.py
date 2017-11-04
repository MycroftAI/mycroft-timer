import dateutil.parser as dparser
import time
from datetime import datetime, timedelta


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
