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

int main(void) {
    if (!setlocale(LC_CTYPE, "C.UTF-8")) return 1;
    if (!initscr()) return 2;
    int result = 0;
    if (cbreak() == ERR || noecho() == ERR || keypad(stdscr, TRUE) == ERR) result = 3;
    if (!result && (!has_colors() || start_color() == ERR || init_pair(1, COLOR_RED, COLOR_BLACK) == ERR)) result = 4;
    cchar_t character;
    const wchar_t text[] = {0x4e2d, 0};
    WINDOW* pane = result ? 0 : newwin(3, 20, 1, 1);
    if (!result && (!pane || setcchar(&character, text, A_NORMAL, 1, 0) == ERR ||
                    mvwadd_wch(pane, 1, 1, &character) == ERR || wrefresh(pane) == ERR)) result = 5;
    const char ready[] = "W2_INPUT_READY\n";
    for (size_t offset = 0; !result && offset < sizeof(ready) - 1;) {
        const ssize_t written = write(2, ready + offset, sizeof(ready) - 1 - offset);
        if (written <= 0) result = 10;
        else offset += (size_t)written;
    }
    wint_t key = 0;
    if (!result && (wget_wch(stdscr, &key) != KEY_CODE_YES || key != KEY_LEFT)) result = 6;
    if (!result && (wget_wch(stdscr, &key) != OK || key != 0x4e2d)) result = 8;
    if (pane && delwin(pane) == ERR && !result) result = 9;
    if (endwin() == ERR && !result) result = 7;
    return result;
}
