// SPDX-License-Identifier: Apache-2.0
#include "xos_rtld_mapping.h"
#include <errno.h>
#include <xos/fault_sha256.hpp>
#include <xos/sdk.hpp>
#include <xos/vm_abi.hpp>

using namespace xos;
#include "dependency_plan.hpp"

extern "C" [[noreturn]] void __real___xos_glibc_start(const startup_info*, void* stack_top);

namespace {
struct dependency {
    int fd;
    const char* path;
    u64 bias;
    u32 size;
    const u8* digest;
    u64 span, hole, pages;
};
constexpr dependency inputs[] = {
    {70, "/tests/small.so", small_bias, small_bytes, small_digest, small_span, small_hole, small_pages},
    {71, "/tests/large.so", large_bias, large_bytes, large_digest, large_span, large_hole, large_pages},
};
struct elf_scan {
    Elf64_Ehdr header;
    Elf64_Phdr phdrs[64];
};
xos_rtld_pin pins[2];
xos_rtld_images state;
xos_u32 last_sequence;

[[noreturn]] void fail(const char* stage, long code = 0) {
    sdk::print("D1_RTLD_MAP_FAIL ");
    sdk::print(stage);
    sdk::print(" code=");
    sdk::signed_decimal(code);
    sdk::print("\n");
    sdk::exit(37);
}

long send(file::op operation, u32 handle, u64 offset = 0, u32 length = 0, u32 flags = 0) {
    state.request.operation = static_cast<xos_file_u16>(operation);
    state.request.handle = handle;
    state.request.offset = offset;
    state.request.length = length;
    state.request.flags = flags;
    state.request.reserved = 0;
    if (operation != file::op::open) { state.request.name_length = 0; }
    return __xos_file_session_call(state.files, &state.request, &state.response);
}

xos_rtld_pin open_pin(const dependency& input) {
    u32 length = 0;
    while (input.path[length] != 0 && length + 1 < sizeof(state.request.name)) {
        state.request.name[length] = input.path[length];
        ++length;
    }
    state.request.name[length] = 0;
    state.request.name_length = length;
    const long opened = send(file::op::open, 0, 0, 0, file::read_only | file::open_pin);
    if (opened != 0 || state.response.value != input.size) { fail("pin open", opened); }
    const xos_rtld_pin pin{input.fd, state.response.handle, state.response.reserved, input.size,
                           input.bias, input.span, input.span};
    if (send(file::op::seek, pin.handle, 73) != 0 || state.response.value != 73) { fail("pin position"); }
    return pin;
}

void verified_scan(const dependency& input, elf_scan& scan) {
    sha256 hash;
    u8 scratch[1024];
    for (u32 at = 0; at < input.size;) {
        const u32 portion = input.size - at < sizeof(scratch) ? input.size - at : sizeof(scratch);
        if (!__xos_rtld_read_pin(input.fd, at, scratch, portion)) { fail("hash same pin"); }
        hash.update(scratch, portion);
        at += portion;
    }
    u8 digest[32];
    hash.finish(digest);
    for (u32 i = 0; i < sizeof(digest); ++i) {
        if (digest[i] != input.digest[i]) { fail("pin digest"); }
    }
    if (!__xos_rtld_read_pin(input.fd, 0, &scan.header, sizeof(scan.header))
        || scan.header.e_phnum == 0 || scan.header.e_phnum > 64
        || !__xos_rtld_read_pin(input.fd, scan.header.e_phoff, scan.phdrs,
                               scan.header.e_phnum * sizeof(Elf64_Phdr))) { fail("pin scan"); }
}

bool same_phdr(void* data, unsigned int index, const Elf64_Phdr* pinned) {
    const auto& scan = *static_cast<const elf_scan*>(data);
    if (index >= scan.header.e_phnum) { return false; }
    const auto* a = reinterpret_cast<const u8*>(&scan.phdrs[index]);
    const auto* b = reinterpret_cast<const u8*>(pinned);
    for (u32 byte = 0; byte < sizeof(*pinned); ++byte) {
        if (a[byte] != b[byte]) { return false; }
    }
    return true;
}

void verify_mapping(const dependency& dep, const elf_scan& scan, xos_rtld_mapped& output) {
    if (output.bias != dep.bias || output.allocation.start != dep.bias || output.allocation.bytes != dep.span
        || output.relative_phdr != scan.header.e_phoff) { fail("link map extent"); }
    const auto* phdrs = reinterpret_cast<const Elf64_Phdr*>(output.bias + output.relative_phdr);
    for (u32 i = 0; i < scan.header.e_phnum; ++i) {
        const auto& p = phdrs[i];
        if (p.p_type != PT_LOAD || p.p_memsz == 0) { continue; }
        const u64 page = dep.bias + xos_image_page_start(p.p_vaddr);
        if ((p.p_flags & PF_W) == 0 && xos_image_vm(XOS_VM_COMMIT, 0, page, XOS_VM_PAGE, 0, 3) != -1) {
            fail("R/RX page unexpectedly writable");
        }
        const auto* bytes = reinterpret_cast<const u8*>(dep.bias + p.p_vaddr);
        for (u64 offset = p.p_filesz; offset < p.p_memsz; ++offset) {
            if (bytes[offset] != 0) { fail("BSS not zero"); }
        }
    }
    // A normal native console write checks the entire buffer range without
    // accessing inaccessible user pages. A reserved hole is still unreadable.
    if (sdk::write(1, reinterpret_cast<const void*>(dep.bias + dep.hole), 1) >= 0) {
        fail("uncommitted hole");
    }
    auto run = reinterpret_cast<u64 (*)(u64)>(output.bias + scan.header.e_entry);
    if (run(7) != 0xd107 || run(7) != 0xd10e) { fail("mapped shared object execution"); }
}

void exercise_mapping(const dependency& dep, const xos_rtld_pin& pin, bool large) {
    elf_scan scan{};
    verified_scan(dep, scan);
    xos_rtld_mapped image{};
    const auto map = [&](int fd) {
        return __xos_rtld_map_fd(fd, &scan.header, 0, same_phdr, &scan, &image);
    };
    if (map(72) != EBADF || image.allocation.bytes != 0) { fail("unknown private descriptor"); }
    xos_image_allocation held{dep.bias, dep.span};
    const auto reserve = [&]() {
        return xos_image_vm(XOS_VM_RESERVE, XOS_VM_EXACT, dep.bias, dep.span, XOS_VM_PAGE, 0);
    };
    if (reserve() != static_cast<i64>(dep.bias) || map(dep.fd) != EEXIST
        || image.allocation.bytes != 0 || reserve() != vm_error_collision) { fail("nonreplace reservation"); }
    __xos_rtld_release_image(&held);
    const int result = map(dep.fd);
    if (result != 0) { fail("map verified pin", result); }
    verify_mapping(dep, scan, image);
    if (large && xos_image_vm(XOS_VM_UNMAP, 0, dep.bias, dep.span, 0, 0) != vm_error_resources) {
        fail("one native unmap should reach its page limit");
    }
    __xos_rtld_release_image(&image.allocation);
    if (image.allocation.bytes != 0 || reserve() != static_cast<i64>(dep.bias)) { fail("release and reuse"); }
    held = {dep.bias, dep.span};
    __xos_rtld_release_image(&held);
    if (send(file::op::seek, pin.handle, 0, 0, file::seek_current) != 0 || state.response.value != 73) {
        fail("positioned mapping changed the pin cursor");
    }
    sdk::print(large ? "D1_RTLD_LARGE pages=" : "D1_RTLD_SMALL pages=");
    sdk::decimal(dep.pages);
    sdk::print(" holes=reserved r_rx_rw=checked pin_cursor=73\n");
}
}

