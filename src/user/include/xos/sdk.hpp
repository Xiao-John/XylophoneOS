// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/process_abi.hpp>
#include <xos/file_abi.hpp>
#include <xos/spawn.hpp>

namespace xos::sdk {
i64 syscall(u64 number, u64 first = 0, u64 second = 0, u64 third = 0);
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
inline i64 wait(u64 child, process_status& status) {
    return syscall(sys_process_wait, child, reinterpret_cast<u64>(&status));
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
}
