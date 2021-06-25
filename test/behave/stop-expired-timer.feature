Feature: Stop an expired timer
  After a timer expires, a beeping alarm is played.  Stop the beeping and cancel the
  expired timer.

  Scenario Outline: stop an expired timer from beeping
    Given an english speaking user
    And no timers are previously set
    And a timer is expired
    When the user says "<stop timer>"
    Then "mycroft-timer" should stop beeping

    Examples: stop timer
      | stop timer |
      | stop timer |
      | stop |
      | cancel |
      | end timer |
      | turn it off |
      | silence |
      | shut up |
      | cancel all timers |
      | cancel the timers |
      | cancel timers |
      | I got it |
      | mute |
      | disable |
      | that's enough |
