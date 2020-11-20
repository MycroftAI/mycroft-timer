import QtQuick.Layouts 1.4
import QtQuick 2.4
import QtQuick.Controls 2.0

import Mycroft 1.0 as Mycroft

Mycroft.ProportionalDelegate {
    id: timerFrame

    /* Colored background for the timer name and time remaining */
    Rectangle {
        id: timerBackground
        Layout.alignment: Qt.AlignHCenter | Qt.AlignTop
        color: sessionData.timer_color
        height: 340
        radius: 30
        width: 450

        /* Name of the timer */
        Label {
            id: timerName
            anchors.horizontalCenter: timerBackground.horizontalCenter
            anchors.top: timerBackground.top
            anchors.topMargin: 36
            color: "#2C3E50"
            font.family: "Noto Sans"
            font.pixelSize: 60
            font.weight: Font.Bold
            text: sessionData.timer_name
        }

        /* Time remaining on the timer */
        Label {
            id: timeRemaining
            anchors.horizontalCenter: timerBackground.horizontalCenter
            anchors.top: timerName.bottom
            anchors.topMargin: 60
            color: "white"
            font.family: "Noto Sans"
            font.pixelSize: 80
            font.weight: Font.Bold
            text: sessionData.time_remaining

            /* Flash the time remaining when the timer expires for a visual cue */
            SequentialAnimation on opacity {
                running: sessionData.timer_expired
                loops: Animation.Infinite

                PropertyAnimation {
                    from: 1;
                    to: 0;
                    duration: 500
                }

                PropertyAnimation {
                    from: 0;
                    to: 1;
                    duration: 500
                }
            }
        }
    }

    /* Progress bar for the timer */
    Rectangle {
        id: timerProgress
        Layout.alignment: Qt.AlignHCenter | Qt.AlignBottom
        width: 450
        height: 20
        color: sessionData.timer_color
        radius: 10
        Rectangle {
            width: sessionData.percent_elapsed * parent.width
            height: 20
            radius: 10
            color: "#FD9E66"
        }
    }
}
