// SPDX-License-Identifier: Apache-2.0
#include <xos/observation.hpp>
#include <xos/sdk.hpp>

namespace xos::observation {
namespace {
const char* kind_name(kind value) {
    switch (value) {
    case kind::process: return "process"; case kind::service: return "service";
    case kind::resource: return "resource"; case kind::runtime: return "runtime";
    case kind::network: return "network"; case kind::trust: return "trust";
    }
    return "invalid";
}
const char* scope_name(scope value) {
    switch (value) {
    case scope::self: return "self"; case scope::direct_child: return "direct_child";
    case scope::held_endpoint: return "held_endpoint"; case scope::controller: return "controller";
    case scope::service: return "service"; case scope::application: return "application";
    }
    return "invalid";
}
void number(const char* name, u64 value) { sdk::print(name); sdk::decimal(value); }
void digest(const u8* value) {
    constexpr char digits[] = "0123456789abcdef";
    char encoded[65]{};
    for (u32 i = 0; i < 32; ++i) {
        encoded[i * 2] = digits[value[i] >> 4]; encoded[i * 2 + 1] = digits[value[i] & 15];
    }
    sdk::print(encoded);
}
}
const char* status_name(status value) {
    switch (value) {
    case status::ok: return "ok"; case status::invalid: return "invalid";
    case status::unauthorized: return "unauthorized"; case status::stale: return "stale";
    case status::revoked: return "revoked"; case status::deadline: return "deadline";
    case status::quota: return "quota"; case status::unavailable: return "unavailable";
    case status::unsupported: return "unsupported";
    }
    return "invalid";
}
status print_json(const response& value) {
    if (!valid_response(value)) return status::invalid;
    sdk::print("{\"schema_version\":1");
    number(",\"observation_id\":", value.observation_id);
    number(",\"source\":{\"pid\":", value.server_pid);
    number(",\"epoch\":", value.server_epoch); sdk::print("}");
    number(",\"caller_pid\":", value.caller_pid);
    number(",\"logical_time_ns\":", value.observed_at_ns);
    number(",\"valid_until_ns\":", value.valid_until_ns);
    sdk::print(",\"status\":\""); sdk::print(status_name(value.outcome)); sdk::print("\",\"records\":[");
    if (value.outcome == status::ok) {
        sdk::print("{\"kind\":\""); sdk::print(kind_name(value.subject));
        sdk::print("\",\"scope\":\""); sdk::print(scope_name(value.origin));
        sdk::print("\",\"status\":\"ok\"");
        number(",\"object_id\":", value.object_id); number(",\"generation\":", value.generation);
        sdk::print(",\"data\":{");
        const auto* data = value.value.values;
        switch (value.subject) {
        case kind::process: {
            const char* states[]{"invalid", "building", "fresh", "ready", "running", "waiting", "dead"};
            number("\"parent_pid\":", data[0]); sdk::print(",\"state\":\"");
            sdk::print(states[data[1]]); sdk::print("\""); number(",\"threads\":", data[2]); break;
        }
        case kind::service:
            number("\"owner_pid\":", data[0]); number(",\"interface_version\":", data[1]);
            sdk::print(",\"state\":\"available\""); break;
        case kind::resource:
            number("\"owner_pid\":", data[0]); number(",\"endpoints_used\":", data[1]);
            number(",\"endpoint_limit\":", data[2]); number(",\"names_used\":", data[3]);
            number(",\"name_limit\":", data[4]); number(",\"parent_pid\":", data[5]); break;
        case kind::runtime:
            number("\"controller_pid\":", data[0]); sdk::print(",\"digest\":\"");
            digest(value.value.digest); sdk::print("\""); break;
        case kind::network: {
            const char* modes[]{"disabled", "static_direct", "dhcp"};
            number("\"service_pid\":", data[0]); sdk::print(",\"mode\":\"");
            sdk::print(modes[data[1]]); sdk::print("\",\"state\":\"");
            sdk::print(data[2] ? "ready" : "unconfigured"); sdk::print("\""); break;
        }
        case kind::trust:
            number("\"owner_pid\":", data[0]); sdk::print(",\"digest\":\"");
            digest(value.value.digest); sdk::print("\",\"selection\":\"loaded_snapshot\""); break;
        }
        sdk::print("}}");
    }
    sdk::print("]}\n"); return status::ok;
}
}
