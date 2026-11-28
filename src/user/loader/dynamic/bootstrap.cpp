// SPDX-License-Identifier: Apache-2.0
#include "startup.hpp"
#include "../glibc_d1/interpreter_entry.hpp"
#include <xos/sdk.hpp>
#include <xos/file_abi.hpp>

using namespace xos;
using namespace xos::dynamic;
using namespace xos::glibc_d1;

// This bootstrap consumes the existing native v3 FD contract unchanged.
extern "C" __attribute__((section(".xos.exec"), used)) const struct {
    u64 magic; u32 version, size;
} xos_dynamic_exec_opt_in = {exec_image_abi_magic, 3, 16};
extern "C" __attribute__((section(".xos.tty"), used)) const struct {
    u64 magic; u32 version, size;
} xos_dynamic_terminal_opt_in = {terminal_image_abi_magic, 1, 16};

extern "C" [[noreturn]] void xos_enter_gnu_interpreter(void**, u64);
asm(".text\n.globl xos_enter_gnu_interpreter\nxos_enter_gnu_interpreter:\n"
    "movq %rdi,%rsp\nxor %ebp,%ebp\njmp *%rsi\n");

namespace {
const startup_capsule* capsule;
xos_file_request request;
xos_file_response response;
struct source { xos_file_session* session; u32 handle; u64 bytes; };

[[noreturn]] void fail(i64 status, u32 phase, const char* detail) {
    if (capsule && capsule->prefix.magic == XOS_DYNAMIC_STARTUP_MAGIC)
        (void)launch::notify_ready(capsule->prefix.control, capsule->prefix.artifact,
                                  status < 0 ? status : process_error_invalid, phase);
    sdk::print("XOS dynamic bootstrap: "); sdk::print(detail); sdk::print("\n");
    sdk::exit(126);
}
long call(xos_file_session& session, file::op operation, u32 handle, u32 length = 0, u64 offset = 0) {
    request = {};
    request.operation = static_cast<xos_file_u16>(operation);
    request.handle = handle;
    request.length = length;
    request.offset = offset;
    return __xos_file_session_call_until(&session, &request, &response, capsule->prefix.control.deadline);
}
bool positioned(void* raw, u64 offset, u8* output, u32 length) {
    auto& input = *static_cast<source*>(raw);
    if (offset > input.bytes || length > input.bytes - offset) return false;
    for (u32 copied = 0; copied < length;) {
        const u32 remaining = length - copied;
        const u32 amount = remaining > sizeof(response.data) ? sizeof(response.data) : remaining;
        if (call(*input.session, file::op::read_at, input.handle, amount, offset + copied) != 0
            || response.length != amount) return false;
        for (u32 i = 0; i < amount; ++i) output[copied + i] = response.data[i];
        copied += amount;
    }
    return true;
}
bool entropy(u8* bytes, u32 length) {
    return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(bytes), length) == 0;
}
pinned_image image(u32 index, source& input) {
    const auto& layout = capsule->images[index];
    const auto& object = capsule->selected.objects[index];
    return {{object.bias, layout.entry, layout.loads, layout.load_count}, object.file_bytes,
            positioned, &input, {object.span, object.span}};
}
}

