// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/task.hpp>
#include <xos/display.hpp>
#include <xos/thread_abi.hpp>
#include "../../core/thread_lifecycle.hpp"
#include "../../core/stream_lease.hpp"
#include "../../core/vm_pin.hpp"
#include "../../core/vm_continuation.hpp"
#include <xos/block.hpp>
#include <xos/syscall.hpp>
#include <xos/memory.hpp>
#include <xos/format.hpp>
#include <xos/platform.hpp>
#include "frame.hpp"
#include "build_info.hpp"
#include "../../core/anonymous_reservations.hpp"
#include "interrupt_entry.hpp"
#include <xos/clock.hpp>
#include "arch/x86_64/interrupt_wait.hpp"
static_assert(xos::clock::resolution_ns == xos::thread_tick_ns);
#include "user_blobs.hpp"
#include "user_images.hpp"
#include <xos/device_abi.hpp>
#include <xos/ipc_v1_abi.hpp>
// Shared audio protocol bounds the PC speaker lease defined below.
#include <xos/audio_abi.hpp>

namespace xos {
extern const u8* boot_payload;
extern u64 boot_payload_size;
}

extern "C" void enter_frame(void* frame) __attribute__((noreturn));
extern "C" void* interrupt_dispatch(void* frame);

namespace xos::arch {
namespace {
constexpr u64 user_base = 0x40000000ull;
constexpr u64 user_data_address = 0x40010000ull;
constexpr u64 user_stack_top = 0x40020000ull;
constexpr u64 user_stack_bottom = user_stack_top - 4 * page_size;
constexpr u64 user_limit = process_user_end;
// E03 receiver, supervisor/files bootstrap channels, and bounded generic IPC.
constexpr u32 max_endpoints = 37;
constexpr u32 file_session_count = 8;
constexpr u32 default_message_bytes = 64;
constexpr u32 file_message_bytes = 4096;
constexpr u32 kernel_stack_bytes = 4096;
// Must outlast the longest legal note (audio::max_note_ms) plus worker
// startup and scheduling delay, otherwise a max-length note expires first.
constexpr u64 pc_speaker_lease_ns = u64{audio::max_note_ms} * 1000000ull + 500000000ull;
constexpr u32 user_code_selector = 0x2b;
constexpr u32 user_data_selector = 0x33;

enum class task_state : u32 { free, building, fresh, ready, running, waiting, dead };

struct stdio_route { bool valid; bool console; bool writable; u8 pipe_index; };
struct pipe_reference { bool used; u32 token; u8 pipe_index; bool writable; };
struct pipe_object {
    bool used;
    u32 references;
    u32 reader_references;
    u32 writer_references;
    u32 head;
    u32 length;
    u8 data[process_pipe_bytes];
};

struct process_record {
    u64 cr3;
    u64 pid;
    u64 ticks;
    // Fixed, kernel-authenticated device grants loaded into the TSS bitmap.
    u32 io_window_first, io_window_length;
    bool pc_speaker_io;
    bool pc_speaker_controller;
    bool pc_speaker_lease_started;
    u64 pc_speaker_deadline_ns;
    task_state state;
    char name[12];
    u32 send_handle;
    u32 recv_handle;
    u32 session_request_handle;
    u32 session_response_handle;
    bool supervisor;
    bool block_access;
    u32 spawn_depth;
    // SL1 identity-carried create authority (shell_launch contract §3).
    // Separate from spawn_depth: set only via sys_process_authority on a
    // building child; copied by fork and exec; never increased by the child.
    bool can_create;
    i32 exit_code;
    u64 parent;
    u64 entry;
    u64 initial_stack;
    u64 startup;
    u32 stdio_mask;
    stdio_route stdio[3];
    pipe_reference pipe_references[process_max_pipe_refs];
    u32 pipe_reference_count;
    u32 user_pages;
    u32 completion_slot;
    u64 heap_break;
    bool threads_enabled;
    bool closing;
    u64 exit_owner;
    process_foreground foreground;
    bool foreground_active, foreground_cancelled;
    // A fork child resumes a copied syscall frame only after the files service
    // authenticates/clones its session. Depth bounds nested isolated shells;
    // ordinary spawn delegation remains a separate capability.
    u64 fork_source;
    u32 fork_depth;
    bool fork_pending, fork_files_ack;
    // Private, never-runnable image constructor for exec. It owns pages and a
    // temporary kernel stack, but no completion, file session, or pipe routes.
    bool replacement_pending;
    vm_continuation continuation;
    process_outcome deferred_outcome;
    i64 deferred_code;
    u64 deferred_vector, deferred_address, deferred_instruction;
};

struct completion_record { bool used; bool ready; u64 parent; process_status status; };
completion_record completions[16];

struct endpoint_record {
    bool used;
    u32 handle;
    u32 derived_from;
    u64 receiver_pid;
    u64 sender_pid;
    u64 owner_pid;
    u32 capacity;
    bool session_response;
    bool generic_channel;
    bool generic;
    u32 channel_id;
    bool pending;
    u32 length;
    u8 data[file_message_bytes];
};
struct ipc_name_record { bool used; u64 owner_pid; char name[32]; };
struct ipc_connection_record {
    bool used;
    u64 service_pid;
    u64 client_pid;
    u32 channel_id;
    ipc_channel service_channel;
};

struct thread_record : thread_lifetime {
    process_record* process;
    u64 kernel_rsp;
    u64 kernel_stack_top;
    u64 thread_pointer;
    u64 entry;
    u64 argument;
    u64 initial_stack;
    u32 wait_channels[channel_wait_many_max], wait_channel_count;
    vm_pin user_pin;
    vm_pin ipc_v1_pins[3];
    u64 ipc_v1_request_address;
    u64 ipc_v1_payload_address;
    u64 ipc_v1_reply_address;
    u64 ipc_v1_label;
    u64 ipc_v1_badge;
    u64 ipc_v1_token;
    u32 ipc_v1_payload_capacity;
    u32 ipc_v1_call_slot;
    u32 ipc_v1_length;
    u32 ipc_v1_phase;
    u32 ipc_v1_reply_consumed;
    u32 ipc_v1_wait_action;
    u32 ipc_v1_event_count;
    u8 ipc_v1_payload[ipc_v1_max_message_bytes];
    ipc_v1_wait_event ipc_v1_events[ipc_v1_max_wait_set_sources];
    alignas(16) u8 fpu_state[512];
};

enum class ipc_v1_call_state : u32 { free, queued, delivered, replied };
struct ipc_v1_endpoint_record { bool used; bool closed; };
struct ipc_v1_handle_record {
    bool used;
    u32 endpoint_slot;
    u32 rights;
    u64 value;
    u64 holder_pid;
    u64 badge;
};
struct ipc_v1_notification_record { bool used; u64 pending_bits; };
struct ipc_v1_notification_handle_record {
    bool used; u32 object_slot; u32 rights; u64 value; u64 holder_pid; u64 badge;
};
struct ipc_v1_wait_set_source_record {
    bool used; bool closed; u32 source_id; u32 source_kind; u32 object_slot;
};
struct ipc_v1_wait_set_record {
    bool used; u32 next_source_id;
    ipc_v1_wait_set_source_record sources[ipc_v1_max_wait_set_sources];
};
struct ipc_v1_wait_set_handle_record {
    bool used; u32 object_slot; u32 rights; u64 value; u64 holder_pid; u64 badge;
};
struct ipc_v1_grant_record {
    bool used; u32 page_count; u64 length; u64 pages[ipc_v1_max_grant_pages];
};
struct ipc_v1_grant_handle_record {
    bool used; u32 object_slot; u32 rights; u64 value; u64 holder_pid;
};
struct ipc_v1_grant_mapping_record {
    bool used; u32 grant_slot; u32 page_count; u32 access; u64 map_id; u64 holder_pid; u64 address;
};
struct ipc_v1_call_record {
    ipc_v1_call_state state;
    u32 endpoint_slot;
    u32 caller_thread_slot;
    u64 order;
    u64 caller_pid;
    u64 receiver_pid;
    u64 reply_token;
    u64 deadline_ns;
    u64 label;
    u64 badge;
    u64 reply_label;
    u32 payload_length;
    u32 reply_capacity;
    u32 reply_length;
    u8 payload[ipc_v1_max_message_bytes];
    u8 reply[ipc_v1_max_message_bytes];
};

process_record tasks[8];
struct fork_copy_transaction {
    process_record* owner=nullptr;
    process_record* child=nullptr;
    interrupt_frame* frame=nullptr;
    u64 copy_cursor=0, release_cursor=0;
    u32 released=0;
    i64 fail_after=-1;
};
fork_copy_transaction fork_copies[8];
bool fork_child_staged(const process_record* task) {
    for (const auto& tx : fork_copies)
        if (tx.child==task && tx.owner && tx.owner->continuation.active()) return true;
    return false;
}
anonymous_vm::reservations vm1_probe_regions[8];
struct vm2_failure_injection { i64 page=-1, table=-1, fork=-1; bool trace=false; };
vm2_failure_injection vm2_failures[8];
#if XOS_VM1_PROBE
struct vm2_probe_state {
    u64 pages[4096];
    u32 target, count, fail_after;
    bool prepare_reported, publish_reported, rollback_reported;
    i64 error;
    const u64* process_ticks;
    u64 initial_ticks;
};
vm2_probe_state vm2_probe_states[8];
vm_step vm2_probe_step(void* opaque, vm_phase phase, u32 budget, i64& result) {
    auto& state = *static_cast<vm2_probe_state*>(opaque);
    if (*state.process_ticks != state.initial_ticks) { state.error=process_error_state; }
    if (phase == vm_phase::preparing) {
        if (!state.prepare_reported) { format::text("[vm2-probe] preparing\r\n"); state.prepare_reported=true; }
        while (budget-- && state.count < state.target) {
            if (state.fail_after && state.count == state.fail_after) {
                state.error=process_error_resources; result=state.error; return vm_step::failed;
            }
            u64 physical=0;
            if (allocate_user_page(&physical) != memory_result::none) { state.error=process_error_resources; result=state.error; return vm_step::failed; }
            state.pages[state.count++]=physical;
        }
        return state.count==state.target ? vm_step::prepared : vm_step::again;
    }
    if (phase == vm_phase::publishing || phase == vm_phase::rolling_back) {
        if (phase == vm_phase::publishing && !state.publish_reported) {
            format::text("[vm2-probe] publishing\r\n"); state.publish_reported=true;
        }
        if (phase == vm_phase::rolling_back && !state.rollback_reported) {
            format::text("[vm2-probe] rolling_back\r\n"); state.rollback_reported=true;
        }
        while (budget-- && state.count) {
            if (release_user_page(state.pages[--state.count]) != memory_result::none) { halt(); }
        }
        if (!state.count) { result=state.error; return vm_step::finished; }
        return vm_step::again;
    }
    halt();
}

#endif
thread_record threads[thread_max_total];
ipc_v1_endpoint_record ipc_v1_endpoints[ipc_v1_max_endpoints_system];
ipc_v1_handle_record ipc_v1_handles[ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process];
ipc_v1_call_record ipc_v1_calls[ipc_v1_max_pending_calls];
ipc_v1_notification_record ipc_v1_notifications[ipc_v1_max_notifications_system];
ipc_v1_notification_handle_record ipc_v1_notification_handles[
    ipc_v1_max_notifications_system * ipc_v1_max_handles_per_process];
ipc_v1_wait_set_record ipc_v1_wait_sets[ipc_v1_max_wait_sets_system];
ipc_v1_wait_set_handle_record ipc_v1_wait_set_handles[
    ipc_v1_max_wait_sets_system * ipc_v1_max_handles_per_process];
ipc_v1_grant_record ipc_v1_grants[ipc_v1_max_grants_system];
ipc_v1_grant_handle_record ipc_v1_grant_handles[
    ipc_v1_max_grants_system * ipc_v1_max_handles_per_process];
ipc_v1_grant_mapping_record ipc_v1_grant_mappings[ipc_v1_max_grant_mappings_system];
u64 ipc_v1_next_handle = 1;
u64 ipc_v1_next_reply_token = 1;
u64 ipc_v1_next_wait_order = 1;
u64 ipc_v1_next_map_id = 1;
thread_record* current_thread;
u64 next_vm_continuation_generation = 1;
[[maybe_unused]] bool begin_vm_continuation(process_record& owner, thread_record& thread,
                                             void* context, vm_step_function step) {
    if (thread.process != &owner || thread.state != thread_state::running || owner.closing ||
        !next_vm_continuation_generation ||
        !owner.continuation.begin(thread.tid, next_vm_continuation_generation, context, step)) return false;
    ++next_vm_continuation_generation;
    return true;
}
u64 next_tid = 1;
u64 next_wait_order = 1;
thread_record& main_thread(process_record* process) {
    return threads[static_cast<u32>(process - tasks) * thread_max_per_process];
}

u32 task_total;
u32 cursor;
process_record* current;
u64 next_pid = 1;
endpoint_record endpoints[max_endpoints];
u64 next_endpoint_handle = 1;
ipc_name_record ipc_names[8];
ipc_connection_record ipc_connections[16];
u64 files_pid;
pipe_object pipes[process_max_pipes];
u64 next_pipe_token = process_pipe_token_min;
bool reap_pending[8];
u8 block_buffer[4096];
alignas(16) u8 fpu_template[512];
bool process_trace_enabled = true;
process_guard_info admission_guard{};
stream_lease input_lease{};
u64 pio_com1_owner, pio_com1_controller;
bool pio_com1_quarantined;
u64 pio_speaker_owner, pio_speaker_controller;
u64 pio_speaker_delegated_controller;
u64 irq_owner, irq_token, irq_next_token = 1, irq_sequence;
bool irq_pending, irq_quarantined;
void ready_with(thread_record& thread, i64 result);
void ipc_v1_revoke_process(u64 pid);
void ipc_v1_notify_wait_sets();
u32 ipc_v1_consume_wait_set(u32 object_slot, ipc_v1_wait_event* output, u32 capacity);

void wake_irq_waiters(i64 result) {
    for (auto& thread : threads) {
        if (thread.state == thread_state::blocked && thread.wait_kind == thread_wait_kind::irq_event &&
            thread.wait_target == irq_token) { ready_with(thread, result); }
    }
}
process_record* task_by_pid(u64 pid);
u32 task_index(process_record* task);
void finish_task(process_record* task, process_outcome outcome, i64 code,
                 u64 vector = 0, u64 address = 0, u64 instruction = 0);

void release_irq() {
    if (irq_token == 0) { return; }
    platform::irq_mask(4);
    wake_irq_waiters(process_error_denied);
    irq_owner = irq_token = 0;
    irq_pending = false;
    irq_quarantined = true;
}

void quarantine_com1(process_record* task) {
    if (task == nullptr || pio_com1_owner != task->pid) { return; }
    platform::irq_mask(4);
    release_irq();
    task->io_window_first = task->io_window_length = 0;
    pio_com1_owner = 0;
    pio_com1_controller = 0;
    pio_com1_quarantined = true;
}

void release_pc_speaker(process_record* task) {
    if (task == nullptr || pio_speaker_owner != task->pid) { return; }
    platform::pc_speaker_stop();
    task->pc_speaker_io = false;
    task->pc_speaker_lease_started = false;
    task->pc_speaker_deadline_ns = 0;
    pio_speaker_owner = 0;
    pio_speaker_controller = 0;
    if (task == current) {
        if (!set_user_io_permissions(task->io_window_first, task->io_window_length, false)) {
            format::text("[sched] event=invalid_io_permissions result=halt\r\n");
            halt();
        }
    }
}

void revoke_pc_speaker_controller(process_record* task) {
    if (task == nullptr || pio_speaker_delegated_controller != task->pid) { return; }
    if (pio_speaker_owner != 0 && pio_speaker_controller == task->pid) {
        process_record* owner = task_by_pid(pio_speaker_owner);
        release_pc_speaker(owner);
        if (owner != nullptr && owner != task && owner->state != task_state::dead)
            finish_task(owner, process_outcome::killed, -9);
    }
    task->pc_speaker_controller = false;
    pio_speaker_delegated_controller = 0;
}

void expire_pc_speaker_lease() {
    if (pio_speaker_owner == 0) { return; }
    process_record* owner = task_by_pid(pio_speaker_owner);
    if (owner == nullptr || !owner->pc_speaker_lease_started ||
        clock::monotonic_ns() < owner->pc_speaker_deadline_ns) { return; }
    release_pc_speaker(owner);
}

bool display_endpoint(u64 handle);
void display_wake(u64 handle,i64 result);
void wake_ipc_waiters(u32 handle, i64 result,
                      thread_wait_kind kind = thread_wait_kind::none);
void display_release(u64 pid);
extern u64 display_service_pid;
extern u32 display_request_handle,display_response_handle;
extern bool display_delivered,display_presented;

// Pipe wait keys use a live kernel pipe slot. Closing the final route wakes
// every sleeper before that slot may be reused; no pending I/O pointer is held.
void wake_pipe_waiters(u32 pipe_index, bool readers, bool writers) {
    for (auto& thread : threads) {
        if (thread.state != thread_state::blocked || thread.wait_target != pipe_index) { continue; }
        if ((readers && thread.wait_kind == thread_wait_kind::pipe_read) ||
            (writers && thread.wait_kind == thread_wait_kind::pipe_write)) {
            ready_with(thread, 0);
        }
    }
}

void wake_channel_waiters(u32 handle, bool readers, bool writers, i64 result) {
    for (auto& thread : threads) {
        if (thread.state != thread_state::blocked) { continue; }
        if (thread.wait_kind == thread_wait_kind::channel_many) {
            for (u32 i = 0; i < thread.wait_channel_count; ++i) {
                if (thread.wait_channels[i] == handle) { ready_with(thread, 0); break; }
            }
            continue;
        }
        if (thread.wait_target != handle) { continue; }
        if ((readers && thread.wait_kind == thread_wait_kind::channel_read) ||
            (writers && thread.wait_kind == thread_wait_kind::channel_write)) {
            ready_with(thread, result);
        }
    }
}

void close_channel(endpoint_record& endpoint) {
    wake_channel_waiters(endpoint.handle, true, true, sys_error_invalid_handle);
    endpoint = endpoint_record{};
}

void release_channels(u64 pid, const u32* preserved = nullptr, u32 count = 0) {
    for (auto& endpoint : endpoints) {
        if (endpoint.used && endpoint.generic_channel &&
            (endpoint.owner_pid == pid || endpoint.sender_pid == pid || endpoint.receiver_pid == pid)) {
            bool keep = false;
            for (u32 i = 0; i < count; ++i) if (preserved[i] == endpoint.handle) keep = true;
            if (keep) continue;
            close_channel(endpoint);
        }
    }
}

void fpu_save(u8* state) {
    __asm__ volatile("fxsave64 (%0)" : : "r"(state) : "memory");
}

void fpu_restore(const u8* state) {
    __asm__ volatile("fxrstor64 (%0)" : : "r"(state) : "memory");
}

void fpu_init() {
    u64 cr0 = 0;
    __asm__ volatile("mov %%cr0, %0" : "=r"(cr0));
    cr0 &= ~u64{0x0c}; // clear EM (2) and TS (3)
    cr0 |= 0x02;       // monitor coprocessor
    __asm__ volatile("mov %0, %%cr0" : : "r"(cr0) : "memory");
    u64 cr4 = 0;
    __asm__ volatile("mov %%cr4, %0" : "=r"(cr4));
    cr4 |= (u64{1} << 9) | (u64{1} << 10); // OSFXSR, OSXMMEXCPT
    __asm__ volatile("mov %0, %%cr4" : : "r"(cr4) : "memory");
    __asm__ volatile("fninit" : : : "memory");
    u32 mxcsr = 0x1f80;
    __asm__ volatile("ldmxcsr %0" : : "m"(mxcsr) : "memory");
    fpu_save(fpu_template);
}

void load_address_space(u64 cr3) {
    __asm__ volatile("mov %0, %%cr3" : : "r"(cr3) : "memory");
}

u64 read_cr2() {
    u64 value;
    __asm__ volatile("mov %%cr2, %0" : "=r"(value));
    return value;
}

void copy_name(char (&destination)[12], const char* source) {
    u32 index = 0;
    while (index + 1 < sizeof(destination) && source[index] != '\0') {
        destination[index] = source[index];
        ++index;
    }
    destination[index] = '\0';
}

void copy_bytes(void* destination, const void* source, u64 length) {
    auto* to = static_cast<u8*>(destination);
    auto* from = static_cast<const u8*>(source);
    for (u64 i = 0; i < length; ++i) { to[i] = from[i]; }
}

void append_text(char* buffer, u32& used, u32 capacity, const char* text) {
    for (u32 i = 0; text[i] != '\0' && used + 1 < capacity; ++i) {
        buffer[used++] = text[i];
    }
}

void append_decimal(char* buffer, u32& used, u32 capacity, u64 value) {
    char digits[20];
    u32 count = 0;
    do {
        digits[count++] = static_cast<char>('0' + (value % 10));
        value /= 10;
    } while (value != 0 && count < sizeof(digits));
    while (count > 0 && used + 1 < capacity) {
        buffer[used++] = digits[--count];
    }
}

char state_label(const process_record& task) {
    if (task.state != task_state::free && task.state != task_state::dead && task.state != task_state::building) {
        bool ready = false, fresh = false, blocked = false;
        for (const auto& thread : threads) {
            if (thread.process != &task) { continue; }
            if (thread.state == thread_state::running) { return 'R'; }
            ready = ready || thread.state == thread_state::ready;
            fresh = fresh || thread.state == thread_state::fresh;
            blocked = blocked || thread.state == thread_state::blocked;
        }
        if (ready) { return 'r'; }
        if (fresh) { return 'N'; }
        if (blocked) { return 'W'; }
    }
    switch (task.state) {
    case task_state::running: return 'R';
    case task_state::ready: return 'r';
    case task_state::fresh: return 'N';
    case task_state::building: return 'B';
    case task_state::waiting: return 'W';
    case task_state::dead: return 'D';
    case task_state::free: return '-';
    }
    return '?';
}

void copy_from_user(void* destination, u64 source, u64 length) {
    copy_bytes(destination, reinterpret_cast<const void*>(source), length);
}

void copy_to_user(u64 destination, const void* source, u64 length) {
    copy_bytes(reinterpret_cast<void*>(destination), source, length);
}

bool user_range_ok(u64 address, u64 length, bool write) {
    if (length == 0) { return true; }
    const bool low = address >= user_base && address < user_limit && length <= user_limit-address;
    const bool arena = address >= 0x100000000000ull && address < 0x200000000000ull &&
                       length <= 0x200000000000ull-address;
    if (!low && !arena) { return false; }
    const u64 first = address & ~(page_size - 1);
    const u64 last = (address + length - 1) & ~(page_size - 1);
    for (u64 page = first; page <= last; page += page_size) {
        u64 physical = 0;
        page_permissions permissions{};
        if (query_page(page, &physical, &permissions) != memory_result::none) {
            return false;
        }
        if (!permissions.user) { return false; }
        if (write && !permissions.writable) { return false; }
    }
    return true;
}

// sys_device (device_authorization_v1) segment 1a: request snapshot and
// frozen header validation; known operations are transient device_unknown
// until segments 1b-1e land the grant/map/irq/dma machinery.
void* device_authorize_syscall(interrupt_frame* frame) {
    i64 result = device_unknown;
    const u64 request_address = frame->rdi;
    do {
        if (frame->rsi != 0 || frame->rdx != 0) { result = device_invalid; break; }
        device_request request{};
        if ((request_address & 7) != 0) { result = device_invalid; break; }
        if (!user_range_ok(request_address, sizeof(request), false)) { result = device_fault; break; }
        copy_from_user(&request, request_address, sizeof(request));
        const u32 operation = static_cast<u32>(request.operation);
        if (request.version != 1 || request.size != sizeof(request) || request.reserved != 0 ||
            request.flags != 0 || operation < 1 || operation > 11) { result = device_invalid; break; }
        if (request.deadline_ns != 0 && request.operation != device_operation::irq_wait) {
            result = device_invalid; break;
        }
        if (request.input_length != 0 &&
            (request.input_address == 0 || !user_range_ok(request.input_address, request.input_length, false))) {
            result = device_fault; break;
        }
        if (request.output_length != 0 &&
            (request.output_address == 0 || !user_range_ok(request.output_address, request.output_length, true))) {
            result = device_fault; break;
        }
        result = device_unknown;
    } while (false);
    frame->rax = static_cast<u64>(result);
    return frame;
}

bool rdrand_supported() {
    u32 eax = 1, ebx = 0, ecx = 0, edx = 0;
    __asm__ volatile("cpuid" : "+a"(eax), "=b"(ebx), "+c"(ecx), "=d"(edx) :: "memory");
    return (ecx & (1u << 30)) != 0;
}

bool rdrand_word(u64& value) {
    for (u32 attempt = 0; attempt < 10; ++attempt) {
        u8 ready = 0;
        __asm__ volatile("rdrand %0; setc %1" : "=&r"(value), "=qm"(ready) :: "cc");
        if (ready != 0) { return true; }
    }
    return false;
}

i64 random_bytes(u64 destination, u64 length) {
    if (length > 256) { return random_error_invalid; }
    if (length == 0) { return 0; }
    if (!user_range_ok(destination, length, true)) { return random_error_fault; }
    if (!rdrand_supported()) { return random_error_unsupported; }

    // Stage the complete request so a transient hardware failure never
    // returns a buffer that looks fully initialized but contains a prefix.
    u8 bytes[256];
    for (u64 offset = 0; offset < length;) {
        u64 word = 0;
        if (!rdrand_word(word)) { return random_error_io; }
        const u64 amount = length - offset < sizeof(word) ? length - offset : sizeof(word);
        for (u64 index = 0; index < amount; ++index) {
            bytes[offset + index] = static_cast<u8>(word >> (index * 8));
        }
        offset += amount;
    }
    copy_to_user(destination, bytes, length);
    return 0;
}

pipe_reference* pipe_reference_for(process_record* task, u64 token) {
    if (task == nullptr || token < process_pipe_token_min || token > 0xffffffffull) {
        return nullptr;
    }
    for (auto& reference : task->pipe_references) {
        if (reference.used && reference.token == token) { return &reference; }
    }
    return nullptr;
}

void pipe_retain(u32 pipe_index, bool writable) {
    if (pipe_index >= process_max_pipes || !pipes[pipe_index].used) { return; }
    ++pipes[pipe_index].references;
    if (writable) { ++pipes[pipe_index].writer_references; }
    else { ++pipes[pipe_index].reader_references; }
}

void pipe_release(u32 pipe_index, bool writable) {
    if (pipe_index >= process_max_pipes || !pipes[pipe_index].used) { return; }
    pipe_object& pipe = pipes[pipe_index];
    if (pipe.references != 0) { --pipe.references; }
    if (writable) {
        if (pipe.writer_references != 0) { --pipe.writer_references; }
    } else if (pipe.reader_references != 0) { --pipe.reader_references; }
    // A raw close may invalidate a sleeping token/route even when another
    // reference of that direction survives. Wake all and require revalidation.
    wake_pipe_waiters(pipe_index, true, true);
    // This also covers EOF/EPIPE, before a final release can reuse the slot.
    if (pipe.references == 0) { pipe = pipe_object{}; }
}

void stdio_route_release(process_record* owner, stdio_route& route) {
    if (route.valid && !route.console) {
        pipe_release(route.pipe_index, route.writable);
        if (owner != nullptr && owner->pipe_reference_count != 0) { --owner->pipe_reference_count; }
    }
    route = stdio_route{};
}

void task_pipe_release_all(process_record* task) {
    for (auto& reference : task->pipe_references) {
        if (!reference.used) { continue; }
        pipe_release(reference.pipe_index, reference.writable);
        if (task->pipe_reference_count != 0) { --task->pipe_reference_count; }
        reference = pipe_reference{};
    }
    for (auto& route : task->stdio) { stdio_route_release(task, route); }
}

bool stdio_route_copy(process_record* owner, stdio_route& destination, const stdio_route& source) {
    if (!source.valid) { return false; }
    if (!source.console &&
        (owner == nullptr || owner->pipe_reference_count >= process_max_pipe_refs)) { return false; }
    destination = source;
    if (!source.console) {
        pipe_retain(source.pipe_index, source.writable);
        ++owner->pipe_reference_count;
    }
    return true;
}

bool inherit_stdio(process_record* child, process_record* parent, u32 mask) {
    child->stdio_mask = 0;
    for (auto& route : child->stdio) { route = stdio_route{}; }
    for (u32 fd = 0; fd < 3; ++fd) {
        if ((mask & (1u << fd)) == 0) { continue; }
        if (!stdio_route_copy(child, child->stdio[fd], parent->stdio[fd])) { return false; }
        child->stdio_mask |= 1u << fd;
    }
    return true;
}

process_record* free_slot() {
    for (u32 i = 0; i < 8; ++i) {
        if (tasks[i].state == task_state::free) { return &tasks[i]; }
    }
    return nullptr;
}

bool map_user(u64 cr3, u64 virtual_address, u64 physical, page_permissions permissions) {
    return map_page_in(cr3, virtual_address, physical, permissions) == memory_result::none;
}

void destroy_task(process_record* task);

process_record* prepare_task(const char* name) {
    process_record* task = free_slot();
    if (task == nullptr || next_pid == 0 || next_pid > 0x7fffffffffffffff ||
        next_tid == 0 || next_tid > 0x7fffffffffffffff) { return nullptr; }
    *task = process_record{};
    vm1_probe_regions[static_cast<u32>(task - tasks)].clear();
    vm2_failures[static_cast<u32>(task - tasks)] = vm2_failure_injection{};
    task->pid = next_pid++;
    copy_name(task->name, name);
    task->cr3 = create_address_space();
    if (task->cr3 == 0) { *task = process_record{}; return nullptr; }
    u64 kernel_stack = 0;
    if (allocate_page(&kernel_stack) != memory_result::none) {
        (void)destroy_address_space(task->cr3); *task = process_record{}; return nullptr;
    }
    auto& thread = main_thread(task);
    thread = thread_record{};
    thread.process = task;
    thread.tid = next_tid++;
    thread.main = true;
    thread.state = thread_state::fresh;
    thread.kernel_stack_top = kernel_stack + kernel_stack_bytes;
    thread.stack_bottom = process_stack_bottom;
    thread.stack_top = process_startup_begin;
    copy_bytes(thread.fpu_state, fpu_template, sizeof(fpu_template));
    task->state = task_state::building;
    task->entry = user_base;
    task->initial_stack = user_stack_top;
    task->stdio_mask = 7;
    task->heap_break = process_heap_begin;
    for (u32 fd = 0; fd < 3; ++fd) {
        task->stdio[fd] = {true, true, fd != 0, 0};
    }
    ++task_total;
    return task;
}

bool add_user_page(process_record* task, u64 address, const u8* bytes, u32 size,
                   u32 offset, page_permissions permissions) {
    if (task->user_pages == process_max_pages || offset > page_size || size > page_size - offset) {
        return false;
    }
    u64 physical = 0;
    if (allocate_user_page(&physical) != memory_result::none) { return false; }
    if (size != 0) { copy_bytes(reinterpret_cast<u8*>(physical) + offset, bytes, size); }
    if (!map_user(task->cr3, address, physical, permissions)) {
        (void)release_user_page(physical); return false;
    }
    ++task->user_pages;
    return true;
}

process_record* create_task(const char* name, const u8* blob, u32 size) {
    if (size == 0 || size > 32 * 1024) { return nullptr; }
    process_record* task = prepare_task(name);
    if (task == nullptr) { return nullptr; }

    const u32 code_pages = static_cast<u32>((size + page_size - 1) / page_size);
    for (u32 i = 0; i < code_pages; ++i) {
        const u32 offset = i * static_cast<u32>(page_size);
        const u32 chunk = (size - offset) > page_size
                              ? static_cast<u32>(page_size)
                              : size - offset;
        if (!add_user_page(task, user_base + offset, blob + offset, chunk, 0, {false, true, true})) {
            destroy_task(task); return nullptr;
        }
    }

    if (!add_user_page(task, user_data_address, nullptr, 0, 0, {true, false, true})) {
        destroy_task(task); return nullptr;
    }

    for (u32 i = 0; i < 4; ++i) {
        if (!add_user_page(task, user_stack_bottom + i * page_size, nullptr, 0, 0, {true, false, true})) {
            destroy_task(task); return nullptr;
        }
    }

    main_thread(task).stack_bottom = user_stack_bottom;
    main_thread(task).stack_top = user_stack_top;
    task->state = task_state::fresh;
    format::text("[task] event=created pid=");
    format::decimal(task->pid);
    format::text(" name=");
    format::text(task->name);
    format::text("\r\n");
    return task;
}

process_record* create_supervisor() {
    using namespace user_images;
    process_record* task = prepare_task("supervisor");
    if (task == nullptr) { return nullptr; }
    for (const auto& segment : bootstrap_segments) {
        const u64 first = segment.address & ~(page_size - 1);
        const u64 end = (segment.address + segment.memory + page_size - 1) & ~(page_size - 1);
        for (u64 address = first; address < end; address += page_size) {
            const u64 from = address > segment.address ? address : segment.address;
            u64 to = segment.address + segment.files;
            if (to > address + page_size) { to = address + page_size; }
            const u32 length = from < to ? static_cast<u32>(to - from) : 0;
            const auto* source = length == 0 ? nullptr : supervisor + segment.offset + from - segment.address;
            if (!add_user_page(task, address, source, length, static_cast<u32>(from - address),
                               {(segment.permissions & 2) != 0, (segment.permissions & 1) != 0, true})) {
                destroy_task(task); return nullptr;
            }
        }
    }
    for (u64 address = process_stack_bottom; address < process_stack_top; address += page_size) {
        if (!add_user_page(task, address, nullptr, 0, 0, {true, false, true})) {
            destroy_task(task); return nullptr;
        }
    }
    task->entry = bootstrap_entry;
    task->initial_stack = process_stack_top - 16;
    main_thread(task).stack_top = process_stack_top;
    task->supervisor = true;
    task->can_create = true;
    task->state = task_state::fresh;
    format::text("[task] event=created pid="); format::decimal(task->pid);
    format::text(" name=supervisor bootstrap=trusted_segments\r\n");
    return task;
}

process_record* create_files_service() {
    using namespace user_images;
    process_record* task = prepare_task("files");
    if (task == nullptr) { return nullptr; }
    for (const auto& segment : bootstrap_segments_files) {
        const u64 first = segment.address & ~(page_size - 1);
        const u64 end = (segment.address + segment.memory + page_size - 1) & ~(page_size - 1);
        for (u64 address = first; address < end; address += page_size) {
            const u64 from = address > segment.address ? address : segment.address;
            u64 to = segment.address + segment.files;
            if (to > address + page_size) { to = address + page_size; }
            const u32 length = from < to ? static_cast<u32>(to - from) : 0;
            const auto* source = length == 0 ? nullptr : files + segment.offset + from - segment.address;
            if (!add_user_page(task, address, source, length, static_cast<u32>(from - address),
                               {(segment.permissions & 2) != 0, (segment.permissions & 1) != 0, true})) {
                destroy_task(task); return nullptr;
            }
        }
    }
    for (u64 address = process_stack_bottom; address < process_stack_top; address += page_size) {
        if (!add_user_page(task, address, nullptr, 0, 0, {true, false, true})) {
            destroy_task(task); return nullptr;
        }
    }
    task->entry = bootstrap_entry_files;
    task->initial_stack = process_stack_top - 16;
    main_thread(task).stack_top = process_stack_top;
    task->stdio_mask = 0;
    for (auto& route : task->stdio) { route = stdio_route{}; }
    task->block_access = true;
    task->state = task_state::fresh;
    format::text("[task] event=created pid="); format::decimal(task->pid);
    format::text(" name=files bootstrap=trusted_segments\r\n");
    return task;
}

u32 endpoint_attach(u64 receiver_pid, u64 sender_pid, u64 owner_pid, u32 capacity,
                    bool session_response = false) {
    if (next_endpoint_handle > 0xffffffffull) { return 0; }
    for (u32 i = 0; i < max_endpoints; ++i) {
        if (!endpoints[i].used) {
            endpoints[i] = endpoint_record{};
            endpoints[i].used = true;
            endpoints[i].handle = static_cast<u32>(next_endpoint_handle++);
            endpoints[i].receiver_pid = receiver_pid;
            endpoints[i].sender_pid = sender_pid;
            endpoints[i].owner_pid = owner_pid;
            endpoints[i].capacity = capacity;
            endpoints[i].session_response = session_response;
            return endpoints[i].handle;
        }
    }
    return 0;
}

endpoint_record* endpoint_for(u64 handle) {
    if (handle == 0 || handle > 0xffffffffull) { return nullptr; }
    for (auto& endpoint : endpoints) {
        if (endpoint.used && endpoint.handle == handle) { return &endpoint; }
    }
    return nullptr;
}

void wake_ipc_waiters(u32 handle, i64 result, thread_wait_kind kind) {
    for (auto& thread : threads) {
        if (thread.state == thread_state::blocked && thread.wait_target == handle &&
            (thread.wait_kind == thread_wait_kind::ipc_receive ||
             thread.wait_kind == thread_wait_kind::ipc_send) &&
            (kind == thread_wait_kind::none || thread.wait_kind == kind)) {
            ready_with(thread, result);
        }
    }
}

void revoke_ipc_channel(u32 channel_id, i64 wake_result) {
    for (auto& connection : ipc_connections) {
        if (connection.used && connection.channel_id == channel_id) {
            connection = ipc_connection_record{};
        }
    }
    for (auto& endpoint : endpoints) {
        if (!endpoint.used || !endpoint.generic || endpoint.channel_id != channel_id) { continue; }
        wake_ipc_waiters(endpoint.handle, wake_result);
        endpoint = endpoint_record{};
    }
}

process_record* task_by_pid(u64 pid) {
    for (auto& task : tasks) {
        if (task.state != task_state::free && task.pid == pid) { return &task; }
    }
    return nullptr;
}

bool copy_ipc_name(u64 address, char (&name)[32]) {
    if (address == 0) return false;
    for (u32 i = 0; i < sizeof(name); ++i) {
        if (address > ~u64{0} - i || !user_range_ok(address + i, 1, false)) return false;
        copy_from_user(&name[i], address + i, 1);
        const char value = name[i];
        if (value == '\0') return i != 0;
        if (!((value >= 'a' && value <= 'z') || (value >= '0' && value <= '9') ||
              value == '-' || value == '_' || value == '.')) return false;
    }
    return false;
}

ipc_name_record* find_ipc_name(const char* name) {
    for (auto& entry : ipc_names) {
        if (!entry.used) continue;
        u32 i = 0;
        while (name[i] != '\0' && entry.name[i] == name[i]) ++i;
        if (name[i] == '\0' && entry.name[i] == '\0') return &entry;
    }
    return nullptr;
}

bool ipc_service_published(u64 pid) {
    for (const auto& entry : ipc_names) if (entry.used && entry.owner_pid == pid) return true;
    return false;
}

bool create_generic_channel(u64 sender_pid, u64 receiver_pid, u64 owner_pid,
                            ipc_channel& sender_channel, ipc_channel& receiver_channel) {
    if (sender_pid == 0 || receiver_pid == 0 || sender_pid == receiver_pid ||
        next_endpoint_handle > 0xfffffffeull) return false;
    u32 free_count = 0;
    for (const auto& endpoint : endpoints) if (!endpoint.used) ++free_count;
    if (free_count < 2) return false;
    const u32 request = endpoint_attach(receiver_pid, sender_pid, owner_pid, file_message_bytes);
    const u32 response = endpoint_attach(sender_pid, receiver_pid, owner_pid, file_message_bytes);
    if (request == 0 || response == 0) {
        if (auto* endpoint = endpoint_for(request)) *endpoint = endpoint_record{};
        if (auto* endpoint = endpoint_for(response)) *endpoint = endpoint_record{};
        return false;
    }
    auto* request_endpoint = endpoint_for(request);
    auto* response_endpoint = endpoint_for(response);
    request_endpoint->generic = true;
    request_endpoint->channel_id = request;
    response_endpoint->generic = true;
    response_endpoint->channel_id = request;
    sender_channel = {request, response};
    receiver_channel = {response, request};
    return true;
}

void wake_ipc_acceptors(u64 service_pid, i64 result) {
    for (auto& thread : threads) {
        if (thread.state == thread_state::blocked && thread.process != nullptr &&
            thread.process->pid == service_pid && thread.wait_kind == thread_wait_kind::ipc_accept) {
            ready_with(thread, result);
        }
    }
}

bool files_service_live() {
    process_record* service = task_by_pid(files_pid);
    return files_pid != 0 && service != nullptr && service->block_access &&
           service->state != task_state::building && service->state != task_state::dead;
}

i64 ipc_send(u64 handle, u64 address, u64 length) {
    endpoint_record* endpoint = endpoint_for(handle);
    if (endpoint == nullptr || current == nullptr || endpoint->sender_pid != current->pid ||
        (current->send_handle != handle &&
         !(current->block_access && endpoint->session_response) && !display_endpoint(handle) &&
         !endpoint->generic_channel && !endpoint->generic)) {
        return sys_error_invalid_handle;
    }
    if (endpoint->receiver_pid == current->pid || length == 0 || length > endpoint->capacity) {
        return sys_error_invalid_argument;
    }
    process_record* receiver = task_by_pid(endpoint->receiver_pid);
    if (receiver == nullptr || receiver->state == task_state::dead ||
        receiver->state == task_state::building ||
        ((endpoint->generic_channel || endpoint->generic) && receiver->closing)) {
        return (endpoint->generic_channel || endpoint->generic) ? pipe_error_broken : sys_error_invalid_handle;
    }
    if (endpoint->pending || (handle==display_request_handle && display_delivered)) { return sys_error_full; }
    if (handle==display_response_handle && !display_delivered) {return sys_error_invalid_argument;}
    if (!user_range_ok(address, length, false)) { return sys_error_invalid_argument; }
    copy_from_user(endpoint->data, address, length);
    endpoint->length = static_cast<u32>(length);
    endpoint->pending = true;
    if (endpoint->generic_channel) { wake_channel_waiters(endpoint->handle, true, false, 0); }
    if (endpoint->generic) { wake_ipc_waiters(endpoint->handle, 0, thread_wait_kind::ipc_receive); }
    if(handle==display_response_handle){display_delivered=false;display_presented=false;}
    if(display_endpoint(handle)){display_wake(handle,0);}
    return 0;
}

i64 ipc_recv(u64 handle, u64 address, u64 length) {
    endpoint_record* endpoint = endpoint_for(handle);
    if (endpoint == nullptr || current == nullptr || endpoint->receiver_pid != current->pid ||
        (current->recv_handle != handle && !current->block_access && !display_endpoint(handle) &&
         !endpoint->generic_channel && !endpoint->generic)) {
        return sys_error_invalid_handle;
    }
    if (!user_range_ok(address, length, true)) { return sys_error_invalid_argument; }
    if (endpoint->generic && !endpoint->pending) {
        const process_record* sender = task_by_pid(endpoint->sender_pid);
        if (sender == nullptr || sender->state == task_state::dead || sender->closing) {
            return pipe_error_broken;
        }
    }
    if (!endpoint->pending) { return sys_error_empty; }
    if (length < endpoint->length) { return sys_error_invalid_argument; }
    copy_to_user(address, endpoint->data, endpoint->length);
    const u32 length_received = endpoint->length;
    endpoint->pending = false;
    if (endpoint->generic_channel) { wake_channel_waiters(endpoint->handle, false, true, 0); }
    if (endpoint->generic) { wake_ipc_waiters(endpoint->handle, 0, thread_wait_kind::ipc_send); }
    if(handle==display_request_handle){display_delivered=true;display_presented=false;}
    else {endpoint->length = 0;}
    return static_cast<i64>(length_received);
}

i64 pipe_read_from(u32 pipe_index, u64 address, u64 length) {
    if (pipe_index >= process_max_pipes || !pipes[pipe_index].used) {
        return process_error_invalid;
    }
    if (length == 0) { return 0; }
    pipe_object& pipe = pipes[pipe_index];
    if (pipe.length == 0) {
        return pipe.writer_references == 0 ? 0 : process_error_would_block;
    }
    const u64 amount64 = length < pipe.length ? length : pipe.length;
    const u32 amount = static_cast<u32>(amount64);
    if (!user_range_ok(address, amount, true)) { return process_error_invalid; }
    for (u32 i = 0; i < amount; ++i) {
        const u32 offset = (pipe.head + i) % process_pipe_bytes;
        copy_to_user(address + i, &pipe.data[offset], 1);
    }
    pipe.head = (pipe.head + amount) % process_pipe_bytes;
    pipe.length -= amount;
    wake_pipe_waiters(pipe_index, false, true);
    return amount;
}

i64 pipe_write_to(u32 pipe_index, u64 address, u64 length, bool atomic = false) {
    if (pipe_index >= process_max_pipes || !pipes[pipe_index].used) {
        return process_error_invalid;
    }
    if (length == 0) { return 0; }
    pipe_object& pipe = pipes[pipe_index];
    if (pipe.reader_references == 0) { return pipe_error_broken; }
    const u32 available = process_pipe_bytes - pipe.length;
    if (atomic && length > process_pipe_bytes) { return process_error_invalid; }
    if (available == 0 || (atomic && length > available)) {
        return process_error_would_block;
    }
    const u64 amount64 = length < available ? length : available;
    const u32 amount = static_cast<u32>(amount64);
    if (!user_range_ok(address, amount, false)) { return process_error_invalid; }
    const u32 tail = (pipe.head + pipe.length) % process_pipe_bytes;
    for (u32 i = 0; i < amount; ++i) {
        copy_from_user(&pipe.data[(tail + i) % process_pipe_bytes], address + i, 1);
    }
    pipe.length += amount;
    wake_pipe_waiters(pipe_index, true, false);
    return amount;
}

i64 stdio_read(process_record* task, u32 fd, u64 address, u64 length,
               bool console_empty_is_error) {
    if (fd >= 3 || task == nullptr || (task->stdio_mask & (1u << fd)) == 0 ||
        !task->stdio[fd].valid || task->stdio[fd].writable) { return process_error_denied; }
    if (length == 0) { return 0; }
    const stdio_route& route = task->stdio[fd];
    if (!route.console) { return pipe_read_from(route.pipe_index, address, length); }
    if (!platform::debug_serial_attached()) { return process_error_denied; }
    if (input_lease.active() && input_lease.holder() != task->pid) { return process_error_denied; }
    if (!user_range_ok(address, 1, true)) { return process_error_invalid; }
    const int value = platform::debug_read();
    if (value < 0) { return console_empty_is_error ? process_error_would_block : 0; }
    const u8 byte = static_cast<u8>(value);
    copy_to_user(address, &byte, 1);
    return 1;
}

i64 stdio_write(process_record* task, u32 fd, u64 address, u64 length, bool atomic = false) {
    if (fd >= 3 || task == nullptr || (task->stdio_mask & (1u << fd)) == 0 ||
        !task->stdio[fd].valid || !task->stdio[fd].writable) { return process_error_denied; }
    if (length == 0) { return 0; }
    const stdio_route& route = task->stdio[fd];
    if (!route.console) { return pipe_write_to(route.pipe_index, address, length, atomic); }
    if (length > 256 || !user_range_ok(address, length, false)) { return process_error_invalid; }
    u8 bytes[256];
    copy_from_user(bytes, address, length);
    return platform::debug_write_bytes(bytes, length);
}

void pipe_reference_close(process_record* task, pipe_reference* reference) {
    if (task == nullptr || reference == nullptr || !reference->used) { return; }
    pipe_release(reference->pipe_index, reference->writable);
    if (task->pipe_reference_count != 0) { --task->pipe_reference_count; }
    *reference = pipe_reference{};
}

i64 block_status(block::result result) {
    switch (result) {
    case block::result::none: return 0;
    case block::result::no_device: return block_error_no_device;
    case block::result::invalid: return block_error_invalid;
    case block::result::io: return block_error_io;
    case block::result::timeout: return block_error_timeout;
    }
    return block_error_io;
}

u32 task_index(process_record* task) {
    return static_cast<u32>(task - tasks);
}

void mark_reap(process_record* task) {
    if (task != nullptr) { reap_pending[task_index(task)] = true; }
}

// This always runs on a different process's kernel stack. Shared pages have one owner.
void destroy_task(process_record* task) {
    if (task == nullptr || task->state == task_state::free || task == current || task->continuation.active() ||
        fork_child_staged(task)) { return; }
    release_pc_speaker(task);
    revoke_pc_speaker_controller(task);
    quarantine_com1(task);
    release_channels(task->pid);
    (void)input_lease.remove(task->pid);
    reap_pending[task_index(task)] = false;
    const u64 pid = task->pid;
    ipc_v1_revoke_process(pid);
    for (auto& entry : ipc_names) {
        if (entry.used && entry.owner_pid == pid) entry = ipc_name_record{};
    }
    wake_ipc_acceptors(pid, pipe_error_broken);
    for (auto& connection : ipc_connections) {
        if (!connection.used || (connection.service_pid != pid && connection.client_pid != pid)) continue;
        const u32 channel_id = connection.channel_id;
        revoke_ipc_channel(channel_id, pipe_error_broken);
        connection = ipc_connection_record{};
    }
    for (auto& endpoint : endpoints) {
        if (!endpoint.used || (endpoint.owner_pid != pid && endpoint.receiver_pid != pid &&
                               endpoint.sender_pid != pid)) { continue; }
        if (endpoint.generic) { revoke_ipc_channel(endpoint.channel_id, pipe_error_broken); }
        else { endpoint = endpoint_record{}; }
    }
    task_pipe_release_all(task);
    u64 freed = 0;
    for (auto& thread : threads) {
        if (thread.process != task) { continue; }
        if (thread.kernel_stack_top != 0 &&
            release_page(thread.kernel_stack_top - kernel_stack_bytes) == memory_result::none) { ++freed; }
        thread = thread_record{};
    }
    if (task->cr3 != 0) { freed += destroy_address_space(task->cr3); }
    vm1_probe_regions[static_cast<u32>(task - tasks)].clear();
    vm2_failures[static_cast<u32>(task - tasks)] = vm2_failure_injection{};
    *task = process_record{};
    if (task_total > 0) { --task_total; }
    if (process_trace_enabled) {
        format::text("[task] event=reclaimed pid="); format::decimal(pid);
        format::text(" pages="); format::decimal(freed); format::text("\r\n");
    }
}

void reap_dead() {
    for (u32 i = 0; i < 8; ++i) {
        if (reap_pending[i] && &tasks[i] != current) { destroy_task(&tasks[i]); }
    }
}

completion_record* completion_for(u64 parent, u64 pid) {
    for (auto& item : completions) {
        if (item.used && item.parent == parent && item.status.pid == pid) { return &item; }
    }
    return nullptr;
}

void finish_task(process_record* task, process_outcome outcome, i64 code,
                  u64 vector, u64 address, u64 instruction) {
    if (task->state == task_state::dead) { return; }
    ipc_v1_revoke_process(task->pid);
    release_pc_speaker(task);
    revoke_pc_speaker_controller(task);
    if (task->continuation.active()) {
        if (!task->continuation.cancelled) {
            task->deferred_outcome=outcome; task->deferred_code=code;
            task->deferred_vector=vector; task->deferred_address=address; task->deferred_instruction=instruction;
            task->closing=true; task->continuation.cancel();
            // Preserve the existing process-tree cancellation semantics even
            // when this task needs multiple batches to release its resources.
            for (auto& child : tasks) {
                if (child.state != task_state::free && child.parent == task->pid) {
                    finish_task(&child, process_outcome::killed, -9);
                }
            }
        }
        return;
    }
    quarantine_com1(task);
    release_channels(task->pid);
    (void)input_lease.remove(task->pid);
    display_release(task->pid);
    task->closing = true;
    task->state = task_state::dead;
    for (auto& thread : threads) {
        if (thread.process == task && thread.state != thread_state::free) {
            thread.state = thread_state::dead;
            thread.user_pin.clear();
            thread.wait_kind = thread_wait_kind::none;
        }
    }
    task->exit_code = static_cast<i32>(code);
    if (task->completion_slot != 0) {
        auto& item = completions[task->completion_slot - 1];
        item.status = {1, outcome, task->pid, code, vector, address, instruction};
        item.ready = true;
        for (auto& parent : threads) {
            if (parent.process != nullptr && parent.process->pid == task->parent &&
                parent.state == thread_state::blocked && parent.wait_kind == thread_wait_kind::process &&
                parent.wait_target == task->pid) { parent.state = thread_state::ready; }
        }
    }
    // Builder authority is not inherited. Losing the builder cancels its children.
    for (auto& child : tasks) {
        if (child.state != task_state::free && child.parent == task->pid) {
            finish_task(&child, process_outcome::killed, -9);
        }
    }
    for (auto& item : completions) {
        if (item.used && item.parent == task->pid) { item = completion_record{}; }
    }
    mark_reap(task);
}

bool cancel_foreground() {
    if (platform::debug_peek() != 27) { return false; }
    for (auto& parent : threads) {
        if (parent.state != thread_state::blocked || parent.wait_kind != thread_wait_kind::process ||
            parent.process == nullptr || !parent.process->supervisor) { continue; }
        process_record* target = nullptr;
        u64 expected_parent = parent.process->pid;
        u64 expected_pid = parent.wait_target;
        for (u32 depth = 0; depth < 8; ++depth) {
            process_record* next = nullptr;
            for (auto& child : tasks) {
                if (child.pid == expected_pid && child.parent == expected_parent &&
                    child.state != task_state::free && child.state != task_state::dead) {
                    next = &child; break;
                }
            }
            if (next == nullptr) { break; }
            target = next;
            if (next->foreground_active) {
                (void)platform::debug_read();
                next->foreground_cancelled = true;
                for (u32 i = 0; i < next->foreground.count; ++i) {
                    for (auto& member : tasks) {
                        if (member.pid == next->foreground.pids[i] && member.parent == next->pid &&
                            member.state != task_state::free && member.state != task_state::dead) {
                            finish_task(&member, process_outcome::killed, -27);
                        }
                    }
                }
                format::text("[process] event=cancelled_by_escape pipeline_parent=");
                format::decimal(next->pid); format::text("\r\n");
                return true;
            }
            thread_record* waiter = nullptr;
            for (auto& thread : threads) {
                if (thread.process == next && thread.state == thread_state::blocked &&
                    thread.wait_kind == thread_wait_kind::process && thread.wait_target != 0) {
                    waiter = &thread; break;
                }
            }
            if (waiter == nullptr) { break; }
            expected_parent = next->pid;
            expected_pid = waiter->wait_target;
        }
        if (target != nullptr) {
            (void)platform::debug_read();
            const u64 pid = target->pid;
            finish_task(target, process_outcome::killed, -27);
            format::text("[process] event=cancelled_by_escape pid="); format::decimal(pid);
            format::text("\r\n");
            return true;
        }
    }
    return false;
}

void deliver_wait(thread_record* thread, interrupt_frame* frame) {
    if (thread->wait_kind == thread_wait_kind::ipc_v1_wait_set) {
        ipc_v1_wait_set_wait request{};
        const u32 count = frame->rax == 0 ? thread->ipc_v1_event_count :
            (frame->rax == static_cast<u64>(ipc_v1_error::buffer_too_small) ? thread->ipc_v1_event_count : 0);
        if (frame->rax == 0 && count == 0) { frame->rax = static_cast<u64>(ipc_v1_error::would_block); }
        if (user_range_ok(thread->ipc_v1_request_address, sizeof(request), true)) {
            copy_from_user(&request, thread->ipc_v1_request_address, sizeof(request));
            request.count_out = count;
            copy_to_user(thread->ipc_v1_request_address, &request, sizeof(request));
            if (frame->rax == 0 && count != 0) {
                copy_to_user(thread->ipc_v1_payload_address, thread->ipc_v1_events,
                             static_cast<u64>(count) * sizeof(ipc_v1_wait_event));
            }
        } else { frame->rax = static_cast<u64>(ipc_v1_error::address); }
        for (auto& pin : thread->ipc_v1_pins) { pin.clear(); }
        thread->ipc_v1_request_address = thread->ipc_v1_payload_address = 0;
        thread->ipc_v1_payload_capacity = thread->ipc_v1_event_count = 0;
        thread->wait_kind = thread_wait_kind::none;
        return;
    }
    if (thread->wait_kind == thread_wait_kind::ipc_v1_notification) {
        ipc_v1_notification_wait request{};
        if (user_range_ok(thread->ipc_v1_request_address, sizeof(request), true)) {
            copy_from_user(&request, thread->ipc_v1_request_address, sizeof(request));
            request.bits_out = frame->rax == 0 ? thread->ipc_v1_label : 0;
            copy_to_user(thread->ipc_v1_request_address, &request, sizeof(request));
        } else { frame->rax = static_cast<u64>(ipc_v1_error::address); }
        for (auto& pin : thread->ipc_v1_pins) { pin.clear(); }
        thread->ipc_v1_request_address = 0;
        thread->ipc_v1_label = 0;
        thread->wait_kind = thread_wait_kind::none;
        return;
    }
    if (thread->wait_kind == thread_wait_kind::ipc_v1_call) {
        ipc_v1_call request{};
        const bool valid = user_range_ok(thread->ipc_v1_request_address, sizeof(request), true) &&
            user_range_ok(thread->ipc_v1_reply_address, thread->ipc_v1_length, true);
        if (valid) {
            copy_from_user(&request, thread->ipc_v1_request_address, sizeof(request));
            request.reply_length_out = thread->ipc_v1_length;
            request.phase_out = thread->ipc_v1_phase;
            request.reply_label_out = thread->ipc_v1_label;
            copy_to_user(thread->ipc_v1_request_address, &request, sizeof(request));
            if (frame->rax == 0 && thread->ipc_v1_phase == static_cast<u32>(ipc_v1_call_phase::replied) &&
                thread->ipc_v1_length != 0) {
                copy_to_user(thread->ipc_v1_reply_address, thread->ipc_v1_payload, thread->ipc_v1_length);
            }
        } else { frame->rax = static_cast<u64>(ipc_v1_error::address); }
        for (auto& pin : thread->ipc_v1_pins) { pin.clear(); }
        thread->wait_kind = thread_wait_kind::none;
        thread->wait_target = 0;
        thread->ipc_v1_request_address = thread->ipc_v1_reply_address = 0;
        thread->ipc_v1_length = thread->ipc_v1_phase = 0;
        thread->ipc_v1_label = 0;
        return;
    }
    if (thread->wait_kind == thread_wait_kind::ipc_v1_receive) {
        bool valid = user_range_ok(thread->ipc_v1_request_address, sizeof(ipc_v1_receive), true) &&
            (frame->rax != 0 || user_range_ok(thread->ipc_v1_payload_address, thread->ipc_v1_length, true));
        if (thread->ipc_v1_wait_action == static_cast<u32>(ipc_v1_action::reply_receive)) {
            ipc_v1_reply_receive request{};
            valid = user_range_ok(thread->ipc_v1_request_address, sizeof(request), true) &&
                (frame->rax != 0 || user_range_ok(thread->ipc_v1_payload_address, thread->ipc_v1_length, true));
            if (valid) {
                copy_from_user(&request, thread->ipc_v1_request_address, sizeof(request));
                request.reply_consumed_out = thread->ipc_v1_reply_consumed;
                request.receive_length_out = thread->ipc_v1_length;
                request.label_out = thread->ipc_v1_label;
                request.badge_out = thread->ipc_v1_badge;
                request.next_reply_token_out = thread->ipc_v1_token;
                copy_to_user(thread->ipc_v1_request_address, &request, sizeof(request));
            }
        } else if (valid) {
            ipc_v1_receive request{};
            copy_from_user(&request, thread->ipc_v1_request_address, sizeof(request));
            request.message_length_out = thread->ipc_v1_length;
            request.label_out = thread->ipc_v1_label;
            request.badge_out = thread->ipc_v1_badge;
            request.reply_token_out = thread->ipc_v1_token;
            copy_to_user(thread->ipc_v1_request_address, &request, sizeof(request));
        }
        if (valid && frame->rax == 0 && thread->ipc_v1_length != 0) {
            copy_to_user(thread->ipc_v1_payload_address, thread->ipc_v1_payload, thread->ipc_v1_length);
        }
        if (!valid) { frame->rax = static_cast<u64>(ipc_v1_error::address); }
        for (auto& pin : thread->ipc_v1_pins) { pin.clear(); }
        thread->wait_kind = thread_wait_kind::none;
        thread->wait_target = 0;
        thread->ipc_v1_request_address = thread->ipc_v1_payload_address = 0;
        thread->ipc_v1_length = 0;
        thread->ipc_v1_label = thread->ipc_v1_badge = thread->ipc_v1_token = 0;
        thread->ipc_v1_wait_action = thread->ipc_v1_reply_consumed = 0;
        return;
    }
    if (thread->wait_kind != thread_wait_kind::process) { return; }
    completion_record* item = completion_for(thread->process->pid, thread->wait_target);
    if (item == nullptr || !item->ready) { return; }
    if (user_range_ok(thread->wait_buffer, sizeof(process_status), true)) {
        copy_to_user(thread->wait_buffer, &item->status, sizeof(process_status));
        *item = completion_record{};
        frame->rax = 0;
    } else { frame->rax = static_cast<u64>(process_error_invalid); }
    thread->user_pin.clear();
    thread->wait_kind = thread_wait_kind::none;
    thread->wait_target = 0;
}

thread_record* pick_ready() {
    for (u32 i = 0; i < thread_max_total; ++i) {
        const u32 index = (cursor + i) % thread_max_total;
        thread_record& thread = threads[index];
        if (thread.process == nullptr || thread.process->state == task_state::building ||
            thread.process->state == task_state::dead) { continue; }
        if (thread.process->continuation.active() &&
            thread.tid != thread.process->continuation.owner_tid) { continue; }
        if (thread.state == thread_state::ready || thread.state == thread_state::fresh) {
            cursor = (index + 1) % thread_max_total;
            return &thread;
        }
    }
    return nullptr;
}

void set_thread_pointer(u64 pointer) {
    const u32 low = static_cast<u32>(pointer), high = static_cast<u32>(pointer >> 32);
    __asm__ volatile("wrmsr" : : "c"(0xc0000100u), "a"(low), "d"(high) : "memory");
}

void switch_to(thread_record* thread) {
    current_thread = thread;
    current = thread->process;
    current->state = task_state::running;
    thread->state = thread_state::running;
    if (current->pc_speaker_io && !current->pc_speaker_lease_started) {
        const u64 now = clock::monotonic_ns();
        current->pc_speaker_lease_started = true;
        current->pc_speaker_deadline_ns = now > ~u64{0} - pc_speaker_lease_ns
            ? ~u64{0} : now + pc_speaker_lease_ns;
    }
    if (!set_user_io_permissions(current->io_window_first, current->io_window_length,
                                 current->pc_speaker_io)) {
        format::text("[sched] event=invalid_io_permissions result=halt\r\n");
        halt();
    }
    set_kernel_stack(thread->kernel_stack_top);
    load_address_space(current->cr3);
    set_thread_pointer(thread->thread_pointer);
}

interrupt_frame* make_initial_frame(thread_record* thread) {
    auto* frame = reinterpret_cast<interrupt_frame*>(thread->kernel_stack_top - sizeof(interrupt_frame));
    *frame = interrupt_frame{};
    frame->rip = thread->main ? thread->process->entry : thread->entry;
    frame->cs = user_code_selector;
    frame->rflags = 0x202;
    frame->rsp = thread->main ? thread->process->initial_stack : thread->initial_stack;
    frame->rdi = thread->main ? thread->process->startup : thread->argument;
    frame->ss = user_data_selector;
    return frame;
}

void reap_threads();
void expire_waiters();
interrupt_frame* schedule(interrupt_frame* frame) {
    expire_waiters();
    reap_dead();
    reap_threads();
    if (current_thread != nullptr && current_thread->state != thread_state::dead) {
        if (current_thread->state == thread_state::running) { current_thread->state = thread_state::ready; }
        if (frame != nullptr) { current_thread->kernel_rsp = reinterpret_cast<u64>(frame); }
        fpu_save(current_thread->fpu_state);
    }
    for (;;) {
        thread_record* next = pick_ready();
        while (next == nullptr) {
            arch::wait_for_interrupt(); expire_waiters(); next = pick_ready();
        }
        interrupt_frame* next_frame = next->state == thread_state::fresh
            ? make_initial_frame(next) : reinterpret_cast<interrupt_frame*>(next->kernel_rsp);
        switch_to(next);
        auto& continuation = next->process->continuation;
        if (continuation.active()) {
            i64 result = 0;
            const auto step_result = continuation.step(continuation.context, continuation.phase,
                                                        vm_continuation_batch, result);
            if (step_result == vm_step::prepared && continuation.phase == vm_phase::preparing) {
                continuation.phase = vm_phase::publishing;
            } else if (step_result == vm_step::failed && continuation.phase == vm_phase::preparing) {
                continuation.failure = result;
                continuation.phase = vm_phase::rolling_back;
            } else if (step_result == vm_step::finished) {
                const bool cancelled = continuation.cancelled;
                if (continuation.phase == vm_phase::rolling_back && !cancelled) result=continuation.failure;
                continuation.clear();
                if (cancelled) {
                    auto* owner = next->process;
                    finish_task(owner, owner->deferred_outcome, owner->deferred_code,
                                owner->deferred_vector, owner->deferred_address, owner->deferred_instruction);
                    continue;
                }
                next_frame->rax = static_cast<u64>(result);
                fpu_restore(next->fpu_state); deliver_wait(next, next_frame); return next_frame;
            } else if (step_result != vm_step::again) {
                format::text("[vm] continuation invariant failure\r\n"); halt();
            }
            next->state = thread_state::ready;
            // If no other process can run, allow the unified clock and wakeups
            // to progress instead of spinning through all remaining batches.
            bool other = false;
            for (const auto& peer : threads) {
                if (peer.process && peer.process != next->process &&
                    peer.process->state != task_state::dead && peer.process->state != task_state::building &&
                    (!peer.process->continuation.active() ||
                     peer.tid == peer.process->continuation.owner_tid) &&
                    (peer.state == thread_state::ready || peer.state == thread_state::fresh)) { other=true; break; }
            }
            if (!other) { arch::wait_for_interrupt(); expire_waiters(); }
            continue;
        }
        fpu_restore(next->fpu_state); deliver_wait(next, next_frame); return next_frame;
    }
}

process_record* owned_process(u64 handle) {
    if (current == nullptr) { return nullptr; }
    for (auto& task : tasks) {
        if (task.state != task_state::free && task.pid == handle && task.parent == current->pid) {
            // SL1: a parent holding identity-carried create authority may operate
            // on its own building children even when legacy spawn_depth is 0.
            if (current->supervisor || current->spawn_depth != 0 || current->can_create ||
                (task.state == task_state::building && task.replacement_pending)) { return &task; }
            return nullptr;
        }
    }
    return nullptr;
}

bool space_range_ok(u64 space, u64 address, u64 length, bool write) {
    if (length == 0) { return true; }
    if (address < process_user_begin || address >= process_user_end || length > process_user_end - address) {
        return false;
    }
    const u64 last = (address + length - 1) & ~(page_size - 1);
    for (u64 page = address & ~(page_size - 1); page <= last; page += page_size) {
        u64 physical = 0;
        page_permissions permissions{};
        if (query_page_in(space, page, &physical, &permissions) != memory_result::none ||
            !permissions.user || (write && !permissions.writable)) { return false; }
    }
    return true;
}

bool valid_process_entry(const process_record* task, const process_entry& entry) {
    u64 physical = 0;
    page_permissions permissions{};
    return space_range_ok(task->cr3, entry.entry, 1, false) &&
        query_page_in(task->cr3, entry.entry & ~(page_size - 1), &physical, &permissions) == memory_result::none &&
        permissions.executable && !permissions.writable && entry.stack % 16 == 0 &&
        entry.stack >= process_stack_bottom + 16 && entry.stack <= process_startup_begin &&
        space_range_ok(task->cr3, entry.stack - 16, 16, true) &&
        entry.startup % alignof(startup_info) == 0 && entry.startup >= process_startup_begin &&
        entry.startup <= process_stack_top - sizeof(startup_info) &&
        space_range_ok(task->cr3, entry.startup, sizeof(startup_info), false);
}

// Replacing a known single-thread image does not require constructing a new
// runnable principal. Multithreaded runtime state and trusted services require
// separate replacement protocols and cannot silently take this path.
i64 replacement_caller_error() {
    if (current == nullptr || current->supervisor || current->block_access) { return process_error_denied; }
    if (current->threads_enabled || current_thread != &main_thread(current) || !current_thread->main) {
        return thread_error_unsupported;
    }
    for (const auto& peer : threads) {
        if (peer.process == current && &peer != current_thread &&
            peer.state != thread_state::free && peer.state != thread_state::dead) {
            return thread_error_unsupported;
        }
    }
    return current->closing || current_thread->leaving ? process_error_state : 0;
}

u64 page_align_up(u64 address) {
    return (address + page_size - 1) & ~(page_size - 1);
}

bool pinned_range(process_record* process, u64 begin, u64 end);

i64 set_heap_break(u64 requested) {
    if (current == nullptr) { return process_error_state; }
    if (requested == 0) { return static_cast<i64>(current->heap_break); }
    if (requested < process_heap_begin || requested > process_heap_end) {
        return process_error_invalid;
    }
    const u64 old_break = current->heap_break;
    const u64 old_end = page_align_up(old_break);
    const u64 new_end = page_align_up(requested);
    if (new_end > old_end) {
        const u64 add_pages = (new_end - old_end) / page_size;
        if (current->user_pages > process_max_pages ||
            add_pages > process_max_pages - current->user_pages) {
            return process_error_resources;
        }
        u64 address = old_end;
        for (; address < new_end; address += page_size) {
            u64 physical = 0;
            if (allocate_user_page(&physical) != memory_result::none) { break; }
            if (map_page_in(current->cr3, address, physical, {true, false, true}) != memory_result::none) {
                (void)release_user_page(physical);
                break;
            }
            ++current->user_pages;
        }
        if (address != new_end) {
            for (u64 rollback = old_end; rollback < address; rollback += page_size) {
                u64 physical = 0;
                if (unmap_page_in(current->cr3, rollback, &physical) == memory_result::none) {
                    (void)release_user_page(physical);
                    if (current->user_pages != 0) { --current->user_pages; }
                }
            }
            return process_error_resources;
        }
    } else if (new_end < old_end) {
        if (pinned_range(current, new_end, old_end)) { return thread_error_busy; }
        for (u64 address = new_end; address < old_end; address += page_size) {
            u64 physical = 0;
            page_permissions permissions{};
            if (query_page_in(current->cr3, address, &physical, &permissions) != memory_result::none ||
                !permissions.user || !permissions.writable) { return process_error_state; }
        }
        for (u64 address = new_end; address < old_end; address += page_size) {
            u64 physical = 0;
            if (unmap_page_in(current->cr3, address, &physical) != memory_result::none ||
                release_user_page(physical) != memory_result::none) { return process_error_state; }
            if (current->user_pages != 0) { --current->user_pages; }
        }
    }
    current->heap_break = requested;
    return static_cast<i64>(requested);
}


bool valid_header(const thread_header& header, u32 size) {
    return header.version == thread_abi_version && header.size == size && header.reserved == 0;
}

template<class T> i64 read_thread_request(u64 address, T& request) {
    if (!user_range_ok(address, sizeof(T), false)) { return thread_error_address; }
    copy_from_user(&request, address, sizeof(T));
    return valid_header(request.header, sizeof(T)) ? 0 : process_error_invalid;
}

thread_record* thread_by_id(u64 tid) {
    for (auto& thread : threads) {
        if (thread.state != thread_state::free && thread.process == current && thread.tid == tid) {
            return &thread;
        }
    }
    return nullptr;
}

// A mapping cannot be removed while the kernel may still use a blocked user's
// word/result buffer. On this single CPU every caller holds the interrupt gate.
bool pinned_range(process_record* process, u64 begin, u64 end) {
    for (const auto& thread : threads) {
        if (thread.process != process || thread.state == thread_state::free ||
            thread.state == thread_state::dead) { continue; }
        if (thread.user_pin.overlaps(begin, end)) { return true; }
        for (const auto& pin : thread.ipc_v1_pins) {
            if (pin.overlaps(begin, end)) { return true; }
        }
    }
    return false;
}

// VM2 page work is staged outside the 4 KiB kernel stack. The owning process
// is frozen by vm_continuation while these records are live.
struct vm2_page_transaction {
    process_record* owner;
    u64 address, end, scan;
    u32 operation, protection, pages, cursor, prepared, staged_count;
    bool allocation_pass, rollback_started, trace, staging_reported, publish_reported;
    i64 fail_page, fail_table;
    u64 staged[4096];
    u64 committed[4096];
    anonymous_vm::reservations regions;
};
vm2_page_transaction vm2_page_transactions[8];
vm_step vm2_page_step(void* opaque, vm_phase phase, u32 budget, i64& result) {
    auto& tx=*static_cast<vm2_page_transaction*>(opaque);
    auto& owner=*tx.owner;
    const auto requested=static_cast<vm_page_protection>(tx.protection);
    if (phase==vm_phase::preparing && tx.operation==5) {
        while (budget-- && tx.scan<tx.end) {
            const u64 address=tx.scan; bool found=false;
            if (vm_scan_page_in(owner.cr3,&tx.scan,tx.end,&found)!=memory_result::none) {
                result=anonymous_vm::invalid; return vm_step::failed;
            }
            if (found) {
                if (tx.staged_count==4096) { result=anonymous_vm::resources; return vm_step::failed; }
                tx.committed[tx.staged_count++]=address;
            }
        }
        if (tx.scan==tx.end) { tx.cursor=0; return vm_step::prepared; }
        return vm_step::again;
    }
    if (phase==vm_phase::preparing) {
        // Check all existing pages and pins before allocating, preserving error precedence.
        while (budget-- && tx.cursor<tx.pages) {
            const u32 index=tx.cursor;
            const u64 address=tx.address+u64{index}*page_size;
            u64 physical=0; vm_page_protection old{};
            const auto lookup=vm_lookup_page_in(owner.cr3,address,&physical,&old);
            if (lookup!=memory_result::none && lookup!=memory_result::not_mapped) {
                result=anonymous_vm::invalid; return vm_step::failed;
            }
            const bool exists=lookup==memory_result::none;
            if (!tx.allocation_pass) {
                if (tx.operation==2 && exists && old!=requested) {
                    result=anonymous_vm::invalid; return vm_step::failed;
                }
                if (exists && (tx.operation==4 || (tx.operation==3 &&
                    (static_cast<u32>(old) & ~tx.protection))) &&
                    pinned_range(&owner,address,address+page_size)) {
                    result=-5; return vm_step::failed;
                }
            } else {
                tx.staged[index]=0;
                if (!exists && (tx.operation==2 || (tx.operation==3 && tx.protection!=0))) {
                    if (owner.user_pages>=process_max_pages || tx.staged_count>=process_max_pages-owner.user_pages ||
                        (tx.fail_page>=0 && static_cast<i64>(tx.staged_count)==tx.fail_page) ||
                        allocate_user_page(&physical)!=memory_result::none) {
                        result=anonymous_vm::resources; return vm_step::failed;
                    }
                    if (tx.fail_table>=0) memory_self_test_fail_after(tx.fail_table);
                    const auto table_result=vm_prepare_page_in(owner.cr3,address);
                    if (tx.fail_table>=0) { memory_self_test_fail_after(-1); tx.fail_table=-1; }
                    if (table_result!=memory_result::none) {
                        (void)release_user_page(physical); vm_prune_empty_page_tables_in(owner.cr3,address);
                        result=anonymous_vm::resources; return vm_step::failed;
                    }
                    tx.staged[index]=physical; ++tx.staged_count;
                    if (tx.trace && !tx.staging_reported && tx.staged_count==64) {
                        format::text("[vm2-pages] staging\r\n"); tx.staging_reported=true;
                    }
                }
                tx.prepared=index+1;
            }
            ++tx.cursor;
        }
        if (tx.cursor==tx.pages) {
            tx.cursor=0;
            if (!tx.allocation_pass) { tx.allocation_pass=true; return vm_step::again; }
            return vm_step::prepared;
        }
        return vm_step::again;
    }
    if (phase==vm_phase::rolling_back) {
        if (!tx.rollback_started) { tx.cursor=0; tx.rollback_started=true; }
        while (budget-- && tx.cursor<tx.prepared) {
            const u32 index=tx.cursor++;
            if (tx.staged[index]) {
                (void)release_user_page(tx.staged[index]);
                vm_prune_empty_page_tables_in(owner.cr3,tx.address+u64{index}*page_size);
                tx.staged[index]=0;
            }
        }
        if (tx.cursor==tx.prepared) { result=0; return vm_step::finished; }
        return vm_step::again;
    }
    if (phase==vm_phase::publishing) {
        if (tx.trace && !tx.publish_reported) {
            format::text("[vm2-pages] publishing\r\n"); tx.publish_reported=true;
        }
        const u32 count=tx.operation==5 ? tx.staged_count : tx.pages;
        while (budget-- && tx.cursor<count) {
            const u32 index=tx.cursor++;
            const u64 address=tx.operation==5 ? tx.committed[index] : tx.address+u64{index}*page_size;
            u64 physical=0; vm_page_protection old{};
            const auto lookup=vm_lookup_page_in(owner.cr3,address,&physical,&old);
            if (tx.operation!=5 && tx.staged[index]) {
                if (lookup!=memory_result::not_mapped || vm_install_page_in(owner.cr3,address,tx.staged[index],requested)!=memory_result::none) halt();
                tx.staged[index]=0; ++owner.user_pages;
            } else if (lookup==memory_result::none) {
                if (tx.operation==4 || tx.operation==5) {
                    if (vm_remove_page_in(owner.cr3,address,&physical)!=memory_result::none ||
                        release_user_page(physical)!=memory_result::none || !owner.user_pages) halt();
                    --owner.user_pages;
                } else if (tx.operation==3 && old!=requested) {
                    if (vm_protect_page_in(owner.cr3,address,requested)!=memory_result::none) halt();
                }
            } else if (lookup!=memory_result::not_mapped || tx.operation==5) halt();
        }
        if (tx.cursor==count) {
            if (tx.operation==5) vm1_probe_regions[static_cast<u32>(&owner-tasks)]=tx.regions;
            result=0; return vm_step::finished;
        }
        return vm_step::again;
    }
    halt();
}

void release_thread_range(thread_record& thread, u64 begin, u64 end) {
    for (u64 address = begin; address < end; address += page_size) {
        u64 physical = 0;
        if (unmap_page_in(thread.process->cr3, address, &physical) == memory_result::none) {
            (void)release_user_page(physical);
            if (thread.process->user_pages != 0) { --thread.process->user_pages; }
        }
    }
}

void ready_with(thread_record& thread, i64 result) {
    auto* saved = reinterpret_cast<interrupt_frame*>(thread.kernel_rsp);
    saved->rax = static_cast<u64>(result);
    thread.user_pin.clear();
    if (thread.wait_kind != thread_wait_kind::ipc_v1_call &&
        thread.wait_kind != thread_wait_kind::ipc_v1_receive &&
        thread.wait_kind != thread_wait_kind::ipc_v1_notification &&
        thread.wait_kind != thread_wait_kind::ipc_v1_wait_set) {
        thread.wait_kind = thread_wait_kind::none;
    }
    thread.wait_target = 0;
    thread.wait_channel_count = 0;
    thread.state = thread_state::ready;
}

void reap_threads() {
    for (auto& thread : threads) {
        if (thread.state != thread_state::dead || thread.process == nullptr ||
            thread.process->state == task_state::dead || &thread == current_thread) { continue; }
        if (!thread.reaped) {
            if (pinned_range(thread.process, thread.stack_bottom, thread.stack_top) ||
                pinned_range(thread.process, thread.tls_begin, thread.tls_end)) { continue; }
            release_thread_range(thread, thread.stack_bottom, thread.stack_top);
            release_thread_range(thread, thread.tls_begin, thread.tls_end);
            if (thread.kernel_stack_top != 0) {
                (void)release_page(thread.kernel_stack_top - kernel_stack_bytes);
                thread.kernel_stack_top = 0;
            }
            thread.reaped = true;
        }
        if (thread.joiner != 0) {
            for (auto& waiter : threads) {
                if (waiter.process != thread.process || waiter.tid != thread.joiner ||
                    waiter.state != thread_state::blocked || waiter.wait_kind != thread_wait_kind::join) { continue; }
                // Reaper may run with another address space active: copy through
                // its validated physical page instead of changing the active CR3.
                u64 physical = 0; page_permissions permissions{};
                const u64 address = waiter.wait_buffer;
                if (query_page_in(waiter.process->cr3, address & ~(page_size - 1), &physical, &permissions)
                    == memory_result::none && permissions.user && permissions.writable) {
                    copy_bytes(reinterpret_cast<void*>(physical + (address & (page_size - 1))),
                               &thread.result, sizeof(u64));
                    ready_with(waiter, 0);
                } else { ready_with(waiter, thread_error_address); }
            }
            thread = thread_record{};
        } else if (thread.detached) { thread = thread_record{}; }
    }
    for (auto& waiter : threads) {
        if (waiter.state != thread_state::blocked || waiter.wait_kind != thread_wait_kind::exit_barrier) { continue; }
        bool stopped = true;
        for (const auto& peer : threads) {
            if (peer.process == waiter.process && &peer != &waiter &&
                peer.state != thread_state::free && peer.state != thread_state::dead &&
                peer.state != thread_state::reserved) { stopped = false; }
        }
        if (stopped) { waiter.leaving = false; ready_with(waiter, 1); }
    }
}

void expire_waiters() {
    const u64 now = clock::monotonic_ns();
    for (auto& thread : threads) {
        if (thread.state == thread_state::blocked &&
            thread.wait_kind == thread_wait_kind::ipc_v1_notification &&
            thread_deadline_reached(now, thread.deadline_ns)) {
            thread.ipc_v1_label = 0;
            ready_with(thread, static_cast<i64>(ipc_v1_error::timeout));
            continue;
        }
        if (thread.state == thread_state::blocked && thread.wait_kind == thread_wait_kind::ipc_v1_wait_set &&
            thread_deadline_reached(now, thread.deadline_ns)) {
            ready_with(thread, static_cast<i64>(ipc_v1_error::timeout));
            continue;
        }
        if (thread.state == thread_state::blocked && thread.wait_kind == thread_wait_kind::ipc_v1_receive &&
            thread_deadline_reached(now, thread.deadline_ns)) {
            thread.ipc_v1_length = 0;
            thread.ipc_v1_label = thread.ipc_v1_badge = thread.ipc_v1_token = 0;
            ready_with(thread, static_cast<i64>(ipc_v1_error::timeout));
            continue;
        }
        if (thread.state == thread_state::blocked && thread.wait_kind == thread_wait_kind::ipc_v1_call &&
            thread_deadline_reached(now, thread.deadline_ns)) {
            if (thread.ipc_v1_call_slot < ipc_v1_max_pending_calls) {
                auto& call = ipc_v1_calls[thread.ipc_v1_call_slot];
                thread.ipc_v1_phase = call.state == ipc_v1_call_state::queued
                    ? static_cast<u32>(ipc_v1_call_phase::not_delivered)
                    : static_cast<u32>(ipc_v1_call_phase::delivered);
                call = ipc_v1_call_record{};
            }
            thread.ipc_v1_length = 0;
            ready_with(thread, static_cast<i64>(ipc_v1_error::timeout));
            continue;
        }
        if (thread.state == thread_state::blocked &&
            (thread.wait_kind == thread_wait_kind::word || thread.wait_kind == thread_wait_kind::sleep ||
             thread.wait_kind == thread_wait_kind::pipe_read || thread.wait_kind == thread_wait_kind::pipe_write ||
             thread.wait_kind == thread_wait_kind::channel_read ||
             thread.wait_kind == thread_wait_kind::channel_write || thread.wait_kind == thread_wait_kind::channel_many ||
             thread.wait_kind == thread_wait_kind::irq_event) &&
            thread_deadline_reached(now, thread.deadline_ns)) {
            ready_with(thread, thread.wait_kind == thread_wait_kind::sleep ? 0 : thread_error_timeout);
        }
    }
}

void* thread_syscall(interrupt_frame* frame) {
    i64 result = process_error_invalid;
    const u64 first = frame->rdi, second = frame->rsi;
    if (frame->rdx != 0 || (second != 0 && frame->rax != sys_thread_prepare &&
        frame->rax != sys_thread_join && frame->rax != sys_wake_word) ||
        ((frame->rax == sys_thread_begin_exit || frame->rax == sys_process_begin_exit) && first != 0)) {
        frame->rax = static_cast<u64>(process_error_invalid); return frame;
    }
    if (current_thread->leaving && frame->rax != sys_thread_exit && frame->rax != sys_exit) {
        frame->rax = static_cast<u64>(process_error_state); return frame;
    }
    switch (frame->rax) {
    case sys_thread_profile: {
        thread_header header{};
        if (!user_range_ok(first, sizeof(header), false)) { result = thread_error_address; break; }
        copy_from_user(&header, first, sizeof(header));
        if (!valid_header(header, sizeof(header))) { break; }
        if (current->closing) { result = process_error_state; break; }
        if (!current->threads_enabled) {
            // Explicit opt-in: an old ELF with a LOAD in this formerly available
            // interval remains executable but cannot opt into the new profile.
            bool occupied = false;
            for (u64 address = thread_arena_begin; address < thread_arena_end; address += page_size) {
                u64 physical = 0; page_permissions permissions{};
                if (query_page_in(current->cr3, address, &physical, &permissions) == memory_result::none) {
                    occupied = true; break;
                }
            }
            if (occupied) { result = thread_error_unsupported; break; }
            current->threads_enabled = true;
            auto& main = main_thread(current);
            main.tls_begin = process_tls_begin;
            main.tls_end = process_tls_end;
        }
        result = 0; break;
    }
    case sys_thread_prepare: {
        thread_prepare_request request{};
        result = read_thread_request(first, request);
        if (result != 0) { break; }
        if (!user_range_ok(second, sizeof(thread_reservation), true)) { result = thread_error_address; break; }
        if (!current->threads_enabled) { result = thread_error_unsupported; break; }
        if (current->closing) { result = process_error_state; break; }
        if (request.stack_bytes < thread_stack_min || request.stack_bytes > thread_stack_max ||
            request.stack_bytes % page_size != 0 || request.tls_bytes < 16 ||
            request.tls_bytes > thread_tls_max || (request.flags & ~thread_flag_detached) != 0) {
            result = process_error_invalid; break;
        }
        thread_record* target = nullptr;
        const u32 offset = task_index(current) * thread_max_per_process;
        // A safely reaped/detached original thread can donate its quota slot.
        for (u32 i = 0; i < thread_max_per_process; ++i) {
            if (threads[offset + i].state == thread_state::free) { target = &threads[offset + i]; break; }
        }
        if (target == nullptr || next_tid == 0 || next_tid > 0x7fffffffffffffff) {
            result = process_error_resources; break;
        }
        *target = thread_record{}; target->process = current; target->tid = next_tid++;
        target->state = thread_state::reserved;
        target->detached = (request.flags & thread_flag_detached) != 0;
        const u64 slot = static_cast<u64>(target - threads) % thread_max_per_process;
        const u64 base = thread_arena_begin + slot * thread_slot_bytes;
        target->stack_top = base + thread_slot_bytes;
        target->stack_bottom = target->stack_top - request.stack_bytes;
        target->tls_begin = base;
        target->tls_end = page_align_up(base + request.tls_bytes);
        u64 kernel_stack = 0;
        bool success = allocate_page(&kernel_stack) == memory_result::none;
        if (success) { target->kernel_stack_top = kernel_stack + kernel_stack_bytes; }
        for (u64 address = target->tls_begin; success && address < target->tls_end; address += page_size) {
            success = add_user_page(current, address, nullptr, 0, 0, {true, false, true});
        }
        for (u64 address = target->stack_bottom; success && address < target->stack_top; address += page_size) {
            success = add_user_page(current, address, nullptr, 0, 0, {true, false, true});
        }
        if (!success) {
            release_thread_range(*target, target->stack_bottom, target->stack_top);
            release_thread_range(*target, target->tls_begin, target->tls_end);
            if (kernel_stack != 0) { (void)release_page(kernel_stack); }
            *target = thread_record{}; result = thread_error_memory; break;
        }
        copy_bytes(target->fpu_state, fpu_template, sizeof(fpu_template));
        thread_reservation reservation{{thread_abi_version, sizeof(thread_reservation), 0}, target->tid,
            target->stack_bottom, target->stack_top, target->tls_begin, target->tls_end};
        copy_to_user(second, &reservation, sizeof(reservation));
        result = 0; break;
    }
    case sys_thread_start: {
        thread_start_request request{};
        result = read_thread_request(first, request); if (result != 0) { break; }
        thread_record* target = thread_by_id(request.tid);
        if (target == nullptr) { result = thread_error_not_found; break; }
        if (current->closing || target->state != thread_state::reserved) { result = process_error_state; break; }
        u64 physical = 0; page_permissions permissions{};
        if (!user_range_ok(request.entry, 1, false) ||
            query_page(request.entry & ~(page_size - 1), &physical, &permissions) != memory_result::none ||
            !permissions.executable || permissions.writable || request.stack % 16 != 0 ||
            request.stack < target->stack_bottom + 16 || request.stack > target->stack_top ||
            request.thread_pointer % 16 != 0 || request.thread_pointer < target->tls_begin ||
            request.thread_pointer > target->tls_end - 16 ||
            !user_range_ok(request.stack - 16, 16, true) || !user_range_ok(request.thread_pointer, 16, true)) {
            result = process_error_invalid; break;
        }
        target->entry = request.entry; target->argument = request.argument;
        target->initial_stack = request.stack; target->thread_pointer = request.thread_pointer;
        target->state = thread_state::fresh; result = 0; break;
    }
    case sys_thread_abort: {
        thread_record* target = thread_by_id(first);
        if (target == nullptr) { result = thread_error_not_found; break; }
        if (target->state != thread_state::reserved) { result = process_error_state; break; }
        if (pinned_range(current, target->stack_bottom, target->stack_top) ||
            pinned_range(current, target->tls_begin, target->tls_end)) { result = thread_error_busy; break; }
        target->state = thread_state::dead; target->detached = true;
        reap_threads(); result = 0; break;
    }
    case sys_thread_info: {
        if (!user_range_ok(first, sizeof(thread_info), true)) { result = thread_error_address; break; }
        const auto& t = *current_thread;
        thread_info info{{thread_abi_version, sizeof(thread_info), 0}, current->pid, t.tid,
            t.stack_bottom, t.stack_top, t.thread_pointer};
        copy_to_user(first, &info, sizeof(info)); result = 0; break;
    }
    case sys_thread_begin_exit: {
        if (current_thread->leaving || current->closing) { result = process_error_state; break; }
        current_thread->leaving = true;
        bool last = true;
        for (const auto& peer : threads) {
            if (peer.process == current && thread_has_user_work(peer)) { last = false; }
        }
        if (!last) { result = 0; break; }
        current->closing = true; current->exit_owner = current_thread->tid;
        bool stopped = true;
        for (auto& peer : threads) {
            if (peer.process != current || &peer == current_thread) { continue; }
            if (peer.state == thread_state::reserved) { peer.state = thread_state::dead; peer.detached = true; }
            else if (peer.state != thread_state::free && peer.state != thread_state::dead) { stopped = false; }
        }
        if (stopped) { current_thread->leaving = false; result = 1; break; }
        current_thread->state = thread_state::blocked;
        current_thread->wait_kind = thread_wait_kind::exit_barrier;
        frame->rax = 1; return schedule(frame);
    }
    case sys_thread_exit: {
        if (!current_thread->leaving && current->exit_owner != current_thread->tid) { result = process_error_state; break; }
        current_thread->result = first;
        current_thread->wait_kind = thread_wait_kind::none;
        current_thread->state = thread_state::dead;
        if (current->exit_owner == current_thread->tid) { finish_task(current, process_outcome::exited, 0); }
        return schedule(frame);
    }
    case sys_process_begin_exit: {
        if (current->closing && current->exit_owner != current_thread->tid) { result = process_error_state; break; }
        current->closing = true; current->exit_owner = current_thread->tid;
        for (auto& peer : threads) {
            if (peer.process == current && &peer != current_thread && peer.state != thread_state::free) {
                peer.state = thread_state::dead; peer.wait_kind = thread_wait_kind::none; peer.detached = true;
            }
        }
        reap_threads(); result = 0; break;
    }
    case sys_thread_join: {
        if (first == current_thread->tid) { result = thread_error_deadlock; break; }
        thread_record* target = thread_by_id(first);
        if (target == nullptr) { result = thread_error_not_found; break; }
        if (target->detached || target->joiner != 0 || target->state == thread_state::reserved) { break; }
        // Eight-byte alignment ensures the physical reaper copy is in one page.
        if ((second < target->stack_top && second + sizeof(u64) > target->stack_bottom) ||
            (second < target->tls_end && second + sizeof(u64) > target->tls_begin) ||
            second % 8 != 0 || !user_range_ok(second, sizeof(u64), true)) { result = thread_error_address; break; }
        if (target->reaped) {
            copy_to_user(second, &target->result, sizeof(u64)); *target = thread_record{}; result = 0; break;
        }
        if (!current_thread->user_pin.set(second, sizeof(u64))) { result = thread_error_busy; break; }
        target->joiner = current_thread->tid;
        current_thread->wait_target = first; current_thread->wait_buffer = second;
        current_thread->wait_kind = thread_wait_kind::join;
        current_thread->state = thread_state::blocked;
        frame->rax = 0; return schedule(frame);
    }
    case sys_thread_detach: {
        thread_record* target = thread_by_id(first);
        if (target == nullptr) { result = thread_error_not_found; break; }
        if (target->detached || target->joiner != 0 || target->state == thread_state::reserved) { break; }
        target->detached = true; reap_threads(); result = 0; break;
    }
    case sys_clock_monotonic:
        result = first == 0 ? static_cast<i64>(clock::monotonic_ns()) : first == 1 ? static_cast<i64>(thread_tick_ns) : process_error_invalid;
        break;
    case sys_sleep_until:
        if (thread_deadline_reached(clock::monotonic_ns(), first)) { result = 0; break; }
        current_thread->deadline_ns = first; current_thread->wait_kind = thread_wait_kind::sleep;
        current_thread->state = thread_state::blocked; frame->rax = 0; return schedule(frame);
    case sys_wait_word: {
        thread_wait_request request{};
        result = read_thread_request(first, request); if (result != 0) { break; }
        if (request.reserved != 0) { result = process_error_invalid; break; }
        if (request.address % 4 != 0 || !user_range_ok(request.address, 4, true)) { result = thread_error_address; break; }
        u32 value = 0; copy_from_user(&value, request.address, sizeof(value));
        if (value != request.expected) { result = thread_value_changed; break; }
        if (thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns)) { result = thread_error_timeout; break; }
        if (next_wait_order == 0) { result = process_error_resources; break; }
        if (!current_thread->user_pin.set(request.address, sizeof(u32))) { result = thread_error_busy; break; }
        current_thread->wait_order = next_wait_order++;
        current_thread->wait_target = request.address;
        current_thread->deadline_ns = request.deadline_ns;
        current_thread->wait_kind = thread_wait_kind::word;
        current_thread->state = thread_state::blocked; frame->rax = 0; return schedule(frame);
    }
    case sys_wake_word: {
        if (first % 4 != 0 || !user_range_ok(first, 4, true)) { result = thread_error_address; break; }
        if (second > 0xffffffffull) { break; }
        u32 count = 0;
        while (count < second) {
            thread_record* oldest = nullptr;
            for (auto& peer : threads) {
                if (peer.process == current && peer.state == thread_state::blocked &&
                    peer.wait_kind == thread_wait_kind::word && peer.wait_target == first &&
                    (oldest == nullptr || peer.wait_order < oldest->wait_order)) { oldest = &peer; }
            }
            if (oldest == nullptr) { break; }
            ready_with(*oldest, 0); ++count;
        }
        result = count; break;
    }
    case sys_thread_stats: {
        if (!user_range_ok(first, sizeof(thread_stats), true)) { result = thread_error_address; break; }
        thread_stats stats{{thread_abi_version, sizeof(thread_stats), 0}, task_total, 0, 0, 0, 0,
            memory_status().free_pages, current->user_pages, 0};
        for (const auto& peer : threads) {
            if (peer.process == current && peer.kernel_stack_top != 0) { ++stats.process_kernel_stack_pages; }
            if (peer.state == thread_state::free || (!current->supervisor && peer.process != current)) { continue; }
            ++stats.threads;
            if (peer.state == thread_state::reserved) { ++stats.reserved; }
            if (peer.state == thread_state::blocked) { ++stats.waiting; }
            if (peer.state == thread_state::dead && peer.reaped) { ++stats.results; }
        }
        copy_to_user(first, &stats, sizeof(stats)); result = 0; break;
    }
    default: break;
    }
    frame->rax = static_cast<u64>(result); return frame;
}

// Fork snapshots run in bounded batches while peer threads remain frozen.
constexpr i64 fork_async_result = (-0x7fffffffffffffffLL);
i64 finish_fork_copy(fork_copy_transaction& tx) {
    auto* child=tx.child;auto* frame=tx.frame;
    if (!child || child->state!=task_state::building || !files_service_live()) return process_error_state;
    completion_record* completion=nullptr;
    for(auto& item:completions) if(!item.used) { completion=&item;break; }
    u32 free_endpoints=0;
    for(const auto& endpoint:endpoints) if(!endpoint.used) ++free_endpoints;
    if(!completion || free_endpoints<2 || next_endpoint_handle>0xfffffffeull) return process_error_resources;
    vm1_probe_regions[static_cast<u32>(child-tasks)]=vm1_probe_regions[static_cast<u32>(current-tasks)];
    if (!inherit_stdio(child, current, current->stdio_mask)) {
        return process_error_resources;
    }
    // libc's copied FD table contains these exact tokens. Retain the underlying
    // objects under the new PID; global monotonic tokens are still authorized
    // by membership in each process's private reference array.
    for (u32 index = 0; index < process_max_pipe_refs; ++index) {
        const auto& reference = current->pipe_references[index];
        if (!reference.used) { continue; }
        if (child->pipe_reference_count >= process_max_pipe_refs ||
            reference.pipe_index >= process_max_pipes || !pipes[reference.pipe_index].used) {
            return process_error_resources;
        }
        child->pipe_references[index] = reference;
        pipe_retain(reference.pipe_index, reference.writable);
        ++child->pipe_reference_count;
    }
    if (child->pipe_reference_count != current->pipe_reference_count) {
        return process_error_state;
    }
    child->session_request_handle = endpoint_attach(files_pid, child->pid, child->pid,
        file_message_bytes);
    child->session_response_handle = endpoint_attach(child->pid, files_pid, child->pid,
        file_message_bytes, true);
    if (child->session_request_handle == 0 || child->session_response_handle == 0) {
        return process_error_resources;
    }
    child->send_handle = child->session_request_handle;
    child->recv_handle = child->session_response_handle;
    auto& thread = main_thread(child);
    thread.stack_bottom = current_thread->stack_bottom;
    thread.stack_top = current_thread->stack_top;
    thread.tls_begin = current_thread->tls_begin;
    thread.tls_end = current_thread->tls_end;
    thread.thread_pointer = current_thread->thread_pointer;
    copy_bytes(thread.fpu_state, current_thread->fpu_state, sizeof(thread.fpu_state));
    auto* child_frame = reinterpret_cast<interrupt_frame*>(thread.kernel_stack_top - sizeof(interrupt_frame));
    *child_frame = *frame;
    child_frame->rax = 0;
    thread.kernel_rsp = reinterpret_cast<u64>(child_frame);
    thread.state = thread_state::ready;
    *completion = completion_record{};
    completion->used = true;
    completion->parent = current->pid;
    completion->status.pid = child->pid;
    child->completion_slot = static_cast<u32>(completion - completions) + 1;
    if (process_trace_enabled) {
        format::text("[process] event=fork_prepared pid="); format::decimal(child->pid);
        format::text(" parent="); format::decimal(child->parent);
        format::text(" depth="); format::decimal(child->fork_depth);
        format::text(" pages="); format::decimal(child->user_pages); format::text("\r\n");
    }
    const i64 pid=static_cast<i64>(child->pid);
    tx.child=nullptr;tx.owner=nullptr;return pid;
}
vm_step fork_copy_step(void* opaque,vm_phase phase,u32 budget,i64& result) {
    auto& tx=*static_cast<fork_copy_transaction*>(opaque);
    if (!tx.owner || !tx.child) halt();
    auto* child=tx.child;
    // One leaf can also allocate or release up to three page-table pages.
    const u32 work = budget >= 4 ? budget / 4 : 1;
    if (phase==vm_phase::preparing) {
        if(child->state!=task_state::building) { result=process_error_state;return vm_step::failed; }
#if XOS_VM1_PROBE
        if (tx.owner->user_pages > 256 && tx.copy_cursor == 0x40000000ull)
            format::text("[vm3-fork] preparing\r\n");
        if(tx.fail_after>=0) memory_self_test_fail_after(tx.fail_after);
#endif
        const auto copied=copy_user_pages_batch(tx.owner->cr3,child->cr3,process_max_pages,
                                                 &child->user_pages,&tx.copy_cursor,work);
#if XOS_VM1_PROBE
        if(tx.fail_after>=0) { tx.fail_after=memory_self_test_remaining();memory_self_test_fail_after(-1); }
#endif
        if(copied!=memory_result::none) { result=process_error_resources;return vm_step::failed; }
        if(tx.copy_cursor!=(u64{1}<<47))return vm_step::again;
        if(child->user_pages!=tx.owner->user_pages) { result=process_error_resources;return vm_step::failed; }
        result=finish_fork_copy(tx);
        return result>0 ? vm_step::finished : vm_step::failed;
    }
    if(phase==vm_phase::rolling_back) {
#if XOS_VM1_PROBE
        if (tx.owner->user_pages > 256 && tx.release_cursor == 0x40000000ull)
            format::text("[vm3-fork] rolling_back\r\n");
#endif
        if(release_user_pages_batch(child->cr3,&tx.release_cursor,&tx.released,work)!=memory_result::none) halt();
        if(tx.release_cursor!=(u64{1}<<47))return vm_step::again;
        if(tx.released!=child->user_pages)halt();
        child->user_pages=0;tx.child=nullptr;tx.owner=nullptr;destroy_task(child);
        result=0;return vm_step::finished;
    }
    halt();
}
i64 prepare_fork(interrupt_frame* frame) {
    if (current == nullptr || current->supervisor || current->block_access) return process_error_denied;
    if (current->threads_enabled || current_thread != &main_thread(current) || !current_thread->main)
        return thread_error_unsupported;
    for (const auto& peer : threads) {
        if (peer.process == current && &peer != current_thread &&
            peer.state != thread_state::free && peer.state != thread_state::dead) return thread_error_unsupported;
    }
    if (current->spawn_depth == 0 && !current->can_create) return process_error_denied;
    if (current->closing || current_thread->leaving) return process_error_state;
    if (current->fork_depth >= process_fork_depth_max || !files_service_live()) return process_error_resources;
    u32 free_endpoints=0;bool free_completion=false;
    for(const auto& item:completions) if(!item.used) { free_completion=true;break; }
    for(const auto& endpoint:endpoints) if(!endpoint.used) ++free_endpoints;
    if(!free_completion || free_endpoints<2 || next_endpoint_handle>0xfffffffeull) return process_error_resources;
    process_record* child=prepare_task(current->name);
    if(!child)return process_error_resources;
    child->parent=current->pid;child->spawn_depth=current->spawn_depth;child->can_create=current->can_create;
    child->fork_source=current->pid;child->fork_depth=current->fork_depth+1;child->fork_pending=true;
    child->heap_break=current->heap_break;child->entry=current->entry;
    child->initial_stack=current->initial_stack;child->startup=current->startup;
    auto& tx=fork_copies[static_cast<u32>(current-tasks)];
    tx.owner=current;tx.child=child;tx.frame=frame;
    tx.copy_cursor=0x40000000ull;tx.release_cursor=0x40000000ull;tx.released=0;tx.fail_after=-1;
#if XOS_VM1_PROBE
    tx.fail_after=vm2_failures[static_cast<u32>(current-tasks)].fork;
    vm2_failures[static_cast<u32>(current-tasks)].fork=-1;
#endif
    fpu_save(current_thread->fpu_state);
    if(!begin_vm_continuation(*current,*current_thread,&tx,fork_copy_step)) {
        tx.owner=nullptr;tx.child=nullptr;destroy_task(child);return process_error_state;
    }
    return fork_async_result;
}

#include "display_tasks.inc"

ipc_v1_handle_record* ipc_v1_handle_for(u64 value, u64 holder) {
    for (auto& handle : ipc_v1_handles) {
        if (handle.used && handle.value == value && handle.holder_pid == holder) { return &handle; }
    }
    return nullptr;
}

u32 ipc_v1_handle_count(u64 pid) {
    u32 count = 0;
    for (const auto& handle : ipc_v1_handles) { if (handle.used && handle.holder_pid == pid) { ++count; } }
    for (const auto& handle : ipc_v1_notification_handles) {
        if (handle.used && handle.holder_pid == pid) { ++count; }
    }
    for (const auto& handle : ipc_v1_wait_set_handles) {
        if (handle.used && handle.holder_pid == pid) { ++count; }
    }
    for (const auto& handle : ipc_v1_grant_handles) {
        if (handle.used && handle.holder_pid == pid) { ++count; }
    }
    return count;
}

ipc_v1_notification_handle_record* ipc_v1_notification_handle_for(u64 value, u64 holder) {
    for (auto& handle : ipc_v1_notification_handles) {
        if (handle.used && handle.value == value && handle.holder_pid == holder) { return &handle; }
    }
    return nullptr;
}

ipc_v1_wait_set_handle_record* ipc_v1_wait_set_handle_for(u64 value, u64 holder) {
    for (auto& handle : ipc_v1_wait_set_handles) {
        if (handle.used && handle.value == value && handle.holder_pid == holder) { return &handle; }
    }
    return nullptr;
}

ipc_v1_grant_handle_record* ipc_v1_grant_handle_for(u64 value, u64 holder) {
    for (auto& handle : ipc_v1_grant_handles) {
        if (handle.used && handle.value == value && handle.holder_pid == holder) { return &handle; }
    }
    return nullptr;
}

u32 ipc_v1_allocate_grant_handle(u32 object_slot, u64 holder, u32 rights) {
    if (!ipc_v1_next_handle || ipc_v1_handle_count(holder) >= ipc_v1_max_handles_per_process) {
        return ipc_v1_max_grants_system * ipc_v1_max_handles_per_process;
    }
    for (u32 i = 0; i < ipc_v1_max_grants_system * ipc_v1_max_handles_per_process; ++i) {
        if (!ipc_v1_grant_handles[i].used) {
            ipc_v1_grant_handles[i] = {true, object_slot, rights, ipc_v1_next_handle++, holder};
            return i;
        }
    }
    return ipc_v1_max_grants_system * ipc_v1_max_handles_per_process;
}

bool ipc_v1_grant_overlap(u64 pid, u64 begin, u64 end) {
    for (const auto& mapping : ipc_v1_grant_mappings) {
        if (mapping.used && mapping.holder_pid == pid) {
            const u64 mapping_end = mapping.address + u64{mapping.page_count} * page_size;
            if (mapping.address < end && begin < mapping_end) { return true; }
        }
    }
    return false;
}

void ipc_v1_remove_grant_mapping(u32 mapping_slot) {
    if (mapping_slot >= ipc_v1_max_grant_mappings_system || !ipc_v1_grant_mappings[mapping_slot].used) { return; }
    const auto mapping = ipc_v1_grant_mappings[mapping_slot];
    process_record* owner = task_by_pid(mapping.holder_pid);
    if (owner == nullptr || owner->cr3 == 0) { halt(); }
    for (u32 page = 0; page < mapping.page_count; ++page) {
        const u64 address = mapping.address + u64{page} * page_size;
        u64 physical = 0;
        if (vm_remove_page_in(owner->cr3, address, &physical) != memory_result::none ||
            mapping.grant_slot >= ipc_v1_max_grants_system || !ipc_v1_grants[mapping.grant_slot].used ||
            page >= ipc_v1_grants[mapping.grant_slot].page_count ||
            physical != ipc_v1_grants[mapping.grant_slot].pages[page] ||
            release_user_page(physical) != memory_result::none || owner->user_pages == 0) { halt(); }
        --owner->user_pages;
        vm_prune_empty_page_tables_in(owner->cr3, address);
    }
    const u32 owner_index = task_index(owner);
    if (vm1_probe_regions[owner_index].unmap(mapping.address, u64{mapping.page_count} * page_size) != 0) { halt(); }
    ipc_v1_grant_mappings[mapping_slot] = ipc_v1_grant_mapping_record{};
}

void ipc_v1_destroy_grant(u32 slot) {
    if (slot >= ipc_v1_max_grants_system || !ipc_v1_grants[slot].used) { return; }
    for (u32 i = 0; i < ipc_v1_max_grant_mappings_system; ++i) {
        if (ipc_v1_grant_mappings[i].used && ipc_v1_grant_mappings[i].grant_slot == slot) {
            ipc_v1_remove_grant_mapping(i);
        }
    }
    for (auto& handle : ipc_v1_grant_handles) {
        if (handle.used && handle.object_slot == slot) { handle = ipc_v1_grant_handle_record{}; }
    }
    for (u32 i = 0; i < ipc_v1_grants[slot].page_count; ++i) {
        if (release_user_page(ipc_v1_grants[slot].pages[i]) != memory_result::none) { halt(); }
    }
    ipc_v1_grants[slot] = ipc_v1_grant_record{};
}

u32 ipc_v1_allocate_wait_set_handle(u32 object_slot, u64 holder, u32 rights, u64 badge) {
    if (!ipc_v1_next_handle || ipc_v1_handle_count(holder) >= ipc_v1_max_handles_per_process) {
        return ipc_v1_max_wait_sets_system * ipc_v1_max_handles_per_process;
    }
    for (u32 i = 0; i < ipc_v1_max_wait_sets_system * ipc_v1_max_handles_per_process; ++i) {
        if (!ipc_v1_wait_set_handles[i].used) {
            auto& handle = ipc_v1_wait_set_handles[i];
            handle = {true, object_slot, rights, ipc_v1_next_handle++, holder, badge};
            return i;
        }
    }
    return ipc_v1_max_wait_sets_system * ipc_v1_max_handles_per_process;
}

struct ipc_v1_ready_event {
    ipc_v1_wait_event event;
    u32 notification_slot;
};

u32 ipc_v1_collect_wait_set(u32 object_slot, ipc_v1_ready_event* output) {
    if (object_slot >= ipc_v1_max_wait_sets_system || !ipc_v1_wait_sets[object_slot].used) { return 0; }
    u32 count = 0;
    const auto& wait_set = ipc_v1_wait_sets[object_slot];
    for (const auto& source : wait_set.sources) {
        if (!source.used) { continue; }
        ipc_v1_wait_event event{};
        if (source.closed) {
            event.kind = static_cast<u32>(ipc_v1_wait_event_kind::closed);
        } else if (source.source_kind == static_cast<u32>(ipc_v1_wait_source::endpoint)) {
            if (source.object_slot >= ipc_v1_max_endpoints_system || !ipc_v1_endpoints[source.object_slot].used) {
                event.kind = static_cast<u32>(ipc_v1_wait_event_kind::closed);
            } else {
                bool queued = false;
                for (const auto& call : ipc_v1_calls) {
                    queued = queued || (call.state == ipc_v1_call_state::queued &&
                                        call.endpoint_slot == source.object_slot);
                }
                if (!queued) { continue; }
                event.kind = static_cast<u32>(ipc_v1_wait_event_kind::endpoint_ready);
            }
        } else if (source.source_kind == static_cast<u32>(ipc_v1_wait_source::notification)) {
            if (source.object_slot >= ipc_v1_max_notifications_system ||
                !ipc_v1_notifications[source.object_slot].used) {
                event.kind = static_cast<u32>(ipc_v1_wait_event_kind::closed);
            } else {
                const u64 bits = ipc_v1_notifications[source.object_slot].pending_bits;
                if (bits == 0) { continue; }
                event.kind = static_cast<u32>(ipc_v1_wait_event_kind::notification);
                event.value = bits;
            }
        } else { continue; }
        event.source_id = source.source_id;
        output[count].event = event;
        output[count].notification_slot = event.kind == static_cast<u32>(ipc_v1_wait_event_kind::notification)
            ? source.object_slot : ipc_v1_max_notifications_system;
        ++count;
    }
    for (u32 i = 1; i < count; ++i) {
        auto value = output[i];
        u32 j = i;
        while (j != 0 && output[j - 1].event.source_id > value.event.source_id) {
            output[j] = output[j - 1]; --j;
        }
        output[j] = value;
    }
    return count;
}

u32 ipc_v1_consume_wait_set(u32 object_slot, ipc_v1_wait_event* output, u32 capacity) {
    ipc_v1_ready_event ready[ipc_v1_max_wait_set_sources]{};
    const u32 count = ipc_v1_collect_wait_set(object_slot, ready);
    if (count > capacity) { return count; }
    for (u32 i = 0; i < count; ++i) {
        output[i] = ready[i].event;
        if (ready[i].notification_slot < ipc_v1_max_notifications_system) {
            ipc_v1_notifications[ready[i].notification_slot].pending_bits = 0;
        }
    }
    return count;
}

void ipc_v1_notify_wait_sets() {
    bool visited[thread_max_total]{};
    for (u32 n = 0; n < thread_max_total; ++n) {
        u32 selected = thread_max_total;
        for (u32 i = 0; i < thread_max_total; ++i) {
            const auto& thread = threads[i];
            if (visited[i] || thread.state != thread_state::blocked ||
                thread.wait_kind != thread_wait_kind::ipc_v1_wait_set) { continue; }
            if (selected == thread_max_total || thread.wait_order < threads[selected].wait_order) { selected = i; }
        }
        if (selected == thread_max_total) { return; }
        visited[selected] = true;
        auto& thread = threads[selected];
        ipc_v1_ready_event ready[ipc_v1_max_wait_set_sources]{};
        const u32 count = ipc_v1_collect_wait_set(thread.ipc_v1_call_slot, ready);
        if (count == 0) { continue; }
        if (count > thread.ipc_v1_payload_capacity) {
            thread.ipc_v1_event_count = count;
            ready_with(thread, static_cast<i64>(ipc_v1_error::buffer_too_small));
        } else {
            thread.ipc_v1_event_count = ipc_v1_consume_wait_set(thread.ipc_v1_call_slot,
                thread.ipc_v1_events, thread.ipc_v1_payload_capacity);
            ready_with(thread, 0);
        }
    }
}

u32 ipc_v1_allocate_notification_handle(u32 object_slot, u64 holder, u32 rights, u64 badge) {
    if (!ipc_v1_next_handle || ipc_v1_handle_count(holder) >= ipc_v1_max_handles_per_process) {
        return ipc_v1_max_notifications_system * ipc_v1_max_handles_per_process;
    }
    for (u32 i = 0; i < ipc_v1_max_notifications_system * ipc_v1_max_handles_per_process; ++i) {
        if (!ipc_v1_notification_handles[i].used) {
            auto& handle = ipc_v1_notification_handles[i];
            handle = {true, object_slot, rights, ipc_v1_next_handle++, holder, badge};
            return i;
        }
    }
    return ipc_v1_max_notifications_system * ipc_v1_max_handles_per_process;
}

void ipc_v1_wake_notification_waiter(u32 object_slot) {
    if (object_slot >= ipc_v1_max_notifications_system) { return; }
    auto& object = ipc_v1_notifications[object_slot];
    if (!object.used || object.pending_bits == 0) { return; }
    thread_record* waiter = nullptr;
    for (auto& thread : threads) {
        if (thread.state != thread_state::blocked ||
            thread.wait_kind != thread_wait_kind::ipc_v1_notification) { continue; }
        auto* handle = ipc_v1_notification_handle_for(thread.wait_target, thread.process->pid);
        if (handle == nullptr || handle->object_slot != object_slot) { continue; }
        if (waiter == nullptr || thread.wait_order < waiter->wait_order) { waiter = &thread; }
    }
    if (waiter != nullptr) {
        waiter->ipc_v1_label = object.pending_bits;
        object.pending_bits = 0;
        ready_with(*waiter, 0);
    }
}

u32 ipc_v1_token_count(u64 pid) {
    u32 count = 0;
    for (const auto& call : ipc_v1_calls) {
        if (call.state == ipc_v1_call_state::delivered && call.reply_token != 0 && call.receiver_pid == pid) { ++count; }
    }
    return count;
}

bool ipc_v1_pin(thread_record& thread, u32 slot, u64 address, u64 length) {
    if (length == 0) { return true; }
    if (slot >= 3 || !thread.ipc_v1_pins[slot].set(address, length)) { return false; }
    return true;
}

void ipc_v1_unpin(thread_record& thread) {
    for (auto& pin : thread.ipc_v1_pins) { pin.clear(); }
}

bool ipc_v1_header_valid(const ipc_v1_header& header, u32 expected) {
    return header.version == ipc_v1_version && header.size == expected && header.reserved == 0;
}

bool ipc_v1_ranges_overlap(u64 first, u64 first_length, u64 second, u64 second_length) {
    return first_length != 0 && second_length != 0 && first < second + second_length &&
           second < first + first_length;
}

u32 ipc_v1_free_handle_slot() {
    for (u32 i = 0; i < ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process; ++i) {
        if (!ipc_v1_handles[i].used) { return i; }
    }
    return ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process;
}

u32 ipc_v1_free_call_slot() {
    for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
        if (ipc_v1_calls[i].state == ipc_v1_call_state::free) { return i; }
    }
    return ipc_v1_max_pending_calls;
}

