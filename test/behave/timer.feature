Feature: mycroft-timer

  Scenario: Start a timer step 1
    Given an english speaking user
     When the user says "start a timer"
     Then "mycroft-timer" should reply with dialog from "ask.how.long.dialog"

  Scenario: Start a timer step 2
    Given an english speaking user
     When the user says "1 minute"
     Then "mycroft-timer" should reply with dialog from "started.timer.dialog"

  Scenario: delete timer
    Given an english speaking user
     When the user says "delete timer"
     Then "mycroft-timer" should reply with dialog from "cancelled.single.timer.dialog"

  Scenario: start timer with time
    Given an english speaking user
     When the user says "start a 30 second timer"
     Then "mycroft-timer" should reply with dialog from "started.timer.dialog"

  Scenario: kill timer
    Given an english speaking user
     When the user says "kill timer"
     Then "mycroft-timer" should reply with dialog from "cancelled.single.timer.dialog"

  Scenario: time left with no active timers
    Given an english speaking user
     When the user says "how much time is left"
     Then "mycroft-timer" should reply with dialog from "no.active.timer.dialog"

  Scenario: start a 20 minute timer
    Given an english speaking user
     When the user says "start a 20 minute timer"
     Then "mycroft-timer" should reply with dialog from "started.timer.dialog"

  Scenario: time remaining
    Given an english speaking user
     When the user says "how much time is left"
     Then "mycroft-timer" should reply with dialog from "time.remaining.dialog"

  Scenario: start an 1 hour timer
    Given an english speaking user
     When the user says "start a 1 hour timer"
     Then "mycroft-timer" should reply with dialog from "started.timer.dialog"

  Scenario: start a 5 minute timer
    Given an english speaking user
     When the user says "start a 5 minute timer"
     Then "mycroft-timer" should reply with dialog from "started.timer.dialog"

  Scenario: how much time left when there are multiple timers step 1
    Given an english speaking user
     When the user says "how much time is left"
     Then "mycroft-timer" should reply with dialog from "ask.which.timer.dialog"

  Scenario: how much time left when there are multiple timers step 2
    Given an english speaking user
     When the user says "first"
     Then "mycroft-timer" should reply with dialog from "time.remaining.dialog"

  Scenario: time remaining on specific timer
    Given an english speaking user
     When the user says "how much time is left on the 5 minute timer"
     Then "mycroft-timer" should reply with dialog from "time.remaining.dialog"

  Scenario: start a named timer
    Given an english speaking user
     When the user says "start a 7 minute timer called lasagna"
     Then "mycroft-timer" should reply with dialog from "started.timer.with.name.dialog"

  Scenario: ask again for time left when multiple timers are running
    Given an english speaking user
     When the user says "how much is left on the timer"
     Then "mycroft-timer" should reply with dialog from "ask.which.timer.dialog"

  Scenario: cancel all timers step 1
    Given an english speaking user
     When the user says "cancel all timers"
     Then "mycroft-timer" should reply with anything

  Scenario: cancel all timers step 2
    Given an english speaking user
     When the user says "yes"
     Then "mycroft-timer" should reply with anything
