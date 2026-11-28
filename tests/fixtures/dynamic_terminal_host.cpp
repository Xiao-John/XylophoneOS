// SPDX-License-Identifier: Apache-2.0
// Production preservation validation; only channel enumeration is modeled.
#include "../../src/user/loader/load.cpp"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

namespace model {
using namespace xos;
channel_info entries[5]{};
u32 entry_count, calls;
i64 trap_error;
void need(bool result, const char* label) {
    if (!result) { std::fprintf(stderr, "FAIL %s\n", label); std::abort(); }
}
void reset() {
    entries[0] = {1, sizeof(channel_info), 10, channel_send, 300, 100};
    entries[1] = {1, sizeof(channel_info), 11, channel_receive, 300, 100};
    // A fork child may have a different direct launch controller from the
    // terminal actor owner. The two relationships remain independent.
    entries[2] = {1, sizeof(channel_info), 20, channel_send, 200, 200};
    entries[3] = {1, sizeof(channel_info), 21, channel_receive, 200, 200};
    entries[4] = {}; entry_count = 4; calls = 0; trap_error = 0;
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64 action, u64 index, u64 output) {
    using namespace model;
    need(number == sys_channel && action == static_cast<u64>(channel_action::enumerate),
         "validation-has-no-side-effects");
    ++calls;
    if (trap_error) return trap_error;
    if (index >= entry_count) return thread_error_not_found;
    *reinterpret_cast<channel_info*>(output) = entries[index];
    return 0;
}
}

int main() {
    using namespace xos;
    using namespace model;
    u32 handles[]{10, 11, 20, 21};
    sdk::spawn_options options{};
    options.replace_image = true;
    options.exec_channels = handles;
    options.exec_channel_count = 4;
    options.exec_terminal_send_handle = 10;
    options.exec_terminal_next_sequence = 72;
    reset(); need(sdk::validate_terminal_exec(options) == 0 && calls == 5, "four-distinct-authorized-channels");
    options.exec_channel_count = 2;
    reset(); need(sdk::validate_terminal_exec(options) == 0, "existing-two-channel-terminal");
    options.exec_channel_count = 4;
    for (u32 bad_count : {0u, 1u, 3u, 5u}) {
        reset(); options.exec_channel_count = bad_count;
        need(sdk::validate_terminal_exec(options) == process_error_invalid && calls == 0, "bad-count-before-enumeration");
    }
    options.exec_channel_count = 4;
    reset(); handles[3] = handles[0];
    need(sdk::validate_terminal_exec(options) == process_error_invalid && calls == 0, "duplicate-before-enumeration");
    handles[3] = 21;
    reset(); options.exec_terminal_next_sequence = 0;
    need(sdk::validate_terminal_exec(options) == process_error_invalid && calls == 0, "zero-sequence");
    options.exec_terminal_next_sequence = 72;
    reset(); options.exec_terminal_send_handle = 11;
    need(sdk::validate_terminal_exec(options) == process_error_denied, "terminal-receive-is-not-send");
    options.exec_terminal_send_handle = 10;
    for (u32 changed = 0; changed < 9; ++changed) {
        reset();
        switch (changed) {
        case 0: entries[1].peer_pid = 301; break;
        case 1: entries[1].controller_pid = 101; break;
        case 2: entries[1].rights = channel_send; break;
        case 3: entries[0].controller_pid = entries[1].controller_pid = 300; break;
        case 4: entries[3].peer_pid = 201; break;
        case 5: entries[3].controller_pid = 201; break;
        case 6: entries[2].rights = channel_receive; entries[3].rights = channel_send; break;
        case 7: entries[2].controller_pid = entries[3].controller_pid = 100; break;
        default: entry_count = 3; break;
        }
        need(sdk::validate_terminal_exec(options) == process_error_denied, "metadata-authority-rejection");
    }
    reset(); entries[3].version = 2;
    need(sdk::validate_terminal_exec(options) == process_error_state, "unknown-metadata-version");
    reset(); entries[4] = entries[0]; entry_count = 5;
    need(sdk::validate_terminal_exec(options) == process_error_state, "ambiguous-native-metadata");
    reset(); trap_error = process_error_state;
    need(sdk::validate_terminal_exec(options) == process_error_state && calls == 1, "enumeration-error-preserved");
    std::puts("DYNAMIC_TERMINAL_HOST_PASS groups=9 metadata_rejections=9");
}
