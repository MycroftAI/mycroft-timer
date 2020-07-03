from time import sleep

# TODO remove this in v20.8 when it should be available in mycroft-core

def wait_for_message(bus, message_type, timeout=8):
    """Wait for specified Message type on the bus.

    Arguments:
        bus: an instance of the message bus to listen on
        message_type: the Message type to wait for
        timeout (int): how long to wait, defaults to 8 secs
    """
    message_detected = False

    def detected_speak(message=None):
        nonlocal message_detected
        message_detected = True
    bus.on(message_type, detected_speak)
    sleep(timeout)
    bus.remove(message_type, detected_speak)
    return message_detected
