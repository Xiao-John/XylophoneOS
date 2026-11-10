// SPDX-License-Identifier: Apache-2.0
// Host test for audio_tone argument parsing: a malformed or overflowing
// frequency must exit 2 (parameter error) instead of silently becoming a
// rest; a literal 0 frequency must stay a rest.
#include <cstdio>

#include "../src/user/programs/audio_tone.cpp"

namespace {
int play_calls = 0;
}

namespace xos::sdk {
// Host stubs: audio_tone only needs the monotonic clock and a sleep.
i64 syscall(u64 number, u64, u64, u64) {
    if (number == sys_clock_monotonic) return 1000000000;
    return 0;
}
}

namespace xos::user::pc_speaker {
i64 play(u32) {
    ++play_calls;
    return 0;
}
}

namespace {
int run_case(const char* frequency, const char* duration, xos::u32 argc) {
    const char* argv[] = {"audio_tone", frequency, duration};
    xos::startup_info info{};
    info.argc = argc;
    info.argv = reinterpret_cast<xos::u64>(argv);
    return xos_user_main(&info);
}
}

int main() {
    struct test_case {
        const char* label;
        const char* frequency;
        const char* duration;
        xos::u32 argc;
        int expected;
    };
    const test_case cases[] = {
        {"malformed frequency", "abc", "100", 3, 2},
        {"overflowing frequency", "99999999999999999999", "100", 3, 2},
        {"trailing junk frequency", "440x", "100", 3, 2},
        {"empty frequency", "", "100", 3, 2},
        {"malformed duration", "440", "abc", 3, 2},
        {"duration below minimum", "440", "5", 3, 2},
        {"duration above maximum", "440", "99999", 3, 2},
        {"missing argument", "440", "100", 2, 2},
        {"literal zero frequency rest", "0", "100", 3, 0},
        {"valid tone", "440", "100", 3, 0},
    };
    int failures = 0;
    for (const auto& item : cases) {
        const int result = run_case(item.frequency, item.duration, item.argc);
        std::printf("%-26s audio_tone '%s' '%s' argc=%u -> %d (expected %d)%s\n",
                    item.label, item.frequency, item.duration, item.argc, result,
                    item.expected, result == item.expected ? "" : "  FAIL");
        if (result != item.expected) ++failures;
    }
    std::printf("pc_speaker play calls=%d (expected 1)\n", play_calls);
    if (play_calls != 1) ++failures;
    if (failures != 0) {
        std::printf("audio_tone_args_test: %d failure(s)\n", failures);
        return 1;
    }
    std::printf("audio_tone_args_test: ok\n");
    return 0;
}
