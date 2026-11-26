// SPDX-License-Identifier: Apache-2.0
#include "service_core.hpp"

namespace xos::user::pumpkin {
namespace {

constexpr u64 max_u64 = ~u64{0};
constexpr u32 resource_mask = resource_read | resource_write | resource_manage;

bool equal_verifier(const u8 (&left)[secret_bytes], const u8 (&right)[secret_bytes]) {
    u8 difference = 0;
    for (usize index = 0; index < secret_bytes; ++index) {
        difference |= left[index] ^ right[index];
    }
    return difference == 0;
}

}

status service_core::start(const store_api& store, const nonce& realm, const entropy_api& entropy) {
    if (active_) {
        return status::conflict;
    }
    if (store.load == nullptr || store.replace == nullptr || entropy.fill == nullptr ||
        !has_bytes(realm.bytes, sizeof(realm.bytes))) {
        return status::invalid;
    }
    u8 bytes[snapshot_capacity]{};
    usize length = 0;
    const auto loaded = store.load(store.context, bytes, sizeof(bytes), length);
    if (loaded == load_result::absent) {
        return status::not_found;
    }
    if (loaded != load_result::loaded) {
        return status::io_error;
    }
    if (!decode_snapshot(bytes, length, realm, accounts_)) {
        stop();
        return status::corrupt;
    }
    nonce incarnation{};
    if (!entropy.fill(entropy.context, incarnation.bytes, sizeof(incarnation.bytes)) ||
        !has_bytes(incarnation.bytes, sizeof(incarnation.bytes)) || incarnation == incarnation_) {
        stop();
        return status::io_error;
    }
    store_ = store;
    entropy_ = entropy;
    incarnation_ = incarnation;
    next_number_ = 1;
    active_ = true;
    return status::ok;
}

void service_core::stop() {
    active_ = false;
    for (auto& entry : connections_) {
        entry = {};
    }
    accounts_ = {};
    store_ = {};
    entropy_ = {};
    next_number_ = 0;
    last_time_ = 0;
}

status service_core::attach(admission_role role, u64 now, connection_id& output) {
    output = {};
    const auto current = expire(now);
    if (current != status::ok) {
        return current;
    }
    if (now > max_u64 - connection_lifetime_ns ||
        (role != admission_role::client && role != admission_role::registrar)) {
        return status::invalid;
    }
    const bool registrar = role == admission_role::registrar;
    const u32 first = registrar ? client_limit : 0;
    const u32 limit = registrar ? client_limit + 1 : client_limit;
    for (u32 index = first; index < limit && next_number_ != 0; ++index) {
        if (connections_[index].number == 0) {
            const u64 number = next_number_++;
            connections_[index] = {number, now + connection_lifetime_ns, 0, 0};
            output = {incarnation_, number};
            return status::ok;
        }
    }
    return status::exhausted;
}

void service_core::detach(const connection_id& id) {
    if (auto* entry = find_connection(id)) {
        *entry = {};
    }
}

status service_core::expire(u64 now) {
    if (!active_) {
        return status::unavailable;
    }
    if (now < last_time_) {
        stop();
        return status::unavailable;
    }
    last_time_ = now;
    for (auto& entry : connections_) {
        if (entry.number != 0 && now >= entry.deadline) {
            entry = {};
        }
    }
    return status::ok;
}

status service_core::create_account(const connection_id& registrar, u64 now, account_name name,
                                    identity_id& identity, credential& enrollment) {
    identity = {};
    wipe_bytes(&enrollment, sizeof(enrollment));
    connection* authenticated = nullptr;
    const auto access = resolve(registrar, now, authenticated, admission_role::registrar);
    if (access != status::ok) {
        return access;
    }
    if (!valid_name(name)) {
        return status::invalid;
    }
    if (find_account(name) < accounts_.count) {
        return status::conflict;
    }
    if (accounts_.count == account_limit || accounts_.revision == max_u64) {
        return status::exhausted;
    }

    auto candidate = accounts_;
    auto& account = candidate.accounts[candidate.count++];
    account = {};
    account.name_length = static_cast<u8>(name.length);
    for (usize index = 0; index < name.length; ++index) {
        account.name[index] = name.data[index];
    }
    const identity_id id{candidate.realm, candidate.count};
    credential issued{};
    if (!random_credential(id, account, issued)) {
        return status::io_error;
    }
    const auto result = publish(candidate);
    if (result == status::ok) {
        identity = id;
        enrollment = issued;
    }
    wipe_bytes(&issued, sizeof(issued));
    return result;
}

status service_core::lookup_account(const connection_id& registrar, u64 now, account_name name,
                                    account_description& output) {
    output = {};
    connection* authenticated = nullptr;
    const auto access = resolve(registrar, now, authenticated, admission_role::registrar);
    if (access != status::ok) {
        return access;
    }
    if (!valid_name(name)) {
        return status::invalid;
    }
    const u32 index = find_account(name);
    if (index == accounts_.count) {
        return status::not_found;
    }
    output = {{accounts_.realm, index + 1}, accounts_.accounts[index].disabled};
    return status::ok;
}

status service_core::rotate_credential(const connection_id& registrar, u64 now,
                                       const identity_id& identity, credential& enrollment) {
    wipe_bytes(&enrollment, sizeof(enrollment));
    connection* authenticated = nullptr;
    const auto access = resolve(registrar, now, authenticated, admission_role::registrar);
    if (access != status::ok) {
        return access;
    }
    if (!active_account(identity)) {
        return status::not_found;
    }
    if (accounts_.revision == max_u64) {
        return status::exhausted;
    }
    auto candidate = accounts_;
    credential issued{};
    auto& account = candidate.accounts[identity.number - 1];
    if (!random_credential(identity, account, issued)) {
        return status::io_error;
    }
    const auto result = publish(candidate);
    if (result == status::ok) {
        end_account_sessions(identity.number);
        enrollment = issued;
    }
    wipe_bytes(&issued, sizeof(issued));
    return result;
}

status service_core::revoke_account(const connection_id& registrar, u64 now,
                                    const identity_id& identity) {
    connection* authenticated = nullptr;
    const auto access = resolve(registrar, now, authenticated, admission_role::registrar);
    if (access != status::ok) {
        return access;
    }
    if (!active_account(identity)) {
        return status::not_found;
    }
    if (accounts_.revision == max_u64) {
        return status::exhausted;
    }
    auto candidate = accounts_;
    auto& account = candidate.accounts[identity.number - 1];
    account.disabled = true;
    wipe_bytes(account.verifier, sizeof(account.verifier));
    const auto result = publish(candidate);
    if (result == status::ok) {
        end_account_sessions(identity.number);
    }
    return result;
}

status service_core::authenticate(const connection_id& id, u64 now, account_name name,
                                   const credential& enrollment, session_id& output) {
    output = {};
    connection* entry = nullptr;
    const auto access = resolve(id, now, entry, admission_role::client);
    if (access != status::ok) {
        return access;
    }
    if (!valid_name(name)) {
        return status::invalid;
    }
    if (entry->session != 0) {
        return status::conflict;
    }
    const u32 index = find_account(name);
    const bool exists = index < accounts_.count;
    constexpr account_record missing{};
    const auto& account = exists ? accounts_.accounts[index] : missing;
    u8 actual[secret_bytes];
    credential_verifier({accounts_.realm, index + 1}, enrollment, actual);
    const bool matches = equal_verifier(actual, account.verifier);
    wipe_bytes(actual, sizeof(actual));
    if (!exists || account.disabled || !matches) {
        return status::denied;
    }
    if (next_number_ == 0) {
        return status::exhausted;
    }
    entry->session = next_number_++;
    entry->account = index + 1;
    output = {incarnation_, entry->session};
    return status::ok;
}

status service_core::logout(const connection_id& id, u64 now, const session_id& session) {
    connection* entry = nullptr;
    const auto access = resolve(id, now, entry, admission_role::client);
    if (access != status::ok) {
        return access;
    }
    if (entry->session == 0 || session != session_id{incarnation_, entry->session}) {
        return status::denied;
    }
    entry->session = 0;
    entry->account = 0;
    return status::ok;
}

status service_core::session_identity(const connection_id& id, u64 now, const session_id& session,
                                      identity_id& output) {
    output = {};
    connection* entry = nullptr;
    const auto access = resolve(id, now, entry, admission_role::client);
    if (access != status::ok) {
        return access;
    }
    if (entry->session == 0 || session != session_id{incarnation_, entry->session}) {
        return status::denied;
    }
    output = {accounts_.realm, entry->account};
    return status::ok;
}

status service_core::authorize_owner(const connection_id& id, u64 now, const session_id& session,
                                     const checked_rights& authority, const owner_record& ownership,
                                     u32 requested) {
    if (requested == 0 || (requested & ~resource_mask) != 0) {
        return status::invalid;
    }
    identity_id identity{};
    const auto access = session_identity(id, now, session, identity);
    if (access != status::ok) {
        return access;
    }
    const auto& object = authority.object;
    if (authority.connection != id || object != ownership.object || object.number == 0 ||
        object.generation == 0 || !has_bytes(object.registry.bytes, sizeof(object.registry.bytes)) ||
        identity != ownership.owner || (requested & authority.permitted & ownership.permitted) != requested) {
        return status::denied;
    }
    return status::ok;
}

status service_core::resolve(const connection_id& id, u64 now, connection*& output, admission_role role) {
    const auto current = expire(now);
    if (current != status::ok) {
        return current;
    }
    auto* entry = find_connection(id);
    if (entry == nullptr || (entry == &connections_[client_limit]) != (role == admission_role::registrar)) {
        return status::denied;
    }
    output = entry;
    return status::ok;
}

service_core::connection* service_core::find_connection(const connection_id& id) {
    if (!active_ || id.incarnation != incarnation_ || id.number == 0) {
        return nullptr;
    }
    for (auto& entry : connections_) {
        if (entry.number == id.number) {
            return &entry;
        }
    }
    return nullptr;
}

u32 service_core::find_account(account_name name) const {
    for (u32 index = 0; index < accounts_.count; ++index) {
        const auto& account = accounts_.accounts[index];
        if (account.name_length != name.length) {
            continue;
        }
        usize same = 0;
        while (same < name.length && account.name[same] == name.data[same]) {
            ++same;
        }
        if (same == name.length) {
            return index;
        }
    }
    return accounts_.count;
}

bool service_core::active_account(const identity_id& id) const {
    return id.realm == accounts_.realm && id.number > 0 && id.number <= accounts_.count &&
        !accounts_.accounts[id.number - 1].disabled;
}

bool service_core::random_credential(const identity_id& id, account_record& account, credential& issued) {
    if (!entropy_.fill(entropy_.context, issued.bytes, sizeof(issued.bytes)) ||
        !has_bytes(issued.bytes, sizeof(issued.bytes))) {
        wipe_bytes(&issued, sizeof(issued));
        return false;
    }
    u8 verifier[secret_bytes];
    credential_verifier(id, issued, verifier);
    // The format reserves the zero verifier for revocation. A repeated key
    // must also fail, since rotation promises to invalidate the old key.
    if (!has_bytes(verifier, sizeof(verifier)) || equal_verifier(verifier, account.verifier)) {
        wipe_bytes(&issued, sizeof(issued));
        return false;
    }
    for (usize index = 0; index < sizeof(verifier); ++index) {
        account.verifier[index] = verifier[index];
    }
    return true;
}

status service_core::publish(account_snapshot& candidate) {
    ++candidate.revision;
    u8 bytes[snapshot_capacity];
    const usize length = encode_snapshot(candidate, bytes);
    if (length == 0) {
        stop();
        return status::corrupt;
    }
    switch (store_.replace(store_.context, accounts_.revision, bytes, length)) {
    case replace_result::committed:
        accounts_ = candidate;
        return status::ok;
    case replace_result::unchanged:
        return status::io_error;
    case replace_result::conflict:
        stop();
        return status::conflict;
    default:
        stop();
        return status::outcome_unknown;
    }
}

void service_core::end_account_sessions(u64 account) {
    for (auto& entry : connections_) {
        if (entry.account == account) {
            entry.session = 0;
            entry.account = 0;
        }
    }
}

}