u32 ipc_v1_allocate_handle(u32 endpoint_slot, u64 holder, u32 rights, u64 badge) {
    if (!ipc_v1_next_handle || ipc_v1_handle_count(holder) >= ipc_v1_max_handles_per_process) {
        return ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process;
    }
    const u32 slot = ipc_v1_free_handle_slot();
    if (slot == ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process) { return slot; }
    auto& handle = ipc_v1_handles[slot];
    handle.used = true; handle.endpoint_slot = endpoint_slot; handle.rights = rights;
    handle.value = ipc_v1_next_handle++; handle.holder_pid = holder; handle.badge = badge;
    return slot;
}

void ipc_v1_wake_call(u32 slot, i64 result) {
    if (slot >= ipc_v1_max_pending_calls) { return; }
    const auto& call = ipc_v1_calls[slot];
    if (call.caller_thread_slot >= thread_max_total) { return; }
    auto& waiter = threads[call.caller_thread_slot];
    if (waiter.state != thread_state::blocked || waiter.wait_kind != thread_wait_kind::ipc_v1_call ||
        waiter.ipc_v1_call_slot != slot) { return; }
    waiter.ipc_v1_phase = call.state == ipc_v1_call_state::queued
        ? static_cast<u32>(ipc_v1_call_phase::not_delivered)
        : static_cast<u32>(ipc_v1_call_phase::delivered);
    if (call.state == ipc_v1_call_state::replied) {
        waiter.ipc_v1_phase = static_cast<u32>(ipc_v1_call_phase::replied);
        waiter.ipc_v1_length = call.reply_length;
        waiter.ipc_v1_label = call.reply_label;
        waiter.ipc_v1_payload_address = waiter.ipc_v1_reply_address;
        copy_bytes(waiter.ipc_v1_payload, call.reply, call.reply_length);
    } else { waiter.ipc_v1_length = 0; }
    ready_with(waiter, result);
}

