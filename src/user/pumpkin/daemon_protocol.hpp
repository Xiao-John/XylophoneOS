// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "service_core.hpp"

namespace xos::user::pumpkin {

// Private P1 integration profile. These values are outside the public SDK.
inline constexpr u32 wire_version = 1;
inline constexpr char test_service_name[] = "pumpkin-p1-test";
inline constexpr u64 max_request_ns = 5'000'000'000ull;
inline constexpr u64 reply_budget_ns = 500'000'000ull;
inline constexpr u64 loop_interval_ns = 1'000'000ull;

enum class wire_operation : u32 {
    authenticate = 1, logout, identity, create_account, lookup_account, rotate_credential, revoke_account,
};
enum class wire_status : u32 {
    ok = 0, invalid, denied, not_found, conflict, exhausted, unavailable, corrupt, io_error, outcome_unknown,
    expired,
};
struct wire_id {
    nonce scope;
    u64 number = 0;
};
struct wire_request {
    u32 version = wire_version;
    wire_operation operation{};
    u64 sequence = 0;
    u64 deadline = 0;
    wire_id token;
    u32 name_length = 0;
    u32 reserved = 0;
    char name[name_limit]{};
    credential key;
};
struct wire_reply {
    u32 version = wire_version;
    wire_operation operation{};
    u64 sequence = 0;
    wire_status result = wire_status::invalid;
    u32 flags = 0;
    wire_id token;
    credential key;
};
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
static_assert(sizeof(wire_request) == 120 && sizeof(wire_reply) == 80);

// Dispatcher inputs already belong to a server-owned authenticated binding.
// A false return indicates malformed/replayed input. Close the connection.
bool dispatch_request(service_core& core, const connection_id& connection, u64& last_sequence,
                      const wire_request& request, u64 now, wire_reply& reply);
bool valid_reply(const wire_request& request, const wire_reply& reply);

}
