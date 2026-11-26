// SPDX-License-Identifier: Apache-2.0
#include "interpreter_entry.hpp"
#include <xos/fault_sha256.hpp>
#include <xos/vm.hpp>

using namespace xos;
using namespace xos::glibc_d1;

#include "interpreter_plan.hpp"

extern "C" [[noreturn]] void __real___xos_glibc_start(const startup_info*, void* stack_top);
extern "C" int check_on_entry_stack(void**, xos_d1_entry_view*);

asm(
    ".text\n"
    ".globl check_on_entry_stack\n"
    "check_on_entry_stack:\n"
    "  pushq %r12\n"
    "  movq %rsp, %r12\n"
    "  movq %rdi, %rsp\n"
    "  call __xos_rtld_check_entry\n"
    "  movq %r12, %rsp\n"
    "  popq %r12\n"
    "  ret\n");

namespace {
struct file_pin { xos_file_session* owner; u32 handle; };
xos_file_request request;
xos_file_response response;
interpreter_allocations images;
xos_d1_entry_view view;
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

bool native_entropy(u8* bytes, u32 size) {
    return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(bytes), size) == 0;
}
}

extern "C" [[noreturn]] void __wrap___xos_glibc_start(const startup_info* startup, void* stack_top) {
    if (reinterpret_cast<u64>(startup) != process_startup_begin || startup->version != 2) { fail("startup"); }
    const auto* extension = reinterpret_cast<const startup_extension*>(process_startup_begin + startup_extension_offset);
    if (extension->file_handles[0] == 0) { fail("inherited stdin"); }
    xos_file_session early{};
    operation(file::op::read, extension->file_handles[0], 4);
    if (__xos_file_session_call(&early, &request, &response) != 0 || response.length != 4
        || response.data[0] != 'A' || response.data[1] != 'B'
        || response.data[2] != 'C' || response.data[3] != 'D') { fail("first read"); }
    file_pin app{&early, 0}, interpreter{&early, 0};
    if (!pin_verified(app, "/tests/main.pie", main_bytes, main_digest)
        || !pin_verified(interpreter, "/tests/interpreter.so", interpreter_bytes, interpreter_digest)) {
        fail("verified pins");
    }
    const pinned_image main_source{main_image, main_bytes, positioned, &app, {main_span, main_span}};
    pinned_image interpreter_source{interpreter_image, interpreter_bytes, positioned, &interpreter, {1, 1}};
    // Sit below the test's active static startup stack, with room for the
    // actual checker call below the synthetic interpreter entry %rsp.
    auto* frame = reinterpret_cast<xos_d1_entry_handoff*>(process_stack_bottom + 16 * vm_page_size);
    *frame = {};
    const auto prepare = [&](main_headers headers) {
        return prepare_interpreter_entry(startup, main_source, headers, interpreter_source,
                                         execution_mode::ordinary, native_entropy, early, *frame, images);
    };
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
    if (!check_on_entry_stack(stack, &view) || view.argc != startup->argc
        || view.record->main_entry != main_image.bias + main_image.entry
        || view.record->interpreter_entry != interpreter_image.bias + interpreter_image.entry
        || view.record->main_phdr != main_image.bias + main_phdr.address
        || view.record->main_phnum != main_phdr.count) { fail("actual rtld target checker"); }
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
