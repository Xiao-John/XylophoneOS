/* SPDX-License-Identifier: Apache-2.0 */
/* Minimal oniguruma self-test shipped with the package. */
#include <oniguruma.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    static const UChar pattern[] = "a(b+)c";
    static const UChar text[] = "xxabbbcyy";
    regex_t* regex = 0;
    OnigErrorInfo error;
    const int compiled = onig_new(&regex, pattern, pattern + sizeof(pattern) - 1,
                                  ONIG_OPTION_DEFAULT, ONIG_ENCODING_UTF8,
                                  ONIG_SYNTAX_DEFAULT, &error);
    if (compiled != ONIG_NORMAL) {
        printf("ONIG_COMPILE_FAILED %d\n", compiled);
        return 1;
    }
    OnigRegion* region = onig_region_new();
    const int found = onig_search(regex, text, text + sizeof(text) - 1,
                                  text, text + sizeof(text) - 1, region,
                                  ONIG_OPTION_NONE);
    printf("start=%d end=%d groups=%d\n", region->beg[0], region->end[0],
           region->num_regs);
    const int ok = found == 2 && region->beg[0] == 2 && region->end[0] == 7
        && region->num_regs == 2 && region->beg[1] == 3 && region->end[1] == 6;
    onig_region_free(region, 1);
    onig_free(regex);
    onig_end();
    printf(ok ? "ONIG_OK\n" : "ONIG_FAILED\n");
    return ok ? 0 : 1;
}
