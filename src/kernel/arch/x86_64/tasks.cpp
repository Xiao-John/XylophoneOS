// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/task.hpp>
#include <xos/display.hpp>
#include <xos/thread_abi.hpp>
#include "../../core/thread_lifecycle.hpp"
#include <xos/block.hpp>
#include <xos/syscall.hpp>
#include <xos/memory.hpp>
#include <xos/format.hpp>
#include <xos/platform.hpp>
#include "frame.hpp"
#include <xos/clock.hpp>
#include "arch/x86_64/interrupt_wait.hpp"
static_assert(xos::clock::resolution_ns == xos::thread_tick_ns);
#include "user_blobs.hpp"
#include "user_images.hpp"

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
// E03's receiver, the supervisor/files bootstrap pair, and eight task pairs.
constexpr u32 max_endpoints = 21;
constexpr u32 file_session_count = 8;
constexpr u32 default_message_bytes = 64;
constexpr u32 file_message_bytes = 4096;
constexpr u32 kernel_stack_bytes = 4096;
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
    task_state state;
    char name[12];
    u32 send_handle;
    u32 recv_handle;
    u32 session_request_handle;
    u32 session_response_handle;
    bool supervisor;
    bool block_access;
    u32 spawn_depth;
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
};

struct completion_record { bool used; bool ready; u64 parent; process_status status; };
completion_record completions[16];

struct endpoint_record {
    bool used;
    u32 handle;
    u64 receiver_pid;
    u64 sender_pid;
    u64 owner_pid;
    u32 capacity;
    bool session_response;
    bool pending;
    u32 length;
    u8 data[file_message_bytes];
};

struct thread_record : thread_lifetime {
    process_record* process;
    u64 kernel_rsp;
    u64 kernel_stack_top;
    u64 thread_pointer;
    u64 entry;
    u64 argument;
    u64 initial_stack;
    alignas(16) u8 fpu_state[512];
};
process_record tasks[8];
thread_record threads[thread_max_total];
thread_record* current_thread;
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
u64 files_pid;
pipe_object pipes[process_max_pipes];
u64 next_pipe_token = process_pipe_token_min;
bool reap_pending[8];
u8 block_buffer[4096];
alignas(16) u8 fpu_template[512];
bool process_trace_enabled = true;
process_guard_info admission_guard{};

void ready_with(thread_record& thread, i64 result);
bool display_endpoint(u64 handle);
void display_wake(u64 handle,i64 result);
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
    if (address < user_base || address >= user_limit) { return false; }
    if (length > user_limit - address) { return false; }
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
    if (allocate_page(&physical) != memory_result::none) { return false; }
    if (size != 0) { copy_bytes(reinterpret_cast<u8*>(physical) + offset, bytes, size); }
    if (!map_user(task->cr3, address, physical, permissions)) {
        (void)release_page(physical); return false;
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

process_record* task_by_pid(u64 pid) {
    for (auto& task : tasks) {
        if (task.state != task_state::free && task.pid == pid) { return &task; }
    }
    return nullptr;
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
         !(current->block_access && endpoint->session_response) && !display_endpoint(handle))) {
        return sys_error_invalid_handle;
    }
    if (endpoint->receiver_pid == current->pid || length == 0 || length > endpoint->capacity) {
        return sys_error_invalid_argument;
    }
    process_record* receiver = task_by_pid(endpoint->receiver_pid);
    if (receiver == nullptr || receiver->state == task_state::dead ||
        receiver->state == task_state::building) { return sys_error_invalid_handle; }
    if (endpoint->pending || (handle==display_request_handle && display_delivered)) { return sys_error_full; }
    if (handle==display_response_handle && !display_delivered) {return sys_error_invalid_argument;}
    if (!user_range_ok(address, length, false)) { return sys_error_invalid_argument; }
    copy_from_user(endpoint->data, address, length);
    endpoint->length = static_cast<u32>(length);
    endpoint->pending = true;
    if(handle==display_response_handle){display_delivered=false;display_presented=false;}
    if(display_endpoint(handle)){display_wake(handle,0);}
    return 0;
}

