// SPDX-License-Identifier: Apache-2.0
#include <errno.h>
#include <stdio.h>
#include <unistd.h>

int main(int argc, char** argv) {
    unsigned char bytes[256]{};
    const bool unsupported = argc > 1 && argv[1][0] == 'u';
    if (unsupported) {
        errno = 0;
        if (getentropy(bytes, 32) != -1 || errno != ENOSYS) {
            puts("PY3_B1_GETENTROPY_UNSUPPORTED_FAILED");
            return 1;
        }
        puts("PY3_B1_GETENTROPY_UNSUPPORTED_ENOSYS_OK");
        return 0;
    }

    if (getentropy(nullptr, 0) != 0 || getentropy(bytes, sizeof(bytes)) != 0) {
        puts("PY3_B1_GETENTROPY_FILL_FAILED");
        return 2;
    }
    errno = 0;
    if (getentropy(bytes, sizeof(bytes) + 1) != -1 || errno != EINVAL) {
        puts("PY3_B1_GETENTROPY_BOUND_FAILED");
        return 3;
    }
    errno = 0;
    if (getentropy(nullptr, 1) != -1 || errno != EFAULT) {
        puts("PY3_B1_GETENTROPY_ADDRESS_FAILED");
        return 4;
    }
    puts("PY3_B1_GETENTROPY_CONTRACT_OK");
    return 0;
}
