// SPDX-License-Identifier: Apache-2.0
#define _XOPEN_SOURCE 700
#include <locale.h>
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
    return 0;
}
