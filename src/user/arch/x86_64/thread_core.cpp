// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>

extern "C" {
extern const unsigned char __xos_tls_template_start[], __xos_tls_file_end[];
extern const unsigned char __xos_tls_memory_end[], __xos_tls_alignment[];
void xos_thread_enter(void*);
}
namespace {
struct entry_record { xos::thread::entry_function function; void* argument; };
xos::u64 align_up(xos::u64 value, xos::u64 alignment) { return (value + alignment - 1) & ~(alignment - 1); }
}
extern "C" [[noreturn]] void xos_thread_dispatch(void* raw) {
    const entry_record record = *static_cast<entry_record*>(raw);
    xos::thread::exit(record.function(record.argument));
}
// The initial context enters by iret, so create the ordinary SysV call frame.
__asm__(".text\n.globl xos_thread_enter\nxos_thread_enter:\n"
        "cld\nxor %ebp,%ebp\nand $-16,%rsp\ncall xos_thread_dispatch\nud2\n");

namespace xos::thread {
i64 create(u64& tid, entry_function entry, void* argument, u64 stack_bytes, bool detached) {
    if (entry == nullptr) { return process_error_invalid; }
    i64 result = enable(); if (result < 0) { return result; }
    const u64 alignment = reinterpret_cast<u64>(__xos_tls_alignment);
    const u64 memory = reinterpret_cast<u64>(__xos_tls_memory_end) - reinterpret_cast<u64>(__xos_tls_template_start);
    const u64 files = reinterpret_cast<u64>(__xos_tls_file_end) - reinterpret_cast<u64>(__xos_tls_template_start);
    if (alignment == 0 || (alignment & (alignment - 1)) != 0 ||
        alignment > process_tls_max_alignment || memory > process_tls_max_bytes || files > memory) {
        return process_error_invalid;
    }
    const u64 size = align_up(memory, alignment);
    const u64 pointer_alignment = alignment < 16 ? 16 : alignment;
    thread_prepare_request request{{thread_abi_version, sizeof(thread_prepare_request), 0},
        stack_bytes, size + pointer_alignment + 16 + sizeof(entry_record), detached ? thread_flag_detached : 0};
    thread_reservation reservation{};
    result = sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&reservation));
    if (result < 0) { return result; }
    const u64 pointer = align_up(reservation.tls_begin + size, pointer_alignment);
    auto* base = reinterpret_cast<u8*>(pointer - size);
    for (u64 i = 0; i < files; ++i) { base[i] = __xos_tls_template_start[i]; }
    *reinterpret_cast<u64*>(pointer) = pointer;
    *reinterpret_cast<u64*>(pointer + 8) = 0;
    auto* record = reinterpret_cast<entry_record*>(pointer + 16);
    *record = {entry, argument};
    thread_start_request start{{thread_abi_version, sizeof(thread_start_request), 0},
        reservation.tid, reinterpret_cast<u64>(&xos_thread_enter), reinterpret_cast<u64>(record),
        reservation.stack_top, pointer};
    // Publish the ID before start: the target can preempt this caller immediately.
    tid = reservation.tid;
    result = sdk::syscall(sys_thread_start, reinterpret_cast<u64>(&start));
    if (result < 0) { (void)sdk::syscall(sys_thread_abort, reservation.tid); tid = 0; }
    return result;
}
[[noreturn]] void exit(u64 value) {
    const i64 last = sdk::syscall(sys_thread_begin_exit);
    if (last < 0) { sdk::exit(126); }
    (void)sdk::syscall(sys_thread_exit, value);
    for (;;) { __asm__ volatile("ud2"); }
}
}
