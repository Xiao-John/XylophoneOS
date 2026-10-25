// SPDX-License-Identifier: Apache-2.0
// XOS canonical readline shim for Open Adventure (no libedit).
#include <xos/sdk.hpp>
#include <stdlib.h>
#include <string.h>

extern "C" char* readline(const char* prompt) {
    if (prompt != nullptr && prompt[0] != '\0') {
        (void)xos::sdk::write(1, prompt, strlen(prompt));
    }
    char* buffer = static_cast<char*>(malloc(1025));
    if (buffer == nullptr) { return nullptr; }
    xos::u32 used = 0;
    for (;;) {
        char byte = 0;
        const xos::i64 got = xos::sdk::read(0, &byte, 1);
        if (got == xos::process_error_would_block || got == 0) {
            xos::sdk::yield();
            continue;
        }
        if (got < 0) {
            free(buffer);
            return nullptr;
        }
        if (byte == '\r' || byte == '\n') {
            (void)xos::sdk::write(1, "\n", 1);
            break;
        }
        if (byte == '\b' || byte == 127) {
            if (used > 0) {
                --used;
                (void)xos::sdk::write(1, "\b \b", 3);
            }
            continue;
        }
        if (used + 1 < 1025) {
            buffer[used++] = byte;
            (void)xos::sdk::write(1, &byte, 1);
        }
    }
    buffer[used] = '\0';
    return buffer;
}

extern "C" void add_history(const char*) {}
