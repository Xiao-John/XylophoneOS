// SPDX-License-Identifier: Apache-2.0
import QtQuick

Window {
    x: 32
    y: 40
    width: 260
    height: 160
    visible: true
    color: "#183c38"

    Text {
        anchors.centerIn: parent
        text: "Qt Quick on XOS"
        color: "#ffffff"
        font.family: "DejaVu Sans"
        font.pixelSize: 20
    }

    Timer {
        interval: 2500
        running: true
        onTriggered: Qt.quit()
    }
}
