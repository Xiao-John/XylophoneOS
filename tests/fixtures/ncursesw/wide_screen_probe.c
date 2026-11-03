/* SPDX-License-Identifier: Apache-2.0 */
#define _XOPEN_SOURCE 700
#define _XOPEN_SOURCE_EXTENDED 1
#include <curses.h>
#include <locale.h>
#include <stdint.h>
#include <wchar.h>
#include <unistd.h>

struct xos_tty_marker { uint64_t magic; uint32_t version, size; };
__attribute__((section(".xos.tty"), used)) static const struct xos_tty_marker marker = {
    0x31595454534f5858ULL, 1, sizeof(struct xos_tty_marker)
};

static int notify(const char *text, size_t length) {
    for (size_t offset = 0; offset < length;) {
        ssize_t count = write(2, text + offset, length - offset);
        if (count <= 0) return -1;
        offset += (size_t)count;
    }
    return 0;
}

int main(void) {
    if (!setlocale(LC_CTYPE, "C.UTF-8")) return 1;
    if (!initscr()) return 2;
    int result = 0;
    if (cbreak() == ERR || noecho() == ERR || keypad(stdscr, TRUE) == ERR) result = 3;
    if (!result && (!has_colors() || start_color() == ERR || init_pair(1, COLOR_RED, COLOR_BLACK) == ERR)) result = 4;
    cchar_t character;
    const wchar_t text[] = {0x4e2d, 0x0301, 0};
    WINDOW* pane = result ? 0 : newwin(3, 20, 1, 1);
    if (!result && (!pane || setcchar(&character, text, A_NORMAL, 1, 0) == ERR ||
                    mvwadd_wch(pane, 1, 1, &character) == ERR || wrefresh(pane) == ERR)) result = 5;
    if (!result && (wmove(pane, 3, 0) != ERR || wmove(pane, 0, 20) != ERR ||
                    mvwaddstr(pane, 0, 0, "W2_LOCAL_CELL") == ERR ||
                    wnoutrefresh(pane) == ERR || doupdate() == ERR)) result = 13;
    cchar_t readback;
    wchar_t readback_text[CCHARW_MAX];
    attr_t attributes = 0;
    short color = 0;
    if (!result && (mvwin_wch(pane, 1, 1, &readback) == ERR ||
                    getcchar(&readback, readback_text, &attributes, &color, 0) == ERR ||
                    readback_text[0] != 0x4e2d || readback_text[1] != 0x0301 || color != 1)) result = 14;
    wint_t key = 0;
    if (!result) {
        wtimeout(stdscr, 20);
        if (wget_wch(stdscr, &key) != ERR) result = 11;
        wtimeout(stdscr, -1);
    }
    const char ready[] = "W2_INPUT_READY\n";
    for (size_t offset = 0; !result && offset < sizeof(ready) - 1;) {
        const ssize_t written = write(2, ready + offset, sizeof(ready) - 1 - offset);
        if (written <= 0) result = 10;
        else offset += (size_t)written;
    }
    if (!result && (wget_wch(stdscr, &key) != KEY_CODE_YES || key != KEY_LEFT)) result = 6;
    const char utf8_ready[] = "W2_UTF8_READY\n";
    for (size_t offset = 0; !result && offset < sizeof(utf8_ready) - 1;) {
        const ssize_t written = write(2, utf8_ready + offset, sizeof(utf8_ready) - 1 - offset);
        if (written <= 0) result = 15;
        else offset += (size_t)written;
    }
    if (!result && (wget_wch(stdscr, &key) != OK || key != 0x4e2d)) result = 8;
    if (!result && (wget_wch(stdscr, &key) != KEY_CODE_YES || key != KEY_F(1))) result = 12;
    if (!result) {
        const char invalid_ready[] = "W2_INVALID_READY\n";
        const char recovery_ready[] = "W2_INVALID_RECOVERY_READY\n";
        wtimeout(stdscr, 1000);
        if (notify(invalid_ready, sizeof(invalid_ready) - 1) != 0 || wget_wch(stdscr, &key) != ERR)
            result = 16;
        if (!result && (notify(recovery_ready, sizeof(recovery_ready) - 1) != 0 ||
                        wget_wch(stdscr, &key) != OK || key != L'B')) result = 17;
        const char combining_ready[] = "W2_COMBINING_READY\n";
        if (!result && (notify(combining_ready, sizeof(combining_ready) - 1) != 0 ||
                        wget_wch(stdscr, &key) != OK || key != L'a' ||
                        wget_wch(stdscr, &key) != OK || key != 0x0301)) result = 18;
    }
    if (pane && delwin(pane) == ERR && !result) result = 9;
    if (endwin() == ERR && !result) result = 7;
    return result;
}