extern "C" [[noreturn]] void __xos_glibc_start(const startup_info* startup, void*) {
    capsule = reinterpret_cast<const startup_capsule*>(XOS_DYNAMIC_STARTUP_ADDRESS);
    if (reinterpret_cast<u64>(startup) != process_startup_begin || !validate_capsule(*capsule)
        || capsule->prefix.control.child_pid != sdk::pid())
        fail(process_error_denied, XOS_LAUNCH_PHASE_PREPARE, "invalid native capsule");
    xos_file_session files{};
    // Initialize the one process session against a transferred pin; its next
    // request number moves into rtld and then libc without restarting it.
    for (u32 i = 1; i < capsule->selected.header.object_count; ++i) {
        if (call(files, file::op::fstat, capsule->pins[i].handle) != 0
            || response.value != capsule->selected.objects[i].file_bytes
            || response.reserved != capsule->pins[i].inode)
            fail(process_error_denied, XOS_LAUNCH_PHASE_PREPARE, "changed transferred pin");
    }
    source main{&files, capsule->pins[2].handle, capsule->selected.objects[2].file_bytes};
    source rtld{&files, capsule->pins[1].handle, capsule->selected.objects[1].file_bytes};
    const auto main_image = image(2, main), rtld_image = image(1, rtld);
    const auto& headers = capsule->images[2];
    const main_headers main_table{headers.phoff, headers.phaddr, headers.phnum};
    xos_rtld_pin_plan pins{};
    pins.deadline_ns = capsule->prefix.control.deadline;
    for (u32 i = 3; i < capsule->selected.header.object_count; ++i) {
        const auto& object = capsule->selected.objects[i];
        const auto& handle = capsule->pins[i];
        auto& pin = pins.pins[pins.count];
        pin = {71 + static_cast<int>(pins.count), handle.handle, handle.inode,
               object.file_bytes, object.bias, object.span, object.span, {}};
        for (u32 j = 0; j < sizeof(pin.soname); ++j) pin.soname[j] = object.soname[j];
        ++pins.count;
    }
    if (capsule->selected.header.version == generation_online_version) {
        pins.online_version = 1;
        pins.online_mask = capsule->selected.header.online_mask >> 3;
        pins.isolated_mask = pins.online_mask;
        // A private namespace cannot introduce a second libc or native TLS
        // runtime. Classify only the same immutable, already verified pins.
        for (u32 i = 3; i < capsule->selected.header.object_count; ++i) {
            if (!(pins.isolated_mask & (1u << (i - 3)))) continue;
            const auto& headers_i = capsule->images[i];
            source input{&files, capsule->pins[i].handle, capsule->selected.objects[i].file_bytes};
            for (u32 ph = 0; ph < headers_i.phnum; ++ph) {
                u32 type = 0;
                if (!positioned(&input, headers_i.phoff + u64(ph) * 56,
                                reinterpret_cast<u8*>(&type), sizeof(type)))
                    fail(process_error_state, XOS_LAUNCH_PHASE_PREPARE, "online pin metadata");
                if (type == 7) pins.isolated_mask &= ~(1u << (i - 3));
            }
        }
        for (u32 pass = 0; pass < pins.count; ++pass)
            for (u32 i = 3; i < capsule->selected.header.object_count; ++i) {
                const auto& object = capsule->selected.objects[i];
                for (u32 edge = 0; edge < object.needed_count; ++edge) {
                    const u32 other = object.needed[edge];
                    if (other < 3 || !(pins.isolated_mask & (1u << (other - 3))))
                        pins.isolated_mask &= ~(1u << (i - 3));
                }
            }
    }
    // This arena is disjoint from the manifest's object placement range.
    const xos_rtld_heap_plan heap{startup_heap_base, startup_heap_bytes, pins.deadline_ns};
    auto* frame = reinterpret_cast<xos_d1_entry_handoff*>(XOS_D1_STACK_ENTRY_MIN);
    *frame = {};
    interpreter_allocations allocations{};
    const auto prepared = prepare_interpreter_entry(startup, main_image, main_table, rtld_image,
        execution_mode::ordinary, entropy, files, *frame, allocations, &pins, &heap);
    if (prepared.error != interpreter_entry_error::none)
        fail(prepared.mapping.vm_error, XOS_LAUNCH_PHASE_MAP, "image mapping or GNU entry stack");
    if (call(frame->record.files, file::op::close, main.handle) != 0
        || call(frame->record.files, file::op::close, rtld.handle) != 0)
        fail(process_error_state, XOS_LAUNCH_PHASE_MAP, "bootstrap pin close");
    xos_enter_gnu_interpreter(reinterpret_cast<void**>(frame->stack.words), frame->record.interpreter_entry);
}
