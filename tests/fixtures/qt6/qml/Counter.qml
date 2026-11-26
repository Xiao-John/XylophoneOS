// SPDX-License-Identifier: Apache-2.0
import QtQml

QtObject {
    property int seed: 6
    readonly property int result: transform(seed)

    function transform(value: int): int {
        return value * (value + 1)
    }
}
