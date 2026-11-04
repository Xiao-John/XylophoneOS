/* SPDX-License-Identifier: Apache-2.0 */
#define _XOPEN_SOURCE 700
#define _XOPEN_SOURCE_EXTENDED 1
#include <curses.h>
#include <locale.h>
#include <stdint.h>
#include <stdio.h>

struct xos_tty_marker { uint64_t magic; uint32_t version, size; };
__attribute__((section(".xos.tty"), used)) static const struct xos_tty_marker marker = {
    0x31595454534f5858ULL, 1, sizeof(struct xos_tty_marker)
};

int main(void) {
    if (!setlocale(LC_CTYPE, "C.UTF-8")) return 1;
    SCREEN* missing = newterm("xos-no-such-terminal", stdout, stdin);
    if (missing) { delscreen(missing); return 7; }
    SCREEN* screen = newterm("xterm", stdout, stdin);
    if (!screen) return 2;
    int rows = 0, columns = 0;
    getmaxyx(stdscr, rows, columns);
    int result = rows == 24 && columns == 80 ? 0 : 3;
    WINDOW* oversized = derwin(stdscr, rows + 1, columns, 0, 0);
    if (oversized) { delwin(oversized); if (!result) result = 8; }
    if ((wmove(stdscr, rows, 0) != ERR || wmove(stdscr, 0, columns) != ERR) && !result) result = 9;
    if (endwin() == ERR && !result) result = 4;
    if (refresh() == ERR && !result) result = 5;
    if (endwin() == ERR && !result) result = 6;
    delscreen(screen);
    return result;
}
