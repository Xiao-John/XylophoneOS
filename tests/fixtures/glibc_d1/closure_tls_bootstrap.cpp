// SPDX-License-Identifier: Apache-2.0
#include "xos_rtld_heap.h"
#include "xos_rtld_mapping.h"
#include "xos_file_trap.h"
#include <string.h>
#include <xos/fault_sha256.hpp>
#include <xos/sdk.hpp>
#include <xos/vm.hpp>

using namespace xos;

namespace {
struct dependency {
    const char* path;
    const char* soname;
    u64 bias;
    u32 size;
    u64 span;
    const u8* digest;
};
#include "closure_tls_plan.hpp"

struct elf_headers {
    Elf64_Ehdr header;
    Elf64_Phdr phdrs[64];
};

[[noreturn]] void fail(const char* message) {
    const char* parts[] = {"D1_CLOSURE_BOOTSTRAP_FAIL ", message, "\n"};
    for (const char* part : parts) {
        (void) file_trap(11, 1, reinterpret_cast<u64>(part), strlen(part));
    }
    (void) file_trap(2, 62, 0, 0);
    __builtin_trap();
}

#ifndef D1_LIBC_HANDOFF
bool exhausted_heap(const char* arg) {
    constexpr char limit[] = "heap-limit";
    for (u32 index = 0; index < sizeof(limit); ++index) {
        if (arg[index] != limit[index]) { return false; }
    }
    return true;
}
#endif

long open_image(xos_rtld_images& state, const char* path, u32 flags) {
    auto& request = state.request;
    request = {};
    request.operation = static_cast<xos_file_u16>(file::op::open);
    request.flags = flags;
    while (path[request.name_length] != 0 && request.name_length + 1 < sizeof(request.name)) {
        request.name[request.name_length] = path[request.name_length];
        ++request.name_length;
    }
    return __xos_file_session_call(state.files, &request, &state.response);
}

bool matching_phdr(void* context, unsigned int index, const Elf64_Phdr* item) {
    const auto& headers = *static_cast<const elf_headers*>(context);
    if (index >= headers.header.e_phnum) { return false; }
    const auto* a = reinterpret_cast<const u8*>(&headers.phdrs[index]);
    const auto* b = reinterpret_cast<const u8*>(item);
    for (u32 i = 0; i < sizeof(*item); ++i) {
        if (a[i] != b[i]) { return false; }
    }
    return true;
}

xos_rtld_mapped verify_map(const dependency& input, int fd) {
    if (__xos_rtld_open_pin(input.soname) != fd) { fail("claim named pin"); }
    sha256 digest;
    u8 buffer[1024];
    for (u32 at = 0; at < input.size;) {
        const u32 bytes = input.size - at > sizeof(buffer) ? sizeof(buffer) : input.size - at;
        if (__xos_rtld_pread_pin(fd, buffer, bytes, at) != bytes) { fail("read pinned image"); }
        digest.update(buffer, bytes);
        at += bytes;
    }
    u8 hash[32];
    digest.finish(hash);
    for (u32 i = 0; i < sizeof(hash); ++i) {
        if (hash[i] != input.digest[i]) { fail("pinned image digest"); }
    }

    elf_headers headers;
    if (__xos_rtld_read_pin(fd, &headers.header, sizeof(headers.header)) != sizeof(headers.header)
        || headers.header.e_phnum == 0 || headers.header.e_phnum > 64) {
        fail("pinned ELF header");
    }
    const u32 bytes = headers.header.e_phnum * sizeof(headers.phdrs[0]);
    if (__xos_rtld_pread_pin(fd, headers.phdrs, bytes, headers.header.e_phoff) != bytes) {
        fail("pinned program headers");
    }
    xos_rtld_mapped result{};
    if (__xos_rtld_map_fd(fd, &headers.header, 0, matching_phdr, &headers, &result) != 0
        || result.bias != input.bias || result.allocation.bytes != input.span
        || result.relative_phdr != headers.header.e_phoff) {
        fail("map verified dependency");
    }
#ifndef D1_LIBC_HANDOFF
    if (__xos_rtld_close_pin(fd) != 0) { fail("close dependency pin"); }
#endif
    return result;
}

#ifdef D1_LIBC_HANDOFF
u32 inherited_input(const startup_info* startup) {
    if (startup->version == 2) {
        const auto* ext = reinterpret_cast<const startup_extension*>(process_startup_begin + startup_extension_offset);
        if (ext->magic != startup_extension_magic || (ext->flags & (1u << 8)) == 0
            || ext->file_handles[0] == 0) { fail("native inherited stdin"); }
        return ext->file_handles[0];
    }
    const auto* exec = reinterpret_cast<const startup_exec_extension*>(process_startup_begin + startup_exec_offset);
    if (exec->magic != startup_exec_magic || exec->reserved != 0 || exec->count > 32
        || (exec->descriptors & 7) != 0 || exec->descriptors < process_startup_begin
        || exec->descriptors > process_stack_top - exec->count * sizeof(startup_descriptor)) {
        fail("native exec descriptors");
    }
    const auto* items = reinterpret_cast<const startup_descriptor*>(exec->descriptors);
    for (u32 i = 0; i < exec->count; ++i) {
        if (items[i].fd == 10 && items[i].kind == 2 && items[i].handle != 0) { return items[i].handle; }
    }
    fail("v3 inherited file");
}
#endif
}

