// SPDX-License-Identifier: Apache-2.0
#include <xos/observation_sources.hpp>
#include <xos/observation_abi.hpp>
#include <xos/sdk.hpp>

namespace xos::observation {
namespace {
status native_result(observe_native::result result) {
    switch (result) {
    case observe_native::result::ok: return status::ok;
    case observe_native::result::denied: return status::unauthorized;
    case observe_native::result::invalid: return status::invalid;
    case observe_native::result::stale: return status::stale;
    case observe_native::result::deadline: return status::deadline;
    case observe_native::result::exhausted: return status::quota;
    case observe_native::result::unavailable: return status::unavailable;
    }
    return status::unsupported;
}
}
status sources::capture(void* context, kind subject, u64 deadline, response& output) {
    output = {};
    if (!context) return status::unavailable;
    auto& source = *static_cast<sources*>(context);
    if (subject == kind::process || subject == kind::resource || subject == kind::service) {
        observe_native::request input{};
        input.version = observe_native::version; input.size = sizeof(input);
        input.kind = subject == kind::process ? observe_native::query::process :
            subject == kind::resource ? observe_native::query::resources : observe_native::query::service;
        input.target = subject == kind::service ? source.service_endpoint : source.process_target;
        output.origin = subject == kind::service ? scope::held_endpoint :
            source.process_target && source.process_target != sdk::pid() ? scope::direct_child : scope::self;
        if (subject == kind::service && !source.service_endpoint) return status::unavailable;
        input.deadline_ns = deadline;
        observe_native::snapshot value{};
        const auto result = sdk::observe(input, value);
        if (result != observe_native::result::ok) return native_result(result);
        output.object_id = value.pid; output.generation = value.image_generation;
        if (subject == kind::process) {
            output.value.values[0] = value.parent_pid;
            output.value.values[1] = static_cast<u32>(value.process_state);
            output.value.values[2] = value.threads;
        } else if (subject == kind::resource) {
            output.value.values[0] = value.pid;
            output.value.values[1] = value.owned_channels; output.value.values[2] = value.channel_limit;
            output.value.values[3] = value.owned_names; output.value.values[4] = value.name_limit;
            output.value.values[5] = value.parent_pid;
        } else {
            output.object_id = value.object_token;
            output.value.values[0] = value.pid; output.value.values[1] = version; output.value.values[2] = 1;
        }
        return status::ok;
    }
    if (subject == kind::runtime) {
        output.origin = scope::controller;
        if (!source.runtime) return status::unavailable;
        dynamic::activation_ticket value{};
        const auto result = source.runtime->capture(value);
        if (result != dynamic::error::none)
            return result == dynamic::error::revoked ? status::revoked : status::unavailable;
        output.object_id = value.root.id; output.generation = value.sequence;
        output.value.values[0] = sdk::pid();
        __builtin_memcpy(output.value.digest, value.root.sha256, 32);
        return status::ok;
    }
    if (subject == kind::network) {
        output.origin = scope::service;
        if (!source.network) return status::unavailable;
        const u64 network_pid = source.network->authenticated_service_pid();
        if (!network_pid) return status::unavailable;
        net2::config_snapshot value{};
        const i64 result = source.network->configuration(deadline, value);
        if (result) {
            if (result == net2::timeout) return status::deadline;
            if (result == net2::denied) return status::unauthorized;
            if (result == net2::unsupported) return status::unsupported;
            if (result == net2::resources) return status::quota;
            if (result == net2::closed) return status::revoked;
            return status::unavailable;
        }
        output.object_id = network_pid; output.generation = value.epoch;
        output.value.values[0] = network_pid;
        output.value.values[1] = static_cast<u32>(value.mode);
        output.value.values[2] = value.address && value.mode != net2::network_mode::disabled ? 1 : 0;
        return status::ok;
    }
    if (subject == kind::trust) {
        output.origin = scope::application;
        if (!source.trust_context || !source.trust_capture) return status::unavailable;
        trust_snapshot value{};
        const status result = source.trust_capture(source.trust_context, value);
        if (result != status::ok) return result;
        if (!value.generation) return status::unavailable;
        u8 present = 0; for (u8 byte : value.sha256) present |= byte;
        if (!present) return status::unavailable;
        output.object_id = output.generation = value.generation;
        output.value.values[0] = sdk::pid();
        __builtin_memcpy(output.value.digest, value.sha256, 32);
        return status::ok;
    }
    return status::unsupported;
}
}
