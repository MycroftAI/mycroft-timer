import dateutil.parser as dparser
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
        speak_string += "{} days ".format(days)
    if hours > 0:
        speak_string += "{} hours ".format(hours)
    if minutes > 0:
        speak_string += "{} minutes ".format(minutes)
    if seconds > 0:
        speak_string += "{} seconds ".format(seconds)

    speak_string += "left on {}".format(timer_name)
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
