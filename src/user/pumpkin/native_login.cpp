// SPDX-License-Identifier: Apache-2.0
#include "native_login.hpp"
#include "disk_test_store.hpp"
#include "login_resource.hpp"

namespace xos::user::pumpkin::native_login {
namespace {
constexpr char rendezvous[] = "pumpkin-holder-bootstrap";
constexpr u32 version = 1;
enum class step : u32 { received = 1, delivery_closed, connected, use_resource, accessed, check_revoked, revoked, finish };

struct delivery {
    u32 format = version;
    u32 name_length = 0;
    u64 daemon = 0;
    wire_id identity;
    char name[name_limit]{};
    credential key;
    ~delivery() { wipe_bytes(&key, sizeof(key)); }
};
struct signal {
    u32 format = version;
    step stage;
};
struct delivery_closed {
    signal message{version, step::delivery_closed};
    u8 zero[sizeof(delivery) - sizeof(signal)]{};
};
struct arrival {
    signal message{version, step::connected};
    ipc_channel daemon_side;
    wire_id session;
};
static_assert(sizeof(delivery) == 104 && sizeof(signal) == 8 && sizeof(arrival) == 40);
static_assert(sizeof(delivery_closed) == sizeof(delivery));

struct endpoints {
    ipc_channel pair{};
    ~endpoints() { close_ipc(pair); }
};

u64 deadline() {
    const auto now = monotonic_now();
    return now < 0 ? 0 : static_cast<u64>(now) + max_request_ns;
}

bool wait_tick(u64 end) {
    const auto now = monotonic_now();
    return now >= 0 && static_cast<u64>(now) < end && sleep_tick(static_cast<u64>(now));
}

template<class Packet>
bool receive(const ipc_channel& pair, Packet& packet, u64 end) {
    for (;;) {
        const auto now = monotonic_now();
        if (now < 0 || static_cast<u64>(now) >= end) { return false; }
        const i64 bytes = sdk::ipc_recv(pair.receive, &packet, sizeof(packet));
        if (bytes == static_cast<i64>(sizeof(packet))) { return true; }
        if (bytes != process_error_would_block || !sleep_tick(static_cast<u64>(now))) { return false; }
    }
}

template<class Packet>
bool send(const ipc_channel& pair, const Packet& packet) {
    return sdk::ipc_send(pair.send, &packet, sizeof(packet)) == 0;
}

bool signal_received(const ipc_channel& pair, step stage) {
    signal packet{};
    return receive(pair, packet, deadline()) && packet.format == version && packet.stage == stage;
}

wire_request request(wire_operation op, wire_id token = {}) {
    wire_request value{};
    value.operation = op;
    value.token = token;
    return value;
}

wire_request named(wire_operation op, account_name name) {
    auto value = request(op);
    value.name_length = static_cast<u32>(name.length);
    __builtin_memcpy(value.name, name.data, name.length);
    return value;
}

bool expect(ipc_client& connection, wire_request& value, wire_reply& response, wire_status expected) {
    return connection.call(value, response) == exchange::received && response.result == expected;
}

bool ordinary(ipc_client& connection, u64 daemon, ipc_channel* daemon_side = nullptr) {
    ipc_channel pair{};
    if (sdk::ipc_name_connect(disk_test_service, pair) != 0 || !connection.bind(pair, daemon)) { return false; }
    if (daemon_side != nullptr) { *daemon_side = sdk::ipc_channel_for_peer(pair); }
    return true;
}

bool authenticate(ipc_client& connection, account_name name, const credential& key,
                  wire_status expected, wire_id& session) {
    auto value = named(wire_operation::authenticate, name);
    value.key = key;
    wire_reply response{};
    const bool accepted = expect(connection, value, response, expected);
    wipe_bytes(&value, sizeof(value));
    session = response.token;
    return accepted;
}

bool current_identity(ipc_client& connection, wire_id session, wire_id identity, wire_status expected) {
    auto value = request(wire_operation::identity, session);
    wire_reply response{};
    return expect(connection, value, response, expected) && (expected != wire_status::ok ||
        (response.token.scope == identity.scope && response.token.number == identity.number));
}

bool read_resource(ipc_client& connection, wire_id session, wire_status expected) {
    auto value = request(wire_operation::read_login_resource, session);
    wire_reply response{};
    return expect(connection, value, response, expected) &&
        (expected != wire_status::ok || response.flags == login_resource_value);
}

bool grant_resource(ipc_client& registrar, const wire_id& identity, u64 holder, ipc_channel daemon_side,
                    wire_status expected) {
    const login_resource_grant grant{holder, daemon_side.send, daemon_side.receive};
    auto value = request(wire_operation::grant_login_resource, identity);
    value.name_length = sizeof(grant);
    __builtin_memcpy(value.name, &grant, sizeof(grant));
    wire_reply response{};
    return expect(registrar, value, response, expected);
}

struct holder_process {
    u64 pid = 0;
    ~holder_process() {
        if (pid != 0) {
            (void)sdk::syscall(10, pid);
            process_status ignored{};
            (void)sdk::wait(pid, ignored);
        }
    }
    bool wait_clean() {
        process_status status{};
        const i64 ready = sdk::syscall(sys_process_wait, pid, reinterpret_cast<u64>(&status),
                                       process_wait_nonblocking);
        if (ready != 0) { return false; }
        pid = 0;
        return status.outcome == process_outcome::exited && status.code == 0;
    }
};

result connect_holder(u32 image, holder_process& holder, endpoints& protected_lane) {
    if (image == 0 || sdk::ipc_name_publish(rendezvous) != 0) { return result::holder_start; }
    struct unpublish { ~unpublish() { (void)sdk::ipc_name_unpublish(rendezvous); } } registration;
    sdk::spawn_options options{};
    for (auto& fd : options.stdio) { fd = -2; }
    const char* args[]{holder_image};
    const i64 child = sdk::spawn_image_options(image, 1, args, options);
    if (child <= 0) { return result::holder_start; }
    holder.pid = static_cast<u64>(child);
    endpoints discovery;
    const u64 end = deadline();
    do {
        const i64 accepted = sdk::ipc_name_try_accept(discovery.pair);
        if (accepted == 0 && authenticated_peer(discovery.pair) == holder.pid) {
            const bool verified = receive(discovery.pair, protected_lane.pair, end) &&
                authenticated_peer(protected_lane.pair) == holder.pid &&
                sdk::ipc_wait(protected_lane.pair.send, ipc_wait_mode::try_send) == 0;
            return verified ? result::passed : result::holder_pair;
        }
        if (accepted != 0 && accepted != process_error_would_block) { return result::holder_discovery; }
        close_ipc(discovery.pair);
    } while (wait_tick(end));
    return result::holder_discovery;
}

bool check_ungranted(ipc_client& owner, account_name name, const delivery& enrollment, wire_id session) {
    auto lookup = named(wire_operation::lookup_account, name);
    wire_reply response{};
    ipc_client other;
    wire_id fresh{};
    if (!expect(owner, lookup, response, wire_status::denied) ||
        !read_resource(owner, session, wire_status::denied) || !ordinary(other, enrollment.daemon) ||
        !current_identity(other, session, enrollment.identity, wire_status::denied) ||
        !authenticate(other, name, enrollment.key, wire_status::ok, fresh) ||
        !current_identity(other, fresh, enrollment.identity, wire_status::ok) ||
        !read_resource(other, fresh, wire_status::denied)) { return false; }
    auto logout = request(wire_operation::logout, fresh);
    return expect(other, logout, response, wire_status::ok) &&
        current_identity(other, fresh, enrollment.identity, wire_status::denied);
}
}

result run(u32 image, u64 daemon, ipc_client& registrar, account_name account) {
    if (account.data == nullptr || account.length == 0 || account.length > name_limit) { return result::enrollment; }
    holder_process holder;
    endpoints channel;
    const auto connected = connect_holder(image, holder, channel);
    if (connected != result::passed) { return connected; }

    wire_id identity{};
    {
        auto create = named(wire_operation::create_account, account);
        wire_reply response{};
        const bool committed = expect(registrar, create, response, wire_status::ok);
        delivery enrollment{};
        identity = response.token;
        enrollment.identity = identity;
        enrollment.daemon = daemon;
        enrollment.name_length = static_cast<u32>(account.length);
        __builtin_memcpy(enrollment.name, account.data, account.length);
        enrollment.key = response.key;
        wipe_bytes(&response, sizeof(response));
        if (!committed || !send(channel.pair, enrollment)) { return result::enrollment; }
    }
    // The receipt proves consumption, then the same-size secret-free frame
    // overwrites the original contents of the transport's single mail slot.
    if (!signal_received(channel.pair, step::received) || !send(channel.pair, delivery_closed{})) {
        return result::delivery_receipt;
    }
    // Replace the registrar's last reply, which carried the one-time secret.
    auto lookup = named(wire_operation::lookup_account, account);
    wire_reply response{};
    if (!expect(registrar, lookup, response, wire_status::ok) || response.flags != 0 ||
        response.token.scope != identity.scope || response.token.number != identity.number) { return result::enrollment_readback; }

    arrival ready{};
    if (!receive(channel.pair, ready, deadline()) || ready.message.format != version ||
        ready.message.stage != step::connected ||
        !grant_resource(registrar, identity, sdk::pid(), ready.daemon_side, wire_status::denied) ||
        !grant_resource(registrar, identity, holder.pid, ready.daemon_side, wire_status::ok) ||
        !send(channel.pair, signal{version, step::use_resource}) || !signal_received(channel.pair, step::accessed)) {
        return result::resource_access;
    }
    ipc_client outsider;
    auto revoke = request(wire_operation::revoke_account, identity);
    if (!ordinary(outsider, daemon) || !current_identity(outsider, ready.session, identity, wire_status::denied) ||
        !read_resource(outsider, ready.session, wire_status::denied) ||
        !expect(registrar, revoke, response, wire_status::ok) ||
        !send(channel.pair, signal{version, step::check_revoked}) || !signal_received(channel.pair, step::revoked) ||
        !send(channel.pair, signal{version, step::finish})) { return result::revocation; }
    const u64 end = deadline();
    do {
        if (holder.wait_clean()) {
            return authenticated_peer(channel.pair) == 0 ? result::passed : result::holder_exit;
        }
    } while (holder.pid != 0 && wait_tick(end));
    return result::holder_exit;
}

int holder_main() {
    endpoints channel;
    if (sdk::ipc_channel_create(0, channel.pair) != 0) { return 10; }
    const u64 parent = authenticated_peer(channel.pair);
    endpoints discovery;
    if (parent == 0 || sdk::ipc_name_connect(rendezvous, discovery.pair) != 0 ||
        authenticated_peer(discovery.pair) != parent ||
        !send(discovery.pair, sdk::ipc_channel_for_peer(channel.pair))) { return 10; }
    delivery enrollment{};
    if (!receive(channel.pair, enrollment, deadline()) || enrollment.format != version ||
        enrollment.name_length == 0 || enrollment.name_length > name_limit || enrollment.daemon == 0 ||
        enrollment.identity.scope != disk_test_realm || enrollment.identity.number == 0 ||
        !has_bytes(enrollment.key.bytes, secret_bytes)) { return 11; }
    close_ipc(discovery.pair);
    delivery_closed closed{};
    if (!send(channel.pair, signal{version, step::received}) || !receive(channel.pair, closed, deadline()) ||
        closed.message.format != version || closed.message.stage != step::delivery_closed ||
        has_bytes(closed.zero, sizeof(closed.zero))) { return 11; }

    ipc_client owner;
    arrival ready{};
    wire_id discarded{};
    const account_name name{enrollment.name, enrollment.name_length};
    if (!ordinary(owner, enrollment.daemon, &ready.daemon_side) ||
        !authenticate(owner, name, {}, wire_status::denied, discarded) ||
        !authenticate(owner, name, enrollment.key, wire_status::ok, ready.session) ||
        !current_identity(owner, ready.session, enrollment.identity, wire_status::ok) ||
        !check_ungranted(owner, name, enrollment, ready.session) || !send(channel.pair, ready) ||
        !signal_received(channel.pair, step::use_resource) || !read_resource(owner, ready.session, wire_status::ok) ||
        !send(channel.pair, signal{version, step::accessed}) || !signal_received(channel.pair, step::check_revoked) ||
        !current_identity(owner, ready.session, enrollment.identity, wire_status::denied) ||
        !read_resource(owner, ready.session, wire_status::denied) ||
        !authenticate(owner, name, enrollment.key, wire_status::denied, discarded)) { return 12; }
    wipe_bytes(&enrollment.key, sizeof(enrollment.key));
    owner.close();
    return send(channel.pair, signal{version, step::revoked}) && signal_received(channel.pair, step::finish) ? 0 : 13;
}
}
