Feature: Timer Status
  Report the status of one or more timers.

  Scenario Outline: status of a single timer
    Given an english speaking user
    And an active 5 minute timer
    When the user says "<timer status request>"
    Then "mycroft-timer" should reply with dialog from "time-remaining.dialog"

    Examples: status of a single timer
      | timer status request |
      | what's left on my timer |
      | how much is left on the timer |
      | what's the remaining time |
      | how's my timer |
      | do I have any timers |
      | are there any timers |
      | what timers do I have |
      | when does the timer end |
      | timer status |

  @xfail
  Scenario Outline: failing status of a single timer
    Given an english speaking user
    And an active 5 minute timer
    When the user says "<timer status request>"
    Then "mycroft-timer" should reply with dialog from "time-remaining.dialog"

    Examples: failing status of a single timer
      | timer status request |
      | when does the timer end |

  Scenario Outline: status when there are no active timers
    Given an english speaking user
    And no active timers
    When the user says "<timer status request>"
    Then "mycroft-timer" should reply with dialog from "no-active-timer.dialog"

    Examples: status when there are no active timers
      | timer status request |
      | what's left on my timer |
      | how much is left on the timer |
      | what's the remaining time |
      | how's my timer |
      | do I have any timers |
      | are there any timers |
      | what timers do I have |
      | timer status |

  Scenario Outline: status of named timer
    Given an english speaking user
    And an active timer named chicken for 20 minutes
    When the user says "<timer status request>"
    Then "mycroft-timer" should reply with dialog from "time-remaining-named.dialog"

    Examples: status of named timer
      | timer status request |
      | status of chicken timer |
      | what is the status of the chicken timer |
      | how much time is left on the chicken timer |

  Scenario Outline: status of two timers
    Given an english speaking user
    And multiple active timers
      | duration |
      | 5 minutes |
      | 10 minutes |
    When the user says "<timer status request>"
    Then "mycroft-timer" should reply with dialog from "number-of-timers.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining-named.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining-named.dialog"

    Examples: status of two timers
      | timer status request |
      | what's left on my timers |
      | how much time is left on the timers |
      | what's the remaining time |
      | how's my timer |
      | do I have any timers |
      | are there any timers |
      | what timers do I have |
      | what's the status of the timers |

  @xfail
  Scenario Outline: failing status of two timers
    Given an english speaking user
    And multiple active timers
      | duration |
      | 5 minutes |
      | 10 minutes |
    When the user says "<timer status request>"
    Then "mycroft-timer" should reply with dialog from "number-of-timers.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining-named.dialog"
    And "mycroft-timer" should reply with dialog from "time-remaining-named.dialog"

    Examples: status of two timers
      | timer status request |
      | when does the timer end |
