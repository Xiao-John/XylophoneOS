// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 2) return 30;
    std::vector<int> values{2, 3, 5};
    std::thread worker([&] { values[1] = 7; });
    worker.join();
    if (values[0] + values[1] + values[2] != 14) return 31;
    bool caught = false;
    try { throw std::runtime_error("rollback"); }
    catch (const std::runtime_error& error) { caught = !std::strcmp(error.what(), "rollback"); }
    if (!caught) return 32;
    char line[64];
    const int length = std::snprintf(line, sizeof(line), "cpp-%s\n", argv[1]);
    if (length <= 0 || static_cast<size_t>(length) >= sizeof(line)) return 33;
    const int file = open("/state/user.txt", O_WRONLY | O_APPEND);
    if (file < 0) return 34;
    if (write(file, line, static_cast<size_t>(length)) != length) { close(file); return 35; }
    if (close(file)) return 36;
    std::printf("P0_R1_GLIBC_CPP_OK %s vector=1 thread=1 exception=1\n", argv[1]);
    return 0;
}
