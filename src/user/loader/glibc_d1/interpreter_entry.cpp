// SPDX-License-Identifier: Apache-2.0
#include "interpreter_entry.hpp"
#include <elf.h>
#include <xos/vm.hpp>

namespace xos::glibc_d1 {
namespace {
static_assert(process_stack_bottom == XOS_D1_STACK_BOTTOM);
static_assert(process_startup_begin == XOS_D1_STARTUP_BEGIN);
static_assert(process_stack_top == XOS_D1_STACK_TOP);
static_assert(XOS_D1_STACK_GROWTH_BYTES * 2 == process_startup_begin - process_stack_bottom);
static_assert(XOS_D1_STACK_ENTRY_MIN + sizeof(xos_d1_entry_handoff) <= process_startup_begin);

const Elf64_Ehdr* linked_header(const mapped_image& image) {
    const auto* header = static_cast<const Elf64_Ehdr*>(mapped_file_address(image, 0, 0, sizeof(Elf64_Ehdr)));
    if (header == nullptr || header->e_ident[0] != ELFMAG0 || header->e_ident[1] != ELFMAG1
        || header->e_ident[2] != ELFMAG2 || header->e_ident[3] != ELFMAG3
        || header->e_ident[EI_CLASS] != ELFCLASS64 || header->e_ident[EI_DATA] != ELFDATA2LSB
        || header->e_ident[EI_VERSION] != EV_CURRENT || header->e_version != EV_CURRENT
        || header->e_type != ET_DYN || header->e_machine != EM_X86_64
        || header->e_ehsize != sizeof(*header) || header->e_phentsize != sizeof(Elf64_Phdr)
        || header->e_entry != image.entry) { return nullptr; }
    return header;
}

bool linked_main_table(const mapped_image& image, main_headers headers) {
    const auto* header = linked_header(image);
    if (header == nullptr || header->e_phoff != headers.file_offset || header->e_phnum != headers.count
        || headers.count == 0 || headers.count > 64 || headers.address % alignof(Elf64_Phdr) != 0) { return false; }
    const u64 bytes = u64{headers.count} * sizeof(Elf64_Phdr);
    const auto* table = static_cast<const Elf64_Phdr*>(mapped_file_address(image, headers.file_offset, headers.address, bytes));
    if (table == nullptr) { return false; }
    bool found = false;
    for (u32 index = 0; index < headers.count; ++index) {
        const auto& item = table[index];
        if (item.p_type == PT_LOAD || item.p_type == PT_INTERP || item.p_type == PT_DYNAMIC) {
            if (!found) { return false; }
        } else if (item.p_type == PT_PHDR) {
            if (found || item.p_offset != headers.file_offset || item.p_vaddr != headers.address
                || item.p_filesz != bytes || item.p_memsz != bytes) { return false; }
            found = true;
        }
    }
    return found;
}

void copy_pin_plan(xos_rtld_pin_plan& output, const xos_rtld_pin_plan* source) {
    output.reserved = 0;
    output.deadline_ns = source == nullptr ? 0 : source->deadline_ns;
    output.count = source == nullptr ? 0 : source->count;
    output.online_version = source == nullptr ? 0 : source->online_version;
    output.online_mask = source == nullptr ? 0 : source->online_mask;
    output.isolated_mask = source == nullptr ? 0 : source->isolated_mask;
    output.online_reserved = 0;
    if (source == nullptr) { return; }
    // No libc memory implementation is available before the interpreter's
    // CPU and runtime initialization. Copy only the verified live entries.
    auto* destination = reinterpret_cast<volatile u8*>(output.pins);
    const auto* input = reinterpret_cast<const u8*>(source->pins);
    const usize bytes = output.count * sizeof(xos_rtld_pin);
    for (usize i = 0; i < bytes; ++i) { destination[i] = input[i]; }
}

interpreter_entry_result abandon(interpreter_entry_error error, interpreter_allocations& scratch,
                                 const image_map_result& mapped = {}) {
    const i64 heap_error = release_image(scratch.early_heap);
    const i64 interpreter_error = release_image(scratch.interpreter);
    const i64 main_error = release_image(scratch.main);
    const i64 image_error = interpreter_error != 0 ? interpreter_error : main_error;
    return {error, mapped, heap_error != 0 ? heap_error : image_error};
}
}

interpreter_entry_result prepare_interpreter_entry(
    const startup_info* startup, const pinned_image& main, main_headers headers,
    const pinned_image& interpreter, execution_mode mode, entropy_source entropy,
    xos_file_session& early_files, xos_d1_entry_handoff& frame,
    interpreter_allocations& allocations, const xos_rtld_pin_plan* dependencies,
    const xos_rtld_heap_plan* early_heap) {
    const auto stack_address = reinterpret_cast<u64>(&frame);
    if (stack_address < XOS_D1_STACK_ENTRY_MIN || stack_address > process_startup_begin - sizeof(frame)
        || (stack_address & 15) != 0 || frame.record.magic != 0
        || allocations.main.start != 0 || allocations.main.bytes != 0
        || allocations.interpreter.start != 0 || allocations.interpreter.bytes != 0
        || allocations.early_heap.start != 0 || allocations.early_heap.bytes != 0
        || !xos_rtld_heap_plan_valid(early_heap)
        || (dependencies != nullptr && !xos_rtld_valid_pin_plan(dependencies))
        || &early_files == &frame.record.files || early_files.phase != xos_file_session_active) {
        return {interpreter_entry_error::layout, {}, 0};
    }
    interpreter_allocations scratch{};
    auto mapped = map_verified_image(main.image, main.file_size, main.read, main.context, main.budget, scratch.main);
    if (mapped.error != image_map_error::none) { return abandon(interpreter_entry_error::main_map, scratch, mapped); }
    mapped = map_verified_image(interpreter.image, interpreter.file_size, interpreter.read,
                                interpreter.context, interpreter.budget, scratch.interpreter);
    if (mapped.error != image_map_error::none) {
        return abandon(interpreter_entry_error::interpreter_map, scratch, mapped);
    }
    if (!linked_main_table(main.image, headers) || linked_header(interpreter.image) == nullptr) {
        return abandon(interpreter_entry_error::elf_headers, scratch);
    }
    if (!build_entry_stack(startup, main.image, headers, interpreter.image, mode, entropy, frame.stack)) {
        return abandon(interpreter_entry_error::stack, scratch);
    }
    const i64 reserved = sdk::vm_reserve(early_heap->base, early_heap->bytes, vm_page_size, true);
    if (reserved >= 0) { scratch.early_heap = {static_cast<u64>(reserved), early_heap->bytes}; }
    if (reserved != static_cast<i64>(early_heap->base)) {
        return abandon(interpreter_entry_error::heap, scratch,
                       {image_map_error::reserve, reserved < 0 ? reserved : vm_error_address, 0});
    }
    if (__xos_file_session_take(&frame.record.files, &early_files) != 0) {
        return abandon(interpreter_entry_error::files, scratch);
    }
    copy_pin_plan(frame.record.dependencies, dependencies);
    frame.record.heap = *early_heap;
    frame.record.version = XOS_D1_ENTRY_VERSION;
    frame.record.size = sizeof(frame.record);
    frame.record.main_phdr = main.image.bias + headers.address;
    frame.record.main_phnum = headers.count;
    frame.record.main_entry = main.image.bias + main.image.entry;
    frame.record.interpreter_base = interpreter.image.bias;
    frame.record.interpreter_entry = interpreter.image.bias + interpreter.image.entry;
    allocations = scratch;
    frame.record.magic = XOS_D1_ENTRY_MAGIC;
    return {};
}
}