void ipc_v1_close_endpoint(u32 endpoint_slot, i64 result) {
    if (endpoint_slot >= ipc_v1_max_endpoints_system || !ipc_v1_endpoints[endpoint_slot].used) { return; }
    ipc_v1_endpoints[endpoint_slot].closed = true;
    for (auto& wait_set : ipc_v1_wait_sets) {
        if (!wait_set.used) { continue; }
        for (auto& source : wait_set.sources) {
            if (source.used && source.source_kind == static_cast<u32>(ipc_v1_wait_source::endpoint) &&
                source.object_slot == endpoint_slot) { source.closed = true; }
        }
    }
    for (auto& handle : ipc_v1_handles) {
        if (handle.used && handle.endpoint_slot == endpoint_slot) { handle = ipc_v1_handle_record{}; }
    }
    for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
        auto& call = ipc_v1_calls[i];
        if (call.state != ipc_v1_call_state::free && call.endpoint_slot == endpoint_slot) {
            ipc_v1_wake_call(i, result);
            call = ipc_v1_call_record{};
        }
    }
    for (auto& thread : threads) {
        if (thread.state == thread_state::blocked && thread.wait_kind == thread_wait_kind::ipc_v1_receive) {
            if (thread.ipc_v1_call_slot != endpoint_slot) { continue; }
            thread.ipc_v1_length = 0; thread.ipc_v1_token = 0;
            ready_with(thread, result);
        }
    }
    ipc_v1_endpoints[endpoint_slot] = ipc_v1_endpoint_record{};
    ipc_v1_notify_wait_sets();
}

