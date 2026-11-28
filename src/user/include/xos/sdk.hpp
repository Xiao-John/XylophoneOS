// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/process_abi.hpp>
#include <xos/process_budget_abi.hpp>
#include <xos/observation_abi.hpp>
#include <xos/file_abi.hpp>
#include <xos/spawn.hpp>

namespace xos::sdk {
i64 syscall(u64 number, u64 first = 0, u64 second = 0, u64 third = 0);
inline i64 set_process_budget(u64 pid, const process_budget_vector& limits) {
    const process_budget_config request{process_budget_version, sizeof(process_budget_config), 0, limits};
    return syscall(sys_process_authority, pid, static_cast<u64>(process_authority_mode::budget_set),
                   reinterpret_cast<u64>(&request));
}
inline i64 query_process_budget(u64 pid, process_budget_snapshot& output, u64 domain_id = 0) {
    process_budget_snapshot request{};
    request.version = process_budget_version; request.size = sizeof(request); request.domain_id = domain_id;
    const i64 result = syscall(sys_process_authority, pid,
        static_cast<u64>(process_authority_mode::budget_query), reinterpret_cast<u64>(&request));
    if (!result) output = request; // Preserve caller output on denial/format failure.
    return result;
}
inline observe_native::result observe(const observe_native::request& request,
                                      observe_native::snapshot& output) {
    output = {};
    return static_cast<observe_native::result>(syscall(sys_observe,
        reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&output), 0));
}
// Runtime initialization only: caller owns and keeps the supplied TCB alive.
inline i64 install_thread_pointer(u64 own_pid, void* pointer) {
    return syscall(sys_process_tls, own_pid, reinterpret_cast<u64>(pointer),
                   static_cast<u64>(process_tls_mode::current_thread));
}
u16 target_elf_machine();
// Optional per-executable console mediation; absent in ordinary applications.
extern "C" i64 xos_console_write_hook(u32, const void*, u64) __attribute__((weak));
extern "C" i64 xos_console_read_hook(u32, void*, u64) __attribute__((weak));
inline i64 write(u32 handle, const void* data, u64 length) {
    if ((handle == 1 || handle == 2) && xos_console_write_hook)
        return xos_console_write_hook(handle, data, length);
    return syscall(sys_handle_write, handle, reinterpret_cast<u64>(data), length);
}
inline i64 read(u32 handle, void* data, u64 length) {
    if (handle == 0 && xos_console_read_hook) return xos_console_read_hook(handle, data, length);
    return syscall(sys_handle_read, handle, reinterpret_cast<u64>(data), length);
}
inline i64 close(u32 handle) { return syscall(sys_handle_close, handle); }
inline i64 query_pipe_status(u64 token, pipe_status_snapshot& output) {
    pipe_status_snapshot request{pipe_status_version, sizeof(pipe_status_snapshot), 0, 0, 0, 0, 0};
    const i64 result = syscall(sys_pipe_wait, token, pipe_wait_query_mode, reinterpret_cast<u64>(&request));
    if (result == 0) output = request;
    return result;
}
inline i64 stream_lease(u32 handle, stream_lease_action action, u64 target = 0) {
    return syscall(sys_stream_lease, handle, static_cast<u64>(action), target);
}
inline i64 pio_grant(pio_grant_action action, u64 target, u64 resource) {
    return syscall(sys_pio_grant, static_cast<u64>(action), target, resource);
}
inline i64 irq_event(irq_event_action action, u64 value, u64 argument = 0) {
    return syscall(sys_irq_event, static_cast<u64>(action), value, argument);
}
inline i64 channel_open(const channel_create& request) {
    return syscall(sys_channel, static_cast<u64>(channel_action::create), reinterpret_cast<u64>(&request));
}
// Explicit bounded composition: six owner channels instead of the legacy four.
// Ownership, endpoint authority, budgets and the wire request are unchanged.
inline i64 channel_open_extended(const channel_create& request) {
    return syscall(sys_channel, static_cast<u64>(channel_action::create_extended), reinterpret_cast<u64>(&request));
}
inline i64 channel_get(u32 index, channel_info& info) {
    return syscall(sys_channel, static_cast<u64>(channel_action::enumerate), index, reinterpret_cast<u64>(&info));
}
inline i64 channel_close(u32 handle) {
    return syscall(sys_channel, static_cast<u64>(channel_action::close), handle);
}
inline i64 channel_wait(u32 handle, u64 deadline) {
    return syscall(sys_channel, static_cast<u64>(channel_action::wait), handle, deadline);
}
inline i64 channel_wait_many(const channel_wait_many_request& request, u64 deadline) {
    return syscall(sys_channel, static_cast<u64>(channel_action::wait_many), reinterpret_cast<u64>(&request), deadline);
}
inline i64 channel_fork(channel_fork_pair& request) {
    return syscall(sys_channel, static_cast<u64>(channel_action::fork_pair), reinterpret_cast<u64>(&request));
}
inline i64 channel_verify_fork(const channel_fork_verification& request) {
    return syscall(sys_channel, static_cast<u64>(channel_action::verify_fork_pair), reinterpret_cast<u64>(&request));
}
inline i64 ipc_send(u32 handle, const void* data, u64 length) {
    return syscall(4, handle, reinterpret_cast<u64>(data), length);
}
inline i64 ipc_recv(u32 handle, void* data, u64 length) {
    return syscall(5, handle, reinterpret_cast<u64>(data), length);
}
inline i64 ipc_handles(u32& send_handle, u32& recv_handle) {
    u32 values[2]{};
    const i64 result = syscall(sys_ipc_handles, reinterpret_cast<u64>(values), 0, 0);
    if (result == 0) { send_handle = values[0]; recv_handle = values[1]; }
    return result;
}
inline i64 ipc_channel_create(u64 peer_pid, ipc_channel& channel) {
    return syscall(sys_ipc_endpoint, static_cast<u64>(ipc_endpoint_action::create), peer_pid,
                   reinterpret_cast<u64>(&channel));
}
inline i64 ipc_channel_revoke(u32 endpoint) {
    return syscall(sys_ipc_endpoint, static_cast<u64>(ipc_endpoint_action::revoke), endpoint, 0);
}
inline i64 ipc_endpoint_peer(u32 endpoint, u64& peer_pid) {
    return syscall(sys_ipc_endpoint, static_cast<u64>(ipc_endpoint_action::query_peer), endpoint,
                   reinterpret_cast<u64>(&peer_pid));
}
inline i64 ipc_channel_close(u32 endpoint) {
    return syscall(sys_ipc_endpoint, static_cast<u64>(ipc_endpoint_action::close), endpoint, 0);
}
inline i64 ipc_wait(u32 endpoint, ipc_wait_mode mode) {
    return syscall(sys_ipc_wait, endpoint, static_cast<u64>(mode), 0);
}
inline i64 ipc_wait_until(u32 endpoint, ipc_wait_mode mode, u64 deadline_ns) {
    if (mode != ipc_wait_mode::receive && mode != ipc_wait_mode::send) return process_error_invalid;
    const auto timed = mode == ipc_wait_mode::receive ? ipc_wait_mode::receive_until : ipc_wait_mode::send_until;
    return syscall(sys_ipc_wait, endpoint, static_cast<u64>(timed), deadline_ns);
}
inline ipc_channel ipc_channel_for_peer(const ipc_channel& channel) {
    return {channel.receive, channel.send};
}
inline i64 ipc_name_publish(const char* name) {
    return syscall(sys_ipc_name, static_cast<u64>(ipc_name_action::publish),
                   reinterpret_cast<u64>(name), 0);
}
inline i64 ipc_name_unpublish(const char* name) {
    return syscall(sys_ipc_name, static_cast<u64>(ipc_name_action::unpublish),
                   reinterpret_cast<u64>(name), 0);
}
inline i64 ipc_name_connect(const char* name, ipc_channel& channel) {
    return syscall(sys_ipc_name, static_cast<u64>(ipc_name_action::connect),
                   reinterpret_cast<u64>(name), reinterpret_cast<u64>(&channel));
}
inline i64 ipc_name_try_accept(ipc_channel& channel) {
    return syscall(sys_ipc_name, static_cast<u64>(ipc_name_action::accept),
                   reinterpret_cast<u64>(&channel), 0);
}
inline i64 ipc_name_wait_accept() {
    return syscall(sys_ipc_name, static_cast<u64>(ipc_name_action::wait_accept), 0, 0);
}
inline i64 ipc_name_accept(ipc_channel& channel) {
    for (;;) {
        const i64 result = ipc_name_try_accept(channel);
        if (result != process_error_would_block) return result;
        const i64 waited = ipc_name_wait_accept();
        if (waited < 0) return waited;
    }
}
inline void yield() { (void)syscall(3); }
inline u64 ticks() { return static_cast<u64>(syscall(7)); }
inline u64 pid() { return static_cast<u64>(syscall(6)); }
[[noreturn]] void exit(i32 code);
usize length(const char* text);
void print(const char* text, u32 handle = 1);
void decimal(u64 value);
void signed_decimal(i64 value);
bool equal(const char* left, const char* right);
i64 spawn(u32 image, u32 argc, const char* const* argv);
i64 spawn_buffer(const char* name, const u8* bytes, u64 size, u32 argc,
                 const char* const* argv);
