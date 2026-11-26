/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <string.h>
#include <zlib.h>

int main(void)
{
    static const char payload[] = "XOS bounded = 3149\n";
    gzFile output = gzopen("/out/zlib-c.gz", "wb");
    if (!output)
        return 2;
    int written = gzprintf(output, "%s bounded = %d\n", "XOS", 3149);
    if (gzclose(output) != Z_OK || written != sizeof(payload) - 1)
        return 3;

    gzFile input = gzopen("/out/zlib-c.gz", "rb");
    if (!input)
        return 4;
    char buffer[sizeof(payload)] = {0};
    int received = gzread(input, buffer, sizeof(buffer));
    if (gzclose(input) != Z_OK || received != sizeof(payload) - 1 || strcmp(buffer, payload))
        return 5;
    if (strcmp(zlibVersion(), "1.3.2"))
        return 6;
    puts("XOS_TARGET_LIBZ_GZPRINTF_GZREAD_OK 1.3.2");
    return 0;
}
