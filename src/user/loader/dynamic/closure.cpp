// SPDX-License-Identifier: Apache-2.0
#include "startup.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::dynamic {
namespace {
launch_policy policy{};
activation_catalog catalog;
file::client files;
closure preflight;
u64 owner_pid = 0, policy_lock = 0;
bool initialized = false, files_initialized = false, poisoned = false;

struct guard {
    bool acquired = false;
    guard() {
        const u64 self = sdk::pid();
        u64 expected = __atomic_load_n(&policy_lock, __ATOMIC_RELAXED);
        if (self && expected != self)
            acquired = __atomic_compare_exchange_n(&policy_lock, &expected, self, false,
                                                   __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
        if (acquired && owner_pid != self) {
            owner_pid = self;
            files_initialized = false;
            // A fork retains its private approved policy snapshot. It neither
            // synchronizes revocation with the parent nor closes parent pins.
        }
    }
    ~guard() { if (acquired) __atomic_store_n(&policy_lock, 0, __ATOMIC_RELEASE); }
};
bool bytes_equal(const u8* left, const u8* right, u32 count) {
    u8 difference = 0;
    for (u32 i = 0; i < count; ++i) difference |= left[i] ^ right[i];
    return difference == 0;
}
bool nonzero(const u8* bytes, u32 count) {
    u8 result = 0;
    for (u32 i = 0; i < count; ++i) result |= bytes[i];
    return result != 0;
}
bool valid_path(const char* path, bool padded) {
    if (!path || path[0] != '/') return false;
    u32 length = 0;
    while (length < 128 && path[length]) ++length;
    if (length < 2 || length == 128 || path[length - 1] == '/') return false;
    u32 component = 1;
    for (u32 i = 1; i <= length; ++i) {
        const char c = path[i];
        if (c == '/' || !c) {
            if (i == component || (i - component == 1 && path[component] == '.') ||
                (i - component == 2 && path[component] == '.' && path[component + 1] == '.')) return false;
            component = i + 1;
        } else if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                     (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.' || c == '+')) return false;
    }
    if (padded) for (u32 i = length; i < 128; ++i) if (path[i]) return false;
    return true;
}
bool same_path(const char* left, const char* right) {
    for (u32 i = 0; i < 128; ++i) {
        if (left[i] != right[i]) return false;
        if (!left[i]) return true;
    }
    return false;
}
i64 deadline_now(u64 deadline, u64& now) {
    const i64 result = sdk::syscall(sys_clock_monotonic);
    if (result < 0) return result;
    now = static_cast<u64>(result);
    if (!deadline || deadline > 0x7fffffffffffffffULL) return process_error_invalid;
    if (deadline <= now) return thread_error_timeout;
    if (deadline - now > startup_deadline_limit_ns) return process_error_invalid;
    return 0;
}
bool unknown_result(i64 result) {
    return result == file::transport_timeout || result == static_cast<i64>(file::status::io);
}
void record_error(closure& value, i64 result) {
    if (result && !value.native_error) value.native_error = result;
    if (unknown_result(result)) { value.quarantined = true; poisoned = true; }
}
i64 close_pin(pinned_object& pin, closure& value) {
    if (!pin.handle) return 0;
    if (!pin.client || !pin.client->set_deadline(value.deadline)) {
        record_error(value, process_error_invalid);
        value.quarantined = true;
        return process_error_invalid;
    }
    const i64 result = pin.client->close(pin.handle);
    if (result) {
        record_error(value, result);
        value.quarantined = true;
        // Even a definite close failure keeps the token. No automatic retry
        // may conflate a delayed reply with a later side effect.
        return result;
    }
    pin.handle = 0;
    pin.cache_length = 0;
    return 0;
}
i64 release_inner(closure& value) {
    if (value.quarantined) return value.native_error ? value.native_error : process_error_state;
    for (auto& pin : value.pins) {
        const i64 result = close_pin(pin, value);
        if (result) return result;
    }
    const i64 result = close_pin(value.manifest_pin, value);
    if (result) return result;
    value.live = false;
    return 0;
}
bool has_tokens(const closure& value) {
    if (value.manifest_pin.handle) return true;
    for (const auto& pin : value.pins) if (pin.handle) return true;
    return false;
}
error fail(closure& value, error result) {
    if (!value.quarantined && release_inner(value)) return error::io;
    return result;
}
error open_pin(const char* path, pinned_object& pin, closure& value, u64 expected_size = 0) {
    pin = {};
    pin.client = &files;
    pin.deadline = value.deadline;
    u32 version = 0;
    i64 result = files.open(path, file::read_only | file::open_pin, pin.handle, pin.size, version);
    if (result) { pin.native_error = result; record_error(value, result); return error::io; }
    if (!pin.handle) { record_error(value, static_cast<i64>(file::status::io)); return error::io; }
    if (!pin.size || (expected_size && pin.size != expected_size)) return error::bounds;
    u32 size = 0, attributes = 0;
    result = files.fstat(pin.handle, size, attributes, pin.inode);
    if (result) { pin.native_error = result; record_error(value, result); return error::io; }
    if (!pin.inode || size != pin.size || (attributes & file::stat_is_directory)) return error::identity;
    return error::none;
}
error acquire_inner(const launch_policy& selected, u32 index, const char* requested,
                    u64 deadline, closure& output) {
    if (output.live || output.quarantined || has_tokens(output) || poisoned || index >= selected.count) return error::state;
    if (selected.revoked & (1u << index)) return error::revoked;
    u64 begin = 0;
    const i64 clock_error = deadline_now(deadline, begin);
    if (clock_error) { output.native_error = clock_error; return error::budget; }
    output = {};
    output.live = true;
    output.deadline = deadline;
    output.ticket = {selected.roots[index].root, selected.sequence, index, 0};
    if (!files.set_deadline(deadline)) return fail(output, error::budget);
    if (!files_initialized) {
        if (!files.init()) { output.native_error = static_cast<i64>(file::status::io); return fail(output, error::io); }
        files_initialized = true;
    }
    error result = open_pin(selected.roots[index].manifest, output.manifest_pin, output);
    if (result != error::none) return fail(output, result);
    result = read_generation(pin_read, &output.manifest_pin, output.manifest_pin.size,
                             selected.roots[index].root, selected.sdk_sha256, output.value);
    if (result != error::none) {
        record_error(output, output.manifest_pin.native_error);
        return fail(output, result);
    }
    const u64 budget = output.value.header.startup_budget_ns;
    if (begin <= ~u64{0} - budget && begin + budget < output.deadline) output.deadline = begin + budget;
    output.manifest_pin.deadline = output.deadline;
    (void)files.set_deadline(output.deadline);
    u64 now = 0;
    const i64 expired = deadline_now(output.deadline, now);
    if (expired) { record_error(output, expired); return fail(output, error::budget); }
    if (requested && !same_path(requested, output.value.objects[2].path)) return fail(output, error::not_selected);
    if (close_pin(output.manifest_pin, output)) return error::io;
    for (u32 i = 0; i < output.value.header.object_count; ++i) {
        auto& pin = output.pins[i];
        const auto& object = output.value.objects[i];
        result = open_pin(object.path, pin, output, object.file_bytes);
        if (result == error::none) result = verify_object(pin_read, &pin, object);
        if (result == error::none && i == 0) {
            elf::load_plan bootstrap{};
            if (object.file_bytes > 131072) result = error::budget;
            else {
                const auto parsed = elf::inspect_reader(pin_read, &pin, object.file_bytes,
                                                        elf::machine_x86_64, bootstrap);
                if (parsed != elf::error::none)
                    result = parsed == elf::error::io ? error::io : error::header;
                else for (u32 segment = 0; segment < bootstrap.count; ++segment) {
                    const auto& load = bootstrap.segments[segment];
                    const u64 first = load.address & ~u64{4095};
                    const u64 end = (load.address + load.memory_bytes + 4095) & ~u64{4095};
                    // Ordinary static ELFs retain their legacy address range.
                    // This bootstrap must also leave worker storage and the
                    // read-only launch capsule available to the new image.
                    if ((first < thread_arena_end && thread_arena_begin < end)
                        || (first < capsule_end && XOS_DYNAMIC_STARTUP_ADDRESS < end)) {
                        result = error::bounds;
                        break;
                    }
                }
            }
        } else if (result == error::none) {
            result = inspect_elf(pin_read, &pin, output.value, i, output.images[i]);
        }
        if (result != error::none) {
            record_error(output, pin.native_error);
            return fail(output, result);
        }
    }
    result = check_versions(output.value, output.images);
    if (result != error::none) return fail(output, result);
    const i64 final_clock = deadline_now(output.deadline, now);
    if (final_clock) { record_error(output, final_clock); return fail(output, error::budget); }
    return error::none;
}
error validate_policy(const launch_policy& value, activation_catalog& destination) {
    if (!value.count || value.count > activation_max_generations || value.reserved ||
        !nonzero(value.sdk_sha256, sizeof(value.sdk_sha256))) return error::state;
    generation_root roots[activation_max_generations]{};
    for (u32 i = 0; i < value.count; ++i) {
        if (!valid_path(value.roots[i].manifest, true)) return error::path;
        roots[i] = value.roots[i].root;
        for (u32 j = 0; j < i; ++j)
            if (same_path(value.roots[i].manifest, value.roots[j].manifest)) return error::duplicate;
    }
    for (u32 i = value.count; i < activation_max_generations; ++i) {
        const auto* bytes = reinterpret_cast<const u8*>(&value.roots[i]);
        if (nonzero(bytes, sizeof(value.roots[i]))) return error::state;
    }
    return destination.restore(roots, value.count, value.active, value.sequence, value.revoked);
}
}

bool pin_read(void* context, u64 offset, u8* destination, u32 length) {
    if (!context || (!destination && length)) return false;
    auto& pin = *static_cast<pinned_object*>(context);
    if (!pin.client || !pin.handle || pin.native_error || offset > pin.size || length > pin.size - offset) return false;
    u64 now = 0;
    pin.native_error = deadline_now(pin.deadline, now);
    if (pin.native_error) return false;
    if (!pin.client->set_deadline(pin.deadline)) { pin.native_error = process_error_invalid; return false; }
    while (length) {
        if (!pin.cache_length || offset < pin.cache_begin || offset - pin.cache_begin >= pin.cache_length) {
            pin.cache_begin = static_cast<u32>(offset & ~u64{4095});
            const u32 available = pin.size - pin.cache_begin;
            const u32 wanted = available < sizeof(pin.cache) ? available : sizeof(pin.cache);
            pin.cache_length = 0;
            while (pin.cache_length < wanted) {
                const u32 remaining = wanted - pin.cache_length;
                const u32 count = remaining < file::response_data_size ? remaining : file::response_data_size;
                const i64 received = pin.client->read_at(pin.handle, pin.cache + pin.cache_length,
                                                        count, u64{pin.cache_begin} + pin.cache_length);
                if (received <= 0 || static_cast<u64>(received) > count) {
                    pin.native_error = received < 0 ? received : static_cast<i64>(file::status::io);
                    pin.cache_length = 0;
                    return false;
                }
                pin.cache_length += static_cast<u32>(received);
            }
        }
        const u32 within = static_cast<u32>(offset - pin.cache_begin);
        const u32 available = pin.cache_length - within;
        const u32 count = available < length ? available : length;
        for (u32 i = 0; i < count; ++i) destination[i] = pin.cache[within + i];
        destination += count;
        offset += count;
        length -= count;
        pin.native_error = deadline_now(pin.deadline, now);
        if (pin.native_error) return false;
    }
    return true;
}

bool configured() { return __atomic_load_n(&initialized, __ATOMIC_ACQUIRE); }

error configure(const launch_policy& supplied, u64 absolute_deadline) {
    guard held;
    if (!held.acquired || initialized || poisoned || preflight.live || preflight.quarantined) return error::state;
    const launch_policy snapshot = supplied;
    activation_catalog candidate;
    error result = validate_policy(snapshot, candidate);
    if (result != error::none) return result;
    if (snapshot.active >= snapshot.count) return error::revoked;
    result = acquire_inner(snapshot, snapshot.active, nullptr, absolute_deadline, preflight);
    if (result != error::none) return result;
    if (release_inner(preflight)) return error::io;
    u64 now = 0;
    if (deadline_now(preflight.deadline, now)) return error::budget;
    policy = snapshot;
    catalog = candidate;
    __atomic_store_n(&initialized, true, __ATOMIC_RELEASE);
    return error::none;
}

error export_policy(launch_policy& output) {
    guard held;
    if (!held.acquired || !initialized || poisoned) return error::state;
    output = policy;
    return error::none;
}

error acquire(const char* path, u64 deadline, closure& output) {
    if (!valid_path(path, false)) return error::path;
    guard held;
    if (!held.acquired || !initialized || poisoned) return error::state;
    activation_ticket ticket{};
    const error result = catalog.capture(ticket);
    if (result != error::none) return result;
    return acquire_inner(policy, ticket.index, path, deadline, output);
}

error acquire_index(u32 index, u64 deadline, closure& output) {
    guard held;
    if (!held.acquired || !initialized || poisoned) return error::state;
    return acquire_inner(policy, index, nullptr, deadline, output);
}

i64 release(closure& value) {
    guard held;
    if (!held.acquired) return thread_error_busy;
    return release_inner(value);
}

error activate(u32 index, u64 expected_sequence, u64 deadline) {
    guard held;
    if (!held.acquired || !initialized || poisoned) return error::state;
    if (catalog.sequence() != expected_sequence) return error::stale;
    error result = acquire_inner(policy, index, nullptr, deadline, preflight);
    if (result != error::none) return result;
    if (release_inner(preflight)) return error::io;
    u64 now = 0;
    if (deadline_now(preflight.deadline, now)) return error::budget;
    result = catalog.activate(index, expected_sequence);
    if (result == error::none) { policy.active = index; policy.sequence = catalog.sequence(); }
    return result;
}

error revoke(u32 index, u64 expected_sequence) {
    guard held;
    if (!held.acquired || !initialized) return error::state;
    const error result = catalog.revoke(index, expected_sequence);
    if (result == error::none) {
        policy.revoked |= 1u << index;
        if (policy.active == index) policy.active = activation_max_generations;
        policy.sequence = catalog.sequence();
    }
    return result;
}

i64 admission(void*, u64 child, const launch::artifact& current,
              const launch::artifact& requested, u64 deadline) {
    if (!child || !requested.id || !nonzero(requested.sha256, sizeof(requested.sha256))) return process_error_denied;
    u64 now = 0;
    const i64 expired = deadline_now(deadline, now);
    if (expired) return expired;
    guard held;
    if (!held.acquired) return thread_error_busy;
    if (!initialized || poisoned) return process_error_denied;
    bool known_current = !current.id && !nonzero(current.sha256, sizeof(current.sha256));
    u32 selected = activation_max_generations;
    for (u32 i = 0; i < policy.count; ++i) {
        const auto& root = policy.roots[i].root;
        if (root.id == current.id && bytes_equal(root.sha256, current.sha256, 32)) known_current = true;
        if (root.id == requested.id && bytes_equal(root.sha256, requested.sha256, 32)) selected = i;
    }
    if (!known_current || selected == activation_max_generations) return process_error_denied;
    const activation_ticket ticket{policy.roots[selected].root, policy.sequence, selected, 0};
    return catalog.admit(ticket) == error::none ? 0 : process_error_denied;
}
}
