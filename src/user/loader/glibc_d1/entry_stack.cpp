// SPDX-License-Identifier: Apache-2.0
#include "entry_stack.hpp"
#include <elf.h>
#include <xos/vm_abi.hpp>

// This standard auxv key is absent from the frozen newlib ELF header.
#ifndef AT_SECURE
# define AT_SECURE 23
#endif

namespace xos::glibc_d1 {
namespace {
constexpr u32 max_headers = 64;

bool contains(u64 begin, u64 end, u64 address, u64 bytes) {
    return address >= begin && address <= end && bytes <= end - address;
}

bool startup_string(u64 address, bool environment) {
    if (!contains(process_startup_begin, process_stack_top, address, 1)) { return false; }
    const auto* string = reinterpret_cast<const char*>(address);
    for (u64 length = 0; length < process_max_exec_arg_bytes && length < process_stack_top - address; ++length) {
        if (string[length] != '\0') { continue; }
        if (!environment) { return true; }
        if (length >= 3 && string[0] == 'L' && string[1] == 'D' && string[2] == '_') { return false; }
        constexpr char tunables[] = "GLIBC_TUNABLES";
        constexpr u64 name_length = sizeof(tunables) - 1;
        if (length < name_length || (length != name_length && string[name_length] != '=')) { return true; }
        for (u64 i = 0; i < name_length; ++i) {
            if (string[i] != tunables[i]) { return true; }
        }
        return false;
    }
    return false;
}

bool startup_vector(u64 address, u32 count, bool environment) {
    if ((address & 7) != 0 ||
        !contains(process_startup_begin, process_stack_top, address, (u64{count} + 1) * sizeof(u64))) {
        return false;
    }
    const auto* vector = reinterpret_cast<const u64*>(address);
    for (u32 i = 0; i < count; ++i) {
        if (!startup_string(vector[i], environment)) { return false; }
    }
    return vector[count] == 0;
}

struct mapped_bounds { u64 begin, end; };

bool image_bounds(const mapped_image& image, mapped_bounds& bounds) {
    if (image.bias < vm_arena_begin || image.bias >= vm_arena_end || image.bias % vm_page_size != 0 ||
        image.loads == nullptr || image.load_count == 0 || image.load_count > mapped_image_max_loads) { return false; }
    bounds = {vm_arena_end, vm_arena_begin};
    bool entry = false;
    for (u32 i = 0; i < image.load_count; ++i) {
        const auto& load = image.loads[i];
        if (load.address >= vm_arena_end - image.bias || load.memory_bytes == 0 ||
            load.file_bytes > load.memory_bytes || load.memory_bytes > vm_arena_end - image.bias - load.address) {
            return false;
        }
        const u64 begin = (image.bias + load.address) & ~(vm_page_size - 1);
        const u64 end = (image.bias + load.address + load.memory_bytes + vm_page_size - 1) & ~(vm_page_size - 1);
        if (begin < bounds.begin) { bounds.begin = begin; }
        if (end > bounds.end) { bounds.end = end; }
        if (load.permissions == (map_read | map_execute) &&
            contains(load.address, load.address + load.file_bytes, image.entry, 1)) { entry = true; }
    }
    return entry;
}


}

bool build_entry_stack(const startup_info* startup, const mapped_image& main,
                       main_headers headers, const mapped_image& interpreter,
                       execution_mode mode, entropy_source entropy, entry_stack& output) {
    if (reinterpret_cast<u64>(startup) != process_startup_begin ||
        !contains(process_stack_bottom, process_startup_begin, reinterpret_cast<u64>(&output), sizeof(output)) ||
        startup->magic != startup_magic || startup->size != sizeof(*startup) ||
        startup->version < 1 || startup->version > 3 || startup->argc == 0 || startup->argc > process_max_args ||
        startup->reserved != (startup->version == 1 ? 0 : startup_extension_offset) ||
        !startup_vector(startup->argv, startup->argc, false)) { return false; }

    u32 envc = 0;
    const u64* envp = nullptr;
    if (startup->version >= 2) {
        const auto* extension = reinterpret_cast<const startup_extension*>(process_startup_begin + startup_extension_offset);
        if (extension->magic != startup_extension_magic || extension->environment_count > startup_environment_max ||
            !startup_vector(extension->environment, extension->environment_count, true)) { return false; }
        envc = extension->environment_count;
        envp = reinterpret_cast<const u64*>(extension->environment);
    }

    mapped_bounds main_bounds, interpreter_bounds;
    u8 random[sizeof(output.random)];
    if (!image_bounds(main, main_bounds) || !image_bounds(interpreter, interpreter_bounds) ||
        (main_bounds.begin < interpreter_bounds.end && interpreter_bounds.begin < main_bounds.end) ||
        headers.count == 0 || headers.count > max_headers || headers.address % alignof(Elf64_Phdr) != 0 ||
        headers.file_offset < sizeof(Elf64_Ehdr) ||
        mapped_file_address(main, headers.file_offset, headers.address, u64{headers.count} * sizeof(Elf64_Phdr)) == nullptr ||
        mapped_file_address(interpreter, 0, 0, sizeof(Elf64_Ehdr)) == nullptr ||
        (mode != execution_mode::ordinary && mode != execution_mode::secure) || entropy == nullptr) { return false; }

    const bool entropy_ready = entropy(random, sizeof(random));
    if (entropy_ready) {
        for (u32 i = 0; i < sizeof(random); ++i) { output.random[i] = random[i]; }
    }
    auto* scratch = static_cast<volatile u8*>(random);
    for (u32 i = 0; i < sizeof(random); ++i) { scratch[i] = 0; }
    if (!entropy_ready) { return false; }

    auto* word = output.words;
    const auto* argv = reinterpret_cast<const u64*>(startup->argv);
    *word++ = startup->argc;
    for (u32 i = 0; i < startup->argc; ++i) { *word++ = argv[i]; }
    *word++ = 0;
    for (u32 i = 0; i < envc; ++i) { *word++ = envp[i]; }
    *word++ = 0;
    const u64 auxv[] = {AT_PHDR, main.bias + headers.address, AT_PHNUM, headers.count, AT_PHENT, sizeof(Elf64_Phdr),
                        AT_ENTRY, main.bias + main.entry, AT_BASE, interpreter.bias, AT_PAGESZ, vm_page_size,
                        AT_SECURE, mode == execution_mode::secure, AT_RANDOM, reinterpret_cast<u64>(output.random),
                        AT_NULL, 0};
    for (const u64 value : auxv) { *word++ = value; }
    return true;
}
}
