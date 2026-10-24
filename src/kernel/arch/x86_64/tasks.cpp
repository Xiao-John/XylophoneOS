// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/task.hpp>
#include <xos/block.hpp>
#include <xos/syscall.hpp>
#include <xos/memory.hpp>
#include <xos/format.hpp>
#include <xos/platform.hpp>
#include "frame.hpp"
#include "pic.hpp"
#include "user_blobs.hpp"
#include "user_images.hpp"

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
constexpr u32 max_endpoints = 19;
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

struct task_record {
    u64 cr3;
    u64 kernel_rsp;
    u64 kernel_stack_top;
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
    bool spawn_access;
    i32 exit_code;
    u64 parent;
    u64 entry;
    u64 initial_stack;
    u64 startup;
    u64 waiting_pid;
    u64 wait_buffer;
    u32 stdio_mask;
    stdio_route stdio[3];
    pipe_reference pipe_references[process_max_pipe_refs];
    u32 pipe_reference_count;
    u32 user_pages;
    u32 completion_slot;
    u64 heap_break;
    u64 thread_pointer;
    alignas(16) u8 fpu_state[512];
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

task_record tasks[8];
u32 task_total;
u32 cursor;
task_record* current;
u64 tick_count;
u64 next_pid = 1;
endpoint_record endpoints[max_endpoints];
u64 next_endpoint_handle = 1;
u64 files_pid;
pipe_object pipes[process_max_pipes];
u64 next_pipe_token = process_pipe_token_min;
bool reap_pending[8];
u8 block_buffer[4096];
alignas(16) u8 fpu_template[512];

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

char state_label(const task_record& task) {
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

pipe_reference* pipe_reference_for(task_record* task, u64 token) {
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
    if (pipe.references == 0) { pipe = pipe_object{}; }
}

void stdio_route_release(task_record* owner, stdio_route& route) {
    if (route.valid && !route.console) {
        pipe_release(route.pipe_index, route.writable);
        if (owner != nullptr && owner->pipe_reference_count != 0) { --owner->pipe_reference_count; }
    }
    route = stdio_route{};
}

void task_pipe_release_all(task_record* task) {
    for (auto& reference : task->pipe_references) {
        if (!reference.used) { continue; }
        pipe_release(reference.pipe_index, reference.writable);
        if (task->pipe_reference_count != 0) { --task->pipe_reference_count; }
        reference = pipe_reference{};
    }
    for (auto& route : task->stdio) { stdio_route_release(task, route); }
}

bool stdio_route_copy(task_record* owner, stdio_route& destination, const stdio_route& source) {
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

bool inherit_stdio(task_record* child, task_record* parent, u32 mask) {
    child->stdio_mask = 0;
    for (auto& route : child->stdio) { route = stdio_route{}; }
    for (u32 fd = 0; fd < 3; ++fd) {
        if ((mask & (1u << fd)) == 0) { continue; }
        if (!stdio_route_copy(child, child->stdio[fd], parent->stdio[fd])) { return false; }
        child->stdio_mask |= 1u << fd;
    }
    return true;
}

task_record* free_slot() {
    for (u32 i = 0; i < 8; ++i) {
        if (tasks[i].state == task_state::free) { return &tasks[i]; }
    }
    return nullptr;
}

bool map_user(u64 cr3, u64 virtual_address, u64 physical, page_permissions permissions) {
    return map_page_in(cr3, virtual_address, physical, permissions) == memory_result::none;
}

void destroy_task(task_record* task);

task_record* prepare_task(const char* name) {
    task_record* task = free_slot();
    if (task == nullptr || next_pid == 0 || next_pid > 0x7fffffffffffffff) { return nullptr; }
    *task = task_record{};
    for (u32 i = 0; i < sizeof(task->fpu_state); ++i) { task->fpu_state[i] = fpu_template[i]; }
    task->pid = next_pid++;
    copy_name(task->name, name);
    task->cr3 = create_address_space();
    if (task->cr3 == 0) { *task = task_record{}; return nullptr; }
    u64 kernel_stack = 0;
    if (allocate_page(&kernel_stack) != memory_result::none) {
        (void)destroy_address_space(task->cr3); *task = task_record{}; return nullptr;
    }
    task->kernel_stack_top = kernel_stack + kernel_stack_bytes;
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

bool add_user_page(task_record* task, u64 address, const u8* bytes, u32 size,
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

task_record* create_task(const char* name, const u8* blob, u32 size) {
    if (size == 0 || size > 32 * 1024) { return nullptr; }
    task_record* task = prepare_task(name);
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

    task->state = task_state::fresh;
    format::text("[task] event=created pid=");
    format::decimal(task->pid);
    format::text(" name=");
    format::text(task->name);
    format::text("\r\n");
    return task;
}

task_record* create_supervisor() {
    using namespace user_images;
    task_record* task = prepare_task("supervisor");
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
    task->supervisor = true;
    task->state = task_state::fresh;
    format::text("[task] event=created pid="); format::decimal(task->pid);
    format::text(" name=supervisor bootstrap=trusted_segments\r\n");
    return task;
}

task_record* create_files_service() {
    using namespace user_images;
    task_record* task = prepare_task("files");
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

task_record* task_by_pid(u64 pid) {
    for (auto& task : tasks) {
        if (task.state != task_state::free && task.pid == pid) { return &task; }
    }
    return nullptr;
}

bool files_service_live() {
    task_record* service = task_by_pid(files_pid);
    return files_pid != 0 && service != nullptr && service->block_access &&
           service->state != task_state::building && service->state != task_state::dead;
}

i64 ipc_send(u64 handle, u64 address, u64 length) {
    endpoint_record* endpoint = endpoint_for(handle);
    if (endpoint == nullptr || current == nullptr || endpoint->sender_pid != current->pid ||
        (current->send_handle != handle &&
         !(current->block_access && endpoint->session_response))) {
        return sys_error_invalid_handle;
    }
    if (endpoint->receiver_pid == current->pid || length == 0 || length > endpoint->capacity) {
        return sys_error_invalid_argument;
    }
    task_record* receiver = task_by_pid(endpoint->receiver_pid);
    if (receiver == nullptr || receiver->state == task_state::dead ||
        receiver->state == task_state::building) { return sys_error_invalid_handle; }
    if (endpoint->pending) { return sys_error_full; }
    if (!user_range_ok(address, length, false)) { return sys_error_invalid_argument; }
    copy_from_user(endpoint->data, address, length);
    endpoint->length = static_cast<u32>(length);
    endpoint->pending = true;
    return 0;
}

i64 ipc_recv(u64 handle, u64 address, u64 length) {
    endpoint_record* endpoint = endpoint_for(handle);
    if (endpoint == nullptr || current == nullptr || endpoint->receiver_pid != current->pid ||
        (current->recv_handle != handle && !current->block_access)) {
        return sys_error_invalid_handle;
    }
    if (!user_range_ok(address, length, true)) { return sys_error_invalid_argument; }
    if (!endpoint->pending) { return sys_error_empty; }
    if (length < endpoint->length) { return sys_error_invalid_argument; }
    copy_to_user(address, endpoint->data, endpoint->length);
    const u32 length_received = endpoint->length;
    endpoint->pending = false;
    endpoint->length = 0;
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
    return amount;
}

i64 pipe_write_to(u32 pipe_index, u64 address, u64 length) {
    if (pipe_index >= process_max_pipes || !pipes[pipe_index].used) {
        return process_error_invalid;
    }
    if (length == 0) { return 0; }
    pipe_object& pipe = pipes[pipe_index];
    if (pipe.reader_references == 0) { return pipe_error_broken; }
    const u32 available = process_pipe_bytes - pipe.length;
    if (available == 0) { return process_error_would_block; }
    const u64 amount64 = length < available ? length : available;
    const u32 amount = static_cast<u32>(amount64);
    if (!user_range_ok(address, amount, false)) { return process_error_invalid; }
    const u32 tail = (pipe.head + pipe.length) % process_pipe_bytes;
    for (u32 i = 0; i < amount; ++i) {
        copy_from_user(&pipe.data[(tail + i) % process_pipe_bytes], address + i, 1);
    }
    pipe.length += amount;
    return amount;
}

i64 stdio_read(task_record* task, u32 fd, u64 address, u64 length,
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

i64 stdio_write(task_record* task, u32 fd, u64 address, u64 length) {
    if (fd >= 3 || task == nullptr || (task->stdio_mask & (1u << fd)) == 0 ||
        !task->stdio[fd].valid || !task->stdio[fd].writable) { return process_error_denied; }
    if (length == 0) { return 0; }
    const stdio_route& route = task->stdio[fd];
    if (!route.console) { return pipe_write_to(route.pipe_index, address, length); }
    if (length > 256 || !user_range_ok(address, length, false)) { return process_error_invalid; }
    u8 bytes[256];
    copy_from_user(bytes, address, length);
    return platform::debug_write_bytes(bytes, length);
}

void pipe_reference_close(task_record* task, pipe_reference* reference) {
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

u32 task_index(task_record* task) {
    return static_cast<u32>(task - tasks);
}

void mark_reap(task_record* task) {
    if (task != nullptr) { reap_pending[task_index(task)] = true; }
}

void destroy_task(task_record* task) {
    if (task == nullptr || task->state == task_state::free) { return; }
    reap_pending[task_index(task)] = false;
    const u64 pid = task->pid;
    for (auto& endpoint : endpoints) {
        if (endpoint.used && (endpoint.owner_pid == pid || endpoint.receiver_pid == pid ||
                              endpoint.sender_pid == pid)) {
            endpoint = endpoint_record{};
        }
    }
    task_pipe_release_all(task);
    u64 freed = 0;
    if (task->cr3 != 0) { freed += destroy_address_space(task->cr3); }
    if (task->kernel_stack_top != 0) {
        if (release_page(task->kernel_stack_top - kernel_stack_bytes) == memory_result::none) {
            ++freed;
        }
    }
    *task = task_record{};
    if (task_total > 0) { --task_total; }
    format::text("[task] event=reclaimed pid=");
    format::decimal(pid);
    format::text(" pages=");
    format::decimal(freed);
    format::text("\r\n");
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

void finish_task(task_record* task, process_outcome outcome, i64 code,
                  u64 vector = 0, u64 address = 0, u64 instruction = 0) {
    task->state = task_state::dead;
    task->exit_code = static_cast<i32>(code);
    if (task->completion_slot != 0) {
        auto& item = completions[task->completion_slot - 1];
        item.status = {1, outcome, task->pid, code, vector, address, instruction};
        item.ready = true;
        for (auto& parent : tasks) {
            if (parent.pid == task->parent && parent.state == task_state::waiting &&
                parent.waiting_pid == task->pid) { parent.state = task_state::ready; }
        }
    }
    // Builder authority is not inherited. Losing the builder cancels its children.
    for (auto& child : tasks) {
        if (child.state != task_state::free && child.parent == task->pid) {
            child.state = task_state::dead; mark_reap(&child);
        }
    }
    for (auto& item : completions) {
        if (item.used && item.parent == task->pid) { item = completion_record{}; }
    }
    mark_reap(task);
}

bool cancel_foreground() {
    if (platform::debug_peek() != 27) { return false; }
    for (auto& parent : tasks) {
        if (parent.state != task_state::waiting || !parent.supervisor) { continue; }
        for (auto& child : tasks) {
            if (child.pid == parent.waiting_pid && child.parent == parent.pid &&
                child.state != task_state::free && child.state != task_state::dead) {
                (void)platform::debug_read();
                finish_task(&child, process_outcome::killed, -27);
                format::text("[process] event=cancelled_by_escape pid="); format::decimal(child.pid);
                format::text("\r\n");
                return true;
            }
        }
    }
    return false;
}

void deliver_wait(task_record* task, interrupt_frame* frame) {
    if (task->waiting_pid == 0) { return; }
    completion_record* item = completion_for(task->pid, task->waiting_pid);
    if (item == nullptr || !item->ready) { return; }
    if (user_range_ok(task->wait_buffer, sizeof(process_status), true)) {
        copy_to_user(task->wait_buffer, &item->status, sizeof(process_status));
        *item = completion_record{};
        frame->rax = 0;
    } else { frame->rax = static_cast<u64>(process_error_invalid); }
    task->waiting_pid = 0;
}

task_record* pick_ready() {
    for (u32 i = 0; i < 8; ++i) {
        const u32 index = (cursor + i) % 8;
        task_record& task = tasks[index];
        if (task.state == task_state::ready || task.state == task_state::fresh) {
            cursor = (index + 1) % 8;
            return &task;
        }
    }
    return nullptr;
}

void set_thread_pointer(u64 pointer) {
    const u32 low = static_cast<u32>(pointer), high = static_cast<u32>(pointer >> 32);
    __asm__ volatile("wrmsr" : : "c"(0xc0000100u), "a"(low), "d"(high) : "memory");
}

void switch_to(task_record* task) {
    current = task;
    task->state = task_state::running;
    set_kernel_stack(task->kernel_stack_top);
    load_address_space(task->cr3);
    set_thread_pointer(task->thread_pointer);
}

interrupt_frame* make_initial_frame(task_record* task) {
    auto* frame = reinterpret_cast<interrupt_frame*>(
        task->kernel_stack_top - sizeof(interrupt_frame));
    *frame = interrupt_frame{};
    frame->rip = task->entry;
    frame->cs = user_code_selector;
    frame->rflags = 0x202; // reserved bit 1 + IF
    frame->rsp = task->initial_stack;
    frame->rdi = task->startup;
    frame->ss = user_data_selector;
    return frame;
}

interrupt_frame* schedule(interrupt_frame* frame) {
    reap_dead();
    if (current != nullptr) {
        if (current->state == task_state::running) {
            current->state = task_state::ready;
        }
        if (frame != nullptr && current->state != task_state::dead) {
            current->kernel_rsp = reinterpret_cast<u64>(frame);
        }
    }
    if (current != nullptr && current->state != task_state::dead) {
        fpu_save(current->fpu_state);
    }
    task_record* next = pick_ready();
    if (next == nullptr) {
        format::text("[sched] event=no_ready_tasks result=halt\r\n");
        halt();
    }
    interrupt_frame* next_frame = next->state == task_state::fresh
                                      ? make_initial_frame(next)
                                      : reinterpret_cast<interrupt_frame*>(next->kernel_rsp);
    switch_to(next);
    fpu_restore(next->fpu_state);
    deliver_wait(next, next_frame);
    return next_frame;
}

task_record* owned_process(u64 handle) {
    if (current == nullptr || (!current->supervisor && !current->spawn_access)) { return nullptr; }
    for (auto& task : tasks) {
        if (task.state != task_state::free && task.pid == handle && task.parent == current->pid) {
            return &task;
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

u64 page_align_up(u64 address) {
    return (address + page_size - 1) & ~(page_size - 1);
}

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

void* process_syscall(interrupt_frame* frame) {
    i64 result = process_error_invalid;
    const u64 first = frame->rdi, second = frame->rsi, third = frame->rdx;
    switch (frame->rax) {
    case sys_handle_write: {
        if (first > 2 || first == 0) { result = process_error_denied; break; }
        result = stdio_write(current, static_cast<u32>(first), second, third);
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
        if (!current->supervisor && !current->spawn_access) { result = process_error_denied; break; }
        if (first > 7 || (first & ~u64{current->stdio_mask}) != 0 || third > 11 ||
            (third != 0 && !user_range_ok(second, third, false))) { break; }
        if (!files_service_live()) { result = process_error_resources; break; }
        completion_record* slot = nullptr;
        for (auto& item : completions) { if (!item.used) { slot = &item; break; } }
        if (slot == nullptr) { result = process_error_resources; break; }
        char name[12] = "elf";
        if (third != 0) { copy_from_user(name, second, third); name[third] = '\0'; }
        task_record* task = prepare_task(name);
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
        result = static_cast<i64>(task->pid);
        break;
    }
    case sys_process_grant: {
        if (!current->supervisor) { result = process_error_denied; break; }
        if (second > 1) { break; }
        task_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        task->spawn_access = second != 0;
        result = 0;
        break;
    }
    case sys_process_tls: {
        task_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        if (second < process_tls_begin || second > process_tls_end - 16 || second % 16 != 0 ||
            !space_range_ok(task->cr3, second, 16, true)) { break; }
        task->thread_pointer = second;
        result = 0;
        break;
    }
    case sys_heap_break:
        result = set_heap_break(first);
        break;
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
        pipe_reference* reference = pipe_reference_for(current, first);
        if (reference == nullptr ||
            (frame->rax == sys_pipe_read && reference->writable) ||
            (frame->rax == sys_pipe_write && !reference->writable)) {
            result = process_error_denied; break;
        }
        result = frame->rax == sys_pipe_read
            ? pipe_read_from(reference->pipe_index, second, third)
            : pipe_write_to(reference->pipe_index, second, third);
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
        if (second >= 3) { break; }
        task_record* child = owned_process(first);
        if (child == nullptr) { result = process_error_denied; break; }
        if (child->state != task_state::building) { result = process_error_state; break; }
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
        const task_record& client = tasks[first];
        if (client.state != task_state::free && client.state != task_state::building &&
            client.state != task_state::dead &&
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
        task_record* task = owned_process(first);
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
        task_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        if (!user_range_ok(second, sizeof(process_entry), false)) { break; }
        process_entry entry{}; copy_from_user(&entry, second, sizeof(entry));
        u64 physical = 0; page_permissions permissions{};
        if (!space_range_ok(task->cr3, entry.entry, 1, false) ||
            query_page_in(task->cr3, entry.entry & ~(page_size - 1), &physical, &permissions) != memory_result::none ||
            !permissions.executable || permissions.writable || entry.stack % 16 != 0 ||
            entry.stack < process_stack_bottom + 16 || entry.stack > process_startup_begin ||
            !space_range_ok(task->cr3, entry.stack - 16, 16, true) ||
            entry.startup % alignof(startup_info) != 0 ||
            entry.startup < process_startup_begin ||
            entry.startup > process_stack_top - sizeof(startup_info) ||
            !space_range_ok(task->cr3, entry.startup, sizeof(startup_info), false)) { break; }
        task->entry = entry.entry; task->initial_stack = entry.stack; task->startup = entry.startup;
        task->state = task_state::fresh;
        format::text("[process] event=started pid="); format::decimal(task->pid);
        format::text(" parent="); format::decimal(task->parent); format::text("\r\n");
        format::text("[process] pid="); format::decimal(task->pid);
        format::text(" address_space="); format::hex(task->cr3); format::text("\r\n");
        result = 0;
        break;
    }
    case sys_process_abort: {
        task_record* task = owned_process(first);
        if (task == nullptr) { result = process_error_denied; break; }
        if (task->state != task_state::building) { result = process_error_state; break; }
        if (task->completion_slot != 0) { completions[task->completion_slot - 1] = completion_record{}; }
        destroy_task(task); result = 0;
        break;
    }
    case sys_process_wait: {
        if (!user_range_ok(second, sizeof(process_status), true)) { break; }
        completion_record* item = completion_for(current->pid, first);
        if (item == nullptr) { result = process_error_denied; break; }
        if (item->ready) {
            copy_to_user(second, &item->status, sizeof(process_status));
            *item = completion_record{}; result = 0;
        } else {
            task_record* child = owned_process(first);
            if (child == nullptr || child->state == task_state::building) { result = process_error_state; break; }
            current->waiting_pid = first; current->wait_buffer = second;
            current->state = task_state::waiting; frame->rax = 0;
            format::text("[process] event=wait_blocked parent="); format::decimal(current->pid);
            format::text(" child="); format::decimal(first); format::text("\r\n");
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

void* timer_entry(interrupt_frame* frame) {
    pic_eoi(0);
    ++tick_count;
    if (current != nullptr) { ++current->ticks; }
    (void)cancel_foreground();
    if ((frame->cs & 3) == 3) { return schedule(frame); }
    return frame;
}

void* syscall_entry(interrupt_frame* frame) {
    reap_dead();
    const u64 number = frame->rax;
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
        result = static_cast<i64>(tick_count);
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
            const task_record& task = tasks[i];
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
    case sys_kill: {
        if (current == nullptr || !current->supervisor) {
            result = sys_error_invalid_handle;
            break;
        }
        const u64 pid = frame->rdi;
        task_record* target = nullptr;
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
        format::text("[task] event=killed_by_supervisor pid=");
        format::decimal(pid);
        format::text("\r\n");
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
    format::text(" result=killed\r\n");
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
    task_record* receiver_task = create_task("receiver", receiver, receiver_size);
    if (receiver_task == nullptr) { return false; }
    const u32 handle = endpoint_attach(receiver_task->pid, 0, receiver_task->pid,
        default_message_bytes);
    if (handle != 1) { return false; }
    receiver_task->recv_handle = handle;
    task_record* sender_task = create_task("sender", sender, sender_size);
    if (sender_task == nullptr) { return false; }
    sender_task->send_handle = handle;
    endpoint_record* channel = endpoint_for(handle);
    if (channel == nullptr) { return false; }
    channel->sender_pid = sender_task->pid;
    if (create_task("probe", probe, probe_size) == nullptr) { return false; }
    if (create_task("quitter", quitter, quitter_size) == nullptr) { return false; }
    task_record* supervisor_task = create_supervisor();
    if (supervisor_task == nullptr) { return false; }
    supervisor_task->supervisor = true;
    task_record* files_task = create_files_service();
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
    pic_init();
    timer_init(100);
    task_record* first = pick_ready();
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
    const task_record& task = tasks[index];
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
