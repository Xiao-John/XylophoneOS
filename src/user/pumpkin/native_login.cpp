// SPDX-License-Identifier: Apache-2.0
#include "native_login.hpp"
#include "disk_test_store.hpp"
#include "login_resource.hpp"
#if XOS_PUMPKIN_USER_LOGIN
#include "user_login.hpp"
#endif
#if XOS_PUMPKIN_USER_RESOURCE
#include "resource_broker_client.hpp"
#endif

namespace xos::user::pumpkin::native_login {
namespace {
constexpr char rendezvous[] = "pumpkin-holder-bootstrap";
constexpr u32 version = 1;
enum class step : u32 {
    received = 1, delivery_closed, connected, use_resource, accessed, check_revoked, revoked, finish,
    signed_out, rejected, resource_denied,
};

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

wire_status submit_key(ipc_client& connection, account_name name, const credential& key, wire_id& session) {
    auto value = named(wire_operation::authenticate, name);
    value.key = key;
    wire_reply response{};
    const auto received = connection.call(value, response);
    wipe_bytes(&value, sizeof(value));
    session = response.token;
    return received == exchange::received ? response.result : wire_status::unavailable;
}

bool authenticate(ipc_client& connection, account_name name, const credential& key,
                  wire_status expected, wire_id& session) {
    return submit_key(connection, name, key, session) == expected;
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

struct child_process {
    u64 pid = 0;
    ~child_process() {
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

result connect_holder(u32 image, child_process& holder, endpoints& protected_lane,
                      holder_mode mode = holder_mode::cycle) {
    if (image == 0 || sdk::ipc_name_publish(rendezvous) != 0) { return result::holder_start; }
    struct unpublish { ~unpublish() { (void)sdk::ipc_name_unpublish(rendezvous); } } registration;
    sdk::spawn_options options{};
    for (auto& fd : options.stdio) { fd = -2; }
    const char* args[]{holder_image, mode == holder_mode::resource ? "resource" : "submit"};
    const i64 child = sdk::spawn_image_options(image, mode == holder_mode::cycle ? 1 : 2, args, options);
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

bool reap_child(child_process& holder, const ipc_channel& channel) {
    const u64 end = deadline();
    do {
        if (holder.wait_clean()) { return authenticated_peer(channel) == 0; }
    } while (holder.pid != 0 && wait_tick(end));
    return false;
}

#if XOS_PUMPKIN_USER_LOGIN
bool lookup_user(ipc_client& registrar, account_name account, wire_reply& response) {
    auto lookup = named(wire_operation::lookup_account, account);
    return expect(registrar, lookup, response, wire_status::ok);
}

#if XOS_PUMPKIN_USER_RESOURCE
constexpr char broker_rendezvous[] = "pumpkin-broker-bootstrap";
constexpr u8 resource_payload[]{'P', 'u', 'm', 'p', 'k', 'i', 'n'};
struct resource_arrival {
    signal message{};
    nonce incarnation{};
};
struct resource_launch {
    u64 broker = 0;
    named_resource_request named{};
};
struct resource_result {
    signal message{};
    u64 generation = 0;
    named_resource_data data{};
    u32 reserved = 0;
};
static_assert(sizeof(resource_arrival) == 24 && sizeof(resource_launch) == 40 && sizeof(resource_result) == 56);

result start_broker(u32 image, u64 daemon, wire_id identity, const nonce& incarnation, ipc_client& registrar,
                    child_process& broker, endpoints& control, bool named_profile) {
    if (!image || incarnation == nonce{} || sdk::ipc_name_publish(broker_rendezvous) != 0) {
        return result::broker_launch;
    }
    struct unpublish { ~unpublish() { (void)sdk::ipc_name_unpublish(broker_rendezvous); } } registration;
    sdk::spawn_options options{};
    for (auto& fd : options.stdio) { fd = -2; }
    const char* args[]{broker_image_name, broker_rendezvous};
    const auto pid = sdk::spawn_image_options(image, 2, args, options);
    if (pid <= 0) { return result::broker_launch; }
    broker.pid = static_cast<u64>(pid);
    const auto end = deadline();
    endpoints discovery;
    for (;;) {
        const auto accepted = sdk::ipc_name_try_accept(discovery.pair);
        if (accepted == 0 && authenticated_peer(discovery.pair) == broker.pid) { break; }
        if (accepted != 0 && accepted != process_error_would_block) { return result::broker_bootstrap; }
        close_ipc(discovery.pair);
        if (!wait_tick(end)) { return result::broker_bootstrap; }
    }
    control_message offer{};
    if (!receive(discovery.pair, offer, end) || offer.version != wire_version || offer.reserved ||
        offer.realm != nonce{} || authenticated_peer(offer.channel) != broker.pid) { return result::broker_bootstrap; }
    control.pair = offer.channel;
    broker_configuration config{};
    config.daemon = daemon;
    if (!named_profile) {
        config.length = sizeof(resource_payload);
        config.owner = {identity.scope, identity.number};
        config.incarnation = incarnation;
        __builtin_memcpy(config.bytes, resource_payload, sizeof(resource_payload));
    }
    broker_ready ready{};
    if (!send(control.pair, config) || !receive(control.pair, ready, end) ||
        ready.version != broker_wire_version || ready.reserved || ready.grant.peer != broker.pid) {
        return result::broker_bootstrap;
    }
    auto grant = request(wire_operation::admit_resource_broker);
    grant.name_length = sizeof(ready.grant);
    __builtin_memcpy(grant.name, &ready.grant, sizeof(ready.grant));
    wire_reply reply{};
    return expect(registrar, grant, reply, wire_status::ok) ? result::passed : result::broker_grant;
}

bool read_owned_resource(const ipc_channel& parental, ipc_client& owner, wire_id session,
                         resource_launch& launch, broker_data& data) {
    if (!send(parental, resource_arrival{{version, step::connected}, session.scope}) ||
        !receive(parental, launch, deadline()) || !launch.broker) { return false; }
    broker_read_client read;
    wire_id ticket{};
    const auto* named = launch.named.length ? &launch.named : nullptr;
    if ((named && !valid_named_request(*named)) ||
        !read.connect(launch.broker) || read.prepare(owner, session, ticket) != wire_status::ok ||
        !read.read(ticket, data, named)) { return false; }
    if (named) { return data.result == wire_status::ok || data.result == wire_status::denied; }
    return data.result == wire_status::ok &&
        data.data.length == sizeof(resource_payload) &&
        __builtin_memcmp(data.data.bytes, resource_payload, sizeof(resource_payload)) == 0;
}
#endif

int submit_and_logout(const ipc_channel& parental, delivery& enrollment, [[maybe_unused]] bool with_resource) {
    ipc_client owner;
    if (!ordinary(owner, enrollment.daemon)) { return 14; }
    const account_name account{enrollment.name, enrollment.name_length};
    wire_id session{};
    const auto result = submit_key(owner, account, enrollment.key, session);
    wipe_bytes(&enrollment.key, sizeof(enrollment.key));
#if XOS_PUMPKIN_USER_RESOURCE
    resource_launch launch{};
    broker_data resource{};
#endif
    if (result == wire_status::ok) {
        if (!current_identity(owner, session, enrollment.identity, wire_status::ok)) { return 14; }
#if XOS_PUMPKIN_USER_RESOURCE
        broker_read_client pending;
        wire_id pending_ticket{};
        i64 before_association = 0;
        bool check_logout = false;
        if (with_resource) {
            if (!read_owned_resource(parental, owner, session, launch, resource)) { return 14; }
            check_logout = resource.result == wire_status::ok;
            if (check_logout) {
                if (!pending.connect(launch.broker)) { return 14; }
                before_association = monotonic_now();
                if (before_association < 0 || pending.prepare(owner, session, pending_ticket) != wire_status::ok) { return 14; }
            }
        }
#endif
        auto logout = request(wire_operation::logout, session);
        wire_reply reply{};
        if (!expect(owner, logout, reply, wire_status::ok) ||
            !current_identity(owner, session, enrollment.identity, wire_status::denied)) return 14;
#if XOS_PUMPKIN_USER_RESOURCE
        if (check_logout) {
            broker_data denied{};
            if (!pending.read(pending_ticket, denied, launch.named.length ? &launch.named : nullptr) ||
                denied.result != wire_status::denied) { return 14; }
            const auto observed = monotonic_now();
            // The authority issues after this lower bound. Observing denial
            // within the lifetime confirms logout independently of expiry.
            if (observed < before_association ||
                static_cast<u64>(observed - before_association) >= read_association_lifetime_ns) { return 14; }
        }
#endif
    } else if (result != wire_status::denied) { return 14; }
    owner.close();
    const auto stage = result == wire_status::ok ? step::signed_out : step::rejected;
#if XOS_PUMPKIN_USER_RESOURCE
    if (with_resource && stage == step::rejected) {
        return send(parental, resource_arrival{{version, stage}, {}}) &&
            signal_received(parental, step::finish) ? 0 : 15;
    }
    if (launch.named.length) {
        resource_result selected{{version, resource.result == wire_status::ok ? stage : step::resource_denied},
                                  resource.generation};
        selected.data.length = resource.data.length;
        __builtin_memcpy(selected.data.bytes, resource.data.bytes, selected.data.length);
        return send(parental, selected) && signal_received(parental, step::finish) ? 0 : 15;
    }
#endif
    return send(parental, signal{version, stage}) && signal_received(parental, step::finish) ? 0 : 15;
}
#endif
}

result run(u32 image, u64 daemon, ipc_client& registrar, account_name account) {
    if (account.data == nullptr || account.length == 0 || account.length > name_limit) { return result::enrollment; }
    child_process holder;
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
    return reap_child(holder, channel.pair) ? result::passed : result::holder_exit;
}

int holder_main([[maybe_unused]] holder_mode mode) {
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
#if XOS_PUMPKIN_USER_LOGIN
    if (mode != holder_mode::cycle) return submit_and_logout(channel.pair, enrollment, mode == holder_mode::resource);
#endif

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

#if XOS_PUMPKIN_USER_LOGIN
u8 enroll_user(ipc_client& registrar, account_name account, const anchor_guest::pair& proxy) {
    auto lookup = named(wire_operation::lookup_account, account);
    wire_reply found{};
    if (registrar.call(lookup, found) != exchange::received) return 0;
    if (found.result == wire_status::ok) return user_login::duplicate_enrollment;
    if (found.result != wire_status::not_found || !user_login::reserve_credential_destination(proxy)) return 0;
    auto create = named(wire_operation::create_account, account);
    wire_reply issued{};
    const bool committed = expect(registrar, create, issued, wire_status::ok);
    user_login::packet request{}, reply{};
    request.op = user_login::operation::issue;
    request.identity = issued.token;
    request.key = issued.key;
    wipe_bytes(&issued, sizeof(issued));
    return committed && lookup_user(registrar, account, issued) && issued.flags == 0 &&
        user_login::same_identity(issued.token, request.identity) &&
        user_login::exchange_with_operator(proxy, request, reply) && !has_bytes(reply.key.bytes, secret_bytes);
}

u8 login_user(u32 image, u64 daemon, ipc_client& registrar, account_name account, const anchor_guest::pair& proxy,
              [[maybe_unused]] u32 broker_image, [[maybe_unused]] named_read* named) {
    wire_reply found{};
    child_process holder;
    endpoints channel;
    const auto mode = broker_image ? holder_mode::resource : holder_mode::submit;
    if (!lookup_user(registrar, account, found) || connect_holder(image, holder, channel, mode) != result::passed) return 0;
    {
        user_login::packet request{}, reply{};
        request.op = user_login::operation::submit;
        request.identity = found.token;
        if (!user_login::exchange_with_operator(proxy, request, reply) || !has_bytes(reply.key.bytes, secret_bytes)) return 0;
        delivery enrollment{};
        enrollment.identity = found.token;
        enrollment.daemon = daemon;
        enrollment.name_length = static_cast<u32>(account.length);
        __builtin_memcpy(enrollment.name, account.data, account.length);
        enrollment.key = reply.key;
        if (!send(channel.pair, enrollment)) return 0;
    }
    if (!signal_received(channel.pair, step::received) || !send(channel.pair, delivery_closed{})) { return 0; }
#if XOS_PUMPKIN_USER_RESOURCE
    child_process broker;
    endpoints broker_control;
    if (mode == holder_mode::resource) {
        resource_arrival arrival{};
        if (!receive(channel.pair, arrival, deadline()) || arrival.message.format != version) {
            return static_cast<u8>(result::resource_access);
        }
        if (arrival.message.stage == step::rejected && arrival.incarnation == nonce{}) {
            return send(channel.pair, signal{version, step::finish}) && reap_child(holder, channel.pair)
                ? user_login::denied : 0;
        }
        if (arrival.message.stage != step::connected || found.flags) { return static_cast<u8>(result::resource_access); }
        const auto launched = start_broker(broker_image, daemon, found.token, arrival.incarnation, registrar,
                                           broker, broker_control, named != nullptr);
        if (launched != result::passed) { return static_cast<u8>(launched); }
        if (!send(channel.pair, resource_launch{broker.pid, named ? named->selection : named_resource_request{}})) {
            return static_cast<u8>(result::resource_access);
        }
    }
#endif
    signal outcome{};
#if XOS_PUMPKIN_USER_RESOURCE
    if (named != nullptr) {
        resource_result selected{};
        auto& selection = named->selection;
        if (!receive(channel.pair, selected, deadline()) || selected.reserved ||
            (selected.message.stage == step::signed_out
                ? !selected.generation || !selected.data.valid() ||
                  (selection.generation && selection.generation != selected.generation)
                : selected.message.stage != step::resource_denied || selected.generation || !selected.data.empty())) {
            return static_cast<u8>(result::resource_access);
        }
        outcome = selected.message;
        selection.generation = selected.generation;
        named->data = selected.data;
    } else
#endif
    if (!receive(channel.pair, outcome, deadline())) {
        return mode == holder_mode::resource ? static_cast<u8>(result::resource_access) : 0;
    }
    if (outcome.format != version ||
        (outcome.stage != step::signed_out && outcome.stage != step::rejected &&
         (named == nullptr || outcome.stage != step::resource_denied)) ||
        !send(channel.pair, signal{version, step::finish}) || !reap_child(holder, channel.pair)) {
        return mode == holder_mode::resource ? static_cast<u8>(result::resource_access) : 0;
    }
#if XOS_PUMPKIN_USER_RESOURCE
    if (mode == holder_mode::resource) {
        close_ipc(broker_control.pair);
        if (!reap_child(broker, broker_control.pair)) {
            return static_cast<u8>(result::broker_cleanup);
        }
    }
#endif
    if (outcome.stage == step::resource_denied) { return user_login::resource_denied; }
    return outcome.stage == step::signed_out ? 1 : user_login::denied;
}

bool revoke_user(ipc_client& registrar, account_name account) {
    wire_reply response{};
    if (!lookup_user(registrar, account, response) || response.flags != 0) return false;
    const auto identity = response.token;
    auto revoke = request(wire_operation::revoke_account, identity);
    return expect(registrar, revoke, response, wire_status::ok) && lookup_user(registrar, account, response) &&
        response.flags == 1 && user_login::same_identity(identity, response.token);
}
#endif
}
