// SPDX-License-Identifier: Apache-2.0
#include "interpreter_entry.hpp"
#include "xos_rtld_heap.h"
#include "xos_rtld_sysdep_start.h"
#include <errno.h>
#include <string.h>
#include <xos/fault_sha256.hpp>
#include <xos/vm.hpp>

using namespace xos;
using namespace xos::glibc_d1;
#include "interpreter_plan.hpp"

extern "C" int d1_gnu_startup_matches(void**, const xos_rtld_startup*, int);
extern "C" int enter_sysdep_stack(void**, xos_rtld_images*, xos_rtld_startup*);
asm(
    ".text\n"
    ".globl enter_sysdep_stack\n"
    "enter_sysdep_stack:\n"
    "  pushq %r12\n"
    "  movq %rsp, %r12\n"
    "  movq %rdi, %rsp\n"
    "  call __xos_rtld_prepare_sysdep_start\n"
    "  movq %r12, %rsp\n"
    "  popq %r12\n"
    "  ret\n");

namespace {
struct source { xos_file_session* owner; u32 handle = 0; u32 inode = 0; };
xos_file_request request;
xos_file_response response;
xos_rtld_images rtld_images;

[[noreturn]] void fail(const char* message) {
    sdk::print("D1_NATIVE_SYSDEP_FAIL ");
    sdk::print(message);
    sdk::print("\n");
    sdk::exit(65);
}

long file_call(xos_file_session& session, file::op operation, u32 handle = 0, u32 length = 0,
               u64 offset = 0, u32 flags = 0, const char* path = nullptr) {
    request = {};
    request.operation = static_cast<xos_file_u16>(operation);
    request.handle = handle;
    request.length = length;
    request.offset = offset;
    request.flags = flags;
    if (path) {
        while (path[request.name_length] != 0 && request.name_length + 1 < sizeof(request.name)) {
            request.name[request.name_length] = path[request.name_length];
            ++request.name_length;
        }
    }
    return __xos_file_session_call(&session, &request, &response);
}

bool positioned(void* context, u64 offset, u8* out, u32 length) {
    auto& file = *static_cast<source*>(context);
    for (u32 done = 0; done < length;) {
        const u32 amount = length - done < sizeof(response.data) ? length - done : sizeof(response.data);
        if (file_call(*file.owner, file::op::read_at, file.handle, amount, offset + done) != 0
            || response.length != amount) { return false; }
        for (u32 i = 0; i < amount; ++i) { out[done + i] = response.data[i]; }
        done += amount;
    }
    return true;
}

void verify(source& image, const char* path, u32 length, const u8 (&digest)[32]) {
    if (file_call(*image.owner, file::op::open, 0, 0, 0, file::read_only | file::open_pin, path) != 0
        || response.value != length) { fail("pin open"); }
    image.handle = response.handle;
    image.inode = response.reserved;
    sha256 hash;
    u8 bytes[1024];
    for (u32 offset = 0; offset < length;) {
        const u32 amount = length - offset < sizeof(bytes) ? length - offset : sizeof(bytes);
        if (!positioned(&image, offset, bytes, amount)) { fail("read verification input"); }
        hash.update(bytes, amount);
        offset += amount;
    }
    u8 sum[32];
    hash.finish(sum);
    for (u32 i = 0; i < sizeof(sum); ++i) {
        if (sum[i] != digest[i]) { fail("pinned digest"); }
    }
}

bool entropy(u8* bytes, u32 length) {
    return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(bytes), length) == 0;
}
}

