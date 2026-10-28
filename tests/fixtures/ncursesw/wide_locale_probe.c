// SPDX-License-Identifier: Apache-2.0
#define _XOPEN_SOURCE 700
#include <locale.h>
#include <errno.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>

/* This consumer must run on the target before its result is evidence. */
int main(void) {
    mbstate_t state;
    wchar_t character = 0;
    char output[8];
    memset(&state, 0, sizeof(state));
    if (!setlocale(LC_CTYPE, "C.UTF-8")) return 1;
    if (mbrtowc(&character, "\xe4\xb8\xad", 3, &state) != 3) return 2;
    if (wcrtomb(output, character, &state) != 3) return 3;
    if (memcmp(output, "\xe4\xb8\xad", 3) != 0) return 4;
    if (wcwidth(character) != 2 || !iswprint(character)) return 5;
    memset(&state, 0, sizeof(state));
    if (mbrtowc(&character, "\xe4", 1, &state) != (size_t)-2) return 6;
    if (mbrtowc(&character, "\xb8\xad", 2, &state) != 2 || character != 0x4e2d) return 7;
    memset(&state, 0, sizeof(state));
    errno = 0;
    if (mbrtowc(&character, "\xff", 1, &state) != (size_t)-1 || errno != EILSEQ) return 8;
    if (wcwidth(L'A') != 1 || wcwidth(0x0301) != 0 || wcwidth(0x4e2d) != 2) return 9;
    return 0;
}
