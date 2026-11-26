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
    grant_login_resource, read_login_resource,
    admit_resource_broker, begin_resource_read,
    put_named_resource, read_named_resource, erase_named_resource,
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

// Anchored native-login profile only. The registrar proposes the exact
// daemon-side endpoint pair and its authenticated holder for the read grant.
struct login_resource_grant {
    u64 holder = 0;
    u32 send = 0, receive = 0;
};
static_assert(sizeof(login_resource_grant) == 16);
struct resource_broker_grant {
    u64 peer = 0;
    u32 send = 0, receive = 0;
};
static_assert(sizeof(resource_broker_grant) == 16);
// Explicit named-store developer profile. The service resolves the logical
// name and the expected object generation within its private namespace.
struct named_resource_request {
    u64 generation = 0;
    u32 data = 0;
    u8 length = 0;
    u8 reserved[3]{};
    char name[16]{};
};
static_assert(sizeof(named_resource_request) == name_limit);
inline bool valid_named_request(const named_resource_request& input, bool writing = false) {
    return input.length <= sizeof(input.name) && valid_name({input.name, input.length}) &&
        !has_bytes(input.reserved, sizeof(input.reserved)) &&
        !has_bytes(reinterpret_cast<const u8*>(input.name) + input.length, sizeof(input.name) - input.length) &&
        (writing || input.data == 0);
}
struct wire_extension {
    void* context;
    status (*invoke)(void*, service_core&, const connection_id&, const wire_request&, u64, wire_reply&);
    wire_operation first = wire_operation::grant_login_resource;
    wire_operation last = wire_operation::read_login_resource;
};

// Dispatcher inputs already belong to a server-owned authenticated binding.
// A false return indicates malformed/replayed input. Close the connection.
bool dispatch_request(service_core& core, const connection_id& connection, u64& last_sequence,
                      const wire_request& request, u64 now, wire_reply& reply,
                      const wire_extension* extension = nullptr);
bool valid_reply(const wire_request& request, const wire_reply& reply);

}
