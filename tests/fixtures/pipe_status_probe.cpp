// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>

using namespace xos;

static void line(const char* text) {
    u64 length = 0;
    while (text[length]) ++length;
    (void)sdk::write(1, text, length);
    (void)sdk::write(1, "\n", 1);
}

static bool check(bool success, const char* name) {
    line(success ? name : "PIPE_STATUS_FAIL");
    return success;
}

static i64 create(pipe_handles& value) {
    return sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&value));
}
static i64 close_pipe(u32 value) { return sdk::syscall(sys_pipe_close, value); }
static i64 write_pipe(u32 value, const void* data, u64 size) {
    return sdk::syscall(sys_pipe_write, value, reinterpret_cast<u64>(data), size);
}
static i64 read_pipe(u32 value, void* data, u64 size) {
    return sdk::syscall(sys_pipe_read, value, reinterpret_cast<u64>(data), size);
}

extern "C" int xos_user_main(const startup_info* startup) {
    const u32 argc = startup->argc;
    const auto argv = reinterpret_cast<const char* const*>(startup->argv);
    if (argc == 2) {
        u64 token = 0;
        for (const char* cursor = argv[1]; *cursor; ++cursor) token = token * 10 + static_cast<u64>(*cursor - '0');
        pipe_status_snapshot output{};
        return sdk::query_pipe_status(token, output) == process_error_denied ? 0 : 41;
    }
    pipe_handles pipe{};
    pipe_status_snapshot read{}, write{};
    if (create(pipe) != 0) return 1;
    if (!check(sdk::query_pipe_status(pipe.read_token, read) == 0 &&
               sdk::query_pipe_status(pipe.write_token, write) == 0 &&
               read.version == 1 && read.size == 32 && read.flags == pipe_status_read_end &&
               !read.readable && !read.writable && write.flags == pipe_status_write_end &&
               !write.readable && write.writable == process_pipe_bytes, "PIPE_STATUS_PASS empty_direction")) return 2;
    char bytes[process_pipe_bytes]{};
    bytes[0] = 'x'; bytes[1] = 'y'; bytes[2] = 'z';
    if (!check(write_pipe(pipe.write_token, bytes, 3) == 3 &&
               sdk::query_pipe_status(pipe.read_token, read) == 0 && read.readable == 3 &&
               sdk::query_pipe_status(pipe.read_token, read) == 0 && read.readable == 3 &&
               sdk::query_pipe_status(pipe.write_token, write) == 0 && write.writable == process_pipe_bytes - 3 &&
               read_pipe(pipe.read_token, bytes, 3) == 3 && bytes[0] == 'x' && bytes[2] == 'z',
               "PIPE_STATUS_PASS non_consuming")) return 3;
    if (!check(write_pipe(pipe.write_token, bytes, sizeof(bytes)) == sizeof(bytes) &&
               sdk::query_pipe_status(pipe.write_token, write) == 0 && write.writable == 0 &&
               sdk::query_pipe_status(pipe.read_token, read) == 0 && read.readable == sizeof(bytes) &&
               read_pipe(pipe.read_token, bytes, sizeof(bytes)) == sizeof(bytes),
               "PIPE_STATUS_PASS capacity")) return 4;
    pipe_status_snapshot bad{99, sizeof(pipe_status_snapshot), 0, 0, 0, 0, 0};
    if (!check(sdk::syscall(sys_pipe_wait, pipe.read_token, pipe_wait_query_mode,
                           reinterpret_cast<u64>(&bad)) == process_error_invalid && bad.version == 99 &&
               sdk::syscall(sys_pipe_wait, pipe.read_token, pipe_wait_query_mode, 1) == process_error_invalid &&
               sdk::syscall(sys_pipe_wait, 0, pipe_wait_query_mode, reinterpret_cast<u64>(&bad)) < 0,
               "PIPE_STATUS_PASS invalid_output_and_console")) return 5;
    bad = {1, sizeof(pipe_status_snapshot), 0, 0, 0, 1, 0};
    if (!check(sdk::syscall(sys_pipe_wait, pipe.read_token, pipe_wait_query_mode,
                           reinterpret_cast<u64>(&bad)) == process_error_invalid && bad.reserved == 1,
               "PIPE_STATUS_PASS reserved_rejected")) return 6;
    char token_text[24]{};
    u64 number = pipe.read_token;
    u32 count = 0;
    do { token_text[count++] = static_cast<char>('0' + number % 10); number /= 10; } while (number);
    for (u32 i = 0; i < count / 2; ++i) {
        const char value = token_text[i]; token_text[i] = token_text[count - i - 1]; token_text[count - i - 1] = value;
    }
    const char* arguments[]{"/bin/pipe_status.elf", token_text};
    const i64 child = sdk::spawn_file(arguments[0], 2, arguments);
    process_status status{};
    if (!check(child > 0 && sdk::wait(static_cast<u64>(child), status) == 0 && status.code == 0 &&
               status.outcome == process_outcome::exited && sdk::query_pipe_status(pipe.read_token, read) == 0,
               "PIPE_STATUS_PASS foreign_owner_denied")) return 7;
    if (!check(close_pipe(pipe.write_token) == 0 && sdk::query_pipe_status(pipe.read_token, read) == 0 &&
               read.flags == (pipe_status_read_end | pipe_status_peer_closed) && read.readable == 0 &&
               read_pipe(pipe.read_token, bytes, 1) == 0 && close_pipe(pipe.read_token) == 0,
               "PIPE_STATUS_PASS eof")) return 8;
    read = {77, 88, 99, 100, 101, 102, 103};
    if (!check(sdk::query_pipe_status(pipe.read_token, read) == process_error_denied && read.version == 77 &&
               read.reserved2 == 103 && sdk::syscall(sys_pipe_wait, pipe.read_token, pipe_wait_query_mode, 1)
               == process_error_denied, "PIPE_STATUS_PASS stale_no_output")) return 9;
    if (create(pipe) != 0) return 10;
    if (!check(close_pipe(pipe.read_token) == 0 && sdk::query_pipe_status(pipe.write_token, write) == 0 &&
               write.flags == (pipe_status_write_end | pipe_status_peer_closed) &&
               write_pipe(pipe.write_token, bytes, 1) == pipe_error_broken && close_pipe(pipe.write_token) == 0,
               "PIPE_STATUS_PASS broken_writer")) return 11;
    line("PIPE_STATUS_OK cases=9");
    return 0;
}
