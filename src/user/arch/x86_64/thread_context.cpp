// SPDX-License-Identifier: Apache-2.0
#include "../../threading/runtime.hpp"
#include <errno.h>
#include <stdint.h>
using namespace xos;
extern "C" {
extern const unsigned char __xos_tls_template_start[], __xos_tls_file_end[];
extern const unsigned char __xos_tls_memory_end[], __xos_tls_alignment[];
void xos_pthread_enter(void*);
}
namespace {
xos_thread_control main_control;
_reent early_reent = _REENT_INIT(early_reent);
u32 initialized;
__thread unsigned profile_tls_marker;
u64 align_up(u64 size, u64 alignment) { return (size + alignment - 1) & ~(alignment - 1); }
void set_control(xos_thread_control* pointer) {
    __asm__ volatile("movq %0, %%fs:8" : : "r"(pointer) : "memory");
}
}
extern "C" xos_thread_control* xos_current_control() {
    xos_thread_control* pointer;
    __asm__ volatile("movq %%fs:8, %0" : "=r"(pointer)); return pointer;
}
extern "C" _reent* __getreent() {
    auto* control = xos_current_control(); return control ? &control->reent : &early_reent;
}
extern "C" int xos_thread_runtime_init() {
    if (__atomic_load_n(&initialized, __ATOMIC_ACQUIRE) == 2) { return 0; }
    const i64 result = thread::enable();
    if (result != 0) { return result == thread_error_unsupported ? ENOTSUP : EINVAL; }
    _REENT_INIT_PTR(&main_control.reent);
    set_control(&main_control); profile_tls_marker = 1;
    __atomic_store_n(&initialized, 2u, __ATOMIC_RELEASE); return 0;
}
extern "C" [[noreturn]] void xos_pthread_dispatch(void* raw) {
    auto* control = static_cast<xos_thread_control*>(raw);
    pthread_exit(control->entry(control->argument));
}
__asm__(".text\n.globl xos_pthread_enter\nxos_pthread_enter:\n"
        "cld\nxor %ebp,%ebp\nand $-16,%rsp\ncall xos_pthread_dispatch\nud2\n");
extern "C" i64 xos_allocate_thread(pthread_t* tid, void*(*entry)(void*), void* argument,
                                   size_t stack_bytes, bool detached) {
    const u64 alignment = reinterpret_cast<u64>(__xos_tls_alignment);
    const u64 memory = reinterpret_cast<u64>(__xos_tls_memory_end) - reinterpret_cast<u64>(__xos_tls_template_start);
    const u64 files = reinterpret_cast<u64>(__xos_tls_file_end) - reinterpret_cast<u64>(__xos_tls_template_start);
    if (alignment == 0 || (alignment & (alignment - 1)) != 0 ||
        alignment > process_tls_max_alignment || memory > process_tls_max_bytes || files > memory) { return process_error_invalid; }
    const u64 size = align_up(memory, alignment);
    const u64 pointer_alignment = alignment < 16 ? 16 : alignment;
    thread_prepare_request request{{thread_abi_version, sizeof(thread_prepare_request), 0},
        stack_bytes, size + pointer_alignment + 16 + sizeof(xos_thread_control), detached ? thread_flag_detached : 0};
    thread_reservation reservation{};
    i64 result = sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&reservation));
    if (result < 0) { return result; }
    const u64 pointer = align_up(reservation.tls_begin + size, pointer_alignment);
    auto* base = reinterpret_cast<u8*>(pointer - size);
    for (u64 i = 0; i < files; ++i) { base[i] = __xos_tls_template_start[i]; }
    *reinterpret_cast<u64*>(pointer) = pointer;
    auto* control = reinterpret_cast<xos_thread_control*>(pointer + 16);
    *reinterpret_cast<xos_thread_control**>(pointer + 8) = control;
    control->entry = entry; control->argument = argument;
    _REENT_INIT_PTR(&control->reent);
    thread_start_request start{{thread_abi_version, sizeof(thread_start_request), 0},
        reservation.tid, reinterpret_cast<u64>(&xos_pthread_enter), reinterpret_cast<u64>(control),
        reservation.stack_top, pointer};
    *tid = reservation.tid;
    result = sdk::syscall(sys_thread_start, reinterpret_cast<u64>(&start));
    if (result < 0) { (void)sdk::syscall(sys_thread_abort, reservation.tid); *tid = 0; }
    return result;
}
