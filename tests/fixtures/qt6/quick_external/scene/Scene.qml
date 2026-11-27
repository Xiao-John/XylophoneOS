// SPDX-License-Identifier: Apache-2.0
import QtQuick

Rectangle {
    id: scene
    width: 360
    height: 230
    color: "#17354d"
    focus: true

    readonly property string palette_tag: palette.tag
    property bool selected: false
    property bool confirmed: false
    state: selected ? "active" : ""

    ScenePalette { id: palette }

    Text {
        x: 18
        y: 22
        color: "#ffffff"
        font.family: "DejaVu Sans"
        font.pixelSize: 29
        text: "XOS Qt Quick"
    }

    Rectangle {
        id: swatch
        x: 18
        y: 112
        width: 140
        height: 40
        color: palette.idle_color
    }

    states: State {
        name: "active"
        PropertyChanges {
            target: swatch
            color: palette.active_color
        }
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_A) {
            selected = true
            event.accepted = true
        } else if (event.key === Qt.Key_B && selected) {
            confirmed = true
            event.accepted = true
        }
    }
}