void ipc_v1_revoke_process(u64 pid) {
    expire_waiters();
    bool had_grant[ipc_v1_max_grants_system]{};
    for (u32 i = 0; i < ipc_v1_max_grant_mappings_system; ++i) {
        if (ipc_v1_grant_mappings[i].used && ipc_v1_grant_mappings[i].holder_pid == pid) {
            had_grant[ipc_v1_grant_mappings[i].grant_slot] = true;
            ipc_v1_remove_grant_mapping(i);
        }
    }
    for (auto& handle : ipc_v1_grant_handles) {
        if (handle.used && handle.holder_pid == pid) {
            if (handle.object_slot < ipc_v1_max_grants_system) { had_grant[handle.object_slot] = true; }
            handle = ipc_v1_grant_handle_record{};
        }
    }
    for (u32 slot = 0; slot < ipc_v1_max_grants_system; ++slot) {
        if (!had_grant[slot] || !ipc_v1_grants[slot].used) { continue; }
        bool remains = false;
        for (const auto& handle : ipc_v1_grant_handles) {
            remains = remains || (handle.used && handle.object_slot == slot);
        }
        if (!remains) { ipc_v1_destroy_grant(slot); }
    }
    bool had_notification[ipc_v1_max_notifications_system]{};
    bool had_wait_set[ipc_v1_max_wait_sets_system]{};
    for (auto& handle : ipc_v1_notification_handles) {
        if (handle.used && handle.holder_pid == pid) {
            if (handle.object_slot < ipc_v1_max_notifications_system) {
                had_notification[handle.object_slot] = true;
            }
            handle = ipc_v1_notification_handle_record{};
        }
    }
    for (auto& handle : ipc_v1_wait_set_handles) {
        if (handle.used && handle.holder_pid == pid) {
            if (handle.object_slot < ipc_v1_max_wait_sets_system) { had_wait_set[handle.object_slot] = true; }
            handle = ipc_v1_wait_set_handle_record{};
        }
    }
    for (u32 slot = 0; slot < ipc_v1_max_wait_sets_system; ++slot) {
        if (!had_wait_set[slot] || !ipc_v1_wait_sets[slot].used) { continue; }
        bool remains = false;
        for (const auto& handle : ipc_v1_wait_set_handles) {
            remains = remains || (handle.used && handle.object_slot == slot);
        }
        if (!remains) {
            ipc_v1_wait_sets[slot] = ipc_v1_wait_set_record{};
            for (auto& thread : threads) {
                if (thread.state == thread_state::blocked &&
                    thread.wait_kind == thread_wait_kind::ipc_v1_wait_set && thread.ipc_v1_call_slot == slot) {
                    ready_with(thread, static_cast<i64>(ipc_v1_error::closed));
                }
            }
        }
    }
    for (u32 slot = 0; slot < ipc_v1_max_notifications_system; ++slot) {
        if (!had_notification[slot] || !ipc_v1_notifications[slot].used) { continue; }
        bool remains = false;
        for (const auto& handle : ipc_v1_notification_handles) {
            remains = remains || (handle.used && handle.object_slot == slot);
        }
        if (!remains) {
            ipc_v1_notifications[slot] = ipc_v1_notification_record{};
            for (auto& wait_set : ipc_v1_wait_sets) {
                for (auto& source : wait_set.sources) {
                    if (source.used && source.source_kind == static_cast<u32>(ipc_v1_wait_source::notification) &&
                        source.object_slot == slot) { source.closed = true; }
                }
            }
            for (auto& thread : threads) {
                if (thread.state == thread_state::blocked &&
                    thread.wait_kind == thread_wait_kind::ipc_v1_notification &&
                    thread.ipc_v1_call_slot == slot) {
                    thread.ipc_v1_label = 0;
                    ready_with(thread, static_cast<i64>(ipc_v1_error::closed));
                }
            }
            ipc_v1_notify_wait_sets();
        }
    }
    bool had_handle[ipc_v1_max_endpoints_system]{};
    bool had_receiver[ipc_v1_max_endpoints_system]{};
    for (const auto& handle : ipc_v1_handles) {
        if (handle.used && handle.holder_pid == pid && handle.endpoint_slot < ipc_v1_max_endpoints_system) {
            had_handle[handle.endpoint_slot] = true;
            if ((handle.rights & static_cast<u32>(ipc_v1_right::receive)) != 0) {
                had_receiver[handle.endpoint_slot] = true;
            }
        }
    }
    for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
        auto& call = ipc_v1_calls[i];
        if (call.state == ipc_v1_call_state::free) { continue; }
        if (call.caller_pid == pid) { call = ipc_v1_call_record{}; continue; }
        if (call.receiver_pid == pid && call.state == ipc_v1_call_state::delivered) {
            ipc_v1_wake_call(i, static_cast<i64>(ipc_v1_error::closed));
            call = ipc_v1_call_record{};
        }
    }
    for (auto& handle : ipc_v1_handles) {
        if (handle.used && handle.holder_pid == pid) { handle = ipc_v1_handle_record{}; }
    }
    for (u32 slot = 0; slot < ipc_v1_max_endpoints_system; ++slot) {
        if (!had_handle[slot] || !ipc_v1_endpoints[slot].used) { continue; }
        bool receiver_remains = false;
        bool handle_remains = false;
        for (const auto& handle : ipc_v1_handles) {
            handle_remains = handle_remains || (handle.used && handle.endpoint_slot == slot);
            receiver_remains = receiver_remains || (handle.used && handle.endpoint_slot == slot &&
                (handle.rights & static_cast<u32>(ipc_v1_right::receive)) != 0);
        }
        if (!handle_remains || (had_receiver[slot] && !receiver_remains)) {
            ipc_v1_close_endpoint(slot, static_cast<i64>(ipc_v1_error::closed));
        }
    }
    for (auto& thread : threads) {
        if (thread.process == nullptr || thread.process->pid != pid) { continue; }
        ipc_v1_unpin(thread);
    }
}

