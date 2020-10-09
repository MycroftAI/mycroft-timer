import time

from behave import given, then

from mycroft.audio import wait_while_speaking
from test.integrationtests.voight_kampff import (
        emit_utterance,
        wait_for_dialog)


@given('a {timer_length} timer is set')
@given('a timer is set for {timer_length}')
def given_set_timer_lenght(context, timer_length):
    emit_utterance(context.bus, 'set a timer for {}'.format(timer_length))
    wait_for_dialog(context.bus, ['started.timer'])
    context.bus.clear_messages()


@given('a timer named {name} is set for {time}')
def given_set_timer_named(context, name, time):
    emit_utterance(context.bus,
                   'set a timer for {} time called {}'.format(time, name))
    wait_for_dialog(context.bus, ['started.timer.with.name'])
    context.bus.clear_messages()


@given('a timer named {name} is set')
def given_set_named_timer(context, name):
    emit_utterance(context.bus,
                   'set a timer for 95 minutes called {}'.format(name))
    wait_for_dialog(context.bus, ['started.timer'])
    context.bus.clear_messages()


@given('there is already an active timer')
def given_set_timer(context):
    emit_utterance(context.bus, 'set a timer for 100 minutes')
    wait_for_dialog(context.bus, ['started.timer'])
    context.bus.clear_messages()


@given('no timers are active')
@given('no timers are set')
@given('no timers are previously set')
def given_no_timers(context):
    followups = ['ask.cancel.running.plural',
                 'ask.cancel.desc.alarm.recurring']
    no_timers = ['no.active.timer',
                 'cancel.all',
                 'cancelled.single.timer',
                 'cancelled.timer.named',
                 'cancelled.timer.named.with.ordinal',
                 'cancelled.timer.with.ordinal']
    cancelled = ['cancel.all',
                 'cancelled.single.timer',
                 'cancelled.timer.named',
                 'cancelled.timer.named.with.ordinal',
                 'cancelled.timer.with.ordinal']

    emit_utterance(context.bus, 'cancel all timers')
    for i in range(10):
        for message in context.bus.get_messages('speak'):
            if message.data.get('meta', {}).get('dialog') in followups:
                print('Answering yes!')
                time.sleep(3)
                wait_while_speaking()
                emit_utterance(context.bus, 'yes')
                wait_for_dialog(context.bus, cancelled)
                context.bus.clear_messages()
                return
            elif message.data.get('meta', {}).get('dialog') in no_timers:
                context.bus.clear_messages()
                return
        time.sleep(1)


@given('only one timer is set')
def given_single_timer(context):
    given_no_timers(context)
    given_set_timer(context)


@given('a timer is expired')
def given_expired_timer(context):
    emit_utterance(context.bus, 'set a 3 second timer')
    wait_for_dialog(context.bus, ['started.timer'])
    time.sleep(4)


@then('"mycroft-timer" should stop beeping')
def then_stop_beeping(context):
    # TODO: Better check!
    import psutil
    for i in range(10):
        if 'paplay' not in [p.name() for p in psutil.process_iter()]:
            break
        time.sleep(1)
    else:
        assert False, "Timer is still ringing"
