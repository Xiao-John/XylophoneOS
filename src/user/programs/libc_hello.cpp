#include <xos/sdk.hpp>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" int xos_user_main(const xos::startup_info*) {
    char* text = static_cast<char*>(malloc(32));
    if (text == nullptr) { printf("malloc failed\n"); return 1; }
    strcpy(text, "malloc+printf");
    printf("libc says: %s %d %x\n", text, 42, 0xbeef);
    free(text);
    puts("second line");
    fflush(stdout);
    return 7;
}
