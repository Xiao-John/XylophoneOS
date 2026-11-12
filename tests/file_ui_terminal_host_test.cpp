// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <cstring>
#include <string>

#include "../src/user/services/file_ui.cpp"

namespace {
std::string input, saved, output;
size_t cursor, fail_at;
unsigned reads, recoveries, saves, failed_recoveries;
bool terminal_failed, failure_injected;
struct endless_read {};
}

namespace xos::sdk {
i64 syscall(u64 number, u64, u64 second, u64 third) {
    if (number == sys_handle_write) {
        output.append(reinterpret_cast<const char*>(second), static_cast<size_t>(third));
        return static_cast<i64>(third);
    }
    if (number == sys_handle_read) {
        if (++reads > 200) throw endless_read{};
        if (!failure_injected && cursor == fail_at) {
            terminal_failed = failure_injected = true;
        }
        if (terminal_failed) return process_error_state;
        if (cursor == input.size()) return 0;
        *reinterpret_cast<char*>(second) = input[cursor++];
        return 1;
    }
    return 0;
}
}

namespace xos::user::shell_terminal {
bool needs_recovery() { return terminal_failed; }
i64 recover(const char*) {
    ++recoveries;
    if (recoveries <= failed_recoveries) return process_error_would_block;
    terminal_failed = false;
    return 57;
}
}

namespace xos::file {
i64 client::read_all(const char*, void* data, u32, u32& length) {
    std::memcpy(data, "kept\n", 5);
    length = 5;
    return 0;
}
i64 client::replace(const char*, const void* data, u32 length) {
    saved.assign(static_cast<const char*>(data), length);
    ++saves;
    return 0;
}
}

int main() {
    const char* before_failure[] = {"added\npartial", ":r 1\nreplacement", ":i 1\ninsertion"};
    unsigned failures = 0;
    for (unsigned test = 0; test < 3; ++test) {
        input = before_failure[test];
        fail_at = input.size();
        input += ":wq\n";
        saved.clear(); output.clear(); cursor = 0;
        reads = recoveries = saves = 0;
        terminal_failed = failure_injected = false;
        failed_recoveries = test == 2 ? 2 : 0;
        bool passed = false;
        try {
            xos::ui::edit("/document.txt");
            passed = saved == (test == 0 ? "kept\nadded\n" : "kept\n") && saves == 1 &&
                     recoveries == failed_recoveries + 1 &&
                     output.find("buffer retained") != std::string::npos;
        } catch (const endless_read&) {}
        std::printf("editor recovery case %u: %s\n", test, passed ? "ok" : "FAIL");
        if (!passed) ++failures;
    }
    if (failures != 0) return 1;
    std::puts("FILE_UI_TERMINAL_CASES_PASSED=3");
    return 0;
}
