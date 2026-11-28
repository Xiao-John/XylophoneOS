// SPDX-License-Identifier: Apache-2.0
#include "startup.hpp"
#include <xos/execution.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::dynamic {
namespace {
closure selected;
alignas(4096) startup_capsule capsule;
alignas(4096) u8 capsule_page[4096];
u64 operation_owner;
launch::descriptor active_control{};
launch::artifact active_artifact{};
bool replacing, registered, exec_pins_moved;
u64 prepared_child;

struct guard {
    bool acquired;
    guard() : acquired(false) {
        u64 expected = 0;
        acquired = __atomic_compare_exchange_n(&operation_owner, &expected, sdk::pid(), false,
                                               __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
    }
    ~guard() { if (acquired) __atomic_store_n(&operation_owner, 0, __ATOMIC_RELEASE); }
};
i64 status(error value, const closure& source) {
    if (source.native_error < 0) return source.native_error;
    if (value == error::budget || value == error::bounds) return process_error_resources;
    if (value == error::state || value == error::stale) return process_error_state;
    return process_error_denied;
}
u64 deadline() {
    const auto now = sdk::syscall(sys_clock_monotonic);
    return now < 0 || static_cast<u64>(now) > 0x7fffffffffffffffULL - startup_deadline_limit_ns
        ? 0 : static_cast<u64>(now) + startup_deadline_limit_ns;
}
launch::artifact artifact(const activation_ticket& ticket) {
    launch::artifact result{};
    result.id = ticket.root.id;
    for (u32 i = 0; i < 32; ++i) result.sha256[i] = ticket.root.sha256[i];
    return result;
}
void fill_capsule(const launch::descriptor& control) {
    capsule = {};
    capsule.prefix = {XOS_DYNAMIC_STARTUP_MAGIC, XOS_DYNAMIC_STARTUP_VERSION, sizeof(capsule),
                      control, artifact(selected.ticket), {}};
    (void)export_policy(capsule.policy);
    capsule.selected = selected.value;
    for (u32 i = 1; i < selected.value.header.object_count; ++i) {
        const auto& source = selected.images[i];
        auto& destination = capsule.images[i];
        destination.entry = source.entry;
        destination.phoff = source.phoff;
        destination.phaddr = source.phaddr;
        destination.phnum = source.phnum;
        destination.load_count = source.load_count;
        for (u32 j = 0; j < source.load_count; ++j) destination.loads[j] = source.loads[j];
    }
}
i64 prepare(u64 child, void*) {
    prepared_child = child;
    launch::descriptor control = capsule.prefix.control;
    if (!replacing) {
        const i64 recorded = launch::record_child(child, selected.deadline, control,
                                                  artifact(selected.ticket), admission);
        if (recorded != 0) return recorded;
        registered = true;
        capsule.prefix.control = control;
    }
    for (u32 i = 1; i < selected.value.header.object_count; ++i) {
        auto& pin = selected.pins[i];
        u32 handle = pin.handle;
        if (!replacing) {
            const i64 transferred = pin.client->transfer(pin.handle, child, handle);
            if (transferred != 0) return transferred;
        }
        capsule.pins[i] = {handle, pin.inode};
    }
    if (!validate_capsule(capsule)) return process_error_denied;
    const auto* bytes = reinterpret_cast<const u8*>(&capsule);
    for (u32 page = 0; page < capsule_pages; ++page) {
        for (u32 i = 0; i < sizeof(capsule_page); ++i) {
            const u32 at = page * 4096 + i;
            capsule_page[i] = at < sizeof(capsule) ? bytes[at] : 0;
        }
        const process_page mapping{XOS_DYNAMIC_STARTUP_ADDRESS + u64{page} * 4096,
                                   reinterpret_cast<u64>(capsule_page), 4096, map_read};
        const i64 mapped = sdk::syscall(sys_process_map, child, reinterpret_cast<u64>(&mapping));
        if (mapped != 0) return mapped;
    }
    if (replacing) {
        // Exec preserves the process's Files owner. These exact open
        // descriptions pass to the new bootstrap, never a reopened path.
        for (u32 i = 1; i < selected.value.header.object_count; ++i) selected.pins[i].handle = 0;
        exec_pins_moved = true;
    }
    return release(selected);
}
bool match_receipt(const execution::image_receipt* expected) {
    if (expected == nullptr) return true;
    const auto& main = selected.value.objects[2];
    if (expected->size != main.file_bytes) return false;
    for (u32 i = 0; i < 32; ++i) if (expected->digest[i] != main.sha256[i]) return false;
    return true;
}
}
}

