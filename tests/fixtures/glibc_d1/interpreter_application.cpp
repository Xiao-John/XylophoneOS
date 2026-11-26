// SPDX-License-Identifier: Apache-2.0
#include <string.h>
#include <unistd.h>

namespace {
thread_local volatile int value = 11;

struct lifetime {
    lifetime() { value = value + 6; }
    ~lifetime() {
        static constexpr char message[] = "D1_DYNAMIC_CPP_FINI\n";
        if (value == 23) (void)write(STDOUT_FILENO, message, sizeof(message) - 1);
    }
};

lifetime application;
}

int main(int argc, char** argv) {
    if (argc != 2 || strcmp(argv[1], "ordinary") != 0 || value != 17) return 41;
    value = 23;
    static constexpr char message[] = "D1_DYNAMIC_CPP_OK ctor=1 tls=1\n";
    return write(STDOUT_FILENO, message, sizeof(message) - 1) == sizeof(message) - 1 ? 0 : 42;
}
