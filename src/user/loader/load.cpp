// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/elf.hpp>
#include <xos/tls.hpp>
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include <xos/execution.hpp>
#include <xos/thread_abi.hpp>

namespace xos::sdk {
namespace {
// The supervisor is single threaded. Keep large working objects out of its
// roughly 12 KiB user stack; only one spawn operation can use them at a time.
u8 image_buffer[131072];
alignas(16) u8 startup_page[startup_page_count * 4096];
alignas(16) u8 page_buffer[4096];
file::Client file_client;
bool file_client_ready;

bool buffer_read(void* context, u64 offset, u8* destination, u32 length) {
    const auto* bytes = static_cast<const u8*>(context);
    if (bytes == nullptr) { return false; }
    for (u32 i = 0; i < length; ++i) { destination[i] = bytes[offset + i]; }
    return true;
}

struct opened_file { file::Client* client; u32 handle; };
bool file_read(void* context, u64 offset, u8* destination, u32 length) {
    auto& source = *static_cast<opened_file*>(context);
    if (offset > 0xffffffffu || source.client->seek(source.handle, static_cast<u32>(offset)) < 0) {
        return false;
    }
    u32 done = 0;
    while (done < length) {
        const u32 remaining = length - done;
        const u32 request_size = remaining > file::response_data_size
            ? file::response_data_size : remaining;
        const i64 got = source.client->read(source.handle, destination + done, request_size);
        if (got <= 0 || static_cast<u64>(got) > request_size) { return false; }
        done += static_cast<u32>(got);
    }
    return true;
}

// Only a CRT declaring the read-only .xos.exec opt-in can restore v3 FDs.
// Ordinary spawn stays compatible with existing static v1/v2 applications.
bool exec_abi_supported(elf::read_exact_fn read, void* context, u64 size,
                        const elf::load_plan& plan) {
    u8 header[64], section[64], strings[64], name[10], record[16];
    auto value = [](const u8* bytes, u32 count) {
        u64 result = 0;
        for (u32 i = 0; i < count; ++i) result |= u64{bytes[i]} << (i * 8);
        return result;
    };
    auto range = [size](u64 offset, u64 length) { return offset <= size && length <= size-offset; };
    if (!read(context,0,header,sizeof(header))) return false;
    const u64 offset=value(header+40,8), count=value(header+60,2), names=value(header+62,2);
    if (value(header+58,2)!=64 || !count || count>4096 || names>=count ||
        !range(offset,count*64) || !read(context,offset+names*64,strings,64)) return false;
    const u64 string_offset=value(strings+24,8), string_size=value(strings+32,8);
    if (!range(string_offset,string_size)) return false;
    for (u64 i=0;i<count;++i) {
        if (!read(context,offset+i*64,section,64)) return false;
        const u64 label=value(section,4);
        if (label>string_size || 10>string_size-label || !read(context,string_offset+label,name,10)) continue;
        const char expected[]=".xos.exec"; bool matches=true;
        for (u32 j=0;j<10;++j) matches=matches && name[j]==static_cast<u8>(expected[j]);
        if (!matches) continue;
        const u64 flags=value(section+8,8), address=value(section+16,8);
        const u64 file=value(section+24,8), bytes=value(section+32,8);
        if (value(section+4,4)!=1 || !(flags&2) || (flags&1) || bytes!=16 ||
            !range(file,bytes) || !read(context,file,record,16) || value(record,8)!=exec_image_abi_magic ||
            value(record+8,4)!=3 || value(record+12,4)!=16) return false;
        for (u32 j=0;j<plan.count;++j) {
            const auto& segment=plan.segments[j];
            if (!(segment.permissions&map_write) && file>=segment.offset &&
                file-segment.offset<=segment.file_bytes && bytes<=segment.file_bytes-(file-segment.offset) &&
                address==segment.address+(file-segment.offset)) return true;
        }
        return false;
    }
    return false;
}

i64 spawn_reader(const char* name, u64 size, elf::read_exact_fn read_exact,
                 void* read_context, u32 argc, const char* const* argv,
                 bool close_file, u32 file_handle, const spawn_options* options = nullptr,
                 execution::launch_diagnostic* diagnostic = nullptr) {
    if (diagnostic != nullptr) { *diagnostic = {execution::launch_stage::none, 0, elf::error::none}; }
    if (argc == 0 || argc > process_max_args || argv == nullptr || size == 0 ||
        read_exact == nullptr || name == nullptr) {
        if (diagnostic != nullptr) { *diagnostic = {execution::launch_stage::prepare, process_error_invalid, elf::error::none}; }
        if (close_file) { (void)file_client.close(file_handle); }
        return process_error_invalid;
    }
    elf::load_plan plan{};
    const auto inspected = elf::inspect_reader(read_exact, read_context, size,
                                                target_elf_machine(), plan);
    if (inspected != elf::error::none) {
        if (diagnostic != nullptr) { *diagnostic = {execution::launch_stage::inspect, process_error_invalid, inspected}; }
        else { print("elf: rejected reason="); print(elf::error_name(inspected)); print("\n"); }
        if (close_file) { (void)file_client.close(file_handle); }
        return process_error_invalid;
    }

    auto fail_before_create = [&](i64 error) {
        if (diagnostic != nullptr && diagnostic->stage == execution::launch_stage::none) {
            *diagnostic = {execution::launch_stage::prepare, error, elf::error::none};
        }
        if (close_file) { (void)file_client.close(file_handle); }
        return error;
    };
    const bool replacing = options != nullptr && options->replace_image;
    if (replacing && !exec_abi_supported(read_exact, read_context, size, plan)) {
        if (diagnostic != nullptr) *diagnostic = {execution::launch_stage::inspect, thread_error_unsupported, elf::error::none};
        return fail_before_create(thread_error_unsupported);
    }
    const u32 env_count = options == nullptr ? 0 : options->environment_count;
    if (env_count > startup_environment_max || (env_count != 0 && options->environment == nullptr)) {
        return fail_before_create(process_error_invalid);
    }
    auto* page = startup_page;
    for (usize i = 0; i < sizeof(startup_page); ++i) { page[i] = 0; }
    const u64 startup_address = process_stack_top - sizeof(startup_page);
    const usize argv_offset = replacing ? 192 : options == nullptr ? 64 : 160;
    const usize env_offset = argv_offset + (argc + 1) * sizeof(u64);
    usize position = (env_offset + (env_count + 1) * sizeof(u64) + 15) & ~usize{15};
    auto* startup = reinterpret_cast<startup_info*>(page);
    *startup = {startup_magic, replacing ? 3u : options == nullptr ? 1u : 2u, sizeof(startup_info), argc, 3,
                startup_address + argv_offset, {0, 1, 2},
                options == nullptr ? 0u : startup_extension_offset};
    auto* arguments = reinterpret_cast<u64*>(page + argv_offset);
    auto* environments = reinterpret_cast<u64*>(page + env_offset);
    auto put_string = [&](const char* text, u64& destination) {
        if (text == nullptr) { return false; }
        usize n = 0;
        while (n < (replacing ? process_max_exec_arg_bytes : process_max_arg_bytes) && text[n] != '\0') { ++n; }
        if (n == (replacing ? process_max_exec_arg_bytes : process_max_arg_bytes) || position > sizeof(startup_page) ||
            n + 1 > sizeof(startup_page) - position) { return false; }
        destination = startup_address + position;
        for (usize i = 0; i <= n; ++i) { page[position++] = static_cast<u8>(text[i]); }
        return true;
    };
    for (u32 i = 0; i < argc; ++i) {
        if (!put_string(argv[i], arguments[i])) { return fail_before_create(process_error_invalid); }
    }
    for (u32 i = 0; i < env_count; ++i) {
        if (!put_string(options->environment[i], environments[i])) { return fail_before_create(process_error_invalid); }
    }
    if (options != nullptr) {
        auto* extension = reinterpret_cast<startup_extension*>(page + startup_extension_offset);
        extension->magic = startup_extension_magic;
        extension->environment_count = env_count;
        for (u32 fd = 0; fd < 3; ++fd) {
            if (options->stdio[fd] == -2) { extension->flags |= 1u << fd; }
            if (options->file_handles[fd] != 0) { extension->flags |= 1u << (8 + fd); }
        }
        extension->environment = startup_address + env_offset;
        if (!put_string(options->working_directory, extension->working_directory)) {
            return fail_before_create(process_error_invalid);
        }
        for (u32 fd = 0; fd < 3; ++fd) {
            if (options->open_paths[fd] != nullptr &&
                !put_string(options->open_paths[fd], extension->open_paths[fd])) {
                return fail_before_create(process_error_invalid);
            }
            extension->open_flags[fd] = options->open_flags[fd];
        }
    }

    if (replacing) {
        if (options->descriptor_count > 32 ||
            (options->descriptor_count && options->descriptors == nullptr)) {
            return fail_before_create(process_error_invalid);
        }
        position = (position + 7) & ~usize{7};
        const usize bytes = static_cast<usize>(options->descriptor_count) * sizeof(startup_descriptor);
        if (position > sizeof(startup_page) || bytes > sizeof(startup_page) - position) {
            return fail_before_create(process_error_invalid);
        }
        auto* execution = reinterpret_cast<startup_exec_extension*>(page + startup_exec_offset);
        *execution = {startup_exec_magic, startup_address + position, options->descriptor_count, 0};
        for (usize i = 0; i < bytes; ++i) {
            page[position + i] = reinterpret_cast<const u8*>(options->descriptors)[i];
        }
    }
    const usize name_size = length(name);
    const u64 name_length = name_size > 11 ? 11 : name_size;
    const i64 child = syscall(replacing ? sys_process_exec_prepare : sys_process_create, options == nullptr ? 7u : 0u, reinterpret_cast<u64>(name), name_length);
    if (child < 0) {
        if (diagnostic != nullptr) { *diagnostic = {execution::launch_stage::create, child, elf::error::none}; }
        if (close_file) { (void)file_client.close(file_handle); }
        return child;
    }
    process_page mapping{};
    i64 result = 0;
    if (options != nullptr && !replacing) {
        auto* extension = reinterpret_cast<startup_extension*>(page + startup_extension_offset);
        for (u32 fd = 0; result >= 0 && fd < 3; ++fd) {
            if (options->file_handles[fd] != 0) {
                if (options->open_paths[fd] != nullptr) { result = process_error_invalid; break; }
                i64 transferred = static_cast<i64>(file::status::would_block);
                u32 target_handle = 0;
                for (u32 attempt = 0; attempt < 64 &&
                     transferred == static_cast<i64>(file::status::would_block); ++attempt) {
                    transferred = file_client.transfer(options->file_handles[fd],
                                                       static_cast<u64>(child), target_handle);
                    if (transferred == static_cast<i64>(file::status::would_block)) { yield(); }
                }
                if (transferred < 0) { result = transferred; break; }
                extension->file_handles[fd] = target_handle;
                continue;
            }
            if (options->open_paths[fd] != nullptr || options->stdio[fd] == -2) { continue; }
            const u64 source = options->stdio[fd] == -1 ? fd : static_cast<u64>(options->stdio[fd]);
            result = syscall(sys_process_stdio, static_cast<u64>(child), fd, source);
        }
        if (result >= 0 && options->delegate_spawn_depth != 0) {
            result = syscall(sys_process_delegate, static_cast<u64>(child),
                             options->delegate_spawn_depth);
        } else if (result >= 0 && options->grant_spawn) {
            result = syscall(sys_process_grant, static_cast<u64>(child), 1);
        }
    }
    for (u32 index = 0; result >= 0 && index < startup_page_count; ++index) {
        mapping = {startup_address + u64{index} * 4096,
                   reinterpret_cast<u64>(page + index * 4096), 4096, map_read | map_write};
        result = syscall(sys_process_map, static_cast<u64>(child), reinterpret_cast<u64>(&mapping));
    }
    for (u32 i = 0; result >= 0 && i < plan.count; ++i) {
        const auto& segment = plan.segments[i];
        const u64 first = segment.address & ~u64{4095};
        const u64 end = (segment.address + segment.memory_bytes + 4095) & ~u64{4095};
        for (u64 address = first; address < end; address += 4096) {
            for (usize byte = 0; byte < sizeof(page_buffer); ++byte) { page_buffer[byte] = 0; }
            const u64 start = address > segment.address ? address : segment.address;
            u64 file_end = segment.address + segment.file_bytes;
            if (file_end > address + 4096) { file_end = address + 4096; }
            if (start < file_end &&
                !read_exact(read_context, segment.offset + start - segment.address,
                            page_buffer + (start - address),
                            static_cast<u32>(file_end - start))) {
                result = process_error_invalid;
                break;
            }
            mapping = {address, reinterpret_cast<u64>(page_buffer), 4096,
                       segment.permissions};
            result = syscall(sys_process_map, static_cast<u64>(child),
                              reinterpret_cast<u64>(&mapping));
            if (result < 0) { break; }
        }
    }
    for (u64 address = process_stack_bottom; result >= 0 && address < startup_address;
         address += 4096) {
        mapping = {address, 0, 0, map_read | map_write};
        result = syscall(sys_process_map, static_cast<u64>(child),
                          reinterpret_cast<u64>(&mapping));
    }

    if (result >= 0) {
        result = map_static_tls(plan, read_exact, read_context, static_cast<u64>(child));
    }
    // The open instance pins this file version through validation and all page
    // copies. A close failure is a failed load and must not make a runnable child.
    if (close_file) {
        const i64 closed = file_client.close(file_handle);
        if (result >= 0 && closed < 0) { result = closed; }
    }
    if (result >= 0) {
        process_entry entry{plan.entry, startup_address - 16, startup_address};
        result = syscall(replacing ? sys_process_exec_commit : sys_process_start, static_cast<u64>(child),
                         reinterpret_cast<u64>(&entry), replacing ? options->exec_depth_mode : 0);
        if (result < 0 && diagnostic != nullptr) {
            *diagnostic = {execution::launch_stage::start, result, elf::error::none};
        }
    }
    if (result < 0) {
        if (diagnostic != nullptr && diagnostic->stage == execution::launch_stage::none) {
            *diagnostic = {execution::launch_stage::map, result, elf::error::none};
        }
        (void)syscall(sys_process_abort, static_cast<u64>(child));
        return result;
    }
    return child;
}
}

i64 spawn_buffer(const char* name, const u8* bytes, u64 size, u32 argc,
                 const char* const* argv) {
    if (name == nullptr || bytes == nullptr || size == 0 || size > sizeof(image_buffer)) {
        return process_error_invalid;
    }
    return spawn_reader(name, size, buffer_read, const_cast<u8*>(bytes), argc, argv,
                        false, 0);
}

i64 spawn_file_impl(const char* path, u32 argc, const char* const* argv, const spawn_options* options) {
    if (path == nullptr || argc == 0 || argc > process_max_args || argv == nullptr) {
        return process_error_invalid;
    }
    if (!file_client_ready) {
        if (!file_client.init()) { return process_error_resources; }
        file_client_ready = true;
    }
    u32 handle = 0, size = 0, version = 0;
    const i64 opened = file_client.open(path, file::read_only, handle, size, version);
    (void)version; // The held read-only handle pins the opened version until close.
    if (opened < 0) { return opened; }
    opened_file source{&file_client, handle};
    return spawn_reader(path, size, file_read, &source, argc, argv, true, handle, options);
}

i64 spawn_file_diagnosed_impl(const char* path, u32 argc, const char* const* argv,
                              const spawn_options& options,
                              execution::launch_diagnostic& diagnostic) {
    diagnostic = {execution::launch_stage::none, 0, elf::error::none};
    if (path == nullptr || argc == 0 || argc > process_max_args || argv == nullptr) {
        diagnostic = {execution::launch_stage::prepare, process_error_invalid, elf::error::none};
        return process_error_invalid;
    }
    if (!file_client_ready) {
        if (!file_client.init()) {
            diagnostic = {execution::launch_stage::open, process_error_resources, elf::error::none};
            return process_error_resources;
        }
        file_client_ready = true;
    }
    u32 handle = 0, size = 0, version = 0;
    const i64 opened = file_client.open(path, file::read_only, handle, size, version);
    (void)version;
    if (opened < 0) {
        diagnostic = {execution::launch_stage::open, opened, elf::error::none};
        return opened;
    }
    opened_file source{&file_client, handle};
    return spawn_reader(path, size, file_read, &source, argc, argv, true, handle,
                        &options, &diagnostic);
}

i64 spawn_file(const char* path, u32 argc, const char* const* argv) {
    return spawn_file_impl(path, argc, argv, nullptr);
}
i64 spawn_file_options(const char* path, u32 argc, const char* const* argv, const spawn_options& options) {
    return spawn_file_impl(path, argc, argv, &options);
}

i64 spawn(u32 image, u32 argc, const char* const* argv) {
    if (argc == 0 || argc > process_max_args || argv == nullptr) { return process_error_invalid; }
    image_info image_metadata{};
    i64 result = syscall(sys_image_info, image, reinterpret_cast<u64>(&image_metadata));
    if (result < 0) { return result; }
    if (image_metadata.size > sizeof(image_buffer)) { return process_error_resources; }
    image_read_request read_request{0, reinterpret_cast<u64>(image_buffer), image_metadata.size};
    result = syscall(sys_image_read, image, reinterpret_cast<u64>(&read_request));
    if (result != static_cast<i64>(image_metadata.size)) {
        return result < 0 ? result : process_error_invalid;
    }
    // The boot-module path remains bounded by the legacy 128 KiB bootstrap
    // staging area. File-backed ELF uses spawn_file and has no image-size cap.
    return spawn_buffer(image_metadata.name, image_buffer, image_metadata.size, argc, argv);
}
}

namespace xos::execution {
i64 spawn_file_diagnosed(const char* path, u32 argc, const char* const* argv,
                         const sdk::spawn_options& options,
                         launch_diagnostic& diagnostic) {
    return sdk::spawn_file_diagnosed_impl(path, argc, argv, options, diagnostic);
}
}