extern "C" [[noreturn]] void __wrap___xos_glibc_start(const startup_info* startup, void* stack_top) {
    if (reinterpret_cast<u64>(startup) != process_startup_begin || startup->version != 2) { fail("startup"); }
    const auto* ext = reinterpret_cast<const startup_extension*>(process_startup_begin + startup_extension_offset);
    xos_file_session early{};
    state.files = &early;
    if (ext->file_handles[0] == 0 || send(file::op::read, ext->file_handles[0], 0, 4) != 0
        || state.response.length != 4 || state.response.data[0] != 'A' || state.response.data[1] != 'B'
        || state.response.data[2] != 'C' || state.response.data[3] != 'D') { fail("inherited object early read"); }
    xos_rtld_mapped unused{};
    if (__xos_rtld_map_fd(70, nullptr, 0, nullptr, nullptr, &unused) != ENOTSUP) { fail("absent closure"); }
    pins[0] = open_pin(inputs[0]);
    pins[1] = open_pin(inputs[1]);
    state.pins = pins;
    state.count = 2;
    if (__xos_rtld_attach_images(&state) != 0 || __xos_rtld_attach_images(&state) != EBUSY) { fail("attachment"); }
    exercise_mapping(inputs[0], pins[0], false);
    exercise_mapping(inputs[1], pins[1], true);
    if (__xos_rtld_detach_images(&state) != 0
        || __xos_rtld_read_pin(pins[0].fd, 0, &unused, 1)
        || send(file::op::close, pins[0].handle) != 0 || send(file::op::close, pins[1].handle) != 0) {
        fail("detach and close");
    }
    last_sequence = early.request_sequence;
    if (__xos_file_adopt_early_session(&early) != 0) { fail("one session into libc"); }
    state.files = nullptr;
    __real___xos_glibc_start(startup, stack_top);
}

extern "C" xos_u32 d1_dependency_sequence() { return last_sequence; }