extern "C" [[noreturn]] void __xos_glibc_start(const startup_info* startup, void*) {
    if (reinterpret_cast<u64>(startup) != process_startup_begin
        || (startup->version != 2 && startup->version != 3) || startup->argc != 2) { fail("native startup"); }
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    const bool secure = sdk::equal(argv[1], "secure");
    if (!secure && !sdk::equal(argv[1], "ordinary")) { fail("fixture mode"); }
    xos_file_session early{};
    if (file_call(early, file::op::open, 0, 0, 0, file::read_only, "/tests/input") != 0) {
        fail("ordinary file open");
    }
    const u32 stream = response.handle;
    if (file_call(early, file::op::read, stream, 4) != 0 || response.length != 4
        || memcmp(response.data, "ABCD", 4) != 0) { fail("early file read"); }

    source main{&early}, ld{&early}, dep{&early};
    verify(main, "/tests/main.pie", main_bytes, main_digest);
    verify(ld, "/tests/interpreter.so", interpreter_bytes, interpreter_digest);
    verify(dep, "/tests/dependency.so", dependency_bytes, dependency_digest);
    const pinned_image main_source{main_image, main_bytes, positioned, &main, {main_span, main_span}};
    const pinned_image ld_source{interpreter_image, interpreter_bytes, positioned, &ld,
                                 {interpreter_span, interpreter_span}};
    const long now = sdk::syscall(46);
    if (now < 0) { fail("clock"); }
    xos_rtld_pin_plan pins{};
    pins.deadline_ns = static_cast<u64>(now) + 30000000000ULL;
    pins.count = 1;
    pins.pins[0] = {71, dep.handle, dep.inode, dependency_bytes, dependency_image.bias,
                    dependency_span, dependency_span, "libhandoff.so"};
    const xos_rtld_heap_plan heap{0x120000200000ULL, 8 * vm_page_size, pins.deadline_ns};
    auto* frame = reinterpret_cast<xos_d1_entry_handoff*>(XOS_D1_STACK_ENTRY_MIN);
    *frame = {};
    interpreter_allocations images{};
    if (prepare_interpreter_entry(startup, main_source, main_phdr, ld_source,
        secure ? execution_mode::secure : execution_mode::ordinary, entropy, early,
        *frame, images, &pins, &heap).error != interpreter_entry_error::none) { fail("prepare entry"); }
    auto& active_files = frame->record.files;
    if (file_call(active_files, file::op::close, main.handle) != 0
        || file_call(active_files, file::op::close, ld.handle) != 0) { fail("close bootstrap pins"); }

    auto** stack = reinterpret_cast<void**>(frame->stack.words);
    xos_rtld_startup gnu{};
    const u32 before = active_files.request_sequence;
    --frame->record.version;
    const int obsolete = enter_sysdep_stack(stack, &rtld_images, &gnu);
    frame->record.version = XOS_D1_ENTRY_VERSION;
    if (obsolete != EINVAL || gnu.phdr != nullptr || gnu.auxv != nullptr
        || active_files.request_sequence != before) { fail("obsolete handoff refusal"); }
    if (enter_sysdep_stack(stack, &rtld_images, &gnu) != 0
        || active_files.request_sequence != before || rtld_images.files != &active_files
        || !d1_gnu_startup_matches(stack, &gnu, secure)) { fail("actual GNU startup state"); }
    if (__xos_rtld_heap_grow(vm_page_size) != reinterpret_cast<void*>(heap.base)) {
        fail("attached native heap");
    }
    const int fd = __xos_rtld_open_pin("libhandoff.so");
    Elf64_Ehdr header;
    if (fd != 71 || __xos_rtld_read_pin(fd, &header, sizeof(header)) != sizeof(header)
        || header.e_ident[EI_CLASS] != ELFCLASS64 || __xos_rtld_close_pin(fd) != 0
        || __xos_rtld_finish_images(&rtld_images) != 0 || __xos_rtld_heap_seal() != 0) {
        fail("authenticated pin phase");
    }
    const u32 before_resume = active_files.request_sequence;
    if (file_call(active_files, file::op::read, stream, 4) != 0 || response.length != 4
        || memcmp(response.data, "EFGH", 4) != 0
        || file_call(active_files, file::op::close, stream) != 0
        || active_files.request_sequence != before_resume + 2) { fail("same file session"); }
    sdk::print(secure
        ? "D1_NATIVE_SYSDEP_OK secure=1 argv_env=gnu auxv=gnu file=continuous heap=live\n"
        : "D1_NATIVE_SYSDEP_OK secure=0 argv_env=gnu auxv=gnu file=continuous heap=live\n");
    sdk::exit(0);
}
