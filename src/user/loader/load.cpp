#include <xos/elf.hpp>
#include <xos/sdk.hpp>

namespace xos::sdk {
namespace {
u8 image_buffer[131072];
}
i64 spawn_buffer(const char* name, const u8* bytes, u64 size, u32 argc,
                 const char* const* argv) {
    if (argc == 0 || argc > process_max_args || argv == nullptr || bytes == nullptr ||
        size == 0 || size > sizeof(image_buffer)) { return process_error_invalid; }
    elf::load_plan plan{};
    const auto inspected = elf::inspect(bytes, size, target_elf_machine(), plan);
    if (inspected != elf::error::none) {
        print("elf: rejected reason="); print(elf::error_name(inspected)); print("\n");
        return process_error_invalid;
    }
    // Prepare arguments before creating any kernel resources.
    alignas(16) u8 page[4096]{};
    auto* startup = reinterpret_cast<startup_info*>(page);
    const u64 startup_address = process_stack_top - 4096;
    *startup = {startup_magic, 1, sizeof(startup_info), argc, 3, startup_address + 64,
                {0, 1, 2}, 0};
    auto* arguments = reinterpret_cast<u64*>(page + 64);
    usize position = 160;
    for (u32 i = 0; i < argc; ++i) {
        if (argv[i] == nullptr) { return process_error_invalid; }
        usize n = 0;
        while (n < 64 && argv[i][n] != '\0') { ++n; }
        if (n == 64 || position + n + 1 > sizeof(page)) { return process_error_invalid; }
        arguments[i] = startup_address + position;
        for (usize j = 0; j <= n; ++j) { page[position++] = static_cast<u8>(argv[i][j]); }
    }
    arguments[argc] = 0;
    const u64 name_length = length(name) > 11 ? 11 : length(name);
    const i64 child = syscall(sys_process_create, 7, reinterpret_cast<u64>(name),
                              name_length); // inherited console refs 0/1/2
    if (child < 0) { return child; }
    process_page mapping{startup_address, reinterpret_cast<u64>(page), 4096, map_read | map_write};
    i64 result = syscall(sys_process_map, static_cast<u64>(child), reinterpret_cast<u64>(&mapping));
    // Once arguments are copied, this scratch page can be reused for segment contents.
    for (u32 i = 0; result >= 0 && i < plan.count; ++i) {
        const auto& segment = plan.segments[i];
        const u64 first = segment.address & ~u64{4095};
        const u64 end = (segment.address + segment.memory_bytes + 4095) & ~u64{4095};
        for (u64 address = first; address < end; address += 4096) {
            for (usize byte = 0; byte < sizeof(page); ++byte) { page[byte] = 0; }
            u64 start = address > segment.address ? address : segment.address;
            u64 file_end = segment.address + segment.file_bytes;
            if (file_end > address + 4096) { file_end = address + 4096; }
            for (u64 at = start; at < file_end; ++at) {
                page[at - address] = bytes[segment.offset + at - segment.address];
            }
            mapping = {address, reinterpret_cast<u64>(page), 4096, segment.permissions};
            result = syscall(sys_process_map, static_cast<u64>(child), reinterpret_cast<u64>(&mapping));
            if (result < 0) { break; }
        }
    }
    for (u64 address = process_stack_bottom; result >= 0 && address < startup_address; address += 4096) {
        mapping = {address, 0, 0, map_read | map_write};
        result = syscall(sys_process_map, static_cast<u64>(child), reinterpret_cast<u64>(&mapping));
    }
    if (result >= 0) {
        process_entry entry{plan.entry, startup_address - 16, startup_address};
        result = syscall(sys_process_start, static_cast<u64>(child), reinterpret_cast<u64>(&entry));
    }
    if (result < 0) {
        (void)syscall(sys_process_abort, static_cast<u64>(child));
        return result;
    }
    return child;
}

i64 spawn(u32 image, u32 argc, const char* const* argv) {
    if (argc == 0 || argc > process_max_args || argv == nullptr) { return process_error_invalid; }
    image_info image_metadata{};
    i64 result = syscall(sys_image_info, image, reinterpret_cast<u64>(&image_metadata));
    if (result < 0) { return result; }
    if (image_metadata.size > sizeof(image_buffer)) { return process_error_resources; }
    image_read_request read_request{0, reinterpret_cast<u64>(image_buffer), image_metadata.size};
    result = syscall(sys_image_read, image, reinterpret_cast<u64>(&read_request));
    if (result != static_cast<i64>(image_metadata.size)) { return result < 0 ? result : process_error_invalid; }
    // The image is copied into this buffer before inspection; spawn_buffer never
    // re-reads the source, so file-backed callers get one consistent snapshot.
    return spawn_buffer(image_metadata.name, image_buffer, image_metadata.size, argc, argv);
}
}
