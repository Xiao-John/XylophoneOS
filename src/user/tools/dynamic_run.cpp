// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic_launch.hpp>
#include <xos/execution.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include "dynamic_roots.hpp"

namespace {
using namespace xos;
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
startup_descriptor forwarded[32];

i64 inherit_authority(u64 child, void*) {
    return sdk::syscall(sys_process_authority, child,
                        static_cast<u64>(process_authority_mode::copy_from_caller));
}
u64 deadline() {
    const i64 now = sdk::syscall(sys_clock_monotonic);
    return now < 0 || static_cast<u64>(now) > 0x7fffffffffffffffULL - dynamic::startup_deadline_limit_ns
        ? 0 : static_cast<u64>(now) + dynamic::startup_deadline_limit_ns;
}
int failure(const char* phase, i64 code) {
    sdk::print("dynamic-run: "); sdk::print(phase); sdk::print(" error=");
    sdk::signed_decimal(code); sdk::print("\n"); return 126;
}
bool startup_range(u64 address, u64 bytes) {
    return address >= process_startup_begin && address <= process_stack_top && bytes <= process_stack_top - address;
}
bool startup_string(u64 address) {
    if (!startup_range(address, 1)) return false;
    const auto* text = reinterpret_cast<const char*>(address);
    const u64 available = process_stack_top - address;
    for (u64 i = 0; i < available && i < process_max_exec_arg_bytes; ++i) if (!text[i]) return true;
    return false;
}
bool startup_arguments(const startup_info* info, const char* const*& arguments) {
    if (reinterpret_cast<u64>(info) != process_startup_begin || info->magic != startup_magic ||
        info->version < 1 || info->version > 3 || info->size != sizeof(*info) ||
        !info->argc || info->argc > process_max_args || info->handle_count != 3 ||
        !startup_range(info->argv, (u64{info->argc} + 1) * sizeof(u64))) return false;
    arguments = reinterpret_cast<const char* const*>(info->argv);
    for (u32 i = 0; i < info->argc; ++i)
        if (!startup_string(reinterpret_cast<u64>(arguments[i]))) return false;
    return !arguments[info->argc];
}
i64 inherit_options(const startup_info& startup, sdk::spawn_options& options) {
    if (startup.version == 1) return startup.reserved ? process_error_invalid : 0;
    if (startup.reserved != startup_extension_offset) return process_error_invalid;
    const auto& extension = *reinterpret_cast<const startup_extension*>(
        reinterpret_cast<const u8*>(&startup) + startup_extension_offset);
    // This native controller uses ordinary console/pipe/files stdio. It does
    // not declare the separate terminal-actor marker or consume that protocol.
    if (extension.magic != startup_extension_magic || extension.reserved ||
        (extension.flags & ~(7u | (7u << 8))) || extension.environment_count > startup_environment_max ||
        !startup_range(extension.environment, (u64{extension.environment_count} + 1) * sizeof(u64)))
        return process_error_invalid;
    options.environment_count = extension.environment_count;
    options.environment = reinterpret_cast<const char* const*>(extension.environment);
    for (u32 i = 0; i < options.environment_count; ++i)
        if (!startup_string(reinterpret_cast<u64>(options.environment[i]))) return process_error_invalid;
    if (options.environment[options.environment_count]) return process_error_invalid;
    // Cwd already belongs to this Files session. A null option preserves its
    // stable reference even if the directory's pathname was renamed/unlinked.
    if (startup.version == 2) {
        for (u32 fd = 0; fd < 3; ++fd) {
            if (extension.flags & (1u << fd)) options.stdio[fd] = -2;
            if (extension.flags & (1u << (8 + fd))) {
                if (!extension.file_handles[fd] || extension.open_paths[fd]) return process_error_invalid;
                options.file_handles[fd] = extension.file_handles[fd];
                options.open_flags[fd] = extension.open_flags[fd];
            }
            if (extension.open_paths[fd]) {
                if (!startup_string(extension.open_paths[fd])) return process_error_invalid;
                options.open_paths[fd] = reinterpret_cast<const char*>(extension.open_paths[fd]);
                options.open_flags[fd] = extension.open_flags[fd];
            }
        }
        return 0;
    }
    const auto& exec = *reinterpret_cast<const startup_exec_extension*>(
        reinterpret_cast<const u8*>(&startup) + startup_exec_offset);
    if (exec.magic != startup_exec_magic || exec.reserved || exec.count > 32 ||
        !startup_range(exec.descriptors, u64{exec.count} * sizeof(startup_descriptor))) return process_error_invalid;
    const auto* entries = reinterpret_cast<const startup_descriptor*>(exec.descriptors);
    options.descriptors = forwarded;
    const startup_descriptor* objects[32]{};
    u32 used_fds = 0, cleanups = 0;
    for (u32 fd = 0; fd < 3; ++fd) options.stdio[fd] = -2;
    // Validate the complete inherited table before any CLOEXEC close effect.
    for (u32 i = 0; i < exec.count; ++i) {
        const auto& item = entries[i];
        if (item.object >= 32 || item.reserved || item.kind < 1 || item.kind > 4 ||
            (item.fd != 0xffffffffu && item.fd >= 32)) return process_error_invalid;
        if (item.fd == 0xffffffffu) {
            if (objects[item.object] || (cleanups & (1u << item.object))) return process_error_invalid;
            cleanups |= 1u << item.object;
        } else {
            if ((used_fds & (1u << item.fd)) || (cleanups & (1u << item.object))) return process_error_invalid;
            used_fds |= 1u << item.fd;
            if (objects[item.object]) {
                const auto& other = *objects[item.object];
                if (other.kind != item.kind || other.handle != item.handle || other.flags != item.flags)
                    return process_error_invalid;
            } else objects[item.object] = &item;
        }
        const auto kind = static_cast<startup_fd_kind>(item.kind);
        if ((kind == startup_fd_kind::kernel && item.handle >= 3) ||
            (kind == startup_fd_kind::file && !item.handle) ||
            ((kind == startup_fd_kind::pipe_read || kind == startup_fd_kind::pipe_write) && item.handle < process_pipe_token_min))
            return process_error_invalid;
        if (item.fd == 0xffffffffu) continue;
        if (kind == startup_fd_kind::pipe_read || kind == startup_fd_kind::pipe_write) {
            bool routed = false;
            for (u32 j = 0; j < exec.count; ++j)
                routed = routed || (entries[j].fd < 3 && entries[j].kind == item.kind && entries[j].handle == item.handle);
            if (!routed) return thread_error_unsupported;
        }
        if (item.fd < 3 && kind != startup_fd_kind::file) {
            if ((item.flags & ~3u) || ((item.fd == 0) !=
                (kind == startup_fd_kind::pipe_read || (kind == startup_fd_kind::kernel && item.handle == 0))))
                return thread_error_unsupported;
            options.stdio[item.fd] = item.handle;
        }
        forwarded[options.descriptor_count++] = item;
    }
    file::client files;
    if (cleanups && (!files.set_deadline(deadline()) || !files.init())) return process_error_state;
    for (u32 i = 0; i < exec.count; ++i) if (entries[i].fd == 0xffffffffu) {
        const auto& item = entries[i];
        const auto kind = static_cast<startup_fd_kind>(item.kind);
        const i64 closed = kind == startup_fd_kind::file ? files.close(item.handle)
            : kind == startup_fd_kind::kernel ? sdk::close(item.handle)
            : sdk::syscall(sys_pipe_close, item.handle);
        if (closed) return closed; // No replay after an unknown close result.
    }
    return 0;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const char* const* args = nullptr;
    if (!startup_arguments(startup, args)) return failure("native startup", process_error_invalid);
    if (startup->argc < 3 || !args[1][0] || args[1][1] || args[1][0] < '0' || args[1][0] > '3') {
        sdk::print("usage: dynamic-run SLOT /absolute/program [args...]\n"); return 2;
    }
    const u32 slot = static_cast<u32>(args[1][0] - '0');
    if (slot >= dynamic_run_approved.count || !sdk::equal(args[2], dynamic_run_main_paths[slot]))
        return failure("target does not match approved slot", process_error_denied);
    sdk::spawn_options options{};
    options.prepare_child = inherit_authority;
    const i64 inherited = inherit_options(*startup, options);
    if (inherited) return failure("inherited stdio", inherited);
    const auto installed = dynamic::install(dynamic_run_approved, deadline());
    if (installed != dynamic::error::none) return failure("approved policy", static_cast<i64>(installed));
    if (slot != dynamic_run_approved.active) {
        const auto activated = dynamic::activate(slot, dynamic_run_approved.sequence, deadline());
        if (activated != dynamic::error::none) return failure("activate", static_cast<i64>(activated));
    }
    const auto candidate = execution::inspect(args[2]);
    if (candidate.kind != execution::candidate_kind::executable) return failure("inspect", candidate.error);
    execution::launch_diagnostic diagnostic{};
    execution::image_receipt receipt{};
    const i64 child = execution::spawn_file_diagnosed_receipt(args[2], startup->argc - 2, args + 2,
                                                             options, diagnostic, receipt);
    if (child < 0) return failure("spawn", child);
    process_status status{};
    const i64 waited = sdk::wait_flags(static_cast<u64>(child), status);
    if (waited || status.pid != static_cast<u64>(child)) return failure("wait", waited ? waited : process_error_state);
    sdk::print("DYNAMIC_RUN_EXIT slot="); sdk::decimal(slot);
    sdk::print(" generation="); sdk::decimal(dynamic_run_approved.roots[slot].root.id);
    sdk::print(" pid="); sdk::decimal(status.pid);
    sdk::print(" outcome="); sdk::decimal(static_cast<u32>(status.outcome));
    sdk::print(" code="); sdk::signed_decimal(status.code); sdk::print("\n");
    if (status.outcome != process_outcome::exited || status.code < 0 || status.code > 255) return 126;
    return static_cast<int>(status.code);
}
