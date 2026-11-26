// SPDX-License-Identifier: Apache-2.0
import QtQuick

Rectangle {
    id: scene
    width: 360
    height: 230
    color: "#17354d"
    focus: true
    property int ticks: 0
    property int key_hits: 0
    property bool acknowledged: false

    Text {
        x: 18
        y: 22
        color: "#ffffff"
        font.family: "DejaVu Sans"
        font.pixelSize: 29
        text: "XOS Qt Quick"
    }

    Rectangle {
        x: 18 + (scene.ticks % 8) * 16
        y: 112
        width: 140
        height: 40
        color: scene.key_hits ? "#f0a945" : "#35c29d"
    }

    Timer {
        interval: 100
        repeat: true
        running: true
        onTriggered: scene.ticks += 1
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_A) {
            scene.key_hits += 1
            event.accepted = true
        } else if (event.key === Qt.Key_B && scene.key_hits > 0) {
            scene.acknowledged = true
            event.accepted = true
        }
    }
}
