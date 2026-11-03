// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

using namespace xos;

static u64 now() { return static_cast<u64>(sdk::syscall(sys_clock_monotonic)); }

extern "C" int xos_user_main(const startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc > 1 && sdk::equal(args[1], "console")) {
        if (sdk::syscall(sys_pipe_wait, 0, 0, 0) != process_error_would_block) return 1;
        sdk::print("W1_CONSOLE_WAIT_READY\n");
        if (sdk::syscall(sys_pipe_wait, 0, 0, now() + 3000000000ull) != 0) return 2;
        char value = 0;
        if (sdk::read(0, &value, 1) != 1 || value != 'X') return 3;
        sdk::print("W1_CONSOLE_WAIT_OK\n");
        return 0;
    }
    pipe_handles handles{};
    if (sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&handles)) != 0) return 4;
    const u64 before = now();
    if (sdk::syscall(sys_pipe_wait, handles.read_token, 0, before + 30000000ull) != thread_error_timeout) return 5;
    if (now() < before + 30000000ull) return 6;
    const char byte = 'p';
    if (sdk::syscall(sys_pipe_write, handles.write_token, reinterpret_cast<u64>(&byte), 1) != 1) return 7;
    // A ready stream wins even when the absolute deadline has expired.
    if (sdk::syscall(sys_pipe_wait, handles.read_token, 0, 1) != 0) return 8;
    char read_byte = 0;
    if (sdk::syscall(sys_pipe_read, handles.read_token, reinterpret_cast<u64>(&read_byte), 1) != 1 || read_byte != byte) return 9;
    if (sdk::syscall(sys_pipe_close, handles.write_token) != 0) return 10;
    if (sdk::syscall(sys_pipe_wait, handles.read_token, 0, thread_deadline_infinite) != 0) return 11;
    if (sdk::syscall(sys_pipe_close, handles.read_token) != 0) return 12;
    sdk::print("W1_PIPE_WAIT_OK\n");
    return 0;
}
