// SPDX-License-Identifier: Apache-2.0
#include "interpreter_entry.hpp"
#include "xos_rtld_mapping.h"
#include <errno.h>
#include <xos/fault_sha256.hpp>
#include <xos/vm.hpp>

using namespace xos;
using namespace xos::glibc_d1;

#include "interpreter_plan.hpp"

extern "C" [[noreturn]] void __real___xos_glibc_start(const startup_info*, void* stack_top);
extern "C" int attach_on_entry_stack(void**, xos_rtld_images*, xos_d1_entry_view*);

asm(
    ".text\n"
    ".globl attach_on_entry_stack\n"
    "attach_on_entry_stack:\n"
    "  pushq %r12\n"
    "  movq %rsp, %r12\n"
    "  movq %rdi, %rsp\n"
    "  call __xos_rtld_attach_entry_images\n"
    "  movq %r12, %rsp\n"
    "  popq %r12\n"
    "  ret\n");

namespace {
struct file_pin { xos_file_session* owner; u32 handle; u32 inode = 0; };
xos_file_request request;
xos_file_response response;
interpreter_allocations images;
xos_d1_entry_view view;
xos_rtld_images bound_images;
u32 early_sequence;

[[noreturn]] void fail(const char* problem) {
    sdk::print("D1_INTERPRETER_ENTRY_FAIL ");
    sdk::print(problem);
    sdk::print("\n");
    sdk::exit(31);
}

void operation(file::op code, u32 handle = 0, u32 bytes = 0, u64 offset = 0) {
    request.operation = static_cast<xos_file_u16>(code);
    request.handle = handle;
    request.flags = 0;
    request.length = bytes;
    request.offset = offset;
    request.name_length = 0;
}

bool positioned(void* context, u64 offset, u8* output, u32 size) {
    auto& source = *static_cast<file_pin*>(context);
    for (u32 done = 0; done < size;) {
        const u32 pending = size - done;
        const u32 amount = pending < sizeof(response.data) ? pending : sizeof(response.data);
        operation(file::op::read_at, source.handle, amount, offset + done);
        if (__xos_file_session_call(source.owner, &request, &response) != 0 || response.length == 0) {
            return false;
        }
        for (u32 i = 0; i < response.length; ++i) { output[done + i] = response.data[i]; }
        done += response.length;
    }
    return true;
}

bool pin_verified(file_pin& source, const char* path, u32 size, const u8 (&wanted)[32]) {
    operation(file::op::open);
    request.flags = file::read_only | file::open_pin;
    while (path[request.name_length] != 0 && request.name_length + 1 < sizeof(request.name)) {
        request.name[request.name_length] = path[request.name_length];
        ++request.name_length;
    }
    request.name[request.name_length] = 0;
    if (__xos_file_session_call(source.owner, &request, &response) != 0 || response.value != size) {
        return false;
    }
    source.handle = response.handle;
    source.inode = response.reserved;
    sha256 hash;
    u8 buffer[1024];
    for (u32 at = 0; at < size;) {
        const u32 amount = size - at < sizeof(buffer) ? size - at : sizeof(buffer);
        if (!positioned(&source, at, buffer, amount)) { return false; }
        hash.update(buffer, amount);
        at += amount;
    }
    u8 digest[32];
    hash.finish(digest);
    for (u32 i = 0; i < sizeof(digest); ++i) { if (digest[i] != wanted[i]) { return false; } }
    return true;
}

bool close_pin(file_pin& source) {
    operation(file::op::close, source.handle);
    return __xos_file_session_call(source.owner, &request, &response) == 0;
}

bool compare_phdr(void* source, unsigned int index, const Elf64_Phdr* pinned) {
    const auto* from = reinterpret_cast<const u8*>(static_cast<const Elf64_Phdr*>(source) + index);
    const auto* to = reinterpret_cast<const u8*>(pinned);
    for (u32 i = 0; i < sizeof(*pinned); ++i) {
        if (from[i] != to[i]) { return false; }
    }
    return true;
}

void prepare_dependency() {
    const int fd = __xos_rtld_open_pin("libhandoff.so");
    Elf64_Ehdr ehdr;
    Elf64_Phdr phdrs[64];
    if (fd != 71 || __xos_rtld_read_pin(fd, &ehdr, sizeof(ehdr)) != static_cast<long>(sizeof(ehdr))
        || ehdr.e_phnum == 0 || ehdr.e_phnum > 64) { fail("rtld closure open and ELF read"); }
    const u32 table_bytes = ehdr.e_phnum * sizeof(Elf64_Phdr);
    if (__xos_rtld_pread_pin(fd, phdrs, table_bytes, ehdr.e_phoff) != table_bytes
        || __xos_rtld_stat_pin(fd) != 0) { fail("rtld closure PHDR and identity"); }
    xos_rtld_mapped mapped{};
    if (__xos_rtld_map_fd(fd, &ehdr, 0, compare_phdr, phdrs, &mapped) != 0
        || mapped.bias != dependency_image.bias || mapped.allocation.bytes != dependency_span) {
        fail("rtld closure map");
    }
    __xos_rtld_release_image(&mapped.allocation);
    if (__xos_rtld_close_pin(fd) != 0 || __xos_rtld_finish_images(&bound_images) != 0) {
        fail("rtld closure release");
    }
    sdk::print("D1_RTLD_ENTRY_CLOSURE_OK soname=libhandoff.so\n");
}

bool native_entropy(u8* bytes, u32 size) {
    return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(bytes), size) == 0;
}
}

