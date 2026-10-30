// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/process_abi.hpp>
#include <xos/file_abi.hpp>
#include <xos/spawn.hpp>

namespace xos::sdk {
i64 syscall(u64 number, u64 first = 0, u64 second = 0, u64 third = 0);
u16 target_elf_machine();
inline i64 write(u32 handle, const void* data, u64 length) {
    return syscall(sys_handle_write, handle, reinterpret_cast<u64>(data), length);
}
inline i64 read(u32 handle, void* data, u64 length) {
    return syscall(sys_handle_read, handle, reinterpret_cast<u64>(data), length);
}
inline i64 close(u32 handle) { return syscall(sys_handle_close, handle); }
inline i64 stream_lease(u32 handle, stream_lease_action action, u64 target = 0) {
    return syscall(sys_stream_lease, handle, static_cast<u64>(action), target);
}
inline i64 pio_grant(pio_grant_action action, u64 target, u64 resource) {
    return syscall(sys_pio_grant, static_cast<u64>(action), target, resource);
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
i64 spawn_file(const char* path, u32 argc, const char* const* argv);
inline i64 wait(u64 child, process_status& status) {
    return syscall(sys_process_wait, child, reinterpret_cast<u64>(&status));
}
inline process_stats stats() {
    process_stats result{};
    (void)syscall(sys_process_stats, reinterpret_cast<u64>(&result));
    return result;
}
}
