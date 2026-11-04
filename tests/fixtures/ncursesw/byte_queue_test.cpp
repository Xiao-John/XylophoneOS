// SPDX-License-Identifier: Apache-2.0
#include <xos/byte_queue.hpp>

int main() {
    xos::byte_queue<3> queue;
    xos::u8 value = 0;
    if (queue.pop(value) || queue.peek(value) || queue.length() != 0 || queue.dropped() != 0) return 1;
    if (!queue.push(1) || !queue.push(2) || !queue.push(3)) return 2;
    if (queue.push(4) || queue.dropped() != 1 || queue.length() != 3 || !queue.peek(value) || value != 1) return 3;
    if (!queue.pop(value) || value != 1 || !queue.push(5)) return 4;
    if (!queue.pop(value) || value != 2 || !queue.pop(value) || value != 3) return 5;
    if (!queue.pop(value) || value != 5 || queue.pop(value) || queue.length() != 0) return 6;
    return 0;
}
