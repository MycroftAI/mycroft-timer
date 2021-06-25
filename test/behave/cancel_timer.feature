Feature: Cancel Timers
  Timers can be canceled one at a time, by name, by duration or all at once

  Scenario Outline: cancel timer with one active timer
    Given an english speaking user
    And no timers are previously set
    And only one timer is set
    When the user says "<stop the timer>"
    Then "mycroft-timer" should reply with dialog from "cancelled-single-timer.dialog"

    Examples: cancel timer with one active timer
      | stop the timer |
      | stop the timer |
      | end timer |
      | end the timer |
      | kill the timer |
      | disable timer |
      | disable the timer |
      | delete timer |
      | remove timer |

  Scenario Outline: cancel timer with two active timers
    Given an english speaking user
    And no timers are previously set
    And a 1 minute timer is set
    And a 2 minute timer is set
    When the user says "<stop the timer>"
    Then "mycroft-timer" should reply with dialog from "ask-which-timer-cancel.dialog"
    And the user replies "1 minute"
    And "mycroft-timer" should reply with dialog from "cancelled-timer-named.dialog"

    Examples: cancel timer with two active timer
      | stop the timer |
      | stop the timer |
      | end timer |
      | end the timer |
      | kill the timer |
      | disable timer |
      | disable the timer |
      | delete timer |
      | remove timer |

  Scenario Outline: cancel timer with three active timers
    Given an english speaking user
    And no timers are previously set
    And a 1 minute timer is set
    And a 2 minute timer is set
    And a 3 minute timer is set
    When the user says "<cancel multiple timers>"
    Then "mycroft-timer" should reply with dialog from "ask-which-timer-cancel.dialog"
    And the user replies "1 minute"
    And "mycroft-timer" should reply with dialog from "cancelled-timer.dialog"

    Examples: cancel timer with three active timer
      | cancel multiple timers |
      | cancel timer |
      | stop the timer |
      | end timer |
      | end the timer |
      | kill the timer |
      | disable timer |
      | disable the timer |
      | delete timer |
      | remove timer |

  Scenario Outline: canceling a timer with three active timers when the user decides not to cancel
    Given an english speaking user
    And no timers are previously set
    And a 1 minute timer is set
    And a 2 minute timer is set
    And a 3 minute timer is set
    When the user says "<user decides not to cancel>"
    Then "mycroft-timer" should reply with dialog from "ask-which-timer-cancel.dialog"
    And the user replies "nevermind"

    Examples: cancel timer with three active timer and user decides not to cancel
      | user decides not to cancel |
      | cancel timer |
      | stop the timer |
      | end timer |

  Scenario Outline: cancel timer with no timer active
    Given an english speaking user
    And no timers are previously set
    And no timers are active
    When the user says "<cancel a timer with none active>"
    Then "mycroft-timer" should reply with dialog from "no-active-timer.dialog"

    Examples: cancel timer with no timer active
      | cancel a timer with none active |
      | stop the timer |
      | end timer |
      | end the timer |
      | kill the timer |
      | disable timer |
      | disable the timer |
      | delete timer |
      | remove timer |

  Scenario Outline: cancel a specific timer
    Given an english speaking user
    And no timers are previously set
    And a 5 minute timer is set
    And a 10 minute timer is set
    When the user says "<cancel a specific timer>"
    Then "mycroft-timer" should reply with dialog from "cancelled-timer-named.dialog"

    Examples: cancel a specific timer
      | cancel a specific timer |
      | stop the 5 minute timer |
      | cancel the 5 minute timer |
      | kill the 5 minute timer |
      | disable 5 minute timer |
      | disable the 5 minute timer |
      | delete the 5 minute timer |

  @xfail
  # Jira MS-61 https://mycroft.atlassian.net/browse/MS-61
  Scenario Outline: Failing cancel a specific timer
    Given an english speaking user
    And no timers are previously set
    And a 5 minute timer is set
    And a 10 minute timer is set
    When the user says "<cancel a specific timer>"
    Then "mycroft-timer" should reply with dialog from "cancelled-timer-named.dialog"

    Examples: cancel a specific timer
      | cancel a specific timer |
      | end 5 minute timer |
      | end the 5 minute timer |

  Scenario Outline: cancel a named timer
    Given an english speaking user
    And no timers are previously set
    And a timer named pasta is set
    When the user says "<cancel a named timer>"
    Then "mycroft-timer" should reply with dialog from "cancelled-single-timer.dialog"

    Examples: cancel a named timer
      | cancel a named timer |
      | cancel pasta timer |
      | stop the pasta timer |
      | kill the pasta timer |
      | disable pasta timer |
      | disable the pasta timer |
      | delete the pasta timer |
      | remove pasta timer |
      | end pasta timer |
      | end the pasta timer |

  Scenario Outline: cancel all timers when 3 timers are active
    Given an english speaking user
    And no timers are previously set
    And a timer is set for 5 minutes
    And a timer is set for  10 minutes
    And a timer is set for 15 minutes
    When the user says "<cancel all timers>"
    Then "mycroft-timer" should reply with dialog from "cancel-all.dialog"

    Examples: cancel all timers
      | cancel all timers |
      | cancel all timers |
      | delete all timers |
      | remove all timers |
      | stop all timers |
      | kill all timers |
      | disable all timers |
      | turn off all timers |
