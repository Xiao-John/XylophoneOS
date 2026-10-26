// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <unistd.h>
#include <errno.h>
#include <xos/text.hpp>

// Canonical serial input owned by this shell; no host termios emulation.
extern "C" ssize_t xos_shell_read(int fd, void* output, size_t count) {
    if (fd != 0 || !isatty(fd)) { return read(fd, output, count); }
    static char line[2048];
    static size_t length, offset;
    static bool last_cr;
    if (!count) { return 0; }
    if (offset == length) {
        length = offset = 0;
        for (;;) {
            char ch;
            const auto got = read(fd, &ch, 1);
            if (got < 0) {
                if (errno == EWOULDBLOCK || errno == EAGAIN || errno == EINTR) {
                    xos::sdk::yield();
                    continue;
                }
                return -1;
            }
            if (!got) { xos::sdk::yield(); continue; }
            if (ch == '\n' && last_cr) { last_cr = false; continue; }
            last_cr = ch == '\r';
            if (ch == 4 && !length) { return 0; }
            if (ch == '\r' || ch == '\n') {
                if (!xos::text::valid(line, length)) {
                    (void)write(1, "\ndash: invalid UTF-8 input\n", 27);
                    length = offset = 0;
                    continue;
                }
                line[length++] = '\n'; (void)write(1, "\n", 1); break;
            }
            if (ch == 8 || ch == 127) {
                if (length) {
                    const auto erased = xos::text::erase_last(line, length);
                    length = erased.size;
                    for (xos::u32 i = 0; i < erased.columns; ++i) { (void)write(1, "\b \b", 3); }
                }
            } else if (ch == '\t' || (ch >= 32 && ch <= 126) ||
                       static_cast<unsigned char>(ch) >= 0x80) {
                if (length + 1 >= sizeof(line)) {
                    // Reject the entire line, never execute a truncated prefix.
                    do {
                        if (read(fd, &ch, 1) <= 0) { xos::sdk::yield(); }
                    } while (ch != '\r' && ch != '\n');
                    length = 0; errno = E2BIG; return -1;
                }
                line[length++] = ch; (void)write(1, &ch, 1);
            }
        }
    }
    size_t used = length - offset;
    if (used > count) { used = count; }
    for (size_t i = 0; i < used; ++i) { static_cast<char*>(output)[i] = line[offset++]; }
    return static_cast<ssize_t>(used);
}

// Private orchestration API. Child cancellation is limited to direct children.
extern "C" int xos_shell_foreground(const int* children, unsigned count, int active) {
    if (count > xos::process_pipeline_max) { return -1; }
    xos::process_foreground request{1, sizeof(request), count, 0, {}};
    for (unsigned i = 0; i < count; ++i) { request.pids[i] = static_cast<xos::u64>(children[i]); }
    return static_cast<int>(xos::sdk::syscall(xos::sys_process_foreground,
                                            reinterpret_cast<xos::u64>(&request), static_cast<xos::u64>(active)));
}
extern "C" void xos_shell_cancel(int child) {
    (void)xos::sdk::syscall(xos::sys_process_cancel, static_cast<xos::u64>(child));
}
