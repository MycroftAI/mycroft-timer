import QtQuick.Layouts 1.4
import QtQuick 2.4
import QtQuick.Controls 2.0
import QtGraphicalEffects 1.0
import QtQml.Models 2.12
import org.kde.kirigami 2.9 as Kirigami
import Mycroft 1.0 as Mycroft

Mycroft.CardDelegate {
    id: timerFrame
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0

    property bool horizontalMode: timerFrame.width > timerFrame.height ? 1 : 0
    property var timerData: sessionData.timer_data
    property var removeTimer: sessionData.remove_timer
    property bool cancelAllTimers: false
    property var previousTimer

    function calculateCellHeight(count){
        horizontalMode && count > 1 ? height / 2 : height || !horizontalMode && count > 1 ? height / 4 : height
        if(horizontalMode && count > 1) {
            return height / 2
        } else if(horizontalMode && count == 1){
            return height
        } else if(!horizontalMode && count > 1){
            if(count > 4){
                return height / 4
            } else {
                return height / count
            }
        } else if(!horizontalMode && count == 1){
            return height
        }
    }

    onTimerDataChanged: {
        if(previousTimer != sessionData.timer_data){
            timerModel.append(sessionData.timer_data)
            previousTimer = sessionData.timer_data
        }
    }

    onCancelAllTimersChanged: {
        if(sessionData.cancelAllTimers){
            timerModel.clear()
        }
    }

    onRemoveTimerChanged: {
        if(removeTimer != ""){
            for (var i = 0; i < timerModel.count; i++) {
                if (timerModel.get(i).timer_index == removeTimer.index && timerModel.get(i).timer_duration == removeTimer.duration){
                    timerModel.remove(i);
                    view.forceLayout()
                }
            }
        }
    }

    DelegateModel {
        id: visualModel
        model: ListModel {
            id: timerModel
        }

        delegate: Rectangle {
            width: view.cellWidth
            height: view.cellHeight
            color: "transparent"
            property var time_remaining_current
            property var time_duration_current
            property var time_remaining_negative: 0

            Component.onCompleted: {
                time_remaining_current = model.time_remaining
                time_duration_current = model.timer_duration
                countdownTimer.start()
            }

            Timer {
                id: countdownTimer
                interval: 1000
                repeat: true
                onTriggered: {
                    if (time_remaining_current > 0){
                        time_remaining_current = time_remaining_current - 1000
                        var seconds = (time_remaining_current / 1000).toFixed(0);
                        var minutes = Math.floor(seconds / 60);
                        minutes = (minutes >= 10) ? minutes : "0" + minutes;
                        var hours = "";
                        if (minutes > 59) {
                            hours = Math.floor(minutes / 60);
                            hours = (hours >= 10) ? hours : "0" + hours;
                            minutes = minutes - (hours * 60);
                            minutes = (minutes >= 10) ? minutes : "0" + minutes;
                        }

                        seconds = Math.floor(seconds % 60);
                        seconds = (seconds >= 10) ? seconds : "0" + seconds;
                        var percent_elapsed = (time_remaining_current / 1000) / time_duration_current;
                        if (hours != "") {
                            timeRemaining.text = hours + ":" + minutes + ":" + seconds
                        } else {
                            timeRemaining.text = minutes + ":" + seconds
                        }
                        progressbar.width = percent_elapsed * timerProgress.width
                    } else {
                        expireAnimation.running = true
                        time_remaining_negative = time_remaining_negative + 1000
                        var seconds = (time_remaining_negative / 1000).toFixed(0);
                        var minutes = Math.floor(seconds / 60);
                        minutes = (minutes >= 10) ? minutes : "0" + minutes;
                        var hours = "";
                        if (minutes > 59) {
                            hours = Math.floor(minutes / 60);
                            hours = (hours >= 10) ? hours : "0" + hours;
                            minutes = minutes - (hours * 60);
                            minutes = (minutes >= 10) ? minutes : "0" + minutes;
                        }

                        seconds = Math.floor(seconds % 60);
                        seconds = (seconds >= 10) ? seconds : "0" + seconds;
                        if (hours != "") {
                            timeRemaining.text = "-" + hours + ":" + minutes + ":" + seconds
                        } else {
                            timeRemaining.text = "-" + minutes + ":" + seconds
                        }
                    }
                }
            }

            Rectangle {
                id: timerBackground
                width: view.cellWidth - Kirigami.Units.gridUnit
                height: view.cellHeight - Kirigami.Units.gridUnit
                anchors.centerIn: parent
                color: "transparent"
                radius: 20
                z: 3
                
                Component.onCompleted: {
                    color = model.timer_color
                }
                
                Rectangle {
                    id: timerProgress
                    color: "transparent"
                    radius: timerBackground.radius
                    anchors.fill: parent
                    visible: true
                    layer.enabled: true
                    layer.effect: OpacityMask {
                        maskSource: Item {
                            width: timerProgress.width
                            height: timerProgress.height
                            Rectangle {
                                anchors.centerIn: parent
                                width: timerProgress.width
                                height: timerProgress.height
                                radius: timerBackground.radius
                            }
                        }
                    }
                    
                    Rectangle {
                        id: progressbar
                        height: Mycroft.Units.gridUnit * 2
                        radius: timerBackground.radius
                        anchors.bottom: parent.bottom
                        color: "#FD9E66"
                    }
                }

                /* Name of the timer */
                Label {
                    id: timerName
                    anchors.horizontalCenter: timerBackground.horizontalCenter
                    anchors.top: timerBackground.top
                    anchors.topMargin: Kirigami.Units.largeSpacing
                    color: "#2C3E50"
                    font.family: "Noto Sans"
                    horizontalAlignment: Text.AlignHCenter
                    width: timerBackground.width - (Kirigami.Units.largeSpacing + Kirigami.Units.smallSpacing)
                    height: parent.height * 0.35
                    font.pixelSize: parent.width * 0.15
                    font.weight: Font.Bold
                    maximumLineCount: 2
                    wrapMode: Text.WrapAnywhere
                    elide: Text.ElideRight
                    Component.onCompleted: {
                        text = model.timer_name
                    }
                }

                /* Time remaining on the timer */
                Label {
                    id: timeRemaining
                    anchors.horizontalCenter: timerBackground.horizontalCenter
                    anchors.top: timerName.bottom
                    horizontalAlignment: Text.AlignHCenter
                    width: timerBackground.width - Kirigami.Units.largeSpacing
                    color: "white"
                    font.family: "Noto Sans"
                    font.pixelSize: parent.width * 0.20
                    font.weight: Font.Bold

                    /* Flash the time remaining when the timer expires for a visual cue */
                    SequentialAnimation on opacity {
                        id: expireAnimation
                        running: false
                        loops: Animation.Infinite

                        onRunningChanged: {
                            if(running){
                                triggerGuiEvent("skill.mycrofttimer.expiredtimer", {"index": model.timer_index, "name": model.timer_name, "duration": model.timer_duration, "ordinal": model.timer_ordinal, "announced": model.timer_announced})
                            }
                        }

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
        }
    }

    GridView {
        id: view
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width - Kirigami.Units.gridUnit * 2
        height: parent.height
        model: visualModel
        cellWidth: horizontalMode && count > 1 ? width / 2 : width
        cellHeight: {
            if(horizontalMode && count >= 3) {
                return view.height / 2
            } else if(horizontalMode && count <= 2){
                return view.height
            } else if(!horizontalMode && count > 1){
                if(count > 4){
                    return view.height / 4
                } else {
                    return view.height / count
                }
            } else if(!horizontalMode && count == 1){
                return view.height
            }
        }
    }
}