i64 ipc_recv(u64 handle, u64 address, u64 length) {
    endpoint_record* endpoint = endpoint_for(handle);
    if (endpoint == nullptr || current == nullptr || endpoint->receiver_pid != current->pid ||
        (current->recv_handle != handle && !current->block_access && !display_endpoint(handle))) {
        return sys_error_invalid_handle;
    }
    if (!user_range_ok(address, length, true)) { return sys_error_invalid_argument; }
    if (!endpoint->pending) { return sys_error_empty; }
    if (length < endpoint->length) { return sys_error_invalid_argument; }
    copy_to_user(address, endpoint->data, endpoint->length);
    const u32 length_received = endpoint->length;
    endpoint->pending = false;
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
    if (task == nullptr || task->state == task_state::free || task == current) { return; }
    reap_pending[task_index(task)] = false;
    const u64 pid = task->pid;
    for (auto& endpoint : endpoints) {
        if (endpoint.used && (endpoint.owner_pid == pid || endpoint.receiver_pid == pid ||
                              endpoint.sender_pid == pid)) { endpoint = endpoint_record{}; }
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
                  u64 vector = 0, u64 address = 0, u64 instruction = 0) {
    if (task->state == task_state::dead) { return; }
    display_release(task->pid);
    task->closing = true;
    task->state = task_state::dead;
    for (auto& thread : threads) {
        if (thread.process == task && thread.state != thread_state::free) {
            thread.state = thread_state::dead;
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
    if (thread->wait_kind != thread_wait_kind::process) { return; }
    completion_record* item = completion_for(thread->process->pid, thread->wait_target);
    if (item == nullptr || !item->ready) { return; }
    if (user_range_ok(thread->wait_buffer, sizeof(process_status), true)) {
        copy_to_user(thread->wait_buffer, &item->status, sizeof(process_status));
        *item = completion_record{};
        frame->rax = 0;
    } else { frame->rax = static_cast<u64>(process_error_invalid); }
    thread->wait_kind = thread_wait_kind::none;
    thread->wait_target = 0;
}

thread_record* pick_ready() {
    for (u32 i = 0; i < thread_max_total; ++i) {
        const u32 index = (cursor + i) % thread_max_total;
        thread_record& thread = threads[index];
        if (thread.process == nullptr || thread.process->state == task_state::building ||
            thread.process->state == task_state::dead) { continue; }
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
    reap_dead();
    reap_threads();
    if (current_thread != nullptr && current_thread->state != thread_state::dead) {
        if (current_thread->state == thread_state::running) { current_thread->state = thread_state::ready; }
        if (frame != nullptr) { current_thread->kernel_rsp = reinterpret_cast<u64>(frame); }
        fpu_save(current_thread->fpu_state);
    }
    thread_record* next = pick_ready();
    // Interrupts in ring0 never schedule: the idle loop keeps this saved syscall
    // frame and only permits IRQs to advance time. No blocked syscall polls userspace.
    while (next == nullptr) {
        arch::wait_for_interrupt();
        expire_waiters();
        next = pick_ready();
    }
    interrupt_frame* next_frame = next->state == thread_state::fresh
        ? make_initial_frame(next) : reinterpret_cast<interrupt_frame*>(next->kernel_rsp);
    switch_to(next);
    fpu_restore(next->fpu_state);
    deliver_wait(next, next_frame);
    return next_frame;
}

process_record* owned_process(u64 handle) {
    if (current == nullptr) { return nullptr; }
    for (auto& task : tasks) {
        if (task.state != task_state::free && task.pid == handle && task.parent == current->pid) {
            if (current->supervisor || current->spawn_depth != 0 ||
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
            if (allocate_page(&physical) != memory_result::none) { break; }
            if (map_page_in(current->cr3, address, physical, {true, false, true}) != memory_result::none) {
                (void)release_page(physical);
                break;
            }
            ++current->user_pages;
        }
        if (address != new_end) {
            for (u64 rollback = old_end; rollback < address; rollback += page_size) {
                u64 physical = 0;
                if (unmap_page_in(current->cr3, rollback, &physical) == memory_result::none) {
                    (void)release_page(physical);
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
                release_page(physical) != memory_result::none) { return process_error_state; }
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
        if (thread.process != process || thread.state != thread_state::blocked) { continue; }
        u64 address = 0, bytes = 0;
        if (thread.wait_kind == thread_wait_kind::word) { address = thread.wait_target; bytes = 4; }
        if (thread.wait_kind == thread_wait_kind::process) { address = thread.wait_buffer; bytes = sizeof(process_status); }
        if (thread.wait_kind == thread_wait_kind::join) { address = thread.wait_buffer; bytes = sizeof(u64); }
        if (bytes != 0 && address < end && address + bytes > begin) { return true; }
    }
    return false;
}

void release_thread_range(thread_record& thread, u64 begin, u64 end) {
    for (u64 address = begin; address < end; address += page_size) {
        u64 physical = 0;
        if (unmap_page_in(thread.process->cr3, address, &physical) == memory_result::none) {
            (void)release_page(physical);
            if (thread.process->user_pages != 0) { --thread.process->user_pages; }
        }
    }
}

void ready_with(thread_record& thread, i64 result) {
    auto* saved = reinterpret_cast<interrupt_frame*>(thread.kernel_rsp);
    saved->rax = static_cast<u64>(result);
    thread.wait_kind = thread_wait_kind::none;
    thread.wait_target = 0;
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
            (thread.wait_kind == thread_wait_kind::word || thread.wait_kind == thread_wait_kind::sleep) &&
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

// Prepare a private address-space snapshot while the single-core kernel cannot
// be preempted. No child context becomes runnable until fork_commit; every
// fallible allocation precedes completion-record publication.
i64 prepare_fork(interrupt_frame* frame) {
    if (current == nullptr || current->supervisor || current->block_access) {
        return process_error_denied;
    }
    if (current->threads_enabled || current_thread != &main_thread(current) ||
        !current_thread->main) { return thread_error_unsupported; }
    for (const auto& peer : threads) {
        if (peer.process == current && &peer != current_thread &&
            peer.state != thread_state::free && peer.state != thread_state::dead) {
            return thread_error_unsupported;
        }
    }
    if (current->spawn_depth == 0) { return process_error_denied; }
    if (current->closing || current_thread->leaving) { return process_error_state; }
    if (current->fork_depth >= process_fork_depth_max || !files_service_live()) {
        return process_error_resources;
    }
    completion_record* completion = nullptr;
    for (auto& item : completions) { if (!item.used) { completion = &item; break; } }
    u32 free_endpoints = 0;
    for (const auto& endpoint : endpoints) { if (!endpoint.used) { ++free_endpoints; } }
    if (completion == nullptr || free_endpoints < 2 || next_endpoint_handle > 0xfffffffeull) {
        return process_error_resources;
    }
    process_record* child = prepare_task(current->name);
    if (child == nullptr) { return process_error_resources; }
    child->parent = current->pid;
    child->spawn_depth = current->spawn_depth;
    child->fork_source = current->pid;
    child->fork_depth = current->fork_depth + 1;
    child->fork_pending = true;
    child->heap_break = current->heap_break;
    child->entry = current->entry;
    child->initial_stack = current->initial_stack;
    child->startup = current->startup;
    if (copy_user_pages_in(current->cr3, child->cr3, process_max_pages,
                           &child->user_pages) != memory_result::none ||
        child->user_pages != current->user_pages) {
        destroy_task(child); return process_error_resources;
    }
    if (!inherit_stdio(child, current, current->stdio_mask)) {
        destroy_task(child); return process_error_resources;
    }
    // libc's copied FD table contains these exact tokens. Retain the underlying
    // objects under the new PID; global monotonic tokens are still authorized
    // by membership in each process's private reference array.
    for (u32 index = 0; index < process_max_pipe_refs; ++index) {
        const auto& reference = current->pipe_references[index];
        if (!reference.used) { continue; }
        if (child->pipe_reference_count >= process_max_pipe_refs ||
            reference.pipe_index >= process_max_pipes || !pipes[reference.pipe_index].used) {
            destroy_task(child); return process_error_resources;
        }
        child->pipe_references[index] = reference;
        pipe_retain(reference.pipe_index, reference.writable);
        ++child->pipe_reference_count;
    }
    if (child->pipe_reference_count != current->pipe_reference_count) {
        destroy_task(child); return process_error_state;
    }
    child->session_request_handle = endpoint_attach(files_pid, child->pid, child->pid,
        file_message_bytes);
    child->session_response_handle = endpoint_attach(child->pid, files_pid, child->pid,
        file_message_bytes, true);
    if (child->session_request_handle == 0 || child->session_response_handle == 0) {
        destroy_task(child); return process_error_resources;
    }
    child->send_handle = child->session_request_handle;
    child->recv_handle = child->session_response_handle;
    auto& thread = main_thread(child);
    thread.stack_bottom = current_thread->stack_bottom;
    thread.stack_top = current_thread->stack_top;
    thread.tls_begin = current_thread->tls_begin;
    thread.tls_end = current_thread->tls_end;
    thread.thread_pointer = current_thread->thread_pointer;
    // The running thread's saved FPU image can predate this syscall. Snapshot
    // the actual registers now rather than copying the last scheduling image.
    fpu_save(current_thread->fpu_state);
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
    return static_cast<i64>(child->pid);
}

#include "display_tasks.inc"

void* process_syscall(interrupt_frame* frame) {
    i64 result = process_error_invalid;
    const u64 first = frame->rdi, second = frame->rsi, third = frame->rdx;
    switch (frame->rax) {
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
        if (!user_range_ok(second, sizeof(process_entry), false)) { break; }
        process_entry entry{};
        copy_from_user(&entry, second, sizeof(entry));
        if (!valid_process_entry(stage, entry)) { break; }
        u32 depth = current->spawn_depth;
        if (third != 0) {
            if (third - 1 > process_max_spawn_depth || third - 1 >= current->spawn_depth) {
                result = process_error_delegation; break;
            }
            depth = static_cast<u32>(third - 1);
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
        display_release(current->pid);
        const u64 old_space = current->cr3;
        const u32 old_pages = current->user_pages;
        const u32 old_depth = current->spawn_depth;
        const auto& staged_thread = main_thread(stage);
        // The new Client starts a fresh request-ID sequence. Re-key the same
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
        if (first == 0 && second == 0 && third == 0) { result = prepare_fork(frame); }
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
        if (!current->supervisor && current->spawn_depth == 0) { result = process_error_denied; break; }
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
        if (second > process_pipe_bytes || third != 0) { result = process_error_invalid; break; }
        u32 pipe_index = process_max_pipes;
        bool writable = false;
        if (first < 3) {
            if ((current->stdio_mask & (1u << first)) == 0 ||
                !current->stdio[first].valid) { result = process_error_denied; break; }
            const auto& route = current->stdio[first];
            if (route.console) { result = second != 0 && !route.writable
                ? process_error_invalid : process_error_would_block; break; }
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
        // Check and sleep in one non-preemptible kernel critical section.
        // A subsequent read/write rechecks the pipe and its own user buffer.
        current_thread->wait_kind = writable ? thread_wait_kind::pipe_write : thread_wait_kind::pipe_read;
        current_thread->wait_target = pipe_index;
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
    display::input_irq(frame->vector == 33 ? 1 : 12, clock::monotonic_ns());
    if(display::input_pending()){display_wake(0,0);}
    return frame;
}

void* timer_entry(interrupt_frame* frame) {
    platform::timer_interrupt();
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
        number==sys_process_delegate || number==sys_process_grant)) {
        frame->rax=static_cast<u64>(display_denied);return frame;
    }
    if (number >= sys_thread_prepare && number <= sys_thread_profile) { return thread_syscall(frame); }
    if (current_thread->leaving && number != sys_exit) {
        frame->rax = static_cast<u64>(process_error_state); return frame;
    }
    if(number==sys_display || number==sys_display_present){return display_syscall(frame);}
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