i64 spawn_buffer_options(const char* name, const u8* bytes, u64 size, u32 argc,
                         const char* const* argv, const spawn_options& options);
i64 spawn_image_options(u32 image, u32 argc, const char* const* argv,
                         const spawn_options& options);
i64 spawn_file(const char* path, u32 argc, const char* const* argv);
i64 spawn_file_options(const char* path, u32 argc, const char* const* argv,
                       const spawn_options& options);
extern "C" i64 xos_launch_wait_hook(u64, process_status*, u32) __attribute__((weak));
inline i64 wait_flags(u64 child, process_status& status, u32 flags = 0) {
    if (xos_launch_wait_hook) return xos_launch_wait_hook(child, &status, flags);
    return syscall(sys_process_wait, child, reinterpret_cast<u64>(&status), flags);
}
inline i64 wait(u64 child, process_status& status) {
    return wait_flags(child, status);
}
inline i64 wait_any(process_status& status, bool nonblocking = false) {
    return wait_flags(0, status,
                   process_wait_any | (nonblocking ? process_wait_nonblocking : 0));
}
inline i64 cpu_time(process_cpu_time& result) {
    result = {};
    result.version = 1;
    result.size = sizeof(result);
    return syscall(sys_process_cpu_time, reinterpret_cast<u64>(&result));
}
inline process_stats stats() {
    process_stats result{};
    (void)syscall(sys_process_stats, reinterpret_cast<u64>(&result));
    return result;
}
inline i64 transfer_pipes(u64 child, process_pipe_transfer& request) {
    return syscall(sys_process_stdio, child, process_pipe_transfer_mode,
                   reinterpret_cast<u64>(&request));
}
}
