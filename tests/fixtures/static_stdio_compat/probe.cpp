// SPDX-License-Identifier: Apache-2.0
#include <xos/execution.hpp>
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
constexpr const char* raw_path = "/bin/raw_stdio.elf";
file::client files;
startup_descriptor descriptors[4];
sdk::spawn_options options;
execution::launch_diagnostic diagnostic;
void reset() {
    options = sdk::spawn_options{};
    for (u32 fd = 0; fd < 3; ++fd) descriptors[fd] = {fd, fd, 1, fd, fd == 0 ? 0u : 1u, 0};
    options.descriptors = descriptors; options.descriptor_count = 3;
}
int fail(const char* name, i64 code) {
    sdk::print("STATIC_STDIO_FAIL "); sdk::print(name); sdk::print(" code=");
    sdk::signed_decimal(code); sdk::print("\n"); return 1;
}
void passed(const char* name) { sdk::print("STATIC_STDIO_PASS "); sdk::print(name); sdk::print("\n"); }
i64 launch(const char* path, const char* mode) {
    const char* arguments[]{path, mode};
    const i64 child = execution::spawn_file_diagnosed(path, 2, arguments, options, diagnostic);
    if (child < 0) return child;
    process_status status{};
    const i64 waited = sdk::wait(static_cast<u64>(child), status);
    if (waited || status.pid != static_cast<u64>(child) || status.outcome != process_outcome::exited)
        return process_error_state;
    return status.code;
}
bool rejected(const char* path = raw_path) {
    const i64 result = launch(path, "basic");
    // Global resource statistics belong to the supervisor, which checks the
    // exact before/after baseline around each complete probe invocation.
    const bool correct = result == thread_error_unsupported && diagnostic.stage == execution::launch_stage::inspect;
    if (!correct) {
        sdk::print("STATIC_STDIO_REJECTION result="); sdk::signed_decimal(result);
        sdk::print(" stage="); sdk::decimal(static_cast<u32>(diagnostic.stage));
        sdk::print("\n");
    }
    return correct;
}
bool read_pin(void* context, u64 offset, u8* destination, u32 length) {
    const u32 handle = *static_cast<u32*>(context);
    for (u32 done = 0; done < length;) {
        const i64 count = files.read_at(handle, destination + done, length - done, offset + done);
        if (count <= 0 || static_cast<u64>(count) > length - done) return false;
        done += static_cast<u32>(count);
    }
    return true;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    if (!files.init()) return fail("files", -1);
    reset();
    i64 result = launch(raw_path, "basic");
    if (result) return fail("raw_kernel_stdio", result);
    passed("raw_kernel_stdio");
    reset(); result = launch("/bin/v3_stdio.elf", "basic");
    if (result) return fail("v3_keeps_descriptor_startup", result);
    passed("v3_keeps_descriptor_startup");
    reset();
    descriptors[0] = descriptors[1]; descriptors[1] = descriptors[2];
    options.descriptor_count = 2; options.stdio[0] = -2;
    result = launch(raw_path, "closed");
    if (result) return fail("raw_closed_stdin", result);
    passed("raw_closed_stdin");

    pipe_handles input{}, output{};
    if (sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&input)) ||
        sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&output))) return fail("pipes", -1);
    if (sdk::syscall(sys_pipe_write, input.write_token, reinterpret_cast<u64>("DATA"), 4) != 4)
        return fail("pipe_input", -1);
    reset();
    descriptors[0] = {0, 0, 3, input.read_token, 0, 0};
    descriptors[1] = {1, 1, 4, output.write_token, 1, 0};
    descriptors[2] = {2, 1, 4, output.write_token, 1, 0};
    options.stdio[0] = input.read_token; options.stdio[1] = options.stdio[2] = output.write_token;
    result = launch(raw_path, "pipes");
    char received[6]{};
    const i64 count = sdk::syscall(sys_pipe_read, output.read_token, reinterpret_cast<u64>(received), sizeof(received));
    const u32 tokens[]{input.read_token, input.write_token, output.read_token, output.write_token};
    for (const u32 token : tokens)
        if (sdk::syscall(sys_pipe_close, token)) return fail("pipe_close", -1);
    if (result || count != 6 || __builtin_memcmp(received, "OUTERR", 6)) return fail("raw_pipe_alias", result);
    passed("raw_pipe_alias");

    reset(); descriptors[3] = {3, 1, 1, 1, 1, 0}; options.descriptor_count = 4;
    if (!rejected()) return fail("extra_fd_rejected", -1);
    passed("extra_fd_rejected");
    reset(); descriptors[1].flags |= 0x4000u;
    if (!rejected()) return fail("status_flags_rejected", -1);
    passed("status_flags_rejected");
    reset(); options.stdio[2] = 1;
    if (!rejected()) return fail("route_mismatch_rejected", -1);
    passed("route_mismatch_rejected");
    reset(); descriptors[2].fd = 1;
    if (!rejected()) return fail("duplicate_fd_rejected", -1);
    passed("duplicate_fd_rejected");
    reset(); descriptors[2].object = 1;
    if (!rejected()) return fail("alias_conflict_rejected", -1);
    passed("alias_conflict_rejected");
    reset(); options.replace_image = true;
    if (!rejected()) return fail("replacement_still_requires_v3", -1);
    passed("replacement_still_requires_v3");
    reset();
    if (!rejected("/bin/bad_marker.elf")) return fail("malformed_optin_rejected", -1);
    passed("malformed_optin_rejected");

    u32 handle = 0, bytes = 0, version = 0;
    if (files.open("/data/preserved.txt", file::write_only, handle, bytes, version)) return fail("file_open", -1);
    reset(); descriptors[1] = {1, 1, 2, handle, 1, 0}; options.stdio[1] = -2;
    if (!rejected()) return fail("files_stdio_rejected", -1);
    passed("files_stdio_rejected");
    reset(); options.file_handles[1] = handle;
    if (!rejected()) return fail("legacy_files_transfer_rejected", -1);
    passed("legacy_files_transfer_rejected");
    reset(); descriptors[3] = {~u32{0}, 3, 2, handle, 1, 0}; options.descriptor_count = 4;
    if (!rejected()) return fail("cleanup_record_rejected", -1);
    passed("cleanup_record_rejected");
    if (files.close(handle)) return fail("file_close", -1);

    if (files.open(raw_path, file::read_only | file::open_pin, handle, bytes, version)) return fail("pin_open", -1);
    reset(); const char* arguments[]{raw_path, "basic"};
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return fail("clock", now);
    result = execution::spawn_pinned_image(raw_path, bytes, read_pin, &handle, 2, arguments, options,
        diagnostic, static_cast<u64>(now) + 5'000'000'000ULL, nullptr, nullptr);
    if (files.close(handle)) return fail("pin_close", -1);
    if (result != thread_error_unsupported || diagnostic.stage != execution::launch_stage::inspect)
        return fail("pinned_bootstrap_no_downgrade", result);
    passed("pinned_bootstrap_no_downgrade");
    sdk::print("STATIC_STDIO_OK cases=15\n");
    return 0;
}