extern "C" [[noreturn]] void __wrap___xos_glibc_start(const startup_info* startup, void* stack_top) {
    if (reinterpret_cast<u64>(startup) != process_startup_begin || startup->version != 2) { fail("startup"); }
    const bool empty = startup->argc == 2;
    const auto* extension = reinterpret_cast<const startup_extension*>(process_startup_begin + startup_extension_offset);
    if (extension->file_handles[0] == 0) { fail("inherited stdin"); }
    xos_file_session early{};
    operation(file::op::read, extension->file_handles[0], 4);
    if (__xos_file_session_call(&early, &request, &response) != 0 || response.length != 4
        || response.data[0] != 'A' || response.data[1] != 'B'
        || response.data[2] != 'C' || response.data[3] != 'D') { fail("first read"); }
    file_pin app{&early, 0}, interpreter{&early, 0}, dependency{&early, 0};
    if (!pin_verified(app, "/tests/main.pie", main_bytes, main_digest)
        || !pin_verified(interpreter, "/tests/interpreter.so", interpreter_bytes, interpreter_digest)
        || (!empty && !pin_verified(dependency, "/tests/dependency.so", dependency_bytes, dependency_digest))) {
        fail("verified pins");
    }
    const pinned_image main_source{main_image, main_bytes, positioned, &app, {main_span, main_span}};
    pinned_image interpreter_source{interpreter_image, interpreter_bytes, positioned, &interpreter, {1, 1}};
    const long now = sdk::syscall(46);
    if (now < 0) { fail("rtld closure clock"); }
    xos_rtld_pin_plan plan{};
    plan.deadline_ns = static_cast<u64>(now) + 30000000000ULL;
    plan.count = 1;
    plan.pins[0] = {71, dependency.handle, dependency.inode, dependency_bytes, dependency_image.bias,
                    dependency_span, dependency_span, "libhandoff.so"};
    const auto stage = [&](xos_d1_entry_handoff& frame, main_headers headers,
                           const xos_rtld_pin_plan* dependencies) {
        return prepare_interpreter_entry(startup, main_source, headers, interpreter_source,
                                         execution_mode::ordinary, native_entropy, early, frame, images, dependencies);
    };
    const u32 prior_sequence = early.request_sequence;
    const u64 too_low_addresses[] = {process_stack_bottom, XOS_D1_STACK_ENTRY_MIN - 16};
    for (const u64 address : too_low_addresses) {
        auto* too_low = reinterpret_cast<xos_d1_entry_handoff*>(address);
        *too_low = {};
        const auto rejected = stage(*too_low, main_phdr, empty ? nullptr : &plan);
        if (rejected.error != interpreter_entry_error::layout || rejected.release_error != 0
            || images.main.bytes != 0 || images.interpreter.bytes != 0 || too_low->record.magic != 0
            || early.phase != xos_file_session_active || early.request_sequence != prior_sequence) {
            fail("entry stack growth");
        }
    }
    sdk::print("D1_INTERPRETER_STACK low=rejected below_min=rejected\n");

    // Exercise the first allowed stack address with an actual checker call.
    auto* frame = reinterpret_cast<xos_d1_entry_handoff*>(XOS_D1_STACK_ENTRY_MIN);
    *frame = {};
    const auto prepare = [&](main_headers headers) { return stage(*frame, headers, empty ? nullptr : &plan); };
    if (empty) {
        plan.count = 0;
        const auto rejected = stage(*frame, main_phdr, &plan);
        if (rejected.error != interpreter_entry_error::layout || images.main.bytes != 0
            || images.interpreter.bytes != 0 || early.request_sequence != prior_sequence) {
            fail("empty closure with a nonzero deadline");
        }
    }
    auto result = prepare(main_phdr);
    if (result.error != interpreter_entry_error::interpreter_map || result.mapping.error != image_map_error::budget
        || result.release_error != 0 || images.main.bytes != 0 || images.interpreter.bytes != 0
        || frame->record.magic != 0 || early.phase != xos_file_session_active) { fail("second map rollback"); }
    interpreter_source.budget = {interpreter_span, interpreter_span};
    auto wrong_table = main_phdr;
    --wrong_table.count;
    result = prepare(wrong_table);
    if (result.error != interpreter_entry_error::elf_headers || result.release_error != 0
        || images.main.bytes != 0 || images.interpreter.bytes != 0
        || frame->record.magic != 0 || early.phase != xos_file_session_active) { fail("ELF metadata rollback"); }

    result = prepare(main_phdr);
    if (result.error != interpreter_entry_error::none || early.phase != xos_file_session_transferred
        || frame->record.files.request_sequence != early.request_sequence) { fail("prepare"); }
    app.owner = &frame->record.files;
    interpreter.owner = &frame->record.files;
    if (!close_pin(interpreter) || !close_pin(app)) { fail("close private pins"); }
    auto** stack = reinterpret_cast<void**>(frame->stack.words);
    if (attach_on_entry_stack(stack, &bound_images, &view) != 0 || view.argc != startup->argc
        || view.record->main_entry != main_image.bias + main_image.entry
        || view.record->interpreter_entry != interpreter_image.bias + interpreter_image.entry
        || view.record->main_phdr != main_image.bias + main_phdr.address
        || view.record->main_phnum != main_phdr.count) { fail("actual rtld target checker"); }
    if (empty) {
        const u32 sequence = view.record->files.request_sequence;
        if (view.record->dependencies.count != 0 || view.record->dependencies.deadline_ns != 0
            || __xos_rtld_open_pin("libhandoff.so") != -ENOENT || __xos_rtld_finish_images(&bound_images) != 0
            || view.record->files.request_sequence != sequence) { fail("empty closure attachment"); }
        sdk::print("D1_RTLD_ENTRY_EMPTY_OK no_requests\n");
    } else {
        prepare_dependency();
    }
    early_sequence = view.record->files.request_sequence;
    if (__xos_file_adopt_early_session(&view.record->files) != 0
        || view.record->files.phase != xos_file_session_transferred) { fail("G3 ownership"); }
    __real___xos_glibc_start(startup, stack_top);
}

extern "C" const xos_d1_entry_view* d1_entry_view() { return &view; }
extern "C" u32 d1_entry_sequence() { return early_sequence; }
extern "C" int d1_release_images() {
    const i64 interpreter = release_image(images.interpreter);
    return release_image(images.main) == 0 && interpreter == 0;
}
