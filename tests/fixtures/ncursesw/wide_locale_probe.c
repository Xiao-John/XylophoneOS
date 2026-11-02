// SPDX-License-Identifier: Apache-2.0
#define _XOPEN_SOURCE 700
#include <locale.h>
#include <errno.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>
#include <stdint.h>

struct xos_tty_marker { uint64_t magic; uint32_t version, size; };
__attribute__((section(".xos.tty"), used)) static const struct xos_tty_marker marker = {
    0x31595454534f5858ULL, 1, sizeof(struct xos_tty_marker)
};

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
    if (wcwidth(0x05b0) != 0 || wcwidth(0x231a) != 2) return 20;
    const char *invalid[] = {"\xc0\x80", "\xed\xa0\x80", "\xed\xbf\xbf", "\xf4\x90\x80\x80"};
    const size_t invalid_length[] = {2, 3, 3, 4};
    for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i) {
        memset(&state, 0, sizeof(state));
        errno = 0;
        if (mbrtowc(&character, invalid[i], invalid_length[i], &state) != (size_t)-1 || errno != EILSEQ)
            return 10 + (int)i;
    }
    memset(&state, 0, sizeof(state));
    if (mbrtowc(&character, "\xed", 1, &state) != (size_t)-2) return 14;
    errno = 0;
    if (mbrtowc(&character, "\xa0", 1, &state) != (size_t)-1 || errno != EILSEQ) return 15;
    memset(&state, 0, sizeof(state));
    errno = 0;
    if (wcrtomb(output, (wchar_t)0xd800, &state) != (size_t)-1 || errno != EILSEQ) return 16;
    memset(&state, 0, sizeof(state));
    errno = 0;
    if (wcrtomb(output, (wchar_t)0xdfff, &state) != (size_t)-1 || errno != EILSEQ) return 17;
    memset(&state, 0, sizeof(state));
    if (mbrtowc(&character, "\xf0\x9f\x98\x80", 4, &state) != 4 || character != 0x1f600) return 18;
    if (wcrtomb(output, character, &state) != 4 || memcmp(output, "\xf0\x9f\x98\x80", 4) != 0) return 19;
    return 0;
}
