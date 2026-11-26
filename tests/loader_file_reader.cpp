// SPDX-License-Identifier: Apache-2.0
#include <xos/execution.hpp>
#include <xos/file_abi.hpp>
#include <xos/sdk.hpp>

#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>

namespace {
using namespace xos;
using file::op;
using file::status;

constexpr u32 pinned_handle = 4;
constexpr u64 child_pid = 15;
constexpr u64 entry = process_user_begin + 4096;
constexpr u64 mapped_end = process_user_begin + 8192;
using fixture_image = std::array<u8, 6000>;

fixture_image make_image() {
    fixture_image image{0x7f, 'E', 'L', 'F', 2, 1, 1};
    auto put = [&](u32 offset, u64 value, u32 width) {
        for (u32 byte = 0; byte < width; ++byte) {
            image[offset + byte] = static_cast<u8>(value >> (8 * byte));
        }
    };
    put(16, 2, 2); // ET_EXEC, ELF64 little endian
    put(18, 62, 2); // EM_X86_64
    put(20, 1, 4);
    put(24, entry, 8);
    put(32, 64, 8);
    put(52, 64, 2);
    put(54, 56, 2);
    put(56, 1, 2);
    put(64, 1, 4); // PT_LOAD followed by a zero-filled tail
    put(68, map_read | map_execute, 4);
    put(80, process_user_begin, 8);
    put(96, image.size(), 8);
    put(104, mapped_end - process_user_begin, 8);
    put(112, 4096, 8);
    for (u32 index = 120; index < image.size(); ++index) {
        image[index] = static_cast<u8>(index * index + 13 * index + 3);
    }
    return image;
}

const fixture_image image = make_image();
constexpr u8 expected_digest[] = {
    0x29, 0xf3, 0x03, 0x18, 0xa8, 0xc2, 0xf5, 0x93, 0x4a, 0x2e, 0x8f, 0xc3, 0x7b, 0x2d, 0x42, 0xf8,
    0x01, 0x73, 0x12, 0xb5, 0xb8, 0x77, 0x9a, 0x77, 0x03, 0xfa, 0xdf, 0xbb, 0xde, 0xb6, 0xe7, 0x65,
};
enum class behavior { positioned, legacy, unsupported, eof, premature_eof, malformed,
                      malformed_legacy, later_invalid };
struct service_state {
    behavior mode;
    bool pinned = false;
    bool started = false;
    bool aborted = false;
    u32 opens = 0, closes = 0, maps = 0;
    u32 seeks = 0, sequential_reads = 0, positioned_reads = 0;
    u32 cursor = 313;
    u32 file_size = image.size();
    file::response response{};
} service;

void respond(const file::request& request) {
    auto& out = service.response;
    out = {};
    out.magic = file::response_magic;
    out.version = file::abi_version;
    out.request_id = request.request_id;
    const auto operation = static_cast<op>(request.operation);
    switch (operation) {
    case op::open:
        assert(++service.opens == 1 && request.flags == (file::read_only | file::open_pin));
        service.pinned = true;
        out.handle = pinned_handle;
        out.value = service.file_size;
        return;
    case op::close:
        assert(service.pinned && request.handle == pinned_handle && !service.started);
        service.pinned = false;
        ++service.closes;
        return;
    case op::cwd_set:
        assert(service.pinned && request.offset == child_pid);
        return;
    case op::seek:
        assert(service.pinned && request.handle == pinned_handle && request.offset <= image.size());
        ++service.seeks;
        service.cursor = static_cast<u32>(request.offset);
        out.value = service.cursor;
        return;
    case op::read_at:
    case op::read:
        break;
    default:
        assert(false);
    }
    assert(service.pinned && request.handle == pinned_handle && request.length != 0);
    const bool positioned = operation == op::read_at;
    const auto offset = positioned ? request.offset : service.cursor;
    assert(offset <= image.size() && request.length <= file::response_data_size);
    if (positioned) {
        ++service.positioned_reads;
        if (service.mode == behavior::legacy || service.mode == behavior::malformed_legacy ||
            (service.mode == behavior::later_invalid && offset >= 4096)) {
            out.status_code = static_cast<i32>(status::invalid);
            out.value = service.mode == behavior::malformed_legacy ? 1 : 0;
            return;
        }
        if (service.mode == behavior::unsupported) {
            out.status_code = static_cast<i32>(status::not_supported);
            return;
        }
        if (service.mode == behavior::eof ||
            (service.mode == behavior::premature_eof && offset >= 4096)) { return; }
        if (service.mode == behavior::malformed) {
            out.length = 2;
            out.value = 1;
            return;
        }
    } else {
        ++service.sequential_reads;
    }
    // Short, successful replies require another read at the next byte.
    out.length = std::min({request.length, static_cast<u32>(image.size() - offset), 1853u});
    out.value = out.length;
    std::copy_n(image.data() + offset, out.length, out.data);
    if (!positioned) { service.cursor += out.length; }
}
}

