Feature: mycroft-timer

  Scenario Outline: set a timer for a specified duration
    Given an english speaking user
    And no timers are previously set
    When the user says "<set a timer for a duration>"
    Then "mycroft-timer" should reply with dialog from "started-timer.dialog"

    Examples: set a timer for for a specified duration
      | set a timer for a duration |
      | timer 10 minutes |
      | timer 30 seconds |
      | set a timer for 5 minutes |
      | start a 1 minute timer |
      | start a timer for 1 minute and 30 seconds |
      | create a timer for 1 hour |
      | create a timer for 1 hour and 30 minutes |
      | ping me in 5 minutes |

  @xfail
  # Jira MS-114 https://mycroft.atlassian.net/browse/MS-114
  Scenario Outline: Failing set a timer for a specified duration
    Given an english speaking user
    And no timers are previously set
    When the user says "<set a timer for a duration>"
    Then "mycroft-timer" should reply with dialog from "started-timer.dialog"

    Examples: set a timer for for a specified duration
      | set a timer for a duration |
      | begin timer 2 minutes |

  Scenario Outline: set another timer for for a specified duration
    Given an english speaking user
    And no timers are previously set
    And there is already an active timer
    When the user says "<set another timer for a duration>"
    Then "mycroft-timer" should reply with dialog from "started-timer.dialog"

    Examples: set another timer
      | set another timer for a duration |
      | second timer 20 minutes |
      | start another timer for 5 minutes |
      | set one more timer for 10 minutes |
      | set a timer for 2 minutes |

  Scenario Outline: set a named timer for for a specified duration
    Given an English speaking user
    And no timers are previously set
    When the user says "<set a named timer for a duration>"
    Then "mycroft-timer" should reply with dialog from "started-timer-named.dialog"

    Examples: set a named timer for a specified duration
      | set a named timer for a duration |
      | set a 10 minute timer for pasta |
      | start a timer for 25 minutes called oven one |
      | start a timer for 15 minutes named oven two |

  @xfail
  # Jira MS-91 https://mycroft.atlassian.net/browse/MS-91
  Scenario Outline: set a named timer for for a specified duration ordinal
    Given an English speaking user
    And no timers are previously set
    When the user says "<set a named timer for a duration ordinal>"
    Then "mycroft-timer" should reply with dialog from "started-timer-named-ordinal.dialog"

    Examples: set a named timer for a specified duration ordinal
      | set a named timer for a duration ordinal |
      | set a timer for 10 minutes for pasta |

  Scenario Outline: set a timer for an unspecified duration
    Given an english speaking user
    And no timers are previously set
    When the user says "<set a timer for unspecified duration>"
    Then "mycroft-timer" should reply with dialog from "ask-how-long.dialog"
    And the user replies with "5 minutes"
    And "mycroft-timer" should reply with dialog from "started-timer.dialog"

    Examples: set a timer for an unspecified duration
      | set a timer for unspecified duration |
      | set a timer |
      | start a timer |
      | timer |

  @xfail
  # Jira MS-60 https://mycroft.atlassian.net/browse/MS-60
  Scenario Outline: Failing set a timer for an unspecified duration
    Given an english speaking user
    And no timers are previously set
    When the user says "<set a timer for unspecified duration>"
    Then "mycroft-timer" should reply with dialog from "ask-how-long.dialog"
    And the user replies with "5 minutes"
    And "mycroft-timer" should reply with dialog from "started-timer.dialog"

    Examples: set a timer for an unspecified duration
      | set a timer for unspecified duration |
      | timer for 5 |

  Scenario Outline: set a timer for an unspecified duration but then dismiss
    Given an english speaking user
    And no timers are previously set
    When the user says "set a timer"
    Then "mycroft-timer" should reply with dialog from "ask-how-long.dialog"
    And the user replies with "<nevermind>"

    Examples: set a timer for an unspecified duration
      | nevermind |
      | forget it |
      | dismiss |

  Scenario Outline: set a timer for an unspecified duration but then says jibberish
    Given an english speaking user
    And no timers are previously set
    When the user says "set a timer"
    Then "mycroft-timer" should reply with dialog from "ask-how-long.dialog"
    And the user replies with "<sandwich>"

    Examples: set a timer for an unspecified duration
      | sandwich |
      | blah |
      | goo |

  Scenario Outline: set another timer for an unspecified duration
    Given an english speaking user
    And no timers are previously set
    And there is already an active timer
    When the user says "<set another timer for unspecified duration>"
    Then "mycroft-timer" should reply with dialog from "ask-how-long.dialog"
    And the user replies with "5 minutes"
    And "mycroft-timer" should reply with dialog from "started-timer.dialog"

    Examples: set another timer for an unspecified duration
      | set another timer for unspecified duration |
      | one more timer |
      | second timer |

  Scenario Outline: set a named timer for an unspecified duration
    Given an english speaking user
    And no timers are previously set
    When the user says "<set a timer named timer for unspecified duration>"
    Then "mycroft-timer" should reply with dialog from "ask-how-long.dialog"
    And the user replies with "5 minutes"
    And "mycroft-timer" should reply with dialog from "started-timer-named.dialog"

    Examples: start a named timer for an unspecified duration
      | set a timer named timer for unspecified duration |
      | start a timer named pasta |
      | set a timer for pasta |
      | set a timer named pasta |
      | start a timer for pasta |