bool ipc_v1_deliver_to_waiter(u32 call_slot) {
    auto& call = ipc_v1_calls[call_slot];
    thread_record* waiter = nullptr;
    for (auto& thread : threads) {
        if (thread.state != thread_state::blocked || thread.wait_kind != thread_wait_kind::ipc_v1_receive) { continue; }
        auto* handle = ipc_v1_handle_for(thread.wait_target, thread.process->pid);
        if (handle == nullptr || handle->endpoint_slot != call.endpoint_slot) { continue; }
        if (waiter == nullptr || thread.wait_order < waiter->wait_order) { waiter = &thread; }
    }
    if (waiter == nullptr) { return false; }
    if (ipc_v1_token_count(waiter->process->pid) >= ipc_v1_max_reply_tokens_per_process ||
        !ipc_v1_next_reply_token) {
        waiter->ipc_v1_length = 0; waiter->ipc_v1_label = waiter->ipc_v1_badge = waiter->ipc_v1_token = 0;
        ready_with(*waiter, static_cast<i64>(ipc_v1_error::resources));
        return true;
    }
    if (call.payload_length > waiter->ipc_v1_payload_capacity) {
        waiter->ipc_v1_length = call.payload_length;
        waiter->ipc_v1_label = waiter->ipc_v1_badge = waiter->ipc_v1_token = 0;
        ready_with(*waiter, static_cast<i64>(ipc_v1_error::buffer_too_small));
        return true;
    }
    auto* receiver = ipc_v1_handle_for(waiter->wait_target, waiter->process->pid);
    if (receiver == nullptr) { return false; }
    call.state = ipc_v1_call_state::delivered;
    call.receiver_pid = waiter->process->pid;
    call.reply_token = ipc_v1_next_reply_token++;
    waiter->ipc_v1_length = call.payload_length;
    waiter->ipc_v1_label = call.label; waiter->ipc_v1_badge = call.badge;
    waiter->ipc_v1_token = call.reply_token; waiter->ipc_v1_call_slot = call_slot;
    copy_bytes(waiter->ipc_v1_payload, call.payload, call.payload_length);
    ready_with(*waiter, 0);
    ipc_v1_notify_wait_sets();
    return true;
}

void ipc_v1_try_deliver_queued(u32 endpoint_slot) {
    for (;;) {
        u32 selected = ipc_v1_max_pending_calls;
        for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
            const auto& call = ipc_v1_calls[i];
            if (call.state == ipc_v1_call_state::queued && call.endpoint_slot == endpoint_slot &&
                (selected == ipc_v1_max_pending_calls || call.order < ipc_v1_calls[selected].order)) {
                selected = i;
            }
        }
        if (selected == ipc_v1_max_pending_calls || !ipc_v1_deliver_to_waiter(selected)) { return; }
    }
}

i64 ipc_v1_reply_token(u64 token, u64 label, const u8* payload, u32 length) {
    u32 call_slot = ipc_v1_max_pending_calls;
    for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
        if (ipc_v1_calls[i].state == ipc_v1_call_state::delivered && ipc_v1_calls[i].reply_token == token) {
            call_slot = i; break;
        }
    }
    if (call_slot == ipc_v1_max_pending_calls) { return static_cast<i64>(ipc_v1_error::stale_token); }
    auto& call = ipc_v1_calls[call_slot];
    if (call.receiver_pid != current->pid) { return static_cast<i64>(ipc_v1_error::denied); }
    if (thread_deadline_reached(clock::monotonic_ns(), call.deadline_ns)) {
        ipc_v1_wake_call(call_slot, static_cast<i64>(ipc_v1_error::timeout));
        call = ipc_v1_call_record{};
        return static_cast<i64>(ipc_v1_error::stale_token);
    }
    if (length > call.reply_capacity) { return static_cast<i64>(ipc_v1_error::buffer_too_small); }
    call.reply_label = label; call.reply_length = length;
    if (length != 0) { copy_bytes(call.reply, payload, length); }
    call.state = ipc_v1_call_state::replied;
    ipc_v1_wake_call(call_slot, 0);
    call = ipc_v1_call_record{};
    return 0;
}

void* ipc_v1_syscall(interrupt_frame* frame) {
    expire_waiters();
    const u64 action = frame->rdi, address = frame->rsi, flags = frame->rdx;
    i64 result = static_cast<i64>(ipc_v1_error::invalid_argument);
    if (flags != 0) { frame->rax = static_cast<u64>(result); return frame; }
    if (action == static_cast<u64>(ipc_v1_action::query_features)) {
        if (!user_range_ok(address, sizeof(ipc_v1_feature_query), false) ||
            !user_range_ok(address, sizeof(ipc_v1_feature_query), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        ipc_v1_feature_query query{};
        copy_from_user(&query, address, sizeof(query));
        const bool outputs_zero = query.known_features == 0 && query.supported_features == 0 &&
            query.max_message_bytes == 0 && query.max_handles_per_process == 0 &&
            query.max_endpoints_system == 0 && query.max_pending_calls == 0 &&
            query.max_queue_per_endpoint == 0 && query.max_reply_tokens_per_process == 0;
        if (query.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(query.header, sizeof(query)) || !outputs_zero ||
                 query.reserved[0] != 0 || query.reserved[1] != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else {
            query.known_features = ipc_v1_feature_known_mask;
            query.supported_features = 0;
            query.max_message_bytes = ipc_v1_max_message_bytes;
            query.max_handles_per_process = ipc_v1_max_handles_per_process;
            query.max_endpoints_system = ipc_v1_max_endpoints_system;
            query.max_pending_calls = ipc_v1_max_pending_calls;
            query.max_queue_per_endpoint = ipc_v1_max_queue_per_endpoint;
            query.max_reply_tokens_per_process = ipc_v1_max_reply_tokens_per_process;
            copy_to_user(address, &query, sizeof(query)); result = 0;
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::grant_create)) {
        ipc_v1_grant_create request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags ||
                 request.length_out || request.handle_out || request.reserved[0] || request.reserved[1] ||
                 !request.length || request.length > u64{ipc_v1_max_grant_pages} * page_size ||
                 !request.rights || (request.rights & ~ipc_v1_grant_right_all)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (request.source && !user_range_ok(request.source, request.length, false)) {
            result = static_cast<i64>(ipc_v1_error::address);
        } else if (current == nullptr || current->closing || current->continuation.active()) {
            result = static_cast<i64>(ipc_v1_error::state);
        } else if (!ipc_v1_next_handle || ipc_v1_handle_count(current->pid) >= ipc_v1_max_handles_per_process) {
            result = static_cast<i64>(ipc_v1_error::resources);
        } else {
            u32 grant_slot = ipc_v1_max_grants_system;
            for (u32 i = 0; i < ipc_v1_max_grants_system; ++i) {
                if (!ipc_v1_grants[i].used) { grant_slot = i; break; }
            }
            u32 handle_slot = ipc_v1_max_grants_system * ipc_v1_max_handles_per_process;
            for (u32 i = 0; i < ipc_v1_max_grants_system * ipc_v1_max_handles_per_process; ++i) {
                if (!ipc_v1_grant_handles[i].used) { handle_slot = i; break; }
            }
            if (grant_slot == ipc_v1_max_grants_system ||
                handle_slot == ipc_v1_max_grants_system * ipc_v1_max_handles_per_process) {
                result = static_cast<i64>(ipc_v1_error::resources);
            } else {
                const u32 page_count = static_cast<u32>((request.length + page_size - 1) / page_size);
                ipc_v1_grant_record grant{};
                grant.used = true; grant.page_count = page_count; grant.length = request.length;
                bool allocated = true;
                u64 offset = 0;
                for (u32 i = 0; i < page_count; ++i) {
                    u64 physical = 0;
                    if (allocate_user_page(&physical) != memory_result::none) { allocated = false; break; }
                    grant.pages[i] = physical;
                    auto* bytes = reinterpret_cast<u8*>(physical);
                    for (u32 j = 0; j < page_size; ++j) { bytes[j] = 0; }
                    const u64 count = request.length - offset < page_size ? request.length - offset : page_size;
                    if (request.source && count) {
                        copy_from_user(bytes, request.source + offset, count);
                    }
                    offset += count;
                }
                if (!allocated) {
                    for (u32 i = 0; i < page_count; ++i) {
                        if (grant.pages[i]) { (void)release_user_page(grant.pages[i]); }
                    }
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else {
                    ipc_v1_grants[grant_slot] = grant;
                    const u32 allocated_handle = ipc_v1_allocate_grant_handle(grant_slot, current->pid, request.rights);
                    if (allocated_handle == ipc_v1_max_grants_system * ipc_v1_max_handles_per_process) {
                        ipc_v1_destroy_grant(grant_slot);
                        result = static_cast<i64>(ipc_v1_error::resources);
                    } else {
                        request.length_out = request.length;
                        request.handle_out = ipc_v1_grant_handles[allocated_handle].value;
                        copy_to_user(address, &request, sizeof(request)); result = 0;
                    }
                }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::grant_delegate)) {
        ipc_v1_object_delegate request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* source = current ? ipc_v1_grant_handle_for(request.handle, current->pid) : nullptr;
        process_record* target = task_by_pid(request.target_pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags || request.badge ||
                 request.handle_out || request.reserved[0] || request.reserved[1] || !request.target_pid ||
                 !request.rights || (request.rights & ~ipc_v1_grant_right_all)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!source) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if (!(source->rights & static_cast<u32>(ipc_v1_grant_right::delegate)) ||
                 (request.rights & ~source->rights)) { result = static_cast<i64>(ipc_v1_error::denied); }
        else if (!target || target->closing || target->state == task_state::dead || target->state == task_state::building) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else {
            const u32 slot = ipc_v1_allocate_grant_handle(source->object_slot, request.target_pid, request.rights);
            if (slot == ipc_v1_max_grants_system * ipc_v1_max_handles_per_process) {
                result = static_cast<i64>(ipc_v1_error::resources);
            } else { request.handle_out = ipc_v1_grant_handles[slot].value; copy_to_user(address, &request, sizeof(request)); result = 0; }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::grant_map)) {
        ipc_v1_grant_map request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = current ? ipc_v1_grant_handle_for(request.handle, current->pid) : nullptr;
        const bool address_valid = request.address && request.address % page_size == 0 &&
            request.address >= anonymous_vm::arena_begin && request.address < anonymous_vm::arena_end;
        const u64 rounded = handle && handle->object_slot < ipc_v1_max_grants_system &&
            ipc_v1_grants[handle->object_slot].used ?
            ((ipc_v1_grants[handle->object_slot].length + page_size - 1) & ~(page_size - 1)) : 0;
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved32 ||
                 request.map_id_out || request.length_out || request.reserved[0] || request.reserved[1] ||
                 !address_valid ||
                 (request.access != static_cast<u32>(ipc_v1_grant_access::read) &&
                  request.access != static_cast<u32>(ipc_v1_grant_access::read_write))) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!handle) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if (!rounded || rounded > anonymous_vm::arena_end - request.address) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!(handle->rights & static_cast<u32>(ipc_v1_grant_right::read_mapping)) ||
                 (request.access == static_cast<u32>(ipc_v1_grant_access::read_write) &&
                  !(handle->rights & static_cast<u32>(ipc_v1_grant_right::write_mapping)))) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else if (current->closing || current->continuation.active()) { result = static_cast<i64>(ipc_v1_error::state); }
        else if (!ipc_v1_next_map_id || current->user_pages > process_max_pages ||
                 rounded / page_size > process_max_pages - current->user_pages) {
            result = static_cast<i64>(ipc_v1_error::resources);
        } else {
            u32 map_slot = ipc_v1_max_grant_mappings_system;
            for (u32 i = 0; i < ipc_v1_max_grant_mappings_system; ++i) {
                if (!ipc_v1_grant_mappings[i].used) { map_slot = i; break; }
            }
            if (map_slot == ipc_v1_max_grant_mappings_system) { result = static_cast<i64>(ipc_v1_error::resources); }
            else {
                auto& grant = ipc_v1_grants[handle->object_slot];
                const u32 page_count = grant.page_count;
                const auto reserved = vm1_probe_regions[static_cast<u32>(current - tasks)].reserve(
                    request.address, rounded, page_size, true);
                if (reserved < 0) { result = reserved == anonymous_vm::collision
                    ? static_cast<i64>(ipc_v1_error::address) : static_cast<i64>(ipc_v1_error::resources); }
                else {
                    bool prepared = true;
                    u32 done = 0;
                    for (; done < page_count; ++done) {
                        const u64 page_address = request.address + u64{done} * page_size;
                        u64 physical = 0; vm_page_protection prior{};
                        if (vm_lookup_page_in(current->cr3, page_address, &physical, &prior) != memory_result::not_mapped ||
                            vm_prepare_page_in(current->cr3, page_address) != memory_result::none) {
                            vm_prune_empty_page_tables_in(current->cr3, page_address);
                            prepared = false; break;
                        }
                        if (retain_user_page(grant.pages[done]) != memory_result::none) {
                            vm_prune_empty_page_tables_in(current->cr3, page_address);
                            prepared = false; break;
                        }
                        if (vm_install_page_in(current->cr3, page_address, grant.pages[done],
                                request.access == static_cast<u32>(ipc_v1_grant_access::read)
                                    ? vm_page_protection::read : vm_page_protection::read_write) != memory_result::none) {
                            if (release_user_page(grant.pages[done]) != memory_result::none) { halt(); }
                            vm_prune_empty_page_tables_in(current->cr3, page_address);
                            prepared = false; break;
                        }
                    }
                    if (!prepared) {
                        for (u32 i = 0; i < done; ++i) {
                            u64 physical = 0;
                            if (vm_remove_page_in(current->cr3, request.address + u64{i} * page_size, &physical) != memory_result::none ||
                                release_user_page(physical) != memory_result::none) { halt(); }
                            vm_prune_empty_page_tables_in(current->cr3, request.address + u64{i} * page_size);
                        }
                        if (vm1_probe_regions[static_cast<u32>(current - tasks)].unmap(request.address, rounded) != 0) { halt(); }
                        result = static_cast<i64>(ipc_v1_error::resources);
                    } else {
                        current->user_pages += page_count;
                        const u64 map_id = ipc_v1_next_map_id++;
                        ipc_v1_grant_mappings[map_slot] = {true, handle->object_slot, page_count,
                            request.access, map_id, current->pid, request.address};
                        request.map_id_out = map_id; request.length_out = grant.length;
                        copy_to_user(address, &request, sizeof(request)); result = 0;
                    }
                }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::grant_unmap)) {
        ipc_v1_grant_unmap request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = current ? ipc_v1_grant_handle_for(request.handle, current->pid) : nullptr;
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || !request.map_id || request.reserved[0] || request.reserved[1]) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!handle) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if (!(handle->rights & static_cast<u32>(ipc_v1_grant_right::read_mapping))) { result = static_cast<i64>(ipc_v1_error::denied); }
        else {
            u32 found = ipc_v1_max_grant_mappings_system;
            for (u32 i = 0; i < ipc_v1_max_grant_mappings_system; ++i) {
                const auto& mapping = ipc_v1_grant_mappings[i];
                if (mapping.used && mapping.map_id == request.map_id && mapping.holder_pid == current->pid &&
                    mapping.grant_slot == handle->object_slot) { found = i; break; }
            }
            if (found == ipc_v1_max_grant_mappings_system) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
            else {
                const auto mapping = ipc_v1_grant_mappings[found];
                if (pinned_range(current, mapping.address, mapping.address + u64{mapping.page_count} * page_size)) {
                    result = static_cast<i64>(ipc_v1_error::busy);
                } else { ipc_v1_remove_grant_mapping(found); result = 0; }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::grant_close)) {
        ipc_v1_object_close request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = current ? ipc_v1_grant_handle_for(request.handle, current->pid) : nullptr;
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved[0] || request.reserved[1]) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!handle) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if (!(handle->rights & static_cast<u32>(ipc_v1_grant_right::manage))) { result = static_cast<i64>(ipc_v1_error::denied); }
        else {
            const u32 slot = handle->object_slot;
            bool busy = false;
            for (const auto& mapping : ipc_v1_grant_mappings) {
                if (!mapping.used || mapping.grant_slot != slot) { continue; }
                process_record* owner = task_by_pid(mapping.holder_pid);
                if (owner && pinned_range(owner, mapping.address, mapping.address + u64{mapping.page_count} * page_size)) {
                    busy = true; break;
                }
            }
            if (busy) { result = static_cast<i64>(ipc_v1_error::busy); }
            else { ipc_v1_destroy_grant(slot); result = 0; }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::endpoint_create)) {
        ipc_v1_endpoint_create request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags != 0 ||
                 request.handle_out != 0 || request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 request.rights == 0 || (request.rights & ~ipc_v1_right_all) != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (current == nullptr || current->closing) { result = static_cast<i64>(ipc_v1_error::state); }
        else if (ipc_v1_handle_count(current->pid) >= ipc_v1_max_handles_per_process || !ipc_v1_next_handle) {
            result = static_cast<i64>(ipc_v1_error::resources);
        } else {
            u32 endpoint_slot = ipc_v1_max_endpoints_system;
            for (u32 i = 0; i < ipc_v1_max_endpoints_system; ++i) {
                if (!ipc_v1_endpoints[i].used) { endpoint_slot = i; break; }
            }
            if (endpoint_slot == ipc_v1_max_endpoints_system) { result = static_cast<i64>(ipc_v1_error::resources); }
            else {
                ipc_v1_endpoints[endpoint_slot] = {true, false};
                const u32 handle_slot = ipc_v1_allocate_handle(endpoint_slot, current->pid, request.rights, 0);
                if (handle_slot == ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process) {
                    ipc_v1_endpoints[endpoint_slot] = ipc_v1_endpoint_record{};
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else {
                    request.handle_out = ipc_v1_handles[handle_slot].value;
                    copy_to_user(address, &request, sizeof(request)); result = 0;
                }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::endpoint_delegate)) {
        ipc_v1_endpoint_delegate request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* source = ipc_v1_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags != 0 ||
                 request.handle_out != 0 || request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 request.target_pid == 0 || request.rights == 0 || (request.rights & ~ipc_v1_right_all) != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (source == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((source->rights & static_cast<u32>(ipc_v1_right::delegate)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else if ((request.rights & ~source->rights) != 0) { result = static_cast<i64>(ipc_v1_error::denied); }
        else if (task_by_pid(request.target_pid) == nullptr || task_by_pid(request.target_pid)->closing ||
                 task_by_pid(request.target_pid)->state == task_state::dead ||
                 task_by_pid(request.target_pid)->state == task_state::building) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else {
            const u32 slot = ipc_v1_allocate_handle(source->endpoint_slot, request.target_pid,
                                                     request.rights, request.badge);
            if (slot == ipc_v1_max_endpoints_system * ipc_v1_max_handles_per_process) {
                result = static_cast<i64>(ipc_v1_error::resources);
            } else { request.handle_out = ipc_v1_handles[slot].value; copy_to_user(address, &request, sizeof(request)); result = 0; }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::endpoint_close)) {
        ipc_v1_endpoint_close request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved[0] != 0 || request.reserved[1] != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_right::manage)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else { ipc_v1_close_endpoint(handle->endpoint_slot, static_cast<i64>(ipc_v1_error::closed)); result = 0; }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::notification_create) ||
        action == static_cast<u64>(ipc_v1_action::wait_set_create)) {
        ipc_v1_object_create request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        const bool notification = action == static_cast<u64>(ipc_v1_action::notification_create);
        const u32 rights_mask = notification ? ipc_v1_notification_right_all : ipc_v1_wait_set_right_all;
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags != 0 ||
                 request.handle_out != 0 || request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 request.rights == 0 || (request.rights & ~rights_mask) != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (current == nullptr || current->closing) { result = static_cast<i64>(ipc_v1_error::state); }
        else if (!notification) {
            u32 object_slot = ipc_v1_max_wait_sets_system;
            for (u32 i = 0; i < ipc_v1_max_wait_sets_system; ++i) {
                if (!ipc_v1_wait_sets[i].used) { object_slot = i; break; }
            }
            if (object_slot == ipc_v1_max_wait_sets_system) { result = static_cast<i64>(ipc_v1_error::resources); }
            else {
                ipc_v1_wait_sets[object_slot] = ipc_v1_wait_set_record{true, 1, {}};
                const u32 slot = ipc_v1_allocate_wait_set_handle(object_slot, current->pid, request.rights, 0);
                if (slot == ipc_v1_max_wait_sets_system * ipc_v1_max_handles_per_process) {
                    ipc_v1_wait_sets[object_slot] = ipc_v1_wait_set_record{};
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else {
                    request.handle_out = ipc_v1_wait_set_handles[slot].value;
                    copy_to_user(address, &request, sizeof(request)); result = 0;
                }
            }
        }
        else {
            u32 object_slot = ipc_v1_max_notifications_system;
            for (u32 i = 0; i < ipc_v1_max_notifications_system; ++i) {
                if (!ipc_v1_notifications[i].used) { object_slot = i; break; }
            }
            if (object_slot == ipc_v1_max_notifications_system) { result = static_cast<i64>(ipc_v1_error::resources); }
            else {
                ipc_v1_notifications[object_slot] = {true, 0};
                const u32 slot = ipc_v1_allocate_notification_handle(object_slot, current->pid, request.rights, 0);
                if (slot == ipc_v1_max_notifications_system * ipc_v1_max_handles_per_process) {
                    ipc_v1_notifications[object_slot] = ipc_v1_notification_record{};
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else {
                    request.handle_out = ipc_v1_notification_handles[slot].value;
                    copy_to_user(address, &request, sizeof(request)); result = 0;
                }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::notification_delegate) ||
        action == static_cast<u64>(ipc_v1_action::wait_set_delegate)) {
        ipc_v1_object_delegate request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        const bool notification = action == static_cast<u64>(ipc_v1_action::notification_delegate);
        auto* notification_source = notification ? ipc_v1_notification_handle_for(request.handle, current->pid) : nullptr;
        auto* wait_set_source = notification ? nullptr : ipc_v1_wait_set_handle_for(request.handle, current->pid);
        const u32 rights_mask = notification ? ipc_v1_notification_right_all : ipc_v1_wait_set_right_all;
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags != 0 ||
                 request.handle_out != 0 || request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 request.target_pid == 0 || request.rights == 0 || (request.rights & ~rights_mask) != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if ((notification && notification_source == nullptr) || (!notification && wait_set_source == nullptr)) {
            result = static_cast<i64>(ipc_v1_error::invalid_handle);
        } else if (notification
            ? ((notification_source->rights & static_cast<u32>(ipc_v1_notification_right::delegate)) == 0 ||
               (request.rights & ~notification_source->rights) != 0)
            : ((wait_set_source->rights & static_cast<u32>(ipc_v1_wait_set_right::delegate)) == 0 ||
               (request.rights & ~wait_set_source->rights) != 0)) { result = static_cast<i64>(ipc_v1_error::denied); }
        else if (task_by_pid(request.target_pid) == nullptr || task_by_pid(request.target_pid)->closing ||
                 task_by_pid(request.target_pid)->state == task_state::dead ||
                 task_by_pid(request.target_pid)->state == task_state::building) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else {
            if (notification) {
                const u32 slot = ipc_v1_allocate_notification_handle(notification_source->object_slot,
                                                                      request.target_pid, request.rights, request.badge);
                if (slot == ipc_v1_max_notifications_system * ipc_v1_max_handles_per_process) {
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else { request.handle_out = ipc_v1_notification_handles[slot].value;
                    copy_to_user(address, &request, sizeof(request)); result = 0; }
            } else {
                const u32 slot = ipc_v1_allocate_wait_set_handle(wait_set_source->object_slot,
                                                                  request.target_pid, request.rights, request.badge);
                if (slot == ipc_v1_max_wait_sets_system * ipc_v1_max_handles_per_process) {
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else { request.handle_out = ipc_v1_wait_set_handles[slot].value;
                    copy_to_user(address, &request, sizeof(request)); result = 0; }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::notification_signal)) {
        ipc_v1_notification_signal request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_notification_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved[0] != 0 ||
                 request.reserved[1] != 0) { result = static_cast<i64>(ipc_v1_error::invalid_argument); }
        else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_notification_right::signal)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            auto& object = ipc_v1_notifications[handle->object_slot];
            if (!object.used) { result = static_cast<i64>(ipc_v1_error::closed); }
            else {
                object.pending_bits |= handle->badge;
                ipc_v1_wake_notification_waiter(handle->object_slot);
                ipc_v1_notify_wait_sets();
                result = 0;
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::wait_set_add)) {
        ipc_v1_wait_set_add request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* wait_handle = ipc_v1_wait_set_handle_for(request.wait_set_handle, current->pid);
        auto* endpoint_handle = request.source_kind == static_cast<u32>(ipc_v1_wait_source::endpoint)
            ? ipc_v1_handle_for(request.source_handle, current->pid) : nullptr;
        auto* notification_handle = request.source_kind == static_cast<u32>(ipc_v1_wait_source::notification)
            ? ipc_v1_notification_handle_for(request.source_handle, current->pid) : nullptr;
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.flags != 0 ||
                 request.source_id_out != 0 || request.reserved32 != 0 ||
                 request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 (request.source_kind != static_cast<u32>(ipc_v1_wait_source::endpoint) &&
                  request.source_kind != static_cast<u32>(ipc_v1_wait_source::notification))) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (wait_handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((wait_handle->rights & static_cast<u32>(ipc_v1_wait_set_right::manage)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else if ((request.source_kind == static_cast<u32>(ipc_v1_wait_source::endpoint) && endpoint_handle == nullptr) ||
                   (request.source_kind == static_cast<u32>(ipc_v1_wait_source::notification) && notification_handle == nullptr)) {
            result = static_cast<i64>(ipc_v1_error::invalid_handle);
        } else if (request.source_kind == static_cast<u32>(ipc_v1_wait_source::endpoint) &&
                   (endpoint_handle->rights & static_cast<u32>(ipc_v1_right::receive)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else if (request.source_kind == static_cast<u32>(ipc_v1_wait_source::notification) &&
                   (notification_handle->rights & static_cast<u32>(ipc_v1_notification_right::wait)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            auto& object = ipc_v1_wait_sets[wait_handle->object_slot];
            u32 source_slot = ipc_v1_max_wait_set_sources;
            for (u32 i = 0; i < ipc_v1_max_wait_set_sources; ++i) {
                if (!object.sources[i].used) { source_slot = i; break; }
            }
            if (source_slot == ipc_v1_max_wait_set_sources || !object.next_source_id) {
                result = static_cast<i64>(ipc_v1_error::resources);
            } else {
                auto& source = object.sources[source_slot];
                source.used = true; source.closed = false; source.source_id = object.next_source_id++;
                source.source_kind = request.source_kind;
                source.object_slot = request.source_kind == static_cast<u32>(ipc_v1_wait_source::endpoint)
                    ? endpoint_handle->endpoint_slot : notification_handle->object_slot;
                request.source_id_out = source.source_id;
                copy_to_user(address, &request, sizeof(request)); result = 0;
                ipc_v1_notify_wait_sets();
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::wait_set_remove)) {
        ipc_v1_wait_set_remove request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_wait_set_handle_for(request.wait_set_handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.source_id == 0 ||
                 request.reserved32 != 0 || request.reserved[0] != 0 || request.reserved[1] != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_wait_set_right::manage)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
            auto& object = ipc_v1_wait_sets[handle->object_slot];
            for (auto& source : object.sources) {
                if (source.used && source.source_id == request.source_id) {
                    source = ipc_v1_wait_set_source_record{}; result = 0; break;
                }
            }
            if (result == 0) { ipc_v1_notify_wait_sets(); }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::wait_set_wait)) {
        ipc_v1_wait_set_wait request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_wait_set_handle_for(request.handle, current->pid);
        const u64 event_bytes = static_cast<u64>(request.capacity) * sizeof(ipc_v1_wait_event);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.count_out != 0 ||
                 request.capacity > ipc_v1_max_wait_set_sources || (request.capacity != 0 && request.events == 0) ||
                 request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 ipc_v1_ranges_overlap(address, sizeof(request), request.events, event_bytes)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!user_range_ok(request.events, event_bytes, true)) { result = static_cast<i64>(ipc_v1_error::address); }
        else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_wait_set_right::wait)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            ipc_v1_ready_event ready[ipc_v1_max_wait_set_sources]{};
            const u32 count = ipc_v1_collect_wait_set(handle->object_slot, ready);
            if (count != 0 && count > request.capacity) {
                request.count_out = count; copy_to_user(address, &request, sizeof(request));
                result = static_cast<i64>(ipc_v1_error::buffer_too_small);
            } else if (count != 0) {
                ipc_v1_wait_event events[ipc_v1_max_wait_set_sources]{};
                request.count_out = ipc_v1_consume_wait_set(handle->object_slot, events, request.capacity);
                if (request.count_out != 0) copy_to_user(request.events, events,
                    static_cast<u64>(request.count_out) * sizeof(ipc_v1_wait_event));
                copy_to_user(address, &request, sizeof(request)); result = 0;
            } else if (request.deadline_ns == 0) { result = static_cast<i64>(ipc_v1_error::would_block); }
            else if (thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns)) {
                result = static_cast<i64>(ipc_v1_error::timeout);
            } else if (!ipc_v1_next_wait_order ||
                       !ipc_v1_pin(*current_thread, 0, address, sizeof(request)) ||
                       !ipc_v1_pin(*current_thread, 1, request.events, event_bytes)) {
                ipc_v1_unpin(*current_thread); result = static_cast<i64>(ipc_v1_error::resources);
            } else {
                current_thread->ipc_v1_request_address = address;
                current_thread->ipc_v1_payload_address = request.events;
                current_thread->ipc_v1_payload_capacity = request.capacity;
                current_thread->ipc_v1_call_slot = handle->object_slot;
                current_thread->ipc_v1_event_count = 0;
                current_thread->wait_target = request.handle;
                current_thread->wait_order = ipc_v1_next_wait_order++;
                current_thread->deadline_ns = request.deadline_ns;
                current_thread->wait_kind = thread_wait_kind::ipc_v1_wait_set;
                current_thread->state = thread_state::blocked;
                frame->rax = 0; return schedule(frame);
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::notification_close)) {
        ipc_v1_object_close request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_notification_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) ||
                 request.reserved[0] != 0 || request.reserved[1] != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_notification_right::manage)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            const u32 slot = handle->object_slot;
            ipc_v1_notifications[slot] = ipc_v1_notification_record{};
            for (auto& wait_set : ipc_v1_wait_sets) {
                if (!wait_set.used) { continue; }
                for (auto& source : wait_set.sources) {
                    if (source.used && source.source_kind == static_cast<u32>(ipc_v1_wait_source::notification) &&
                        source.object_slot == slot) { source.closed = true; }
                }
            }
            for (auto& candidate : ipc_v1_notification_handles) {
                if (candidate.used && candidate.object_slot == slot) {
                    candidate = ipc_v1_notification_handle_record{};
                }
            }
            for (auto& thread : threads) {
                if (thread.state == thread_state::blocked &&
                    thread.wait_kind == thread_wait_kind::ipc_v1_notification &&
                    thread.ipc_v1_call_slot == slot) {
                    thread.ipc_v1_label = 0;
                    ready_with(thread, static_cast<i64>(ipc_v1_error::closed));
                }
            }
            ipc_v1_notify_wait_sets();
            result = 0;
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::wait_set_close)) {
        ipc_v1_object_close request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_wait_set_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) ||
                 request.reserved[0] != 0 || request.reserved[1] != 0) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_wait_set_right::manage)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            const u32 slot = handle->object_slot;
            ipc_v1_wait_sets[slot] = ipc_v1_wait_set_record{};
            for (auto& candidate : ipc_v1_wait_set_handles) {
                if (candidate.used && candidate.object_slot == slot) {
                    candidate = ipc_v1_wait_set_handle_record{};
                }
            }
            for (auto& thread : threads) {
                if (thread.state == thread_state::blocked &&
                    thread.wait_kind == thread_wait_kind::ipc_v1_wait_set && thread.ipc_v1_call_slot == slot) {
                    ready_with(thread, static_cast<i64>(ipc_v1_error::closed));
                }
            }
            result = 0;
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::notification_wait)) {
        ipc_v1_notification_wait request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_notification_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.bits_out != 0 ||
                 request.reserved[0] != 0 || request.reserved[1] != 0) { result = static_cast<i64>(ipc_v1_error::invalid_argument); }
        else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_notification_right::wait)) == 0) {
            result = static_cast<i64>(ipc_v1_error::denied);
        } else {
            auto& object = ipc_v1_notifications[handle->object_slot];
            if (!object.used) { result = static_cast<i64>(ipc_v1_error::closed); }
            else if (object.pending_bits != 0) {
                request.bits_out = object.pending_bits; object.pending_bits = 0;
                copy_to_user(address, &request, sizeof(request)); result = 0;
            } else if (request.deadline_ns == 0) { result = static_cast<i64>(ipc_v1_error::would_block); }
            else if (thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns)) {
                result = static_cast<i64>(ipc_v1_error::timeout);
            } else if (!ipc_v1_next_wait_order || !ipc_v1_pin(*current_thread, 0, address, sizeof(request))) {
                ipc_v1_unpin(*current_thread); result = static_cast<i64>(ipc_v1_error::resources);
            } else {
                current_thread->ipc_v1_request_address = address;
                current_thread->ipc_v1_label = 0;
                current_thread->ipc_v1_call_slot = handle->object_slot;
                current_thread->wait_target = request.handle;
                current_thread->wait_order = ipc_v1_next_wait_order++;
                current_thread->deadline_ns = request.deadline_ns;
                current_thread->wait_kind = thread_wait_kind::ipc_v1_notification;
                current_thread->state = thread_state::blocked;
                frame->rax = 0; return schedule(frame);
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::call)) {
        ipc_v1_call request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved != 0 ||
                 request.reply_length_out != 0 || request.phase_out != 0 || request.reply_label_out != 0 ||
                 request.send_length > ipc_v1_max_message_bytes || request.reply_capacity > ipc_v1_max_message_bytes ||
                 (request.send_length != 0 && request.send_buffer == 0) ||
                 (request.reply_capacity != 0 && request.reply_buffer == 0)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_right::call)) == 0) { result = static_cast<i64>(ipc_v1_error::denied); }
        else if (!user_range_ok(request.send_buffer, request.send_length, false) ||
                 !user_range_ok(request.reply_buffer, request.reply_capacity, true)) {
            result = static_cast<i64>(ipc_v1_error::address);
        } else if (ipc_v1_ranges_overlap(address, sizeof(request), request.reply_buffer, request.reply_capacity)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else {
            u32 endpoint_slot = handle->endpoint_slot;
            bool receiver_can_accept = false;
            for (const auto& thread : threads) {
                if (thread.state == thread_state::blocked && thread.wait_kind == thread_wait_kind::ipc_v1_receive) {
                    auto* receive_handle = ipc_v1_handle_for(thread.wait_target, thread.process->pid);
                    if (receive_handle != nullptr && receive_handle->endpoint_slot == endpoint_slot) {
                        receiver_can_accept = receiver_can_accept ||
                            (thread.ipc_v1_payload_capacity >= request.send_length &&
                             ipc_v1_token_count(thread.process->pid) < ipc_v1_max_reply_tokens_per_process);
                    }
                }
            }
            u32 queue_depth = 0;
            for (const auto& call : ipc_v1_calls) {
                if (call.state == ipc_v1_call_state::queued && call.endpoint_slot == endpoint_slot) { ++queue_depth; }
            }
            if (thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns) &&
                request.deadline_ns != 0 && !receiver_can_accept) {
                request.phase_out = static_cast<u32>(ipc_v1_call_phase::not_delivered);
                copy_to_user(address, &request, sizeof(request)); result = static_cast<i64>(ipc_v1_error::timeout);
            } else if (request.deadline_ns == 0 && !receiver_can_accept) {
                result = static_cast<i64>(ipc_v1_error::would_block);
            } else if (queue_depth >= ipc_v1_max_queue_per_endpoint && !receiver_can_accept) {
                result = static_cast<i64>(ipc_v1_error::queue_full);
            } else {
                const u32 slot = ipc_v1_free_call_slot();
                if (slot == ipc_v1_max_pending_calls || !ipc_v1_next_wait_order) { result = static_cast<i64>(ipc_v1_error::resources); }
                else if (!ipc_v1_pin(*current_thread, 0, address, sizeof(request)) ||
                         !ipc_v1_pin(*current_thread, 1, request.reply_buffer, request.reply_capacity)) {
                    ipc_v1_unpin(*current_thread); result = static_cast<i64>(ipc_v1_error::resources);
                } else {
                    auto& call = ipc_v1_calls[slot]; call = ipc_v1_call_record{};
                    call.state = ipc_v1_call_state::queued; call.endpoint_slot = endpoint_slot;
                    call.caller_thread_slot = static_cast<u32>(current_thread - threads);
                    call.caller_pid = current->pid; call.deadline_ns = request.deadline_ns;
                    call.order = ipc_v1_next_wait_order++; call.label = request.label;
                    call.badge = handle->badge;
                    call.payload_length = request.send_length; call.reply_capacity = request.reply_capacity;
                    if (request.send_length != 0) copy_from_user(call.payload, request.send_buffer, request.send_length);
                    current_thread->ipc_v1_request_address = address;
                    current_thread->ipc_v1_reply_address = request.reply_buffer;
                    current_thread->ipc_v1_call_slot = slot;
                    current_thread->ipc_v1_phase = static_cast<u32>(ipc_v1_call_phase::not_delivered);
                    current_thread->ipc_v1_length = 0;
                    current_thread->deadline_ns = request.deadline_ns;
                    ipc_v1_try_deliver_queued(endpoint_slot);
                    if (call.state == ipc_v1_call_state::queued) { ipc_v1_notify_wait_sets(); }
                    if (request.deadline_ns == 0 && call.state == ipc_v1_call_state::queued) {
                        call = ipc_v1_call_record{}; ipc_v1_unpin(*current_thread);
                        current_thread->ipc_v1_request_address = current_thread->ipc_v1_reply_address = 0;
                        result = static_cast<i64>(ipc_v1_error::would_block);
                        frame->rax = static_cast<u64>(result); return frame;
                    }
                    current_thread->wait_kind = thread_wait_kind::ipc_v1_call;
                    current_thread->state = thread_state::blocked;
                    frame->rax = 0; return schedule(frame);
                }
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::receive)) {
        ipc_v1_receive request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        auto* handle = ipc_v1_handle_for(request.handle, current->pid);
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved[0] != 0 ||
                 request.reserved[1] != 0 || request.message_length_out != 0 || request.label_out != 0 ||
                 request.badge_out != 0 || request.reply_token_out != 0 || request.capacity > ipc_v1_max_message_bytes ||
                 (request.capacity != 0 && request.buffer == 0)) { result = static_cast<i64>(ipc_v1_error::invalid_argument); }
        else if (handle == nullptr) { result = static_cast<i64>(ipc_v1_error::invalid_handle); }
        else if ((handle->rights & static_cast<u32>(ipc_v1_right::receive)) == 0) { result = static_cast<i64>(ipc_v1_error::denied); }
        else if (!user_range_ok(request.buffer, request.capacity, true)) { result = static_cast<i64>(ipc_v1_error::address); }
        else if (ipc_v1_ranges_overlap(address, sizeof(request), request.buffer, request.capacity)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        }
        else {
            u32 call_slot = ipc_v1_max_pending_calls;
            for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
                if (ipc_v1_calls[i].state == ipc_v1_call_state::queued && ipc_v1_calls[i].endpoint_slot == handle->endpoint_slot &&
                    (call_slot == ipc_v1_max_pending_calls || ipc_v1_calls[i].order < ipc_v1_calls[call_slot].order)) call_slot = i;
            }
            if (call_slot != ipc_v1_max_pending_calls) {
                auto& call = ipc_v1_calls[call_slot];
                if (call.payload_length > request.capacity) {
                    request.message_length_out = call.payload_length; copy_to_user(address, &request, sizeof(request));
                    result = static_cast<i64>(ipc_v1_error::buffer_too_small);
                } else if (ipc_v1_token_count(current->pid) >= ipc_v1_max_reply_tokens_per_process || !ipc_v1_next_reply_token) {
                    result = static_cast<i64>(ipc_v1_error::resources);
                } else {
                    call.state = ipc_v1_call_state::delivered; call.receiver_pid = current->pid;
                    call.reply_token = ipc_v1_next_reply_token++;
                    request.message_length_out = call.payload_length; request.label_out = call.label;
                    request.badge_out = call.badge; request.reply_token_out = call.reply_token;
                    copy_to_user(address, &request, sizeof(request));
                    if (call.payload_length) copy_to_user(request.buffer, call.payload, call.payload_length);
                    ipc_v1_try_deliver_queued(handle->endpoint_slot);
                    ipc_v1_notify_wait_sets();
                    result = 0;
                }
            } else if (request.deadline_ns == 0) { result = static_cast<i64>(ipc_v1_error::would_block); }
            else if (thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns)) { result = static_cast<i64>(ipc_v1_error::timeout); }
            else if (!ipc_v1_next_wait_order) { result = static_cast<i64>(ipc_v1_error::resources); }
            else if (!ipc_v1_pin(*current_thread, 0, address, sizeof(request)) ||
                     !ipc_v1_pin(*current_thread, 1, request.buffer, request.capacity)) {
                ipc_v1_unpin(*current_thread); result = static_cast<i64>(ipc_v1_error::resources);
            } else {
                current_thread->ipc_v1_request_address = address; current_thread->ipc_v1_payload_address = request.buffer;
                current_thread->ipc_v1_payload_capacity = request.capacity; current_thread->ipc_v1_length = 0;
                current_thread->ipc_v1_call_slot = handle->endpoint_slot;
                current_thread->wait_target = request.handle; current_thread->wait_order = ipc_v1_next_wait_order++;
                current_thread->deadline_ns = request.deadline_ns; current_thread->wait_kind = thread_wait_kind::ipc_v1_receive;
                current_thread->state = thread_state::blocked;
                ipc_v1_try_deliver_queued(handle->endpoint_slot);
                frame->rax = 0; return schedule(frame);
            }
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::reply)) {
        ipc_v1_reply request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reserved32 != 0 ||
                 request.reserved[0] != 0 || request.reserved[1] != 0 || request.length > ipc_v1_max_message_bytes ||
                 (request.length != 0 && request.buffer == 0)) { result = static_cast<i64>(ipc_v1_error::invalid_argument); }
        else if (!user_range_ok(request.buffer, request.length, false)) { result = static_cast<i64>(ipc_v1_error::address); }
        else {
            u8 payload[ipc_v1_max_message_bytes]{};
            if (request.length) copy_from_user(payload, request.buffer, request.length);
            result = ipc_v1_reply_token(request.reply_token, request.label, payload, request.length);
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    if (action == static_cast<u64>(ipc_v1_action::reply_receive)) {
        ipc_v1_reply_receive request{};
        if ((address & 7u) != 0 || !user_range_ok(address, sizeof(request), false) ||
            !user_range_ok(address, sizeof(request), true)) {
            frame->rax = static_cast<u64>(ipc_v1_error::address); return frame;
        }
        copy_from_user(&request, address, sizeof(request));
        if (request.header.version != ipc_v1_version) { result = static_cast<i64>(ipc_v1_error::unsupported); }
        else if (!ipc_v1_header_valid(request.header, sizeof(request)) || request.reply_consumed_out != 0 ||
                 request.receive_length_out != 0 || request.label_out != 0 || request.badge_out != 0 ||
                 request.next_reply_token_out != 0 || request.reserved[0] != 0 || request.reserved[1] != 0 ||
                 request.reply_length > ipc_v1_max_message_bytes || request.receive_capacity > ipc_v1_max_message_bytes ||
                 (request.reply_length != 0 && request.reply_buffer == 0) ||
                 (request.receive_capacity != 0 && request.receive_buffer == 0)) {
            result = static_cast<i64>(ipc_v1_error::invalid_argument);
        } else if (!user_range_ok(request.reply_buffer, request.reply_length, false)) {
            result = static_cast<i64>(ipc_v1_error::address);
        } else {
            u8 reply_payload[ipc_v1_max_message_bytes]{};
            if (request.reply_length) copy_from_user(reply_payload, request.reply_buffer, request.reply_length);
            result = ipc_v1_reply_token(request.reply_token, request.reply_label,
                                        reply_payload, request.reply_length);
            if (result != 0) { frame->rax = static_cast<u64>(result); return frame; }
            request.reply_consumed_out = ipc_v1_reply_consumed;
            auto finish_receive_error = [&](i64 error, u32 required = 0) {
                request.receive_length_out = required;
                copy_to_user(address, &request, sizeof(request));
                frame->rax = static_cast<u64>(error);
                return static_cast<void*>(frame);
            };
            auto* receive_handle = ipc_v1_handle_for(request.receive_handle, current->pid);
            if (receive_handle == nullptr) { return finish_receive_error(static_cast<i64>(ipc_v1_error::invalid_handle)); }
            if ((receive_handle->rights & static_cast<u32>(ipc_v1_right::receive)) == 0) {
                return finish_receive_error(static_cast<i64>(ipc_v1_error::denied));
            }
            if (!user_range_ok(request.receive_buffer, request.receive_capacity, true)) {
                return finish_receive_error(static_cast<i64>(ipc_v1_error::address));
            }
            if (ipc_v1_ranges_overlap(address, sizeof(request), request.receive_buffer, request.receive_capacity)) {
                return finish_receive_error(static_cast<i64>(ipc_v1_error::invalid_argument));
            }
            u32 call_slot = ipc_v1_max_pending_calls;
            for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
                if (ipc_v1_calls[i].state == ipc_v1_call_state::queued &&
                    ipc_v1_calls[i].endpoint_slot == receive_handle->endpoint_slot &&
                    (call_slot == ipc_v1_max_pending_calls || ipc_v1_calls[i].order < ipc_v1_calls[call_slot].order)) {
                    call_slot = i;
                }
            }
            if (call_slot != ipc_v1_max_pending_calls) {
                auto& call = ipc_v1_calls[call_slot];
                if (call.payload_length > request.receive_capacity) {
                    return finish_receive_error(static_cast<i64>(ipc_v1_error::buffer_too_small), call.payload_length);
                }
                if (ipc_v1_token_count(current->pid) >= ipc_v1_max_reply_tokens_per_process || !ipc_v1_next_reply_token) {
                    return finish_receive_error(static_cast<i64>(ipc_v1_error::resources));
                }
                call.state = ipc_v1_call_state::delivered; call.receiver_pid = current->pid;
                call.reply_token = ipc_v1_next_reply_token++;
                request.receive_length_out = call.payload_length; request.label_out = call.label;
                request.badge_out = call.badge; request.next_reply_token_out = call.reply_token;
                copy_to_user(address, &request, sizeof(request));
                if (call.payload_length) copy_to_user(request.receive_buffer, call.payload, call.payload_length);
                ipc_v1_try_deliver_queued(receive_handle->endpoint_slot);
                ipc_v1_notify_wait_sets();
                frame->rax = 0; return frame;
            }
            if (request.deadline_ns == 0) { return finish_receive_error(static_cast<i64>(ipc_v1_error::would_block)); }
            if (thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns)) {
                return finish_receive_error(static_cast<i64>(ipc_v1_error::timeout));
            }
            if (!ipc_v1_next_wait_order || !ipc_v1_pin(*current_thread, 0, address, sizeof(request)) ||
                !ipc_v1_pin(*current_thread, 1, request.receive_buffer, request.receive_capacity)) {
                ipc_v1_unpin(*current_thread);
                return finish_receive_error(static_cast<i64>(ipc_v1_error::resources));
            }
            current_thread->ipc_v1_request_address = address;
            current_thread->ipc_v1_payload_address = request.receive_buffer;
            current_thread->ipc_v1_payload_capacity = request.receive_capacity;
            current_thread->ipc_v1_reply_consumed = ipc_v1_reply_consumed;
            current_thread->ipc_v1_wait_action = static_cast<u32>(ipc_v1_action::reply_receive);
            current_thread->ipc_v1_length = 0;
            current_thread->ipc_v1_call_slot = receive_handle->endpoint_slot;
            current_thread->wait_target = request.receive_handle;
            current_thread->wait_order = ipc_v1_next_wait_order++;
            current_thread->deadline_ns = request.deadline_ns;
            current_thread->wait_kind = thread_wait_kind::ipc_v1_receive;
            current_thread->state = thread_state::blocked;
            ipc_v1_try_deliver_queued(receive_handle->endpoint_slot);
            frame->rax = 0; return schedule(frame);
        }
        frame->rax = static_cast<u64>(result); return frame;
    }
    frame->rax = static_cast<u64>(ipc_v1_error::unsupported); return frame;
}

