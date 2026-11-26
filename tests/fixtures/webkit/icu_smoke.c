// SPDX-License-Identifier: Apache-2.0
#include <stdio.h>
#include <string.h>
#include <unicode/ubrk.h>
#include <unicode/ucol.h>
#include <unicode/unorm2.h>
#include <unicode/ustring.h>

int main(void)
{
    UErrorCode status = U_ZERO_ERROR;
    const UChar decomposed[] = {0x0065, 0x0301};
    UChar normalized[8];
    const UNormalizer2 *nfc = unorm2_getNFCInstance(&status);
    if (U_FAILURE(status) || nfc == NULL
        || unorm2_normalize(nfc, decomposed, 2, normalized, 8, &status) != 1
        || U_FAILURE(status) || normalized[0] != 0x00e9)
        return 1;

    const UChar word[] = {0x0053, 0x0074, 0x0072, 0x0061, 0x00df, 0x0065};
    UChar uppercase[16];
    char utf8[16];
    int32_t length = u_strToUpper(uppercase, 16, word, 6, "de", &status);
    if (U_FAILURE(status) || length != 7)
        return 2;
    u_strToUTF8(utf8, sizeof utf8, NULL, uppercase, length, &status);
    if (U_FAILURE(status) || strcmp(utf8, "STRASSE") != 0)
        return 3;

    const UChar two_words[] = {0x0061, 0x0020, 0x0062};
    UBreakIterator *words = ubrk_open(UBRK_WORD, "en", two_words, 3, &status);
    if (U_FAILURE(status) || words == NULL)
        return 4;
    const int boundaries_ok = ubrk_first(words) == 0 && ubrk_next(words) == 1
        && ubrk_next(words) == 2 && ubrk_next(words) == 3 && ubrk_next(words) == UBRK_DONE;
    ubrk_close(words);
    if (!boundaries_ok)
        return 5;

    UCollator *collator = ucol_open("de", &status);
    if (U_FAILURE(status) || collator == NULL)
        return 6;
    const UCollationResult ordering = ucol_strcoll(collator, two_words, 1, two_words + 2, 1);
    ucol_close(collator);
    if (ordering != UCOL_LESS)
        return 7;

    puts("ICU_SMOKE_OK");
    return 0;
}
