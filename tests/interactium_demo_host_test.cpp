// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <cstring>

#include "../src/user/programs/interactium_demo.cpp"

namespace {
enum class input_case { unavailable, idle_then_quit, wait_failure, redraw_failure };
input_case scenario;
display_request pending_request;
unsigned input_calls, wait_calls, close_calls, present_calls;
struct endless_input {};
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64) {
    if (number == sys_display) {
        const auto action = static_cast<display_action>(first);
        if (action == display_action::connect) {
            *reinterpret_cast<display_channel*>(second) = {101, 102, 10};
        } else if (action == display_action::disconnect) {
            ++close_calls;
        } else if (action == display_action::wait && second == 0) {
            ++wait_calls;
            if (scenario == input_case::wait_failure) return display_unavailable;
        }
        return 0;
    }
    if (number == 4) {
        pending_request = *reinterpret_cast<const display_request*>(second);
        return 0;
    }
    if (number == 5) {
        auto& reply = *reinterpret_cast<display_reply*>(second);
        reply = {};
        if (pending_request.operation == display_operation::mode) {
            reply.mode = {1, sizeof(display_mode), 800, 600, 3200, display_xrgb8888, 1920000};
        } else if (pending_request.operation == display_operation::present) {
            if (++present_calls > 1 && scenario == input_case::redraw_failure)
                reply.result = display_unavailable;
        } else if (pending_request.operation == display_operation::input) {
            if (++input_calls > 2) throw endless_input{};
            if (scenario == input_case::unavailable) reply.result = display_unavailable;
            else if (scenario == input_case::wait_failure ||
                     (scenario == input_case::idle_then_quit && input_calls == 1))
                reply.result = display_again;
            else if (scenario == input_case::redraw_failure)
                reply.event = {1, 0, 3, 0, 0, 0, 0, 0, 40, 40, 0, 0};
            else reply.event = {1, 0, 1, 16, 0, 0, 0, 0, 0, 0, 0, 0};
        }
        return sizeof(reply);
    }
    return process_error_invalid;
}
void print(const char*, u32) {}
}

int main() {
    unsigned failures = 0;
    const input_case cases[] = {input_case::unavailable, input_case::idle_then_quit,
                               input_case::wait_failure, input_case::redraw_failure};
    for (auto item : cases) {
        scenario = item;
        input_calls = wait_calls = close_calls = present_calls = 0;
        bool passed = false;
        try {
            const int result = xos_user_main(nullptr);
            const bool normal = item == input_case::idle_then_quit;
            const unsigned expected_waits = normal || item == input_case::wait_failure ? 1 : 0;
            passed = (normal ? result == 0 : result != 0) && close_calls == 1 &&
                     wait_calls == expected_waits;
        } catch (const endless_input&) {}
        std::printf("demo input case %u: %s\n", static_cast<unsigned>(item), passed ? "ok" : "FAIL");
        if (!passed) ++failures;
    }
    if (failures != 0) return 1;
    std::puts("INTERACTIUM_DEMO_CASES_PASSED=4");
    return 0;
}