void* process_syscall(interrupt_frame* frame) {
    if (frame->rax == sys_ipc_v1) { return ipc_v1_syscall(frame); }
    i64 result = process_error_invalid;
    const u64 first = frame->rdi, second = frame->rsi, third = frame->rdx;
    switch (frame->rax) {
    case sys_irq_event: {
        const auto action = static_cast<irq_event_action>(first);
        if (action == irq_event_action::bind) {
            if (second != pio_resource_com1 || third != 0) { break; }
            if (current->pid != pio_com1_owner) { result = process_error_denied; break; }
            if (irq_token != 0 || irq_quarantined || irq_next_token > 0x7fffffffffffffffull) {
                result = process_error_state; break;
            }
            irq_owner = current->pid;
            irq_token = irq_next_token++;
            irq_sequence = 0;
            irq_pending = false;
            platform::irq_unmask(4);
            result = static_cast<i64>(irq_token);
        } else {
            if (irq_token == 0 || second != irq_token || current->pid != irq_owner) {
                result = process_error_denied; break;
            }
            if (action == irq_event_action::wait) {
                if (irq_pending) { result = static_cast<i64>(irq_sequence); break; }
                if (third == 0) { result = process_error_would_block; break; }
                if (thread_deadline_reached(clock::monotonic_ns(), third)) { result = thread_error_timeout; break; }
                current_thread->wait_kind = thread_wait_kind::irq_event;
                current_thread->wait_target = irq_token;
                current_thread->deadline_ns = third;
                current_thread->state = thread_state::blocked;
                frame->rax = 0; return schedule(frame);
            }
            if (action == irq_event_action::ack) {
                if (!irq_pending || third != irq_sequence) { result = process_error_state; break; }
                irq_pending = false;
                platform::irq_unmask(4);
                result = 0;
            } else if (action == irq_event_action::close) {
                if (third != 0) { break; }
                release_irq(); result = 0;
            }
        }
        break;
    }
    case sys_pio_grant: {
        if (third == pio_resource_pc_speaker) {
            const auto speaker_action = static_cast<pio_grant_action>(first);
            if (speaker_action == pio_grant_action::delegate) {
                if (!current->supervisor) { result = process_error_denied; break; }
                process_record* target = owned_process(second);
                if (target == nullptr || target->state != task_state::building ||
                    target->replacement_pending || target->fork_pending || target->pc_speaker_controller) {
                    result = process_error_denied; break;
                }
                if (pio_speaker_delegated_controller != 0 || pio_speaker_owner != 0) {
                    result = process_error_state; break;
                }
                target->pc_speaker_controller = true;
                pio_speaker_delegated_controller = target->pid;
                result = 0;
                break;
            }
            if (speaker_action == pio_grant_action::release) {
                if (second != 0 || current->pid != pio_speaker_owner) {
                    result = process_error_denied; break;
                }
                release_pc_speaker(current); result = 0;
                break;
            }
            if (speaker_action == pio_grant_action::controller) {
                if (second != 0) { break; }
                result = current->pid == pio_speaker_owner && pio_speaker_controller != 0
                    ? static_cast<i64>(pio_speaker_controller) : process_error_denied;
                break;
            }
            if (speaker_action == pio_grant_action::query) {
                if (second != 0) { break; }
                if (!current->supervisor && current->pid != pio_speaker_delegated_controller) {
                    result = process_error_denied; break;
                }
                result = pio_speaker_owner != 0 ? 1 : 0;
            } else if (speaker_action == pio_grant_action::grant) {
                if (!current->supervisor && current->pid != pio_speaker_delegated_controller) {
                    result = process_error_denied; break;
                }
                process_record* target = owned_process(second);
                if (target == nullptr || target->state != task_state::building ||
                    target->replacement_pending || target->fork_pending || target->pc_speaker_io ||
                    target->pc_speaker_controller) {
                    result = process_error_denied; break;
                }
                if (pio_speaker_owner != 0) { result = process_error_state; break; }
                target->pc_speaker_io = true;
                target->pc_speaker_lease_started = false;
                target->pc_speaker_deadline_ns = 0;
                pio_speaker_owner = target->pid;
                pio_speaker_controller = current->pid;
                result = 0;
            } else if (speaker_action == pio_grant_action::revoke) {
                process_record* target = task_by_pid(second);
                if (target != nullptr && target->pid == pio_speaker_delegated_controller &&
                    current->supervisor && target->parent == current->pid) {
                    revoke_pc_speaker_controller(target);
                    result = 0; break;
                }
                if ((!current->supervisor && current->pid != pio_speaker_delegated_controller) ||
                    target == nullptr || target->parent != current->pid ||
                    target->pid != pio_speaker_owner || pio_speaker_controller != current->pid) {
                    result = process_error_denied; break;
                }
                release_pc_speaker(target); result = 0;
            }
            break;
        }
        if (third != pio_resource_com1) { break; }
        const auto action = static_cast<pio_grant_action>(first);
        if (action == pio_grant_action::controller) {
            if (second != 0) { break; }
            result = current->pid == pio_com1_owner && pio_com1_controller != 0
                ? static_cast<i64>(pio_com1_controller) : process_error_denied;
            break;
        }
        if (!current->supervisor) { result = process_error_denied; break; }
        if (action == pio_grant_action::query) {
            if (second != 0) { break; }
            result = pio_com1_quarantined ? 2 : pio_com1_owner != 0 ? 1 : 0;
        } else if (action == pio_grant_action::grant) {
            process_record* target = owned_process(second);
            if (target == nullptr || target->state != task_state::building || target->replacement_pending ||
                target->fork_pending || target->io_window_length != 0) {
                result = process_error_denied; break;
            }
            if (pio_com1_owner != 0 || pio_com1_quarantined) { result = process_error_state; break; }
            if (platform::debug_serial_attached() && !platform::debug_detach_serial()) {
                result = process_error_busy; break;
            }
            platform::irq_mask(4);
            target->io_window_first = 0x3f8;
            target->io_window_length = 8;
            pio_com1_owner = target->pid;
            pio_com1_controller = current->pid;
            result = 0;
        } else if (action == pio_grant_action::recover) {
            if (second != 0) { break; }
            // COM1 has no DMA and IRQ4 is exclusively routed. Reset only the
            // kernel's access/interrupt bookkeeping; the next user driver must
            // reinitialize the device and cannot infer prior I/O results.
            if (!pio_com1_quarantined || pio_com1_owner != 0 || irq_owner != 0 || irq_token != 0 ||
                platform::debug_serial_attached()) { result = process_error_state; break; }
            platform::irq_mask(4);
            irq_quarantined = false;
            pio_com1_quarantined = false;
            result = 0;
        } else if (action == pio_grant_action::revoke) {
            process_record* target = task_by_pid(second);
            if (target == nullptr || target->parent != current->pid || target->pid != pio_com1_owner) {
                result = process_error_denied; break;
            }
            quarantine_com1(target); result = 0;
        }
        break;
    }
    case sys_channel: {
        const auto action = static_cast<channel_action>(first);
        if (action == channel_action::create) {
            if (third != 0 || !user_range_ok(second, sizeof(channel_create), false)) { break; }
            channel_create request{};
            copy_from_user(&request, second, sizeof(request));
            if (request.version != channel_version || request.size != sizeof(request) || request.reserved != 0 ||
                request.capacity == 0 || request.capacity > file_message_bytes ||
                request.sender_pid == request.receiver_pid) { break; }
            process_record* sender = task_by_pid(request.sender_pid);
            process_record* receiver = task_by_pid(request.receiver_pid);
            auto controlled = [](const process_record* task) {
                return task != nullptr && task->state != task_state::dead && !task->closing &&
                    !task->replacement_pending &&
                    (task == current || (task->parent == current->pid &&
                     completion_for(current->pid, task->pid) != nullptr));
            };
            if (!controlled(sender) || !controlled(receiver)) { result = process_error_denied; break; }
            u32 owned = 0;
            for (const auto& endpoint : endpoints) {
                if (endpoint.used && endpoint.generic_channel && endpoint.owner_pid == current->pid) { ++owned; }
            }
            if (owned >= 4) { result = process_error_resources; break; }
            const u32 handle = endpoint_attach(receiver->pid, sender->pid, current->pid, request.capacity);
            if (handle == 0) { result = process_error_resources; break; }
            endpoint_for(handle)->generic_channel = true;
            result = static_cast<i64>(handle);
        } else if (action == channel_action::fork_pair) {
            if (third != 0 || !user_range_ok(second, sizeof(channel_fork_pair), false) ||
                !user_range_ok(second, sizeof(channel_fork_pair), true)) break;
            channel_fork_pair request{};
            copy_from_user(&request, second, sizeof(request));
            if (request.version != channel_version || request.size != sizeof(request) ||
                request.child_send != 0 || request.child_receive != 0 ||
                request.source_send == request.source_receive) break;
            endpoint_record* send = endpoint_for(request.source_send);
            endpoint_record* receive = endpoint_for(request.source_receive);
            process_record* child = owned_process(request.child_pid);
            if (child == nullptr || child->state != task_state::building || !child->fork_pending ||
                child->fork_source != current->pid || child->parent != current->pid ||
                completion_for(current->pid, child->pid) == nullptr || send == nullptr || receive == nullptr ||
                !send->generic_channel || !receive->generic_channel || send->sender_pid != current->pid ||
                receive->receiver_pid != current->pid || send->receiver_pid != receive->sender_pid ||
                send->owner_pid != receive->owner_pid || send->pending || receive->pending) {
                result = process_error_denied; break;
            }
            const u64 peer = send->receiver_pid;
            process_record* peer_task = task_by_pid(peer);
            process_record* owner = task_by_pid(send->owner_pid);
            if (peer_task == nullptr || peer_task->closing || peer_task->state == task_state::dead ||
                owner == nullptr || owner->closing || owner->state == task_state::dead) {
                result = process_error_state; break;
            }
            u32 free_count = 0, owned = 0;
            bool duplicate = false;
            for (const auto& endpoint : endpoints) {
                if (!endpoint.used) { ++free_count; continue; }
                if (!endpoint.generic_channel) continue;
                if (endpoint.owner_pid == send->owner_pid) ++owned;
                if ((endpoint.sender_pid == child->pid && endpoint.receiver_pid == peer) ||
                    (endpoint.receiver_pid == child->pid && endpoint.sender_pid == peer)) duplicate = true;
            }
            if (duplicate) { result = process_error_state; break; }
            if (owned > 6 || free_count < 2 || next_endpoint_handle > 0xfffffffeull) {
                result = process_error_resources; break;
            }
            request.child_send = endpoint_attach(peer, child->pid, send->owner_pid, send->capacity);
            request.child_receive = endpoint_attach(child->pid, peer, send->owner_pid, receive->capacity);
            // Free slots and handle space were reserved by checks in this
            // non-preemptible kernel section; both allocations must succeed.
            endpoint_for(request.child_send)->generic_channel = true;
            endpoint_for(request.child_receive)->generic_channel = true;
            endpoint_for(request.child_send)->derived_from = request.source_send;
            endpoint_for(request.child_receive)->derived_from = request.source_receive;
            copy_to_user(second, &request, sizeof(request));
            result = 0;
        } else if (action == channel_action::verify_fork_pair) {
            if (third != 0 || !user_range_ok(second, sizeof(channel_fork_verification), false)) break;
            channel_fork_verification request{};
            copy_from_user(&request, second, sizeof(request));
            if (request.version != channel_version || request.size != sizeof(request)) break;
            endpoint_record* source_in = endpoint_for(request.source_incoming);
            endpoint_record* source_out = endpoint_for(request.source_outgoing);
            endpoint_record* child_in = endpoint_for(request.child_incoming);
            endpoint_record* child_out = endpoint_for(request.child_outgoing);
            process_record* child = task_by_pid(request.child_pid);
            if (source_in == nullptr || source_out == nullptr || child_in == nullptr || child_out == nullptr ||
                child == nullptr || child->state != task_state::building || !child->fork_pending ||
                !source_in->generic_channel || !source_out->generic_channel ||
                !child_in->generic_channel || !child_out->generic_channel ||
                source_in->receiver_pid != current->pid || source_out->sender_pid != current->pid ||
                child_in->receiver_pid != current->pid || child_out->sender_pid != current->pid ||
                source_in->sender_pid != source_out->receiver_pid ||
                child->parent != source_in->sender_pid || child->fork_source != child->parent ||
                child_in->sender_pid != child->pid || child_out->receiver_pid != child->pid ||
                source_in->owner_pid != source_out->owner_pid ||
                child_in->owner_pid != source_in->owner_pid || child_out->owner_pid != source_in->owner_pid ||
                child_in->derived_from != source_in->handle || child_out->derived_from != source_out->handle) {
                result = process_error_denied; break;
            }
            result = 0;
        } else if (action == channel_action::enumerate) {
            if (second >= max_endpoints || !user_range_ok(third, sizeof(channel_info), true)) { break; }
            u64 ordinal = 0;
            result = thread_error_not_found;
            for (const auto& endpoint : endpoints) {
                if (!endpoint.used || !endpoint.generic_channel ||
                    (endpoint.sender_pid != current->pid && endpoint.receiver_pid != current->pid)) { continue; }
                if (ordinal++ != second) { continue; }
                const bool sender = endpoint.sender_pid == current->pid;
                const channel_info info{channel_version, sizeof(channel_info), endpoint.handle,
                    sender ? channel_send : channel_receive,
                    sender ? endpoint.receiver_pid : endpoint.sender_pid, endpoint.owner_pid};
                copy_to_user(third, &info, sizeof(info)); result = 0; break;
            }
        } else if (action == channel_action::close) {
            if (third != 0) { break; }
            endpoint_record* endpoint = endpoint_for(second);
            if (endpoint == nullptr || !endpoint->generic_channel ||
                (endpoint->owner_pid != current->pid && endpoint->sender_pid != current->pid &&
                 endpoint->receiver_pid != current->pid)) { result = process_error_denied; break; }
            close_channel(*endpoint); result = 0;
        } else if (action == channel_action::wait_many) {
            if (!user_range_ok(second, sizeof(channel_wait_many_request), false)) break;
            channel_wait_many_request request{};
            copy_from_user(&request, second, sizeof(request));
            if (request.version != channel_version || request.size != sizeof(request) || request.reserved != 0 ||
                request.count == 0 || request.count > channel_wait_many_max) break;
            u32 ready = 0;
            bool valid = true;
            for (u32 i = 0; i < request.count; ++i) {
                endpoint_record* endpoint = endpoint_for(request.handles[i]);
                if (endpoint == nullptr || !endpoint->generic_channel ||
                    (endpoint->sender_pid != current->pid && endpoint->receiver_pid != current->pid)) {
                    result = process_error_denied; valid = false; break;
                }
                for (u32 j = 0; j < i; ++j) if (request.handles[j] == request.handles[i]) valid = false;
                if (!valid) { result = process_error_invalid; break; }
                const bool sender = endpoint->sender_pid == current->pid;
                if (sender ? !endpoint->pending : endpoint->pending) ready |= 1u << i;
            }
            if (!valid) break;
            if (ready != 0) { result = static_cast<i64>(ready); break; }
            if (third == 0) { result = process_error_would_block; break; }
            if (thread_deadline_reached(clock::monotonic_ns(), third)) { result = thread_error_timeout; break; }
            for (u32 i = 0; i < request.count; ++i) current_thread->wait_channels[i] = request.handles[i];
            current_thread->wait_channel_count = request.count;
            current_thread->wait_kind = thread_wait_kind::channel_many;
            current_thread->deadline_ns = third;
            current_thread->state = thread_state::blocked;
            frame->rax = 0; return schedule(frame);
        } else if (action == channel_action::wait) {
            endpoint_record* endpoint = endpoint_for(second);
            if (endpoint == nullptr || !endpoint->generic_channel ||
                (endpoint->sender_pid != current->pid && endpoint->receiver_pid != current->pid)) {
                result = process_error_denied; break;
            }
            const bool sender = endpoint->sender_pid == current->pid;
            if (sender ? !endpoint->pending : endpoint->pending) { result = 0; break; }
            if (third == 0) { result = process_error_would_block; break; }
            if (thread_deadline_reached(clock::monotonic_ns(), third)) { result = thread_error_timeout; break; }
            current_thread->wait_kind = sender ? thread_wait_kind::channel_write : thread_wait_kind::channel_read;
            current_thread->wait_target = endpoint->handle;
            current_thread->deadline_ns = third;
            current_thread->state = thread_state::blocked;
            frame->rax = 0; return schedule(frame);
        }
        break;
    }
    case sys_stream_lease: {
        if (first != 0 || (current->stdio_mask & 1u) == 0 ||
            !current->stdio[0].valid || !current->stdio[0].console || current->stdio[0].writable) {
            result = process_error_denied; break;
        }
        const auto action = static_cast<stream_lease_action>(second);
        if (action == stream_lease_action::claim) {
            if (third != 0) { break; }
            if (!current->supervisor) { result = process_error_denied; break; }
            // User-mode UART and a non-kernel terminal cancellation policy
            // are prerequisites. Do not activate a lease with unsafe semantics.
            result = thread_error_unsupported;
        } else if (action == stream_lease_action::delegate) {
            if (!input_lease.active() || input_lease.holder() != current->pid) {
                result = process_error_denied; break;
            }
            process_record* child = task_by_pid(third);
            if (child == nullptr || child->parent != current->pid || completion_for(current->pid, third) == nullptr ||
                child->state == task_state::dead || child->replacement_pending ||
                (child->stdio_mask & 1u) == 0 || !child->stdio[0].valid ||
                !child->stdio[0].console || child->stdio[0].writable) {
                result = process_error_denied; break;
            }
            result = input_lease.delegate(current->pid, child->pid) ? 0 : process_error_state;
        } else if (action == stream_lease_action::reclaim) {
            if (third != 0) { break; }
            if (!input_lease.contains(current->pid)) { result = process_error_denied; break; }
            result = input_lease.reclaim(current->pid) ? 0 : process_error_state;
        } else if (action == stream_lease_action::query) {
            if (third != 0) { break; }
            result = input_lease.contains(current->pid) ? static_cast<i64>(input_lease.holder()) : process_error_denied;
        } else { break; }
        break;
    }
    case sys_process_guard: {
        if (third != 0) { break; }
        const auto action = static_cast<process_guard_action>(first);
        if (action == process_guard_action::query) {
            if (!user_range_ok(second, sizeof(admission_guard), true)) { break; }
            copy_to_user(second, &admission_guard, sizeof(admission_guard)); result = 0; break;
        }
        if (!current->supervisor) { result = process_error_denied; break; }
        if (second != 0) { break; }
        if (action == process_guard_action::begin) {
            if (admission_guard.owner_pid != 0) { result = process_error_busy; break; }
            bool busy = false;
            for (const auto& task : tasks) {
                if (task.state != task_state::free && task.state != task_state::dead &&
                    &task != current && task.pid != files_pid) { busy = true; }
            }
            if (busy) { result = process_error_busy; break; }
            admission_guard = {current->pid, 0}; result = 0; break;
        }
        if (admission_guard.owner_pid != current->pid) { result = process_error_state; break; }
        const process_record* worker = task_by_pid(admission_guard.worker_pid);
        if (worker != nullptr && worker->state != task_state::dead) { result = process_error_busy; break; }
        if (action == process_guard_action::end) { admission_guard = {}; result = 0; }
        else if (action == process_guard_action::rearm) { admission_guard.worker_pid = 0; result = 0; }
        break;
    }
    case sys_process_exec_prepare: {
        if (admission_guard.owner_pid != 0) { result = process_error_busy; break; }
        if (first != 0 || third > 11 ||
            (third != 0 && !user_range_ok(second, third, false))) { break; }
        result = replacement_caller_error();
        if (result != 0) { break; }
        // A single-threaded process can have only one replacement transaction.
        // This is not authority to reserve arbitrary child process slots.
        bool pending = false;
        for (const auto& task : tasks) {
            pending = pending || (task.parent == current->pid && task.replacement_pending &&
                                   task.state != task_state::free && task.state != task_state::dead);
        }
        if (pending) { result = process_error_state; break; }
        char name[12] = "exec";
        if (third != 0) { copy_from_user(name, second, third); name[third] = '\0'; }
        process_record* stage = prepare_task(name);
        if (stage == nullptr) { result = process_error_resources; break; }
        stage->parent = current->pid;
        stage->can_create = current->can_create;
        stage->replacement_pending = true;
        stage->stdio_mask = 0;
        for (auto& route : stage->stdio) { route = stdio_route{}; }
        if (process_trace_enabled) {
            format::text("[process] event=exec_prepared pid="); format::decimal(current->pid);
            format::text(" staging_pid="); format::decimal(stage->pid); format::text("\r\n");
        }
        result = static_cast<i64>(stage->pid);
        break;
    }
    case sys_process_exec_commit: {
        if (admission_guard.owner_pid != 0) { result = process_error_busy; break; }
        result = replacement_caller_error();
        if (result != 0) { break; }
        process_record* stage = owned_process(first);
        if (stage == nullptr) { result = process_error_denied; break; }
        if (stage->state != task_state::building || !stage->replacement_pending) {
            result = process_error_state; break;
        }
        // Validate the complete request while the original user mappings and
        // identity remain intact. Every fallible check precedes the first
        // state/queue mutation below.
        result = process_error_invalid;
        process_entry entry{};
        process_exec_channel_entry extended{};
        const bool preserve_channels = (third & exec_preserve_channels_flag) != 0;
        const u64 depth_mode = third & ~exec_preserve_channels_flag;
        if (preserve_channels) {
            if (!user_range_ok(second, sizeof(extended), false)) { break; }
            copy_from_user(&extended, second, sizeof(extended));
            if (extended.version != 1 || extended.size != sizeof(extended) ||
                extended.count == 0 || extended.count > exec_preserve_channels_max || extended.reserved != 0) break;
            bool channels_valid = true;
            for (u32 i = 0; i < extended.count; ++i) {
                endpoint_record* endpoint = endpoint_for(extended.channels[i]);
                if (endpoint == nullptr || !endpoint->generic_channel || endpoint->pending ||
                    (endpoint->sender_pid != current->pid && endpoint->receiver_pid != current->pid)) {
                    channels_valid = false; break;
                }
                bool duplicate = false;
                for (u32 j = 0; j < i; ++j) if (extended.channels[j] == extended.channels[i]) duplicate = true;
                if (duplicate) { channels_valid = false; break; }
            }
            if (!channels_valid) break;
            entry = extended.entry;
        } else {
            if (!user_range_ok(second, sizeof(entry), false)) { break; }
            copy_from_user(&entry, second, sizeof(entry));
        }
        if (!valid_process_entry(stage, entry)) { break; }
        u32 depth = current->spawn_depth;
        if (depth_mode != 0) {
            if (depth_mode - 1 > process_max_spawn_depth || depth_mode - 1 >= current->spawn_depth) {
                result = process_error_delegation; break;
            }
            depth = static_cast<u32>(depth_mode - 1);
        }
        endpoint_record* request = endpoint_for(current->session_request_handle);
        endpoint_record* response = endpoint_for(current->session_response_handle);
        if (!files_service_live() || request == nullptr || response == nullptr || request == response ||
            request->owner_pid != current->pid || request->sender_pid != current->pid ||
            request->receiver_pid != files_pid || request->session_response ||
            request->capacity != file_message_bytes ||
            response->owner_pid != current->pid || response->receiver_pid != current->pid ||
            response->sender_pid != files_pid || !response->session_response ||
            response->capacity != file_message_bytes || current->send_handle != request->handle ||
            current->recv_handle != response->handle) {
            result = process_error_state; break;
        }
        if (next_endpoint_handle > 0xfffffffeull) { result = process_error_resources; break; }
        ipc_v1_revoke_process(current->pid);
        release_pc_speaker(current);
        revoke_pc_speaker_controller(current);
        quarantine_com1(current);
        release_channels(current->pid, extended.channels, preserve_channels ? extended.count : 0);
        display_release(current->pid);
        const u64 old_space = current->cr3;
        const u32 old_pages = current->user_pages;
        const u32 old_depth = current->spawn_depth;
        const auto& staged_thread = main_thread(stage);
        // The new client starts a fresh request-ID sequence. Re-key the same
        // two session slots so a pending/late old-image reply cannot match it.
        // PID and files-service open descriptions survive; opaque IPC tokens
        // do not. No fallible step follows the first queue replacement.
        *request = endpoint_record{};
        request->used = true;
        request->handle = static_cast<u32>(next_endpoint_handle++);
        request->receiver_pid = files_pid;
        request->sender_pid = request->owner_pid = current->pid;
        request->capacity = file_message_bytes;
        *response = endpoint_record{};
        response->used = true;
        response->handle = static_cast<u32>(next_endpoint_handle++);
        response->receiver_pid = response->owner_pid = current->pid;
        response->sender_pid = files_pid;
        response->capacity = file_message_bytes;
        response->session_response = true;
        current->send_handle = current->session_request_handle = request->handle;
        current->recv_handle = current->session_response_handle = response->handle;
        current->cr3 = stage->cr3;
        current->io_window_first = current->io_window_length = 0;
        (void)set_user_io_permissions(0, 0, false);
        current->user_pages = stage->user_pages;
        current->entry = entry.entry;
        current->initial_stack = entry.stack;
        current->startup = entry.startup;
        current->heap_break = process_heap_begin;
        current->spawn_depth = depth;
        copy_name(current->name, stage->name);
        current_thread->thread_pointer = staged_thread.thread_pointer;
        current_thread->stack_bottom = staged_thread.stack_bottom;
        current_thread->stack_top = staged_thread.stack_top;
        current_thread->tls_begin = staged_thread.tls_begin;
        current_thread->tls_end = staged_thread.tls_end;
        current_thread->entry = 0;
        current_thread->argument = 0;
        current_thread->initial_stack = 0;
        current_thread->wait_kind = thread_wait_kind::none;
        current_thread->wait_target = current_thread->wait_buffer = 0;
        current_thread->deadline_ns = current_thread->wait_order = 0;
        current_thread->kernel_rsp = reinterpret_cast<u64>(frame);
        copy_bytes(current_thread->fpu_state, fpu_template, sizeof(fpu_template));
        *frame = interrupt_frame{};
        frame->rip = entry.entry;
        frame->cs = user_code_selector;
        frame->rflags = 0x202;
        frame->rsp = entry.stack;
        frame->rdi = entry.startup;
        frame->ss = user_data_selector;
        // The staging identity never runs and never receives the caller's
        // handles or children. It retires only the old image and its own spare
        // kernel stack; the caller keeps PID/TID, parent/completion, session
        // slots, stdio/pipe references, fork depth, and its active kernel stack.
        stage->cr3 = old_space;
        stage->user_pages = old_pages;
        vm1_probe_regions[static_cast<u32>(stage - tasks)] = vm1_probe_regions[static_cast<u32>(current - tasks)];
        vm1_probe_regions[static_cast<u32>(current - tasks)].clear();
        load_address_space(current->cr3);
        set_thread_pointer(current_thread->thread_pointer);
        if (process_trace_enabled) {
            format::text("[process] event=exec_replaced old_pid="); format::decimal(current->pid);
            format::text(" current_pid="); format::decimal(current->pid);
            format::text(" target_pid="); format::decimal(current->pid);
            format::text(" staging_pid="); format::decimal(stage->pid);
            format::text(" tid="); format::decimal(current_thread->tid);
            format::text(" old_address_space="); format::hex(old_space);
            format::text(" address_space="); format::hex(current->cr3);
            format::text(" file_session_rekeyed=1 old_spawn_depth="); format::decimal(old_depth);
            format::text(" spawn_depth="); format::decimal(current->spawn_depth); format::text("\r\n");
        }
        destroy_task(stage);
        fpu_restore(current_thread->fpu_state);
        // Return the replacement frame directly. Assigning the ordinary
        // syscall result or returning to the old user continuation is wrong.
        return frame;
    }
    case sys_process_fork_prepare:
        if (admission_guard.owner_pid != 0) { result = process_error_busy; break; }
        if (first == 0 && second == 0 && third == 0) {
            result = prepare_fork(frame);
            if(result==fork_async_result) { frame->rax=0;return schedule(frame); }
        }
        break;
    case sys_process_fork_commit: {
        if (admission_guard.owner_pid != 0) { result = process_error_busy; break; }
        if (second != 0 || third != 0) { break; }
        process_record* child = owned_process(first);
        if (child == nullptr) { result = process_error_denied; break; }
        if (current->closing || child->state != task_state::building || !child->fork_pending ||
            child->fork_source != current->pid || !child->fork_files_ack) {
            result = process_error_state; break;
        }
        child->fork_pending = false;
        child->state = task_state::ready;
        if (process_trace_enabled) {
            format::text("[process] event=fork_committed pid="); format::decimal(child->pid);
            format::text(" parent="); format::decimal(child->parent); format::text("\r\n");
        }
        result = 0; break;
    }
    case sys_process_fork_files: {
        if (admission_guard.owner_pid != 0) { result = process_error_busy; break; }
        if (current == nullptr || !current->block_access || current->pid != files_pid) {
            result = process_error_denied; break;
        }
        if (third > 1) { break; }
        process_record* child = task_by_pid(first);
        process_record* source = task_by_pid(second);
        if (child == nullptr || source == nullptr || source->closing ||
            source->state == task_state::building || source->state == task_state::dead ||
            child->state != task_state::building || !child->fork_pending ||
            child->fork_source != second || child->parent != second) {
            result = process_error_denied; break;
        }
        if (third == 1) { child->fork_files_ack = true; }
        result = 0; break;
    }
    case sys_boot_payload: {
        if (current == nullptr || !current->supervisor) {
            result = process_error_denied;
            break;
        }
        if (second == 0 && third == 0) {
            result = static_cast<i64>(boot_payload_size);
            break;
        }
        if (first > boot_payload_size) {
            result = process_error_invalid;
            break;
        }
        u64 length = third;
        if (length > boot_payload_size - first) { length = boot_payload_size - first; }
        if (!user_range_ok(second, length, true)) { break; }
        copy_to_user(second, boot_payload + first, length);
        result = static_cast<i64>(length);
        break;
    }
    case sys_debug_trace:
        if (current == nullptr || !current->supervisor) {
            result = process_error_denied;
            break;
        }
        if (first > 1 || second != 0 || third != 0) {
            result = process_error_invalid;
            break;
        }
        process_trace_enabled = first != 0;
        result = 0;
        break;
    case sys_handle_write: {
        const u64 handle = first & ~pipe_write_atomic_flag;
        if (handle > 2 || handle == 0) { result = process_error_denied; break; }
        result = stdio_write(current, static_cast<u32>(handle), second, third,
                             (first & pipe_write_atomic_flag) != 0);
        break;
    }
    case sys_handle_read: {
        if (first != 0) { result = process_error_denied; break; }
        if (current->stdio[0].valid && current->stdio[0].console &&
            cancel_foreground() && current->state == task_state::dead) { return schedule(frame); }
        result = stdio_read(current, 0, second, third, true);
        break;
    }
    case sys_handle_close:
        if (first > 2 || (current->stdio_mask & (1u << first)) == 0) {
            result = process_error_denied;
        } else {
            if (first == 0 && current->stdio[0].console) {
                (void)input_lease.remove(current->pid);
            }
            current->stdio_mask &= ~(1u << first);
            stdio_route_release(current, current->stdio[first]);
            result = 0;
        }
        break;
    case sys_image_info:
    case sys_image_read: {
        if (!current->supervisor) { result = process_error_denied; break; }
        constexpr u64 count = sizeof(user_images::catalog) / sizeof(user_images::catalog[0]);
        if (first == 0 || first > count) { result = process_error_denied; break; }
        const auto& image = user_images::catalog[first - 1];
        if (frame->rax == sys_image_info) {
            if (!user_range_ok(second, sizeof(image_info), true)) { break; }
            image_info info{};
            info.size = image.size;
            for (u32 i = 0; i + 1 < sizeof(info.name) && image.name[i] != '\0'; ++i) {
                info.name[i] = image.name[i];
            }
            copy_to_user(second, &info, sizeof(info)); result = 0;
        } else {
            if (!user_range_ok(second, sizeof(image_read_request), false)) { break; }
            image_read_request request{};
            copy_from_user(&request, second, sizeof(request));
            if (request.offset > image.size || request.length > 131072) { break; }
            const u64 length = request.length < image.size - request.offset ? request.length : image.size - request.offset;
            if (!user_range_ok(request.destination, length, true)) { break; }
            copy_to_user(request.destination, image.bytes + request.offset, length);
            result = static_cast<i64>(length);
        }
        break;
    }
    case sys_process_create: {
        if (admission_guard.owner_pid != 0 &&
            (current->pid != admission_guard.owner_pid || admission_guard.worker_pid != 0)) {
            result = process_error_busy; break;
        }
        if (!current->supervisor && current->spawn_depth == 0 && !current->can_create) {
            result = process_error_denied; break;
        }
        if (first > 7 || (first & ~u64{current->stdio_mask}) != 0 || third > 11 ||
            (third != 0 && !user_range_ok(second, third, false))) { break; }
        if (!files_service_live()) { result = process_error_resources; break; }
        completion_record* slot = nullptr;
        for (auto& item : completions) { if (!item.used) { slot = &item; break; } }
        if (slot == nullptr) { result = process_error_resources; break; }
        char name[12] = "elf";
        if (third != 0) { copy_from_user(name, second, third); name[third] = '\0'; }
        process_record* task = prepare_task(name);
        if (task == nullptr) { result = process_error_resources; break; }
        task->parent = current->pid;
        if (!inherit_stdio(task, current, static_cast<u32>(first))) {
            destroy_task(task); result = process_error_state; break;
        }
        {
            u32 free_count = 0;
            for (const auto& endpoint : endpoints) { if (!endpoint.used) { ++free_count; } }
            if (free_count < 2) {
                destroy_task(task); result = process_error_resources; break;
            }
            task->session_request_handle = endpoint_attach(files_pid, task->pid, task->pid,
                file_message_bytes);
            task->session_response_handle = endpoint_attach(task->pid, files_pid, task->pid,
                file_message_bytes, true);
            if (task->session_request_handle == 0 || task->session_response_handle == 0) {
                destroy_task(task); result = process_error_resources; break;
            }
            task->send_handle = task->session_request_handle;
            task->recv_handle = task->session_response_handle;
        }
        *slot = completion_record{};
        slot->used = true; slot->parent = current->pid; slot->status.pid = task->pid;
        task->completion_slot = static_cast<u32>(slot - completions) + 1;
        if (admission_guard.owner_pid != 0) { admission_guard.worker_pid = task->pid; }
        result = static_cast<i64>(task->pid);
        break;
    }
    case sys_process_grant: {
        if (admission_guard.owner_pid != 0) { result = process_error_denied; break; }
        if (!current->supervisor) { result = process_error_denied; break; }
        if (second > 1) { break; }
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building || task->replacement_pending) {
            result = process_error_state; break;
        }
        task->spawn_depth = second != 0 ? 1 : 0;
        task->can_create = second != 0;
        result = 0;
        break;
    }
    case sys_process_delegate: {
        if (admission_guard.owner_pid != 0) { result = process_error_denied; break; }
        if (current == nullptr || second > process_max_spawn_depth) {
            result = process_error_invalid; break;
        }
        if (!current->supervisor && (current->spawn_depth < 2 || second >= current->spawn_depth)) {
            result = process_error_delegation; break;
        }
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_delegation; break; }
        if (task->state != task_state::building || task->replacement_pending) {
            result = process_error_state; break;
        }
        task->spawn_depth = static_cast<u32>(second);
        task->can_create = second != 0;
        result = 0;
        break;
    }
    case sys_process_authority: {
        // SL1: identity-carried create authority on a building child (or query).
        // mode 0 clear, 1 set, 2 copy from caller, 3 query (result = 0/1).
        if (admission_guard.owner_pid != 0) { result = process_error_denied; break; }
        const auto mode = static_cast<process_authority_mode>(second);
        if (second > static_cast<u64>(process_authority_mode::query)) {
            result = process_error_invalid; break;
        }
        process_record* task = nullptr;
        if (first == current->pid) {
            task = current;  // self-query
        } else {
            task = owned_process(first);
        }
        if (task == nullptr) { result = process_error_denied; break; }
        const bool is_parent = task->parent == current->pid;
        if (mode == process_authority_mode::query) {
            // Self, parent, or supervisor may query.
            if (task != current && !is_parent && !current->supervisor) {
                result = process_error_denied; break;
            }
            result = task->can_create ? 1 : 0;
            break;
        }
        if (task->state != task_state::building || task->replacement_pending) {
            result = process_error_state; break;
        }
        if (!current->supervisor && !is_parent) {
            result = process_error_denied; break;
        }
        if (mode == process_authority_mode::clear) {
            // Full reduction: drop new-track authority and legacy depth so the
            // child cannot create through either track (shell_launch §3).
            task->can_create = false;
            task->spawn_depth = 0;
            result = 0;
            break;
        }
        // set / copy_from_caller: caller must already hold create authority.
        if (!current->supervisor && !current->can_create) {
            result = process_error_denied; break;
        }
        task->can_create = true;
        result = 0;
        break;
    }
    case sys_process_tls: {
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        if (second < process_tls_begin || second > process_tls_end - 16 || second % 16 != 0 ||
            !space_range_ok(task->cr3, second, 16, true)) { break; }
        main_thread(task).thread_pointer = second;
        result = 0;
        break;
    }
    case sys_heap_break:
        result = set_heap_break(first);
        break;
    case sys_process_cancel: {
        if (second != 0 || third != 0) { break; }
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state == task_state::building) { result = process_error_state; break; }
        finish_task(task, process_outcome::killed, -9);
        destroy_task(task);
        result = 0; break;
    }
    case sys_process_foreground: {
        if (second > 1 || third != 0 || !user_range_ok(first, sizeof(process_foreground), false)) { break; }
        process_foreground request{};
        copy_from_user(&request, first, sizeof(request));
        if (request.version != 1 || request.size != sizeof(request) || request.reserved != 0 ||
            request.count > process_pipeline_max || (second == 0 && request.count != 0)) { break; }
        bool valid = true;
        for (u32 i = 0; i < process_pipeline_max; ++i) {
            if (i >= request.count) { valid = valid && request.pids[i] == 0; continue; }
            valid = valid && completion_for(current->pid, request.pids[i]) != nullptr;
            for (u32 j = 0; j < i; ++j) { valid = valid && request.pids[j] != request.pids[i]; }
        }
        if (!valid) { result = process_error_denied; break; }
        if (second == 1 && current->foreground_active && current->foreground_cancelled) {
            result = process_error_state; break;
        }
        current->foreground = request;
        current->foreground_active = second == 1;
        current->foreground_cancelled = false;
        result = 0; break;
    }
    case sys_pipe_wait: {
        if (second > process_pipe_bytes) { result = process_error_invalid; break; }
        u32 pipe_index = process_max_pipes;
        bool writable = false;
        if (first < 3) {
            if ((current->stdio_mask & (1u << first)) == 0 ||
                !current->stdio[first].valid) { result = process_error_denied; break; }
            const auto& route = current->stdio[first];
            if (route.console) {
                if (input_lease.active() && input_lease.holder() != current->pid) {
                    result = process_error_denied; break;
                }
                result = second != 0 && !route.writable
                    ? process_error_invalid : process_error_would_block;
                break;
            }
            pipe_index = route.pipe_index;
            writable = route.writable;
        } else {
            const pipe_reference* reference = pipe_reference_for(current, first);
            if (reference == nullptr) { result = process_error_denied; break; }
            pipe_index = reference->pipe_index;
            writable = reference->writable;
        }
        if (pipe_index >= process_max_pipes || !pipes[pipe_index].used) {
            result = process_error_invalid; break;
        }
        if (!writable && second != 0) { result = process_error_invalid; break; }
        const auto& pipe = pipes[pipe_index];
        const bool ready = writable
            ? pipe.reader_references == 0 || process_pipe_bytes - pipe.length >= (second == 0 ? 1 : second)
            : pipe.writer_references == 0 || pipe.length != 0;
        if (ready) { result = 0; break; }
        if (third != 0 && thread_deadline_reached(clock::monotonic_ns(), third)) {
            result = thread_error_timeout; break;
        }
        // Check and sleep in one non-preemptible kernel critical section.
        // A subsequent read/write rechecks the pipe and its own user buffer.
        current_thread->wait_kind = writable ? thread_wait_kind::pipe_write : thread_wait_kind::pipe_read;
        current_thread->wait_target = pipe_index;
        current_thread->deadline_ns = third == 0 ? thread_deadline_infinite : third;
        current_thread->state = thread_state::blocked;
        frame->rax = 0;
        return schedule(frame);
    }
    case sys_pipe_create: {
        if (!user_range_ok(first, sizeof(pipe_handles), true)) { break; }
        if (next_pipe_token + 1 > 0xffffffffull ||
            current->pipe_reference_count > process_max_pipe_refs - 2) {
            result = process_error_resources; break;
        }
        u32 pipe_index = process_max_pipes;
        for (u32 i = 0; i < process_max_pipes; ++i) {
            if (!pipes[i].used) { pipe_index = i; break; }
        }
        pipe_reference* first_reference = nullptr;
        pipe_reference* second_reference = nullptr;
        for (auto& reference : current->pipe_references) {
            if (reference.used) { continue; }
            if (first_reference == nullptr) { first_reference = &reference; }
            else { second_reference = &reference; break; }
        }
        if (pipe_index == process_max_pipes || first_reference == nullptr || second_reference == nullptr) {
            result = process_error_resources; break;
        }
        const u32 read_token = static_cast<u32>(next_pipe_token++);
        const u32 write_token = static_cast<u32>(next_pipe_token++);
        pipes[pipe_index] = pipe_object{};
        pipes[pipe_index].used = true;
        pipes[pipe_index].references = 2;
        pipes[pipe_index].reader_references = 1;
        pipes[pipe_index].writer_references = 1;
        *first_reference = {true, read_token, static_cast<u8>(pipe_index), false};
        *second_reference = {true, write_token, static_cast<u8>(pipe_index), true};
        current->pipe_reference_count += 2;
        const pipe_handles handles{read_token, write_token};
        copy_to_user(first, &handles, sizeof(handles));
        result = 0;
        break;
    }
    case sys_pipe_read:
    case sys_pipe_write: {
        const bool atomic = frame->rax == sys_pipe_write && (first & pipe_write_atomic_flag) != 0;
        pipe_reference* reference = pipe_reference_for(current, atomic ? first & ~pipe_write_atomic_flag : first);
        if (reference == nullptr ||
            (frame->rax == sys_pipe_read && reference->writable) ||
            (frame->rax == sys_pipe_write && !reference->writable)) {
            result = process_error_denied; break;
        }
        result = frame->rax == sys_pipe_read
            ? pipe_read_from(reference->pipe_index, second, third)
            : pipe_write_to(reference->pipe_index, second, third, atomic);
        break;
    }
    case sys_pipe_close: {
        pipe_reference* reference = pipe_reference_for(current, first);
        if (reference == nullptr) { result = process_error_invalid; break; }
        pipe_reference_close(current, reference);
        result = 0;
        break;
    }
    case sys_process_stdio: {
        // PID zero is a read-only query of this process's fixed kernel route.
        if (first == 0) {
            if (second > 2 || third != 0) { break; }
            const auto& route = current->stdio[second];
            result = (current->stdio_mask & (1u << second)) && route.valid
                ? (route.console ? 1 : 0) : process_error_denied;
            break;
        }
        if (second >= 3) { break; }
        process_record* child = owned_process(first);
        if (child == nullptr) { result = process_error_denied; break; }
        if (child->state != task_state::building || child->replacement_pending) {
            result = process_error_state; break;
        }
        stdio_route replacement{};
        const bool target_writable = second != 0;
        if (third == process_stdio_close) {
            if (second == 0 && child->stdio[0].valid && child->stdio[0].console &&
                input_lease.contains(child->pid)) { (void)input_lease.remove(child->pid); }
            child->stdio_mask &= ~(1u << second);
            stdio_route_release(child, child->stdio[second]);
            result = 0;
            break;
        }
        if (third <= 2) {
            const u32 source_fd = static_cast<u32>(third);
            if ((current->stdio_mask & (1u << source_fd)) == 0 ||
                !current->stdio[source_fd].valid ||
                current->stdio[source_fd].writable != target_writable ||
                !stdio_route_copy(child, replacement, current->stdio[source_fd])) {
                result = process_error_denied; break;
            }
        } else {
            pipe_reference* reference = pipe_reference_for(current, third);
            if (reference == nullptr || reference->writable != target_writable) {
                result = process_error_denied; break;
            }
            replacement = {true, false, reference->writable, reference->pipe_index};
            if (child->pipe_reference_count >= process_max_pipe_refs) {
                result = process_error_resources; break;
            }
            pipe_retain(reference->pipe_index, reference->writable);
            ++child->pipe_reference_count;
        }
        if (second == 0 && child->stdio[0].valid && child->stdio[0].console && !replacement.console &&
            input_lease.contains(child->pid)) { (void)input_lease.remove(child->pid); }
        stdio_route_release(child, child->stdio[second]);
        child->stdio[second] = replacement;
        child->stdio_mask |= 1u << second;
        result = 0;
        break;
    }
    case sys_file_session: {
        if (current == nullptr || !current->block_access || current->pid != files_pid) {
            result = process_error_denied; break;
        }
        if (first >= file_session_count ||
            !user_range_ok(second, sizeof(file_session_info), true)) { break; }
        file_session_info info{};
        const process_record& client = tasks[first];
        if (client.state != task_state::free && client.state != task_state::dead &&
            client.session_request_handle != 0 && client.session_response_handle != 0) {
            info.pid = client.pid;
            info.parent_pid = client.parent;
            info.request_handle = client.session_request_handle;
            info.response_handle = client.session_response_handle;
        }
        copy_to_user(second, &info, sizeof(info));
        result = 0;
        break;
    }
    case sys_process_map: {
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        if (!user_range_ok(second, sizeof(process_page), false)) { break; }
        process_page page{}; copy_from_user(&page, second, sizeof(page));
        const bool stack_or_startup = page.address >= process_stack_bottom &&
                                      page.address < process_user_end;
        const bool image_page = page.address >= process_user_begin &&
                                page.address < process_stack_guard;
        if ((!image_page && !stack_or_startup) ||
            (page.address >= process_heap_begin && page.address < process_heap_end) ||
            page.address % page_size != 0 || page.length > page_size ||
            (page.permissions & ~u32{7}) != 0 || (page.permissions & map_read) == 0 ||
            (page.permissions & 3) == 3 || !user_range_ok(page.source, page.length, false)) { break; }
        if (stack_or_startup && page.permissions != (map_read | map_write)) { break; }
        if (task->user_pages == process_max_pages) { result = process_error_resources; break; }
        const page_permissions permissions{(page.permissions & 2) != 0, (page.permissions & 1) != 0, true};
        result = add_user_page(task, page.address, reinterpret_cast<const u8*>(page.source), page.length,
                               0, permissions) ? 0 : process_error_resources;
        break;
    }
    case sys_process_start: {
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        // A copied continuation must use fork_commit after authenticated files
        // cloning; the ordinary ELF start API cannot bypass that barrier.
        if (task->state != task_state::building || task->fork_pending || task->replacement_pending) {
            result = process_error_state; break;
        }
        if (!user_range_ok(second, sizeof(process_entry), false)) { break; }
        process_entry entry{}; copy_from_user(&entry, second, sizeof(entry));
        if (!valid_process_entry(task, entry)) { break; }
        task->entry = entry.entry; task->initial_stack = entry.stack; task->startup = entry.startup;
        task->state = task_state::fresh;
        if (process_trace_enabled) {
            format::text("[process] event=started pid="); format::decimal(task->pid);
            format::text(" parent="); format::decimal(task->parent); format::text("\r\n");
            format::text("[process] pid="); format::decimal(task->pid);
            format::text(" address_space="); format::hex(task->cr3); format::text("\r\n");
        }
        result = 0;
        break;
    }
    case sys_process_abort: {
        process_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        if (task->completion_slot != 0) { completions[task->completion_slot - 1] = completion_record{}; }
        destroy_task(task); result = 0;
        break;
    }
    case sys_process_wait: {
        if (third > 1) { break; }
        if (!user_range_ok(second, sizeof(process_status), true)) { break; }
        completion_record* item = completion_for(current->pid, first);
        if (item == nullptr) { result = process_error_denied; break; }
        if (item->ready) {
            copy_to_user(second, &item->status, sizeof(process_status));
            *item = completion_record{}; result = 0;
        } else {
            if (third == 1) { result = process_error_would_block; break; }
            process_record* child = owned_process(first);
            if (child == nullptr || child->state == task_state::building) { result = process_error_state; break; }
            for (const auto& waiter : threads) {
                if (waiter.process == current && waiter.wait_kind == thread_wait_kind::process &&
                    waiter.wait_target == first) { result = thread_error_busy; break; }
            }
            if (result == thread_error_busy) { break; }
            if (!current_thread->user_pin.set(second, sizeof(process_status))) { result = thread_error_busy; break; }
            current_thread->wait_target = first; current_thread->wait_buffer = second;
            current_thread->wait_kind = thread_wait_kind::process;
            current_thread->state = thread_state::blocked; frame->rax = 0;
            if (process_trace_enabled) {
                format::text("[process] event=wait_blocked parent="); format::decimal(current->pid);
                format::text(" child="); format::decimal(first); format::text("\r\n");
            }
            return schedule(frame);
        }
        break;
    }
    case sys_process_stats: {
        if (!current->supervisor) { result = process_error_denied; break; }
        if (!user_range_ok(first, sizeof(process_stats), true)) { break; }
        process_stats status{memory_status().free_pages, task_total, 0, 0};
        for (const auto& item : completions) { if (item.used) { ++status.completions; } }
        copy_to_user(first, &status, sizeof(status)); result = 0;
        break;
    }
    case sys_ipc_handles: {
        if (!user_range_ok(first, 2 * sizeof(u32), true)) { break; }
        u32 values[2] = {current->send_handle, current->recv_handle};
        copy_to_user(first, values, sizeof(values)); result = 0;
        break;
    }
    case sys_ipc_endpoint: {
        const auto action = static_cast<ipc_endpoint_action>(first);
        if (action == ipc_endpoint_action::create) {
            process_record* peer = task_by_pid(second == 0 ? current->parent : second);
            if (peer == nullptr || peer == current || peer->state == task_state::building ||
                peer->state == task_state::dead || peer->closing ||
                !user_range_ok(third, sizeof(ipc_channel), true)) {
                result = process_error_invalid; break;
            }
            ipc_channel channel{}, peer_channel{};
            if (!create_generic_channel(current->pid, peer->pid, current->pid,
                                        channel, peer_channel)) {
                result = process_error_resources; break;
            }
            (void)peer_channel;
            copy_to_user(third, &channel, sizeof(channel));
            result = 0;
            break;
        }
        if (action == ipc_endpoint_action::revoke && third == 0) {
            auto* endpoint = endpoint_for(second);
            if (endpoint == nullptr || !endpoint->generic || endpoint->owner_pid != current->pid) {
                result = process_error_denied; break;
            }
            revoke_ipc_channel(endpoint->channel_id, pipe_error_broken);
            result = 0;
            break;
        }
        if (action == ipc_endpoint_action::close && third == 0) {
            auto* endpoint = endpoint_for(second);
            if (endpoint == nullptr || !endpoint->generic ||
                (endpoint->sender_pid != current->pid && endpoint->receiver_pid != current->pid)) {
                result = process_error_denied; break;
            }
            revoke_ipc_channel(endpoint->channel_id, pipe_error_broken);
            result = 0;
            break;
        }
        if (action == ipc_endpoint_action::query_peer &&
            user_range_ok(third, sizeof(u64), true)) {
            const auto* endpoint = endpoint_for(second);
            if (endpoint == nullptr || !endpoint->generic) { result = process_error_denied; break; }
            u64 peer = 0;
            if (endpoint->sender_pid == current->pid) peer = endpoint->receiver_pid;
            else if (endpoint->receiver_pid == current->pid) peer = endpoint->sender_pid;
            else { result = process_error_denied; break; }
            copy_to_user(third, &peer, sizeof(peer));
            result = 0;
            break;
        }
        break;
    }
    case sys_ipc_wait: {
        if (third != 0 || second > static_cast<u64>(ipc_wait_mode::try_send)) { break; }
        auto* endpoint = endpoint_for(first);
        if (endpoint == nullptr || !endpoint->generic) { result = process_error_denied; break; }
        const auto mode = static_cast<ipc_wait_mode>(second);
        const bool receiving = mode == ipc_wait_mode::receive || mode == ipc_wait_mode::try_receive;
        const bool nonblocking = mode == ipc_wait_mode::try_receive || mode == ipc_wait_mode::try_send;
        if ((receiving && endpoint->receiver_pid != current->pid) ||
            (!receiving && endpoint->sender_pid != current->pid)) {
            result = process_error_denied; break;
        }
        const process_record* peer = task_by_pid(receiving ? endpoint->sender_pid : endpoint->receiver_pid);
        if (peer == nullptr || peer->state == task_state::dead || peer->closing) {
            result = pipe_error_broken; break;
        }
        if ((receiving && endpoint->pending) || (!receiving && !endpoint->pending)) {
            result = 0; break;
        }
        if (nonblocking) { result = process_error_would_block; break; }
        current_thread->wait_kind = receiving ? thread_wait_kind::ipc_receive : thread_wait_kind::ipc_send;
        current_thread->wait_target = endpoint->handle;
        current_thread->state = thread_state::blocked;
        frame->rax = 0;
        return schedule(frame);
    }
    case sys_ipc_name: {
        const auto action = static_cast<ipc_name_action>(first);
        if (action == ipc_name_action::publish || action == ipc_name_action::unpublish ||
            action == ipc_name_action::connect) {
            if (action != ipc_name_action::connect && third != 0) { break; }
            char name[32]{};
            if (!copy_ipc_name(second, name)) { result = process_error_invalid; break; }
            auto* entry = find_ipc_name(name);
            if (action == ipc_name_action::publish) {
                if (entry != nullptr) {
                    result = entry->owner_pid == current->pid ? 0 : process_error_busy;
                    break;
                }
                if (current->closing) { result = process_error_state; break; }
                for (auto& slot : ipc_names) {
                    if (!slot.used) {
                        slot.used = true;
                        slot.owner_pid = current->pid;
                        for (u32 i = 0; i < sizeof(slot.name); ++i) slot.name[i] = name[i];
                        result = 0;
                        break;
                    }
                }
                if (result == sys_error_invalid_argument) result = process_error_resources;
                break;
            }
            if (action == ipc_name_action::unpublish) {
                if (entry == nullptr || entry->owner_pid != current->pid) {
                    result = process_error_denied; break;
                }
                *entry = ipc_name_record{};
                if (!ipc_service_published(current->pid)) {
                    wake_ipc_acceptors(current->pid, pipe_error_broken);
                    for (auto& connection : ipc_connections) {
                        if (connection.used && connection.service_pid == current->pid) {
                            revoke_ipc_channel(connection.channel_id, pipe_error_broken);
                        }
                    }
                }
                result = 0;
                break;
            }
            if (!user_range_ok(third, sizeof(ipc_channel), true)) { break; }
            if (entry == nullptr) { result = ipc_error_name_not_found; break; }
            process_record* server = task_by_pid(entry->owner_pid);
            if (server == nullptr || server == current || server->state == task_state::dead ||
                server->state == task_state::building || server->closing) {
                result = ipc_error_name_not_found; break;
            }
            ipc_connection_record* slot = nullptr;
            for (auto& connection : ipc_connections) {
                if (!connection.used) { slot = &connection; break; }
            }
            if (slot == nullptr) { result = process_error_resources; break; }
            ipc_channel client_channel{}, service_channel{};
            if (!create_generic_channel(current->pid, server->pid, current->pid,
                                        client_channel, service_channel)) {
                result = process_error_resources; break;
            }
            slot->used = true;
            slot->service_pid = server->pid;
            slot->client_pid = current->pid;
            slot->channel_id = client_channel.send;
            slot->service_channel = service_channel;
            copy_to_user(third, &client_channel, sizeof(client_channel));
            wake_ipc_acceptors(server->pid, 0);
            result = 0;
            break;
        }
        if (action == ipc_name_action::accept) {
            if (third != 0 || !user_range_ok(second, sizeof(ipc_channel), true)) { break; }
            if (!ipc_service_published(current->pid)) { result = process_error_denied; break; }
            for (auto& connection : ipc_connections) {
                if (!connection.used || connection.service_pid != current->pid) continue;
                copy_to_user(second, &connection.service_channel, sizeof(ipc_channel));
                connection = ipc_connection_record{};
                result = 0;
                break;
            }
            if (result == sys_error_invalid_argument) result = process_error_would_block;
            break;
        }
        if (action == ipc_name_action::wait_accept && second == 0 && third == 0) {
            if (!ipc_service_published(current->pid)) { result = process_error_denied; break; }
            bool pending = false;
            for (const auto& connection : ipc_connections) {
                pending |= connection.used && connection.service_pid == current->pid;
            }
            if (pending) { result = 0; break; }
            current_thread->wait_kind = thread_wait_kind::ipc_accept;
            current_thread->wait_target = current->pid;
            current_thread->state = thread_state::blocked;
            frame->rax = 0;
            return schedule(frame);
        }
        break;
    }
    case sys_block_read:
    case sys_block_write: {
        if (current == nullptr || !current->block_access) { result = block_error_denied; break; }
        const u64 sector = first;
        const u64 address = second;
        const u64 count = third;
        const u64 bytes = count * block::sector_size;
        if (count == 0 || count > block::max_transfer_sectors ||
            sector >= block::sector_count() || sector + count > block::sector_count() ||
            !user_range_ok(address, bytes, frame->rax == sys_block_write ? false : true)) {
            result = block_error_invalid; break;
        }
        if (frame->rax == sys_block_write) {
            copy_from_user(block_buffer, address, bytes);
            result = block_status(block::write(sector, block_buffer, static_cast<u32>(count)));
        } else {
            const block::result read_result = block::read(sector, block_buffer, static_cast<u32>(count));
            if (read_result != block::result::none) { result = block_status(read_result); break; }
            copy_to_user(address, block_buffer, bytes);
            result = 0;
        }
        break;
    }
    case sys_block_sync:
        if (current == nullptr || !current->block_access) { result = block_error_denied; break; }
        result = block_status(block::sync());
        break;
    case sys_block_info: {
        if (current == nullptr || !current->block_access) { result = block_error_denied; break; }
        if (!user_range_ok(first, sizeof(u64), true)) { result = block_error_invalid; break; }
        const u64 sectors = block::sector_count();
        copy_to_user(first, &sectors, sizeof(sectors)); result = 0;
        break;
    }
    default: break;
    }
    frame->rax = static_cast<u64>(result);
    return frame;
}
}