namespace xos::sdk {
u16 target_elf_machine() { return elf::machine_x86_64; }

i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    switch (number) {
    case sys_ipc_handles: {
        auto* handles = reinterpret_cast<u32*>(first);
        handles[0] = 12;
        handles[1] = 13;
        return 0;
    }
    case 6: return 42;
    case 4:
        assert(first == 12 && third == sizeof(file::request));
        respond(*reinterpret_cast<const file::request*>(second));
        return 0;
    case 5:
        assert(first == 13 && third == sizeof(file::response));
        *reinterpret_cast<file::response*>(second) = service.response;
        return sizeof(file::response);
    case sys_handle_write:
        assert(first == 1);
        return static_cast<i64>(third);
    case sys_process_create:
        assert(service.pinned);
        return child_pid;
    case sys_process_stdio:
        assert(first == child_pid && service.pinned);
        return 0;
    case sys_process_map: {
        assert(first == child_pid && service.pinned);
        const auto& page = *reinterpret_cast<const process_page*>(second);
        if (page.address >= process_user_begin && page.address < mapped_end) {
            assert(page.address == process_user_begin + 4096 * service.maps++);
            assert(page.length == 4096 && page.permissions == (map_read | map_execute));
            const auto* bytes = reinterpret_cast<const u8*>(page.source);
            for (u32 i = 0; i < page.length; ++i) {
                const auto offset = page.address - process_user_begin + i;
                assert(bytes[i] == (offset < image.size() ? image[offset] : 0));
            }
        }
        return 0;
    }
    case sys_process_start:
        assert(first == child_pid && service.maps == 2 && service.closes == 1 && !service.pinned);
        assert(reinterpret_cast<const process_entry*>(second)->entry == entry);
        service.started = true;
        return 0;
    case sys_process_abort:
        assert(first == child_pid && service.closes == 1 && !service.pinned);
        service.aborted = true;
        return 0;
    default:
        std::fprintf(stderr, "unexpected syscall %llu\n", static_cast<unsigned long long>(number));
        assert(false);
        return -1;
    }
}
}

int main() {
    const char* path = "/fixture.elf";
    const char* args[] = {path};
    for (auto mode : {behavior::positioned, behavior::legacy, behavior::unsupported}) {
        service = {mode};
        assert(xos::sdk::spawn_file(path, 1, args) == child_pid && service.started);
        if (mode == behavior::positioned) {
            assert(service.seeks == 0 && service.positioned_reads > 3);
            assert(service.sequential_reads == 0 && service.cursor == 313);
        } else {
            assert(service.positioned_reads == 1 && service.seeks == 4);
            assert(service.sequential_reads > service.seeks);
        }

        // The native service can open a pre-existing FAT32 file of UINT32_MAX
        // bytes. Its last byte remains within the positioned offset limit.
        service = {mode};
        service.file_size = 0xffffffffu;
        assert(xos::sdk::spawn_file(path, 1, args) == child_pid && service.started);

        service = {mode};
        xos::execution::launch_diagnostic diagnostic{};
        xos::execution::image_receipt receipt{};
        xos::sdk::spawn_options options{};
        assert(xos::execution::spawn_file_diagnosed_receipt(path, 1, args, options,
                                                          diagnostic, receipt) == child_pid);
        assert(service.started && receipt.size == image.size());
        assert(std::equal(std::begin(receipt.digest), std::end(receipt.digest), expected_digest));
    }
    for (auto mode : {behavior::eof, behavior::premature_eof, behavior::malformed,
                      behavior::malformed_legacy, behavior::later_invalid}) {
        service = {mode};
        assert(xos::sdk::spawn_file(path, 1, args) < 0);
        assert(service.closes == 1 && !service.started && !service.pinned);
        assert(service.seeks == 0 && service.sequential_reads == 0);
        if (mode == behavior::later_invalid || mode == behavior::premature_eof) {
            assert(service.maps == 1 && service.aborted && service.positioned_reads > 1);
        } else {
            assert(service.maps == 0 && !service.aborted && service.positioned_reads == 1);
        }
    }
    std::puts("PASS loader positioned reads, old services, pinned exact bytes and receipt, EOF and malformed replies");
}
