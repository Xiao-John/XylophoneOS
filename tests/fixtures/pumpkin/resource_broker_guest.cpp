// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/native_ipc.hpp"
#include "pumpkin/sealed_blob.hpp"

namespace {
using namespace xos;
using namespace xos::user::pumpkin;

constexpr u8 sample[] = {'p', 'u', 'm', 'p', 'k', 'i', 'n'};
constexpr u64 object = 1;
constexpr char program[] = "/bin/pumpkin_resource_probe.elf";
constexpr char owner_name[] = "owner";
constexpr char other_name[] = "other";

struct test_store {
    u8 bytes[snapshot_capacity]{};
    usize size = 0;
    u64 revision = 0;

    static load_result load(void* context, u8* destination, usize capacity, usize& length) {
        const auto& store = *static_cast<test_store*>(context);
        if (store.size == 0) { return load_result::absent; }
        if (store.size > capacity) { return load_result::io_error; }
        __builtin_memcpy(destination, store.bytes, store.size);
        length = store.size;
        return load_result::loaded;
    }

    static replace_result replace(void* context, u64 previous, const u8* source, usize length) {
        auto& store = *static_cast<test_store*>(context);
        if (previous != store.revision) { return replace_result::conflict; }
        if (length == 0 || length > sizeof(store.bytes)) { return replace_result::unchanged; }
        __builtin_memcpy(store.bytes, source, length);
        store.size = length;
        ++store.revision;
        return replace_result::committed;
    }
};

struct welcome {
    credential enrollment;
    session_id other_session;
    u32 separate_files_handle;
};
struct result_frame {
    status result = status::invalid;
    sealed_blob_reply data{};
};
struct test_peer {
    ipc_channel channel{};
    connection_id connection{};
    u64 pid = 0;
};

test_store memory;
service_core core;
file::client files;

u64 now() {
    const auto clock = monotonic_now();
    return clock < 0 ? ~u64{0} : static_cast<u64>(clock);
}

bool entropy(void*, u8* out, usize size) {
    return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(out), size) == 0;
}

template<class T>
bool receive(const ipc_channel& channel, T& message) {
    const u64 deadline = now() + max_request_ns;
    while (now() < deadline) {
        const i64 result = sdk::ipc_recv(channel.receive, &message, sizeof(message));
        if (result == static_cast<i64>(sizeof(message))) { return true; }
        if (result != process_error_would_block || !sleep_tick(now())) { return false; }
    }
    return false;
}

template<class T>
bool send(const ipc_channel& channel, const T& message) {
    return sdk::ipc_send(channel.send, &message, sizeof(message)) == 0;
}

bool attach_child(test_peer& peer, const char* user, const char* name,
                  credential& enrollment, session_id foreign, u32 separate_handle,
                  session_id& session) {
    const char* args[] = {program, "client", user, name};
    const i64 child = sdk::spawn_file(program, 4, args);
    if (child <= 0) { return false; }
    peer.pid = static_cast<u64>(child);
    const u64 deadline = now() + max_request_ns;
    i64 accepted = process_error_would_block;
    while (now() < deadline && accepted == process_error_would_block) {
        accepted = sdk::ipc_name_try_accept(peer.channel);
        if (accepted == process_error_would_block && !sleep_tick(now())) { return false; }
    }
    if (accepted != 0 || authenticated_peer(peer.channel) != peer.pid ||
        core.attach(admission_role::client, now(), peer.connection) != status::ok) {
        return false;
    }
    welcome introduction{enrollment, foreign, separate_handle};
    const bool introduced = send(peer.channel, introduction);
    wipe_bytes(&introduction, sizeof(introduction));
    wipe_bytes(&enrollment, sizeof(enrollment));
    wire_request request{};
    wire_reply response{};
    u64 sequence = 0;
    const bool accepted_login = introduced && receive(peer.channel, request) &&
        request.operation == wire_operation::authenticate &&
        authenticated_peer(peer.channel) == peer.pid &&
        dispatch_request(core, peer.connection, sequence, request, now(), response) &&
        response.result == wire_status::ok && send(peer.channel, response);
    session = {response.token.scope, response.token.number};
    wipe_bytes(&request, sizeof(request));
    wipe_bytes(&response, sizeof(response));
    return accepted_login;
}

bool dispatch_read(sealed_blob& blob, const test_peer& peer, status expected, bool grant = true) {
    resource_request request{};
    result_frame reply{};
    if (!receive(peer.channel, request) || authenticated_peer(peer.channel) != peer.pid) { return false; }
    reply.result = blob.read(core, {peer.connection, grant}, now(), request, reply.data);
    return reply.result == expected && send(peer.channel, reply);
}

bool wait_child(test_peer& peer) {
    process_status result{};
    const bool waited = sdk::wait(peer.pid, result) >= 0 &&
        result.outcome == process_outcome::exited && result.code == 0;
    core.detach(peer.connection);
    close_ipc(peer.channel);
    return waited;
}

bool published_sample(sealed_blob& blob, const nonce& scope, const nonce& authority, const identity_id& owner,
                      u32& witness_handle) {
    // A separate ordinary anonymous file supplies an exact native handle
    // number for the cross-files-session witness. The broker handle stays private.
    return files.init() && files.anonymous(witness_handle) == 0 && witness_handle != 0 &&
        files.write(witness_handle, sample, sizeof(sample)) == sizeof(sample) &&
        files.seal_anonymous(witness_handle) == 0 && files.write(witness_handle, sample, 1) < 0 &&
        blob.publish({scope, object, 1}, authority, owner, sample, sizeof(sample)) == status::ok;
}