void* input_entry(interrupt_frame* frame) {
    if (frame->vector == 36) {
        platform::irq_mask(4);
        platform::irq_acknowledge(4);
        if (irq_token != 0 && !irq_pending) {
            if (irq_sequence == 0x7fffffffffffffffull) { release_irq(); }
            else { irq_pending = true; ++irq_sequence; wake_irq_waiters(static_cast<i64>(irq_sequence)); }
        }
        return frame;
    }
    display::input_irq(frame->vector == 33 ? 1 : 12, clock::monotonic_ns());
    if(display::input_pending()){display_wake(0,0);}
    return frame;
}

void* timer_entry(interrupt_frame* frame) {
    platform::timer_interrupt();
    expire_pc_speaker_lease();
    // Boot diagnostics may enable IRQ0 before any process has been entered.
    // They advance the same clock without expiring/scheduling prepared tasks.
    if (current == nullptr || current_thread == nullptr) { return frame; }
    if (current != nullptr && current_thread != nullptr &&
        current_thread->state == thread_state::running) { ++current->ticks; }
    expire_waiters();
    (void)cancel_foreground();
    if ((frame->cs & 3) == 3) { return schedule(frame); }
    return frame;
}

void* syscall_entry(interrupt_frame* frame) {
    reap_dead();
    reap_threads();
    const u64 number = frame->rax;
    if(current->pid==display_service_pid &&
       (number==sys_process_create || number==sys_process_exec_prepare || number==sys_process_fork_prepare ||
        number==sys_process_delegate || number==sys_process_grant ||
        number==sys_ipc_endpoint || number==sys_ipc_wait || number==sys_ipc_name)) {
        frame->rax=static_cast<u64>(display_denied);return frame;
    }
    if (number >= sys_thread_prepare && number <= sys_thread_profile) { return thread_syscall(frame); }
    if (current_thread->leaving && number != sys_exit) {
        frame->rax = static_cast<u64>(process_error_state); return frame;
    }
    if(number==sys_display || number==sys_display_present){return display_syscall(frame);}
    if(number==sys_device){return device_authorize_syscall(frame);}
    i64 result = sys_error_invalid_argument;
    switch (number) {
    case sys_write: {
        const u64 address = frame->rdi;
        const u64 length = frame->rsi;
        result = stdio_write(current, 1, address, length);
        break;
    }
    case sys_exit:
        if (current != nullptr) {
            finish_task(current, process_outcome::exited, static_cast<i32>(frame->rdi));
        }
        return schedule(frame);
    case sys_yield:
        return schedule(frame);
    case sys_send:
        result = ipc_send(frame->rdi, frame->rsi, frame->rdx);
        break;
    case sys_recv:
        result = ipc_recv(frame->rdi, frame->rsi, frame->rdx);
        break;
    case sys_getpid:
        result = current != nullptr ? static_cast<i64>(current->pid) : -1;
        break;
    case sys_ticks:
        result = static_cast<i64>(clock::ticks());
        break;
    case sys_read: {
        result = stdio_read(current, 0, frame->rdi, frame->rsi, false);
        break;
    }
    case sys_tasklist: {
        const u64 address = frame->rdi;
        const u64 length = frame->rsi;
        if (length == 0 || !user_range_ok(address, length, true)) {
            result = sys_error_invalid_argument;
            break;
        }
        char buffer[768];
        u32 used = 0;
        for (u32 i = 0; i < 8; ++i) {
            const process_record& task = tasks[i];
            if (task.state == task_state::free || task.state == task_state::dead) { continue; }
            append_text(buffer, used, sizeof(buffer), "pid=");
            append_decimal(buffer, used, sizeof(buffer), task.pid);
            append_text(buffer, used, sizeof(buffer), " name=");
            append_text(buffer, used, sizeof(buffer), task.name);
            append_text(buffer, used, sizeof(buffer), " state=");
            if (used + 1 < sizeof(buffer)) {
                buffer[used++] = state_label(task);
            }
            append_text(buffer, used, sizeof(buffer), " ticks=");
            append_decimal(buffer, used, sizeof(buffer), task.ticks);
            if (used + 1 < sizeof(buffer)) {
                buffer[used++] = '\n';
            }
        }
        if (used > length) {
            result = sys_error_invalid_argument;
        } else {
            copy_to_user(address, buffer, used);
            result = static_cast<i64>(used);
        }
        break;
    }
    case sys_vm: {
        // Public anonymous VM request; diagnostic operations are probe-only.
        if ((frame->rdi & 7) || !user_range_ok(frame->rdi, sizeof(anonymous_vm::request), false)) {
            result = -2; break;
        }
        if (frame->rsi || frame->rdx) { result = anonymous_vm::invalid; break; }
        anonymous_vm::request request{};
        copy_from_user(&request, frame->rdi, sizeof(request));
#if XOS_VM1_PROBE
        // Exercise a genuine ready-but-not-yet-delivered process wait pin.
        if (request.operation == 0xfffd && request.version == 1 && request.size == sizeof(request) &&
            !request.flags && request.address && request.length && !request.alignment &&
            !request.protection && !request.reserved0 && !request.reserved1 && !request.reserved2) {
            auto* child = owned_process(request.address);
            const u64 address = request.length;
            if (!child || child->state == task_state::building || child->state == task_state::dead ||
                child->continuation.active() ||
                !user_range_ok(address, sizeof(process_status), true)) { result=process_error_invalid; break; }
            const u64 first_page = address & ~(page_size-1);
            const u64 last_page = (address+sizeof(process_status)-1) & ~(page_size-1);
            const bool before = pinned_range(current, first_page, first_page+page_size) &&
                                pinned_range(current, last_page, last_page+page_size);
            finish_task(child, process_outcome::killed, -9);
            destroy_task(child);
            bool waiter_ready = false;
            for (const auto& thread : threads) {
                if (thread.process == current && thread.state == thread_state::ready &&
                    thread.wait_kind == thread_wait_kind::process && thread.wait_target == request.address) waiter_ready=true;
            }
            const bool after = pinned_range(current, first_page, first_page+page_size) &&
                               pinned_range(current, last_page, last_page+page_size);
            result = before && waiter_ready && after ? 0 : process_error_state; break;
        }
        if (request.operation==0xfffb && request.version==1 && request.size==sizeof(request) &&
            !request.flags && !request.address && !request.length && !request.alignment &&
            !request.protection && !request.reserved0 && !request.reserved1 && !request.reserved2) {
            vm2_failures[static_cast<u32>(current-tasks)].trace=true; result=0; break;
        }
        // Probe-only scoped allocation failure. The global allocator hook is
        // active only inside one non-yielding page-table preparation call.
        if (request.operation==0xfffc && request.version==1 && request.size==sizeof(request) &&
            request.flags<=1 && request.address<=4096 && !request.length && !request.alignment &&
            !request.protection && !request.reserved0 && !request.reserved1 && !request.reserved2) {
            auto& injection=vm2_failures[static_cast<u32>(current-tasks)];
            injection.page=request.flags==0 ? static_cast<i64>(request.address) : -1;
            injection.table=request.flags==1 ? static_cast<i64>(request.address) : -1;
            result=0; break;
        }
        // Private test diagnostic, deliberately absent from the public wire.
        if (request.operation == 0xffff && request.version == 1 && request.size == sizeof(request) &&
            !request.flags && !request.address && !request.length && !request.alignment &&
            !request.protection && !request.reserved0 && !request.reserved1 && !request.reserved2) {
            result = memory_status().free_pages; break;
        }
        if (request.operation == 0xfffe && request.version == 1 && request.size == sizeof(request) &&
            request.flags <= 1 && request.address > 0 && request.address <= 4096 &&
            ((!request.flags && !request.length) || (request.flags == 1 && request.length > 0 && request.length < request.address)) &&
            !request.alignment && !request.protection && !request.reserved0 && !request.reserved1 && !request.reserved2) {
            if (current->closing || current->continuation.active()) { result=process_error_state; break; }
            auto& state=vm2_probe_states[static_cast<u32>(current - tasks)];
            state.target=static_cast<u32>(request.address); state.count=0; state.error=0;
            state.fail_after=static_cast<u32>(request.length);
            state.process_ticks=&current->ticks; state.initial_ticks=current->ticks;
            state.prepare_reported=false; state.publish_reported=false; state.rollback_reported=false;
            if (!begin_vm_continuation(*current, *current_thread, &state, vm2_probe_step)) {
                result=process_error_state; break;
            }
            frame->rax=0; return schedule(frame);
        }
        if (request.operation==0xfffa && request.version==1 && request.size==sizeof(request) &&
            !request.flags && request.address<=65536 && !request.length && !request.alignment &&
            !request.protection && !request.reserved0 && !request.reserved1 && !request.reserved2) {
            vm2_failures[static_cast<u32>(current-tasks)].fork=static_cast<i64>(request.address); result=0; break;
        }
#endif
        if (request.operation>=2 && request.operation<=5) {
            if (request.version!=1 || request.size!=sizeof(request) || request.flags || request.alignment ||
                request.reserved0 || request.reserved1 || request.reserved2 || !request.length ||
                (request.address % page_size) || (request.length % page_size) ||
                request.address<anonymous_vm::arena_begin || request.address>=anonymous_vm::arena_end ||
                request.length>anonymous_vm::arena_end-request.address) { result=anonymous_vm::invalid; break; }
            if ((request.protection & 6)==6) { result=-3; break; }
            if ((request.protection!=0 && request.protection!=1 && request.protection!=3 && request.protection!=5) ||
                (request.operation==2 && !request.protection) ||
                (request.operation>=4 && request.protection)) { result=anonymous_vm::invalid; break; }
            if (current->closing || current->continuation.active()) { result=anonymous_vm::closing; break; }
            const u32 slot=static_cast<u32>(current-tasks);
            if (ipc_v1_grant_overlap(current->pid, request.address, request.address + request.length)) {
                result = static_cast<i64>(ipc_v1_error::busy); break;
            }
            auto& regions=vm1_probe_regions[slot];
            if (request.operation!=5 && !regions.contains(request.address,request.length)) { result=-6; break; }
            if (request.operation==5 && pinned_range(current,request.address,request.address+request.length)) { result=-5; break; }
            if (request.operation!=5 && request.length/page_size>4096) { result=anonymous_vm::resources; break; }
            auto& tx=vm2_page_transactions[slot];
            tx.owner=current; tx.address=request.address; tx.end=request.address+request.length; tx.scan=tx.address;
            tx.operation=request.operation; tx.protection=request.protection;
            tx.pages=request.operation==5 ? 0 : static_cast<u32>(request.length/page_size);
            tx.cursor=0; tx.prepared=0; tx.staged_count=0; tx.allocation_pass=false; tx.rollback_started=false;
            tx.fail_page=vm2_failures[slot].page; tx.fail_table=vm2_failures[slot].table;
            tx.trace=vm2_failures[slot].trace; tx.staging_reported=false; tx.publish_reported=false;
            vm2_failures[slot]=vm2_failure_injection{};
            if (request.operation==5) {
                tx.regions=regions;
                result=tx.regions.unmap(request.address,request.length);
                if (result) break;
            }
            if (!begin_vm_continuation(*current,*current_thread,&tx,vm2_page_step)) { result=anonymous_vm::closing; break; }
            frame->rax=0; return schedule(frame);
        }
        result = vm1_probe_regions[static_cast<u32>(current - tasks)].apply(request, current->closing);
        break;
    }
    case sys_random_bytes:
        result = frame->rdx == 0 ? random_bytes(frame->rdi, frame->rsi)
                                 : random_error_invalid;
        break;
    case sys_clock_realtime:
        result = frame->rdi == 0 ? platform::realtime_clock_ns(clock::monotonic_ns())
                                 : process_error_invalid;
        break;
    case sys_kill: {
        if (current == nullptr || !current->supervisor) {
            result = sys_error_invalid_handle;
            break;
        }
        const u64 pid = frame->rdi;
        process_record* target = nullptr;
        for (u32 i = 0; i < 8; ++i) {
            if (tasks[i].state != task_state::free && tasks[i].pid == pid) {
                target = &tasks[i];
                break;
            }
        }
        if (target == nullptr || target == current || target->supervisor || target->block_access ||
            target->state == task_state::dead || target->state == task_state::free) {
            result = sys_error_invalid_handle;
            break;
        }
        finish_task(target, process_outcome::killed, -9);
        if (process_trace_enabled) {
            format::text("[task] event=killed_by_supervisor pid=");
            format::decimal(pid);
            format::text("\r\n");
        }
        destroy_task(target);
        result = 0;
        break;
    }
    default:
        return process_syscall(frame);
    }
    frame->rax = static_cast<u64>(result);
    return frame;
}

