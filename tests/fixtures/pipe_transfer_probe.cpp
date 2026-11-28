// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/spawn.hpp>
#include <xos/thread_abi.hpp>
#include <xos/vm_abi.hpp>
namespace {
using namespace xos;
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker metadata{exec_image_abi_magic, 3, sizeof(exec_marker)};
[[noreturn]] void fail(const char* name, i64 value = 0) {
    sdk::print("PIPE_TRANSFER_FAIL "); sdk::print(name); sdk::print(" value=");
    sdk::signed_decimal(value); sdk::print("\n"); sdk::exit(93);
}
void need(bool good, const char* name, i64 value = 0) { if (!good) fail(name, value); }
process_budget_snapshot budget() {
    process_budget_snapshot result{};
    need(!sdk::query_process_budget(sdk::pid(), result), "budget-query"); return result;
}
u64 create() {
    const auto child = sdk::syscall(sys_process_create, 0);
    need(child > 0, "create", child); return static_cast<u64>(child);
}
void abort(u64 child) { need(!sdk::syscall(sys_process_abort, child), "abort"); }
pipe_handles pipe() {
    pipe_handles value{}; need(!sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&value)), "pipe-create"); return value;
}
void close(u32 token) { need(!sdk::syscall(sys_pipe_close, token), "pipe-close"); }
process_pipe_transfer request(u32 first, u32 second = 0) {
    process_pipe_transfer value{1, sizeof(value), second ? 2u : 1u, 0, {}};
    value.entries[0].source = first; value.entries[1].source = second; return value;
}
bool same(const process_pipe_transfer& left, const process_pipe_transfer& right) {
    const auto* a = reinterpret_cast<const u8*>(&left);
    const auto* b = reinterpret_cast<const u8*>(&right);
    for (u32 i = 0; i < sizeof(left); ++i) if (a[i] != b[i]) return false;
    return true;
}
void rejected(u64 child, process_pipe_transfer& value, i64 expected, const char* name) {
    const auto before = value;
    const auto result = sdk::transfer_pipes(child, value);
    need(result == expected && same(before, value), name, result);
}
void zero_pipe_credit() { need(!budget().usage.pipes, "all-pipe-credits-returned"); }
void invalid() {
    const auto handles = pipe(); const auto child = create();
    auto value = request(handles.read_token);
    rejected(sdk::pid(), value, process_error_denied, "not-owned-child");
    need(sdk::syscall(sys_process_stdio, child, 3, 0) == process_error_invalid, "legacy-unknown-mode");
    value.version = 2; rejected(child, value, process_error_invalid, "version"); value.version = 1;
    value.size -= 8; rejected(child, value, process_error_invalid, "size"); value.size = sizeof(value);
    value.reserved = 1; rejected(child, value, process_error_invalid, "reserved"); value.reserved = 0;
    value.count = 0; rejected(child, value, process_error_invalid, "zero-count"); value.count = 17;
    rejected(child, value, process_error_invalid, "large-count"); value.count = 1;
    value.entries[0].target = 123; rejected(child, value, process_error_invalid, "nonzero-target"); value.entries[0].target = 0;
    value.entries[15].source = handles.write_token;
    rejected(child, value, process_error_invalid, "unused-entry"); value.entries[15].source = 0;
    value = request(handles.read_token, handles.read_token);
    rejected(child, value, process_error_invalid, "duplicate-source");
    value = request(handles.read_token, 0xffffffffu);
    rejected(child, value, process_error_denied, "late-unowned-source-no-partial-retain");
    value = request(handles.read_token);
    need(!sdk::transfer_pipes(child, value) && value.entries[0].target == handles.read_token, "retry-after-invalid");
    value = request(handles.read_token);
    rejected(child, value, process_error_state, "already-present-not-retained-twice");
    close(handles.read_token);
    const auto other = create();
    rejected(other, value, process_error_denied, "known-token-without-caller-authority");
    abort(other); abort(child); close(handles.write_token); zero_pipe_credit();
}
void readonly_output() {
    const auto handles = pipe(); const auto child = create();
    vm_request memory{1, sizeof(memory), 1, vm_exact_nonreplace, vm_arena_begin, 8192, 4096, 0, 0, 0, 0};
    need(sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)) == static_cast<i64>(vm_arena_begin), "reserve-output");
    memory.operation = 2; memory.flags = 0; memory.alignment = 0; memory.protection = 3;
    need(!sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)), "commit-output");
    auto& value = *reinterpret_cast<process_pipe_transfer*>(vm_arena_begin + 4096 - 72);
    value = request(handles.read_token, handles.write_token);
    memory.operation = 3; memory.address += 4096; memory.length = 4096; memory.protection = 1;
    need(!sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)), "protect-second-output-page");
    rejected(child, value, process_error_invalid, "readonly-output-no-partial-retain");
    memory.protection = 3; need(!sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)), "unprotect-output");
    need(!sdk::transfer_pipes(child, value) && value.entries[0].target == handles.read_token &&
         value.entries[1].target == handles.write_token, "retry-after-output-failure");
    memory.operation = 5; memory.address = vm_arena_begin; memory.length = 8192; memory.protection = 0;
    need(!sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)), "unmap-output");
    abort(child); close(handles.read_token); close(handles.write_token); zero_pipe_credit();
}
void pending() {
    const auto handles = pipe(); auto value = request(handles.read_token);
    auto child = sdk::syscall(sys_process_exec_prepare, 0, 0, 0);
    need(child > 0, "exec-prepare", child);
    rejected(static_cast<u64>(child), value, process_error_state, "replacement-pending"); abort(static_cast<u64>(child));
    child = sdk::syscall(sys_process_fork_prepare);
    need(child > 0, "fork-prepare", child);
    rejected(static_cast<u64>(child), value, process_error_state, "fork-pending"); abort(static_cast<u64>(child));
    close(handles.read_token); close(handles.write_token); zero_pipe_credit();
}
void capacity() {
    pipe_handles handles[8]{}; u32 tokens[16]{};
    for (u32 i = 0; i < 8; ++i) { handles[i] = pipe(); tokens[2*i] = handles[i].read_token; tokens[2*i+1] = handles[i].write_token; }
    need(budget().usage.pipes == 8, "eight-object-credits");
    const auto child = create();
    need(!sdk::syscall(sys_process_stdio, child, 0, tokens[0]) &&
         !sdk::syscall(sys_process_stdio, child, 1, tokens[1]) &&
         !sdk::syscall(sys_process_stdio, child, 2, tokens[1]), "three-route-references");
    process_pipe_transfer value{1, sizeof(value), 13, 0, {}};
    for (u32 i = 0; i < 13; ++i) value.entries[i].source = tokens[i];
    need(!sdk::transfer_pipes(child, value), "thirteen-plus-three-is-sixteen");
    value = {1, sizeof(value), 3, 0, {}};
    for (u32 i = 0; i < 3; ++i) value.entries[i].source = tokens[13+i];
    rejected(child, value, process_error_resources, "capacity-all-or-none");
    for (u32 fd = 0; fd < 3; ++fd) need(!sdk::syscall(sys_process_stdio, child, fd, process_stdio_close), "retire-routes");
    need(!sdk::transfer_pipes(child, value), "capacity-failure-retry-three");
    for (const auto token : tokens) close(token);
    need(budget().usage.pipes == 8 && budget().attributed.pipes == 8, "child-retains-original-object-credits");
    abort(child); zero_pipe_credit();
    const auto recycled = pipe(); close(recycled.read_token); close(recycled.write_token); zero_pipe_credit();
}
u32 callback_count;
i64 reject_after_mapping(u64, void*) { ++callback_count; return process_error_resources; }
void loader() {
    const auto handles = pipe();
    sdk::spawn_options options{};
    const startup_descriptor descriptors[]{{8, 0, 3, handles.read_token, 0, 0}};
    options.descriptor_count = 1; options.descriptors = descriptors;
    options.prepare_child = reject_after_mapping;
    const char* argv[]{"pipe_transfer", "unreachable"};
    need(sdk::spawn_file_options("/bin/pipe_transfer.elf", 2, argv, options) == process_error_invalid &&
         callback_count == 0, "default-false-unrouted-rejection");
    options.transfer_independent_pipes = true;
    need(sdk::spawn_file_options("/bin/pipe_transfer.elf", 2, argv, options) == process_error_resources &&
         callback_count == 1, "post-transfer-mapping-callback-failure");
    close(handles.read_token);
    const char byte = 'X';
    need(sdk::syscall(sys_pipe_write, handles.write_token, reinterpret_cast<u64>(&byte), 1) == pipe_error_broken,
         "aborted-child-reader-reclaimed");
    close(handles.write_token); zero_pipe_credit();
    options.replace_image = true;
    need(sdk::spawn_file_options("/bin/pipe_transfer.elf", 2, argv, options) == process_error_invalid,
         "explicit-transfer-cannot-mix-with-replacement");
}
u64 number(const char* text) {
    u64 value = 0;
    for (; *text; ++text) {
        need(*text >= '0' && *text <= '9', "decimal");
        value = value * 10 + static_cast<u64>(*text - '0');
    }
    return value;
}
void decimal(u32 number, char (&text)[11]) {
    char reverse[10]; u32 count = 0;
    do { reverse[count++] = static_cast<char>('0' + number % 10); number /= 10; } while (number);
    for (u32 i = 0; i < count; ++i) text[i] = reverse[count - i - 1];
    text[count] = 0;
}
void positive_child(const startup_info* startup, u64 foreign) {
    const auto* extension = reinterpret_cast<const startup_exec_extension*>(
        reinterpret_cast<const u8*>(startup) + startup_exec_offset);
    need(extension->magic == startup_exec_magic && extension->count == 5, "child-snapshot");
    const auto* descriptors = reinterpret_cast<const startup_descriptor*>(extension->descriptors);
    const auto& reader = descriptors[3]; const auto& writer = descriptors[4];
    need(reader.fd == 8 && reader.kind == 3 && writer.fd == 9 && writer.kind == 4, "child-independent-kinds");
    char byte = 'Y';
    const auto unowned = sdk::syscall(sys_pipe_read, foreign, reinterpret_cast<u64>(&byte), 1);
    need(unowned == process_error_denied, "child-no-ambient-foreign-token", unowned);
    need(sdk::syscall(sys_pipe_write, reader.handle, reinterpret_cast<u64>(&byte), 1) == process_error_denied &&
         sdk::syscall(sys_pipe_read, writer.handle, reinterpret_cast<u64>(&byte), 1) == process_error_denied,
         "child-native-direction");
    need(sdk::syscall(sys_pipe_write, writer.handle, reinterpret_cast<u64>(&byte), 1) == 1 &&
         sdk::syscall(sys_pipe_read, reader.handle, reinterpret_cast<u64>(&byte), 1) == 1 && byte == 'Y',
         "child-private-token-read-write");
    close(writer.handle);
    const auto now = sdk::syscall(sys_clock_monotonic); need(now >= 0, "child-clock");
    const auto deadline = static_cast<u64>(now) + 2'000'000'000;
    for (;;) {
        const auto value = sdk::syscall(sys_pipe_read, reader.handle, reinterpret_cast<u64>(&byte), 1);
        if (!value) break;
        need(value == process_error_would_block && sdk::syscall(sys_clock_monotonic) < static_cast<i64>(deadline), "child-parent-last-close", value);
        sdk::yield();
    }
    close(reader.handle);
}
void positive() {
    const auto handles = pipe(); const auto foreign = pipe();
    char token[11]; decimal(foreign.read_token, token);
    const char* argv[]{"pipe_transfer", "child", token};
    const startup_descriptor descriptors[]{
        {0, 0, 1, 0, 0, 0}, {1, 1, 1, 1, 1, 0}, {2, 2, 1, 2, 1, 0},
        {8, 3, 3, handles.read_token, 0, 0}, {9, 4, 4, handles.write_token, 1, 0}};
    sdk::spawn_options options{};
    options.descriptor_count = 5; options.descriptors = descriptors; options.transfer_independent_pipes = true;
    const auto child = sdk::spawn_file_options("/bin/pipe_transfer.elf", 3, argv, options);
    need(child > 0, "positive-loader", child);
    close(handles.read_token); close(handles.write_token);
    process_status status{};
    need(!sdk::wait(static_cast<u64>(child), status) && status.outcome == process_outcome::exited && !status.code,
         "positive-wait", status.code);
    need(budget().usage.pipes == 1, "exited-child-last-reference-reclaimed");
    close(foreign.read_token); close(foreign.write_token); zero_pipe_credit();
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    const auto argv = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc == 3 && sdk::equal(argv[1], "child")) { positive_child(startup, number(argv[2])); return 0; }
    need(startup->argc == 2, "arguments");
    const auto initial = budget();
    process_budget_vector limits{3, initial.attributed.pages * 4 + 512, 3, 0, 0, 8};
    need(!sdk::set_process_budget(sdk::pid(), limits), "set-cumulative-budget");
    const auto before = budget();
    if (sdk::equal(argv[1], "invalid")) invalid();
    else if (sdk::equal(argv[1], "readonly")) readonly_output();
    else if (sdk::equal(argv[1], "pending")) pending();
    else if (sdk::equal(argv[1], "capacity")) capacity();
    else if (sdk::equal(argv[1], "loader")) loader();
    else if (sdk::equal(argv[1], "positive")) positive();
    else fail("unknown-mode");
    const auto after = budget();
    need(after.usage.processes == before.usage.processes && after.usage.threads == before.usage.threads &&
         after.usage.pages == before.usage.pages && after.usage.pipes == before.usage.pipes, "budget-recovered");
    sdk::print("PIPE_TRANSFER_PASS "); sdk::print(argv[1]); sdk::print("\n"); return 0;
}
