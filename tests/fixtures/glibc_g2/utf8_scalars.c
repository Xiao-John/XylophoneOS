// SPDX-License-Identifier: Apache-2.0
#define _XOPEN_SOURCE 700

#include <errno.h>
#include <iconv.h>
#include <limits.h>
#include <locale.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static int reject_input(const char *input, size_t length)
{
    mbstate_t state = {0};
    wchar_t result = L'X';
    errno = 0;
    return mbrtowc(&result, input, length, &state) == (size_t)-1
        && errno == EILSEQ && result == L'X';
}

static int reject_split(const char *lead, const char *trail)
{
    mbstate_t state = {0};
    if (mbrlen(lead, 1, &state) != (size_t)-2 || mbsinit(&state))
        return 0;
    errno = 0;
    if (mbrlen(trail, 1, &state) != (size_t)-1 || errno != EILSEQ)
        return 0;
    /* The caller must reinitialize the conversion state after EILSEQ. */
    memset(&state, 0, sizeof(state));
    return mbrlen("A", 1, &state) == 1 && mbsinit(&state);
}

static int reject_output(wchar_t value)
{
    mbstate_t state = {0};
    char output[MB_LEN_MAX];
    memset(output, 'X', sizeof(output));
    errno = 0;
    return wcrtomb(output, value, &state) == (size_t)-1
        && errno == EILSEQ && output[0] == 'X';
}

static int roundtrip(wchar_t value, const char *encoded, size_t length)
{
    mbstate_t state = {0};
    wchar_t decoded = L'X';
    for (size_t i = 0; i + 1 < length; ++i)
        if (mbrtowc(&decoded, encoded + i, 1, &state) != (size_t)-2
                || decoded != L'X' || mbsinit(&state))
            return 0;
    if (mbrtowc(&decoded, encoded + length - 1, 1, &state) != 1
            || decoded != value || !mbsinit(&state))
        return 0;
    char output[MB_LEN_MAX];
    return wcrtomb(output, value, &state) == length && mbsinit(&state)
        && memcmp(encoded, output, length) == 0;
}

static int verify_iconv(const char *to, const char *from,
                        void *input, size_t length, const void *expected, size_t expected_length)
{
    iconv_t conversion = iconv_open(to, from);
    if (conversion == (iconv_t)-1)
        return 0;
    char *source = input;
    union { wchar_t alignment; char bytes[16]; } buffer;
    char *output = buffer.bytes;
    size_t space = sizeof(buffer.bytes);
    errno = 0;
    size_t result = iconv(conversion, &source, &length, &output, &space);
    int passed;
    if (expected)
        passed = result == 0 && length == 0 && output - buffer.bytes == (ptrdiff_t)expected_length
            && memcmp(buffer.bytes, expected, expected_length) == 0;
    else
        passed = result == (size_t)-1 && errno == EILSEQ && source == input
            && output == buffer.bytes;
    return iconv_close(conversion) == 0 && passed;
}

int main(void)
{
    if (!setlocale(LC_CTYPE, "C.UTF-8"))
        return 1;
    const struct { wchar_t value; const char *bytes; size_t length; } valid[] = {
        {0x007f, "\x7f", 1},
        {0x0080, "\xc2\x80", 2},
        {0x07ff, "\xdf\xbf", 2},
        {0x0800, "\xe0\xa0\x80", 3},
        {0xd7ff, "\xed\x9f\xbf", 3},
        {0xe000, "\xee\x80\x80", 3},
        {0xffff, "\xef\xbf\xbf", 3},
        {0x10000, "\xf0\x90\x80\x80", 4},
        {0x10ffff, "\xf4\x8f\xbf\xbf", 4},
        {0x0301, "\xcc\x81", 2},
        {0x4e2d, "\xe4\xb8\xad", 3},
    };
    for (size_t i = 0; i < sizeof(valid) / sizeof(valid[0]); ++i)
        if (!roundtrip(valid[i].value, valid[i].bytes, valid[i].length))
            return 2;
    if (wcwidth(0x0301) != 0 || wcwidth(0x4e2d) != 2)
        return 3;

    if (!reject_input("\xc0", 1)
            || !reject_input("\xe0\x9f", 2)
            || !reject_input("\xed\xa0", 2)
            || !reject_input("\xf0\x8f", 2)
            || !reject_input("\xf4\x90\x80\x80", 4)
            || !reject_input("\xf5", 1)
            || !reject_input("\xf8\x88\x80\x80\x80", 5)
            || !reject_input("\xfc\x84\x80\x80\x80\x80", 6))
        return 4;
    if (!reject_split("\xe0", "\x9f")
            || !reject_split("\xed", "\xa0")
            || !reject_split("\xf0", "\x8f")
            || !reject_split("\xf4", "\x90")
            || !reject_split("\xf4", "A"))
        return 5;
    if (!reject_output(0xd800) || !reject_output(0xdfff)
            || !reject_output(0x110000) || !reject_output(0x200000)
            || !reject_output(0x4000000))
        return 6;

    wchar_t max = 0x10ffff, above = 0x110000;
    char max_bytes[] = "\xf4\x8f\xbf\xbf";
    char above_bytes[] = "\xf4\x90\x80\x80";
    const uint8_t ucs4_le[] = {0x00, 0x00, 0x11, 0x00};
    if (!verify_iconv("WCHAR_T", "UTF-8", max_bytes, 4, &max, sizeof(max))
            || !verify_iconv("UTF-8", "WCHAR_T", &max, sizeof(max), max_bytes, 4)
            || !verify_iconv("WCHAR_T", "UTF-8", above_bytes, 4, NULL, 0)
            || !verify_iconv("UTF-8", "WCHAR_T", &above, sizeof(above), NULL, 0)
            || !verify_iconv("UCS-4LE", "WCHAR_T", &above, sizeof(above), ucs4_le, sizeof(ucs4_le)))
        return 7;

    if (!setlocale(LC_CTYPE, "C") || !roundtrip(L'A', "A", 1)
            || !reject_input("\xc2\x80", 2) || !reject_output(0x0301))
        return 8;
    puts("XOS_UTF8_SCALARS_PASS");
    return 0;
}
