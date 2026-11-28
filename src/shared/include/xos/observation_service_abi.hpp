// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::observation {
inline constexpr u32 version = 1;
inline constexpr u32 max_clients = 4, max_reads = 64;
inline constexpr u64 max_request_ns = 5'000'000'000ULL;
inline constexpr u64 max_grant_ns = 30'000'000'000ULL;
enum class kind : u32 { process = 1, service, resource, runtime, network, trust };
enum class scope : u32 { self = 1, direct_child, held_endpoint, controller, service, application };
enum class status : u32 { ok, invalid, unauthorized, stale, revoked, deadline, quota, unavailable, unsupported };
inline constexpr u32 all_kinds = 63;
constexpr u32 mask(kind value) {
    const u32 number = static_cast<u32>(value);
    return number >= 1 && number <= 6 ? u32{1} << (number - 1) : 0;
}
// The only wire operation is read=1. No body field conveys authority.
struct request {
    u32 version, size, operation;
    kind subject;
    u64 sequence, deadline_ns, server_epoch, expected_object, expected_generation, reserved;
};
// Fixed, typed per-kind fields; unused words and digest bytes MUST be zero.
// process: parent_pid,state,threads; service: owner_pid,interface_version,state;
// resource: owner_pid,channels_used,channel_limit,names_used,name_limit,parent_pid;
// runtime: controller_pid + digest; network: service_pid,mode,state;
// trust: owner_pid + digest of the owner's selected, ready/verified snapshot.
struct data { u64 values[10]; u8 digest[32]; };
struct response {
    u32 version, size;
    status outcome;
    kind subject;
    scope origin;
    u32 reserved;
    u64 sequence, observation_id, server_pid, server_epoch, caller_pid;
    u64 observed_at_ns, valid_until_ns, object_id, generation;
    data value;
};
static_assert(sizeof(request) == 64);
static_assert(sizeof(data) == 112);
static_assert(sizeof(response) == 208);
}