extern "C" bool xos_dynamic_spawn_hook(const char* path, xos::u32 argc, const char* const* argv,
    const xos::sdk::spawn_options* input, xos::execution::launch_diagnostic* reported,
    xos::execution::image_receipt* receipt, const xos::execution::image_receipt* expected, xos::i64* output) {
    using namespace xos;
    using namespace xos::dynamic;
    if (!configured()) return false;
    guard held;
    execution::launch_diagnostic local{};
    auto& diagnostic = reported ? *reported : local;
    diagnostic = {execution::launch_stage::inspect, process_error_denied, elf::error::header};
    if (!held.acquired || !path || !argc || argc > process_max_args || !argv) {
        *output = held.acquired ? process_error_invalid : process_error_busy;
        diagnostic.code = *output;
        return true;
    }
    const auto admitted = acquire(path, deadline(), selected);
    if (admitted == error::not_selected) return false;
    if (admitted != error::none) { *output = status(admitted, selected); diagnostic.code = *output; return true; }
    if (!match_receipt(expected)) {
        (void)release(selected);
        *output = process_error_denied;
        return true;
    }
    if (receipt) {
        receipt->size = static_cast<u32>(selected.value.objects[2].file_bytes);
        for (u32 i = 0; i < 32; ++i) receipt->digest[i] = selected.value.objects[2].sha256[i];
    }
    sdk::spawn_options options = input ? *input : sdk::spawn_options{};
    replacing = options.replace_image;
    registered = exec_pins_moved = false;
    prepared_child = 0;
    launch::descriptor pending{};
    u32 channels[exec_preserve_channels_max]{};
    i64 result = 0;
    if (replacing) {
        if (!active_control.magic || options.exec_channel_count > exec_preserve_channels_max - 2
            || (options.exec_channel_count && !options.exec_channels)) result = process_error_denied;
        else result = launch::prepare_exec(active_control, selected.deadline, artifact(selected.ticket), pending);
        if (result == 0) {
            for (u32 i = 0; i < options.exec_channel_count; ++i) channels[i] = options.exec_channels[i];
            channels[options.exec_channel_count++] = pending.ready_handle;
            channels[options.exec_channel_count++] = pending.ack_handle;
            options.exec_channels = channels;
        }
    }
    if (result == 0) {
        fill_capsule(pending);
        result = execution::spawn_pinned_image(path, selected.value.objects[0].file_bytes,
            pin_read, &selected.pins[0], argc, argv, options, diagnostic,
            selected.deadline, prepare, nullptr);
    }
    if (result < 0 && exec_pins_moved) {
        // Commit failed: the old image still owns the moved handles.
        selected.live = true;
        for (u32 i = 1; i < capsule.selected.header.object_count; ++i)
            selected.pins[i].handle = capsule.pins[i].handle;
    }
    const i64 closed = release(selected);
    if (result >= 0 && closed < 0) result = closed;
    if (result < 0) {
        if (pending.magic) (void)launch::cancel_exec(pending, capsule.prefix.artifact);
        if (registered) (void)launch::close_control(prepared_child);
    } else {
        launch::diagnostic readiness{};
        const i64 ready = launch::await_ready(static_cast<u64>(result), readiness);
        if (ready != 0) {
            (void)sdk::syscall(sys_process_cancel, static_cast<u64>(result));
            process_status ended{};
            (void)launch::wait(static_cast<u64>(result), ended);
            result = ready;
            diagnostic = {execution::launch_stage::start, ready, elf::error::none};
        }
    }
    if (result < 0 && receipt) *receipt = {};
    *output = result;
    return true;
}

extern "C" bool xos_dynamic_inspect_hook(const char* path, xos::execution::candidate* output) {
    using namespace xos;
    using namespace xos::dynamic;
    if (!configured()) return false;
    guard held;
    if (!held.acquired) { output->error = process_error_busy; return true; }
    const auto admitted = acquire(path, deadline(), selected);
    if (admitted == error::not_selected) return false;
    const i64 closed = release(selected);
    output->kind = admitted == error::none && !closed
        ? execution::candidate_kind::executable : execution::candidate_kind::not_executable;
    output->error = closed ? closed : admitted == error::none ? 0 : status(admitted, selected);
    return true;
}

extern "C" long xos_dynamic_adopt_startup(xos::u64 deadline) {
    using namespace xos;
    using namespace xos::dynamic;
    const auto& startup = *reinterpret_cast<const startup_capsule*>(XOS_DYNAMIC_STARTUP_ADDRESS);
    if (!validate_capsule(startup) || startup.prefix.control.child_pid != sdk::pid()
        || startup.prefix.control.deadline != deadline) return -22;
    if (configure(startup.policy, deadline) != error::none) return -8;
    active_control = startup.prefix.control;
    active_artifact = startup.prefix.artifact;
    return 0;
}
