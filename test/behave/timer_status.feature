Feature: Timer Status
  Report the status of one or more timers.

  Scenario Outline: status of a single timer
    Given an english speaking user
    And no timers are previously set
    And a timer is set for 5 minutes
    When the user says "<timer status>"
    Then "mycroft-timer" should reply with dialog from "time-remaining.dialog"

    Examples: status of a single timer
      | timer status |
      | what's left on my timer |
      | how much is left on the timer |
      | what's the remaining time |
      | how's my timer |
      | do I have any timers |
      | are there any timers |
      | what timers do I have |
      | when does the timer end |
      | timer status |

  Scenario Outline: status when there are no active timers
    Given an english speaking user
    And no timers are previously set
    And no timers are set
    When the user says "<timer status>"
    Then "mycroft-timer" should reply with dialog from "no-active-timer.dialog"

    Examples: status when there are no active timers
      | timer status |
      | what's left on my timer |
      | how much is left on the timer |
      | what's the remaining time |
      | how's my timer |
      | do I have any timers |
      | are there any timers |
      | what timers do I have |
      | when does the timer end |
      | timer status |

  Scenario Outline: status of named timer
    Given an english speaking user
    And no timers are previously set
    And a timer named chicken is set for 20 minutes
    When the user says "<status of named timer>"
    Then "mycroft-timer" should reply with dialog from "time-remaining-named.dialog"

    Examples: status of named timer
      | status of named timer |
      | status of chicken timer |
      | what is the status of the chicken timer |
      | how much time is left on the chicken timer |

  Scenario Outline: status of two timers
    Given an english speaking user
    And no timers are previously set
    And a 5 minute timer is set
    And a 10 minute timer is set
    When the user says "<what's the status of the timers>"
    Then "mycroft-timer" should reply with dialog from "number-of-timers.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining.dialog"

    Examples: status of two timers
      | what's the status of the timers |
      | what's left on my timers |
      | how much time is left on the timers |
      | what's the remaining time |
      | how's my timer |
      | do I have any timers |
      | are there any timers |
      | what timers do I have |
      | when does the timer end |

  @xfail
  # Jira MS-95 https://mycroft.atlassian.net/browse/MS-95
  Scenario Outline: Failing status of two timers
    Given an english speaking user
    And no timers are previously set
    And a 5 minute timer is set
    And a 10 minute timer is set
    When the user says "<what's the status of the timers>"
    Then "mycroft-timer" should reply with dialog from "number-of-timers.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining.dialog"

    Examples: status of two timers
      | what's the status of the timers |
      | what's the status of the timers |