#ifdef D1_LIBC_HANDOFF
extern "C" [[noreturn]] void d1_run_libc_handoff(u64, u64, xos_rtld_images*, u32, u32, int);
#else
extern "C" [[noreturn]] void d1_run_closure_tls(u64, u64, int);
#endif

extern "C" [[noreturn]] void __xos_glibc_start(const startup_info* startup, void*) {
#ifdef D1_LIBC_HANDOFF
    if (reinterpret_cast<u64>(startup) != process_startup_begin || startup->argc != 2
        || (startup->version != 2 && startup->version != 3)) { fail("native startup"); }
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    const bool wrong_version = strcmp(argv[1], "wrong-version") == 0;
    if (!wrong_version && strcmp(argv[1], "ordinary") != 0) { fail("handoff mode"); }
    const bool exhausted = false;
#else
    if (reinterpret_cast<u64>(startup) != process_startup_begin || startup->version != 2) {
        fail("native startup");
    }
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    const bool exhausted = startup->argc == 2 && exhausted_heap(argv[1]);
#endif
    xos_file_session early{};
    xos_rtld_pin_plan plan{};
    xos_rtld_images state{};
    state.files = &early;
    state.plan = &plan;
#ifdef D1_LIBC_HANDOFF
    const u32 native_input = inherited_input(startup);
    const auto* images = &dependencies[wrong_version ? 2 : 0];
    const auto* images_end = images + 2;
    state.request.operation = static_cast<xos_file_u16>(file::op::read);
    state.request.handle = native_input;
    state.request.length = 4;
    if (__xos_file_session_call(&early, &state.request, &state.response) != 0
        || state.response.length != 4 || memcmp(state.response.data, "ABCD", 4) != 0) { fail("early inherited read"); }
#else
    const auto* images = dependencies;
    const auto* images_end = dependencies + sizeof(dependencies) / sizeof(dependencies[0]);
#endif
    for (const auto* input = images; input != images_end; ++input) {
        if (open_image(state, input->path, file::write_only) != 0) { fail("previous pin released"); }
        state.request = {};
        state.request.operation = static_cast<xos_file_u16>(file::op::close);
        state.request.handle = state.response.handle;
        if (__xos_file_session_call(&early, &state.request, &state.response) != 0) {
            fail("close writer control");
        }
    }
    for (const auto* input = images; input != images_end; ++input) {
        if (open_image(state, input->path, file::read_only | file::open_pin) != 0
            || state.response.value != input->size) { fail("open verified dependency pin"); }
        auto& pin = plan.pins[plan.count];
        pin = {70 + static_cast<int>(plan.count), state.response.handle, state.response.reserved,
               input->size, input->bias, input->span, input->span, {}};
        for (u32 i = 0; input->soname[i] != 0; ++i) { pin.soname[i] = input->soname[i]; }
        ++plan.count;
    }
    const long now = file_trap(46, 0, 0, 0);
    if (now < 0) { fail("startup clock"); }
    plan.deadline_ns = static_cast<u64>(now) + 30000000000ULL;
    if (__xos_rtld_attach_images(&state) != 0) { fail("authenticated startup session"); }

    const auto first = verify_map(images[0], 70);
    const auto second = verify_map(images[1], 71);
#ifndef D1_LIBC_HANDOFF
    if (__xos_rtld_finish_images(&state) != 0) { fail("finish authenticated pin phase"); }
#endif

    const xos_rtld_heap_plan heap{0x130000000000ULL,
                                (exhausted ? 2ULL : 16ULL) * vm_page_size, plan.deadline_ns};
    if (xos_image_vm(XOS_VM_RESERVE, XOS_VM_EXACT, heap.base, heap.bytes, vm_page_size, 0)
            != static_cast<i64>(heap.base)
        || __xos_rtld_heap_begin(&heap) != 0) { fail("bounded private heap"); }
#ifdef D1_LIBC_HANDOFF
    d1_run_libc_handoff(first.bias, second.bias, &state, startup->version, native_input, wrong_version);
#else
    d1_run_closure_tls(first.bias, second.bias, exhausted);
#endif
}