int broker(const char* name) {
    nonce realm{}, scope{};
    const store_api store{&memory, test_store::load, test_store::replace};
    connection_id registrar{};
    identity_id owner{}, other{};
    credential owner_key{}, other_key{};
    if (!entropy(nullptr, realm.bytes, sizeof(realm.bytes)) ||
        !entropy(nullptr, scope.bytes, sizeof(scope.bytes)) ||
        provision_store(store, realm) != status::ok ||
        core.start(store, realm, {nullptr, entropy}) != status::ok ||
        core.attach(admission_role::registrar, now(), registrar) != status::ok ||
        core.create_account(registrar, now(), {owner_name, sizeof(owner_name) - 1}, owner, owner_key) != status::ok ||
        core.create_account(registrar, now(), {other_name, sizeof(other_name) - 1}, other, other_key) != status::ok ||
        sdk::ipc_name_publish(name) != 0) {
        return 10;
    }
    sealed_blob blob(files);
    sealed_blob previous_boot(files);
    u32 witness_handle = 0;
    if (!published_sample(blob, scope, registrar.incarnation, owner, witness_handle) ||
        scope == registrar.incarnation ||
        previous_boot.publish({scope, object, 1}, scope, owner, sample, sizeof(sample)) != status::ok) {
        return 11;
    }
    test_peer first{}, second{};
    session_id owner_session{}, other_session{};
    if (!attach_child(first, owner_name, name, owner_key, {}, witness_handle, owner_session) ||
        !dispatch_read(blob, first, status::denied, false) ||  // native right absent
        !dispatch_read(previous_boot, first, status::denied) ||
        !dispatch_read(blob, first, status::ok) ||
        !dispatch_read(blob, first, status::denied) ||        // write to sealed object
        !dispatch_read(blob, first, status::denied)) {        // guessed object
        return 12;
    }
    if (!attach_child(second, other_name, name, other_key, owner_session, witness_handle, other_session) ||
        !dispatch_read(blob, second, status::denied) ||      // valid other account
        !dispatch_read(blob, second, status::denied) ||      // copied still-live owner session
        !wait_child(second)) {
        return 13;
    }
    if (core.revoke_account(registrar, now(), owner) != status::ok ||
        !dispatch_read(blob, first, status::denied) ||
        !wait_child(first) || files.close(witness_handle) != 0 || sdk::ipc_name_unpublish(name) != 0) {
        return 14;
    }
    sdk::print("PUMPKIN_BLOB_PASS owner_read native_right stale_incarnation wrong_account "
               "live_session_copy revoked direct_files_denied\n");
    return 0;
}

bool request_blob(const ipc_channel& channel, const session_id& session, u64 handle, u32 operation,
                  status expected) {
    const resource_request request{session, handle, operation};
    result_frame response{};
    if (!send(channel, request) || !receive(channel, response) || response.result != expected ||
        response.data.length != (expected == status::ok ? sizeof(sample) : 0)) {
        return false;
    }
    for (u32 index = 0; index < sealed_blob_capacity; ++index) {
        const u8 wanted = index < response.data.length ? sample[index] : 0;
        if (wanted != response.data.bytes[index]) { return false; }
    }
    return true;
}

int client(const char* user, const char* name) {
    ipc_channel parent_pair{}, channel{};
    if (sdk::ipc_channel_create(0, parent_pair) != 0) { return 20; }
    const u64 parent = authenticated_peer(parent_pair);
    close_ipc(parent_pair);
    ipc_client native;
    if (parent == 0 || sdk::ipc_name_connect(name, channel) != 0 || !native.bind(channel, parent)) { return 20; }
    welcome introduction{};
    if (!receive(channel, introduction) || !files.init()) { return 21; }
    u8 byte = 0;
    if (files.read_at(introduction.separate_files_handle, &byte, 1, 0) !=
            static_cast<i64>(file::status::bad_handle)) {
        return 22;
    }
    wire_request authentication{};
    authentication.operation = wire_operation::authenticate;
    authentication.name_length = sdk::length(user);
    __builtin_memcpy(authentication.name, user, authentication.name_length);
    authentication.key = introduction.enrollment;
    const auto foreign = introduction.other_session;
    wipe_bytes(&introduction, sizeof(introduction));
    wire_reply authentication_reply{};
    const bool connected = native.call(authentication, authentication_reply) == exchange::received &&
        authentication_reply.result == wire_status::ok;
    const session_id session{authentication_reply.token.scope, authentication_reply.token.number};
    wipe_bytes(&authentication, sizeof(authentication));
    wipe_bytes(&authentication_reply, sizeof(authentication_reply));
    if (!connected) { return 23; }
    if (sdk::equal(user, owner_name)) {
        return request_blob(channel, session, object, resource_read, status::denied) &&
            request_blob(channel, session, object, resource_read, status::denied) &&
            request_blob(channel, session, object, resource_read, status::ok) &&
            request_blob(channel, session, object, resource_write, status::denied) &&
            request_blob(channel, session, object + 1, resource_read, status::denied) &&
            request_blob(channel, session, object, resource_read, status::denied) ? 0 : 24;
    }
    return request_blob(channel, session, object, resource_read, status::denied) &&
        request_blob(channel, foreign, object, resource_read, status::denied) ? 0 : 25;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    if (startup == nullptr || startup->magic != xos::startup_magic) { return 2; }
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc == 3 && xos::sdk::equal(args[1], "broker")) { return broker(args[2]); }
    if (startup->argc == 4 && xos::sdk::equal(args[1], "client")) { return client(args[2], args[3]); }
    return 2;
}