void* user_fault(interrupt_frame* frame) {
    const u64 fault_address = frame->vector == 14 ? read_cr2() : 0;
    format::text("[task] event=fault pid=");
    format::decimal(current != nullptr ? current->pid : 0);
    format::text(" vector=");
    format::decimal(static_cast<u32>(frame->vector));
    format::text(" rip=");
    format::hex(frame->rip);
    if (frame->vector == 14) {
        format::text(" cr2=");
        format::hex(fault_address);
    }
    format::text(" result=killed tid=");
    format::decimal(current_thread != nullptr ? current_thread->tid : 0);
    format::text("\r\n");
    if (current != nullptr) {
        finish_task(current, process_outcome::faulted, 0, frame->vector, fault_address, frame->rip);
    }
    return schedule(frame);
}

bool tasks_create_default() {
    fpu_init();
    using namespace xos::user_blobs;
    if (create_task("heartbeat", heartbeat, heartbeat_size) == nullptr) { return false; }
    if (create_task("spinner", spinner, spinner_size) == nullptr) { return false; }
    process_record* receiver_task = create_task("receiver", receiver, receiver_size);
    if (receiver_task == nullptr) { return false; }
    const u32 handle = endpoint_attach(receiver_task->pid, 0, receiver_task->pid,
        default_message_bytes);
    if (handle != 1) { return false; }
    receiver_task->recv_handle = handle;
    process_record* sender_task = create_task("sender", sender, sender_size);
    if (sender_task == nullptr) { return false; }
    sender_task->send_handle = handle;
    endpoint_record* channel = endpoint_for(handle);
    if (channel == nullptr) { return false; }
    channel->sender_pid = sender_task->pid;
    if (create_task("probe", probe, probe_size) == nullptr) { return false; }
    if (create_task("quitter", quitter, quitter_size) == nullptr) { return false; }
    process_record* supervisor_task = create_supervisor();
    if (supervisor_task == nullptr) { return false; }
    supervisor_task->supervisor = true;
    process_record* files_task = create_files_service();
    if (files_task == nullptr) { return false; }
    files_pid = files_task->pid;
    const u32 request_handle = endpoint_attach(files_task->pid, supervisor_task->pid,
        supervisor_task->pid, file_message_bytes);
    const u32 response_handle = endpoint_attach(supervisor_task->pid, files_task->pid,
        supervisor_task->pid, file_message_bytes, true);
    if (request_handle != 2 || response_handle != 3) { return false; }
    supervisor_task->send_handle = request_handle;
    supervisor_task->recv_handle = response_handle;
    supervisor_task->session_request_handle = request_handle;
    supervisor_task->session_response_handle = response_handle;
    files_task->recv_handle = request_handle;
    files_task->send_handle = response_handle;
    format::text("[task] event=ready count=");
    format::decimal(task_total);
    format::text("\r\n");
    return true;
}

[[noreturn]] void tasks_enter() {
    display::input_init();
    if (!platform::realtime_clock_init(clock::monotonic_ns())) {
        format::text("[clock] event=realtime unavailable=rtc_invalid\r\n");
    }
    thread_record* first = pick_ready();
    if (first == nullptr) {
        format::text("[sched] event=no_ready_tasks result=halt\r\n");
        halt();
    }
    interrupt_frame* frame = make_initial_frame(first);
    switch_to(first);
    format::text("[sched] event=start tasks=");
    format::decimal(task_total);
    format::text("\r\n");
    enter_frame(frame);
}

u32 snapshot_count() {
    return task_total;
}

task_snapshot snapshot_at(u32 index) {
    task_snapshot snapshot{};
    if (index >= 8) { return snapshot; }
    const process_record& task = tasks[index];
    snapshot.pid = static_cast<u32>(task.pid);
    snapshot.ticks = task.ticks;
    snapshot.name = task.name;
    return snapshot;
}
}

namespace xos {
bool tasks_init() {
    return arch::tasks_create_default();
}

[[noreturn]] void tasks_start() {
    arch::tasks_enter();
}

u32 task_count() {
    return arch::snapshot_count();
}

task_snapshot task_at(u32 index) {
    return arch::snapshot_at(index);
}
}
