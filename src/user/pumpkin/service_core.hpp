// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "account_store.hpp"
#include "session_limits.hpp"

namespace xos::user::pumpkin {

inline constexpr u32 client_limit = 16;

struct entropy_api {
    void* context = nullptr;
    bool (*fill)(void*, u8*, usize) = nullptr;
};

enum class admission_role { client, registrar };

struct connection_id {
    nonce incarnation;
    u64 number = 0;
    bool operator==(const connection_id&) const = default;
};

struct session_id {
    nonce incarnation;
    u64 number = 0;
    bool operator==(const session_id&) const = default;
};

struct resource_key {
    nonce registry;
    u64 number;
    u64 generation;
    bool operator==(const resource_key&) const = default;
};

inline constexpr u32 resource_read = 1u << 0;
inline constexpr u32 resource_write = 1u << 1;
inline constexpr u32 resource_manage = 1u << 2;

// Populated by the trusted object service from its own authorization and
// ownership state. These are never decoded from a client's request.
struct checked_rights {
    connection_id connection;
    resource_key object;
    u32 permitted;
};

struct owner_record {
    resource_key object;
    identity_id owner;
    u32 permitted;
};

struct account_description {
    identity_id identity;
    bool disabled = false;
};

// Single owner loop. Times and connection admission come from the trusted
// transport adapter. Only the connection's server-side binding selects its ID.
class service_core {
public:
    service_core() = default;
    service_core(const service_core&) = delete;
    service_core& operator=(const service_core&) = delete;

    status start(const store_api& store, const nonce& realm, const entropy_api& entropy);
    void stop();
    status attach(admission_role role, u64 now, connection_id& output);
    void detach(const connection_id& connection);
    status expire(u64 now);

    status create_account(const connection_id& registrar, u64 now, account_name name,
                          identity_id& identity, credential& enrollment);
    status lookup_account(const connection_id& registrar, u64 now, account_name name,
                          account_description& output);
    status rotate_credential(const connection_id& registrar, u64 now, const identity_id& identity,
                             credential& enrollment);
    status revoke_account(const connection_id& registrar, u64 now, const identity_id& identity);

    status authenticate(const connection_id& connection, u64 now, account_name name,
                        const credential& enrollment, session_id& output);
    status logout(const connection_id& connection, u64 now, const session_id& session);
    status session_identity(const connection_id& connection, u64 now, const session_id& session,
                            identity_id& output);
    status authorize_owner(const connection_id& connection, u64 now, const session_id& session,
                           const checked_rights& authority, const owner_record& ownership,
                           u32 requested);

private:
    struct connection {
        u64 number = 0;
        u64 deadline = 0;
        u64 session = 0;
        u64 account = 0;
    };

    status resolve(const connection_id& id, u64 now, connection*& output, admission_role role);
    connection* find_connection(const connection_id& id);
    u32 find_account(account_name name) const;
    bool active_account(const identity_id& id) const;
    bool random_credential(const identity_id& id, account_record& account, credential& issued);
    status publish(account_snapshot& candidate);
    void end_account_sessions(u64 account);

    store_api store_{};
    entropy_api entropy_{};
    account_snapshot accounts_{};
    connection connections_[client_limit + 1]{};
    nonce incarnation_{};
    u64 next_number_ = 0;
    u64 last_time_ = 0;
    bool active_ = false;
};

}
