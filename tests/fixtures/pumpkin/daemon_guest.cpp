// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/native_ipc.hpp"
#if XOS_PUMPKIN_RESOURCE_BRIDGE
#include "pumpkin/resource_broker.hpp"
#endif

namespace {
using namespace xos;
using namespace xos::user::pumpkin;

constexpr char rendezvous_name[] = "pumpkin-p1-bootstrap";
constexpr char daemon_path[] = "/bin/pumpkind.elf";

[[noreturn]] void fail(const char* check) {
    sdk::print("PUMPKIN_P1_FAIL ");
    sdk::print(check);
    sdk::print("\n");
    sdk::exit(91);
}

void require(bool condition, const char* check) {
    if (!condition) {
        fail(check);
    }
}

u64 now() {
    const auto clock = monotonic_now();
    require(clock >= 0, "clock");
    return static_cast<u64>(clock);
}

void pause(u64 deadline) {
    const auto current = now();
    require(current < deadline && sleep_tick(current), "timeout");
}

void bind_user(ipc_client& client, u64 daemon) {
    const auto deadline = now() + max_request_ns;
    ipc_channel channel{};
    for (;;) {
        const auto result = sdk::ipc_name_connect(test_service_name, channel);
        if (result == 0) {
            require(client.bind(channel, daemon), "authenticate-daemon");
            return;
        }
        require(result == ipc_error_name_not_found, "connect");
        pause(deadline);
    }
}

wire_request request(wire_operation operation, const char* login = nullptr) {
    wire_request value{};
    value.operation = operation;
    if (login != nullptr) {
        value.name_length = static_cast<u32>(sdk::length(login));
        require(value.name_length <= name_limit, "login-length");
        __builtin_memcpy(value.name, login, value.name_length);
    }
    return value;
}

void expect(ipc_client& client, wire_request& command, wire_reply& response, wire_status result,
            const char* check) {
    require(client.call(command, response) == exchange::received && response.result == result, check);
}

struct daemon_run {
    u64 pid = 0;
    nonce realm;
    ipc_client control;

    void start(const char* mode = "--volatile-test") {
        require(sdk::ipc_name_publish(rendezvous_name) == 0, "publish-rendezvous");
        const char* args[] = {daemon_path, mode, rendezvous_name};
        const auto spawned = sdk::spawn_file(daemon_path, 3, args);
        require(spawned > 0, "spawn-daemon");
        pid = static_cast<u64>(spawned);
        const auto deadline = now() + max_request_ns;
        ipc_channel bootstrap{};
        for (;;) {
            const auto accepted = sdk::ipc_name_try_accept(bootstrap);
            if (accepted == 0) {
                if (authenticated_peer(bootstrap) == pid) {
                    break;
                }
                close_ipc(bootstrap);
            } else {
                require(accepted == process_error_would_block, "accept-rendezvous");
            }
            pause(deadline);
        }
        control_message offer{};
        i64 received = 0;
        while ((received = sdk::ipc_recv(bootstrap.receive, &offer, sizeof(offer))) == process_error_would_block) {
            pause(deadline);
        }
        require(received == sizeof(offer) && offer.version == wire_version && offer.reserved == 0,
                "bootstrap-offer");
        require(control.bind(offer.channel, pid), "bind-control");
        realm = offer.realm;

        // The daemon closes the temporary pair after observing consumption.
        // The following control request also verifies startup has finished.
        auto missing = request(wire_operation::lookup_account, "alice");
        wire_reply response;
        expect(control, missing, response, wire_status::not_found, "known-empty-test-realm");
        close_ipc(bootstrap);
        require(sdk::ipc_name_unpublish(rendezvous_name) == 0, "unpublish-rendezvous");
    }

    void stop() {
        control.close();
        process_status result{};
        require(sdk::wait(pid, result) == 0 && result.outcome == process_outcome::exited &&
                result.code == 0, "daemon-exit");
        ipc_channel absent{};
        require(sdk::ipc_name_connect(test_service_name, absent) == ipc_error_name_not_found, "name-cleanup");
    }
};

void exercise(daemon_run& daemon) {
    ipc_client first, second;
    bind_user(first, daemon.pid);
    bind_user(second, daemon.pid);
    auto create = request(wire_operation::create_account, "alice");
    wire_reply response{};
    expect(first, create, response, wire_status::denied, "client-cannot-create");
    expect(daemon.control, create, response, wire_status::ok, "create");
    const auto account = response.token;
    credential initial = response.key;
    require(account.scope == daemon.realm && account.number == 1, "identity-realm");
    expect(daemon.control, create, response, wire_status::conflict, "duplicate-create");

    auto login = request(wire_operation::authenticate, "alice");
    expect(first, login, response, wire_status::denied, "wrong-key");
    login.key = initial;
    expect(daemon.control, login, response, wire_status::denied, "registrar-role-distinct");
    expect(first, login, response, wire_status::ok, "authenticate");
    const auto session = response.token;
    auto identity = request(wire_operation::identity);
    identity.token = session;
    expect(second, identity, response, wire_status::denied, "session-bound-to-channel");
    expect(first, identity, response, wire_status::ok, "own-session");
    require(response.token.scope == account.scope && response.token.number == account.number, "identity-matches");
    auto logout = request(wire_operation::logout);
    logout.token = session;
    expect(first, logout, response, wire_status::ok, "logout");
    expect(first, identity, response, wire_status::denied, "logged-out");
    expect(first, login, response, wire_status::ok, "reauthenticate");
    identity.token = response.token;
    require(response.token.number != session.number, "new-session");

    auto rotate = request(wire_operation::rotate_credential);
    rotate.token = account;
    expect(daemon.control, rotate, response, wire_status::ok, "rotate-credential");
    credential fresh = response.key;
    expect(first, identity, response, wire_status::denied, "rotated-session-invalid");
    expect(first, login, response, wire_status::denied, "rotated-key-invalid");
    login.key = fresh;
    expect(first, login, response, wire_status::ok, "rotated-key-valid");
    identity.token = response.token;
    auto revoke = request(wire_operation::revoke_account);
    revoke.token = account;
    expect(daemon.control, revoke, response, wire_status::ok, "revoke-account");
    expect(first, identity, response, wire_status::denied, "revoked-session-invalid");
    expect(first, login, response, wire_status::denied, "revoked-key-invalid");
    auto lookup = request(wire_operation::lookup_account, "alice");
    expect(daemon.control, lookup, response, wire_status::ok, "find-tombstone");
    require(response.flags == 1 && response.token.number == account.number, "tombstone-identity");

    auto malformed = request(wire_operation::create_account, "malformed");
    malformed.reserved = 1;
    require(second.call(malformed, response) == exchange::outcome_unknown, "closed-after-send-result-unknown");
    require(second.call(malformed, response) == exchange::not_sent, "never-retry-closed-request");

    wipe_bytes(&initial, sizeof(initial));
    wipe_bytes(&fresh, sizeof(fresh));
    wipe_bytes(&login, sizeof(login));
    wipe_bytes(&response, sizeof(response));
}

#if XOS_PUMPKIN_RESOURCE_BRIDGE
constexpr char broker_path[] = "/bin/pumpkin_sealed_broker.elf";
constexpr char guest_fixture_path[] = "/bin/pumpkin_probe.elf";
constexpr u8 record[] = {'s', 'e', 'a', 'l', 'e', 'd'};

ipc_channel accept_bootstrap(u64 pid, u64 deadline) {
    ipc_channel handshake{};
    for (;;) {
        const auto accepted = sdk::ipc_name_try_accept(handshake);
        if (accepted == 0) {
            if (authenticated_peer(handshake) == pid) { break; }
            close_ipc(handshake);
        } else {
            require(accepted == process_error_would_block, "bridge-bootstrap-accept");
        }
        pause(deadline);
    }
    control_message offer{};
    require(receive_broker_frame(handshake, offer, deadline) && offer.version == wire_version &&
        !offer.reserved && offer.realm == nonce{} && authenticated_peer(offer.channel) == pid, "bridge-bootstrap-offer");
    close_ipc(handshake);
    require(sdk::ipc_name_unpublish(rendezvous_name) == 0, "bridge-bootstrap-unpublish");
    return offer.channel;
}

struct broker_run {
    u64 pid = 0;
    ipc_channel control{};

    void start(daemon_run& daemon, wire_id account, wire_id session, ipc_client& ordinary) {
        require(sdk::ipc_name_publish(rendezvous_name) == 0, "broker-rendezvous");
        const char* args[]{broker_path, rendezvous_name};
        const auto child = sdk::spawn_file(broker_path, 2, args);
        require(child > 0, "broker-spawn");
        pid = static_cast<u64>(child);
        const auto deadline = now() + max_request_ns;
        control = accept_bootstrap(pid, deadline);
        broker_configuration config{wire_version, sizeof(record), daemon.pid,
            {account.scope, account.number}, session.scope};
        __builtin_memcpy(config.bytes, record, sizeof(record));
        require(sdk::ipc_send(control.send, &config, sizeof(config)) == 0, "broker-configure");
        broker_ready ready{};
        require(receive_broker_frame(control, ready, deadline) && ready.version == wire_version &&
            !ready.reserved && ready.grant.peer == pid, "broker-ready");
        auto grant = request(wire_operation::admit_resource_broker);
        grant.name_length = sizeof(ready.grant);
        __builtin_memcpy(grant.name, &ready.grant, sizeof(ready.grant));
        wire_reply reply{};
        expect(ordinary, grant, reply, wire_status::denied, "broker-ordinary-cannot-admit");
        expect(daemon.control, grant, reply, wire_status::ok, "broker-registrar-admits");
    }

    void stop() {
        close_ipc(control);
        expect_exit();
    }

    void expect_exit() {
        process_status result{};
        require(sdk::wait(pid, result) == 0 && result.outcome == process_outcome::exited &&
            result.code == 0, "broker-exited");
        ipc_channel missing{};
        require(sdk::ipc_name_connect(broker_service_name, missing) == ipc_error_name_not_found, "broker-unpublished");
    }
};

wire_id prepare_read(ipc_client& actor, wire_id session, u64 number, wire_status expected) {
    auto begin = request(wire_operation::begin_resource_read);
    begin.token = session;
    begin.name_length = sizeof(number);
    __builtin_memcpy(begin.name, &number, sizeof(number));
    wire_reply reply{};
    expect(actor, begin, reply, expected, "prepare-read");
    return reply.token;
}

class read_lane {
public:
    explicit read_lane(u64 broker_pid) {
        const auto deadline = now() + max_request_ns;
        for (;;) {
            const auto connected = sdk::ipc_name_connect(broker_service_name, pair_);
            if (connected == 0) { break; }
            require(connected == ipc_error_name_not_found, "broker-connect");
            pause(deadline);
        }
        broker_opened opened{};
        require(authenticated_peer(pair_) == broker_pid && receive_broker_frame(pair_, opened, deadline) &&
            opened.version == wire_version && !opened.reserved && opened.connection, "broker-open");
        number_ = opened.connection;
    }
    ~read_lane() { close_ipc(pair_); }
    read_lane(const read_lane&) = delete;
    read_lane& operator=(const read_lane&) = delete;
    u64 number() const { return number_; }

    wire_id prepare(ipc_client& actor, wire_id session, wire_status expected = wire_status::ok) const {
        return prepare_read(actor, session, number_, expected);
    }

    void take(wire_id ticket, wire_status expected, const char* what) {
        broker_read read{wire_version, 0, broker_object_number, now() + max_request_ns, ticket};
        broker_data data{};
        require(sdk::ipc_send(pair_.send, &read, sizeof(read)) == 0 &&
            receive_broker_frame(pair_, data, read.deadline) && data.version == wire_version &&
            data.result == expected, what);
        if (expected == wire_status::ok) {
            require(data.data.length == sizeof(record) && __builtin_memcmp(data.data.bytes, record, sizeof(record)) == 0,
                "broker-data");
        } else {
            require(!data.data.length && !has_bytes(data.data.bytes, sizeof(data.data.bytes)), "broker-empty-denial");
        }
    }

private:
    ipc_channel pair_{};
    u64 number_ = 0;
};

int read_other_process(const char* name) {
    ipc_channel parental{}, rendezvous{};
    require(sdk::ipc_channel_create(0, parental) == 0 && sdk::ipc_name_connect(name, rendezvous) == 0,
        "separate-client-bootstrap");
    const auto parent = authenticated_peer(parental);
    const control_message offer{wire_version, 0, sdk::ipc_channel_for_peer(parental), {}};
    require(parent && authenticated_peer(rendezvous) == parent &&
        sdk::ipc_send(rendezvous.send, &offer, sizeof(offer)) == 0, "separate-client-offer");
    const auto deadline = now() + max_request_ns;
    u64 broker = 0;
    require(receive_broker_frame(parental, broker, deadline) && broker, "separate-client-broker");
    close_ipc(rendezvous);
    read_lane lane(broker);
    const auto number = lane.number();
    require(sdk::ipc_send(parental.send, &number, sizeof(number)) == 0, "separate-client-index");
    wire_id ticket{};
    require(receive_broker_frame(parental, ticket, deadline), "separate-client-ticket");
    lane.take(ticket, wire_status::denied, "broker-process-binding");
    close_ipc(parental);
    return 0;
}

void prove_process_binding(u64 broker, ipc_client& owner, wire_id session) {
    require(sdk::ipc_name_publish(rendezvous_name) == 0, "separate-client-listen");
    const char* args[]{guest_fixture_path, "--read-other-process", rendezvous_name};
    const auto child = sdk::spawn_file(guest_fixture_path, 3, args);
    require(child > 0, "separate-client-spawn");
    const auto deadline = now() + max_request_ns;
    auto control = accept_bootstrap(static_cast<u64>(child), deadline);
    require(sdk::ipc_send(control.send, &broker, sizeof(broker)) == 0, "separate-client-bind");
    u64 number = 0;
    require(receive_broker_frame(control, number, deadline) && number, "separate-client-connected");
    const auto ticket = prepare_read(owner, session, number, wire_status::ok);
    require(sdk::ipc_send(control.send, &ticket, sizeof(ticket)) == 0, "separate-client-challenge");
    process_status result{};
    require(sdk::wait(static_cast<u64>(child), result) == 0 &&
        result.outcome == process_outcome::exited && result.code == 0, "separate-client-exit");
    close_ipc(control);
}

wire_id identity_login(ipc_client& client, const char* name, const credential& key) {
    auto login = request(wire_operation::authenticate, name);
    login.key = key;
    wire_reply reply{};
    expect(client, login, reply, wire_status::ok, "bridge-user-login");
    wipe_bytes(&login, sizeof(login));
    return reply.token;
}

void exercise_bridge(daemon_run& daemon) {
    wire_reply reply{};
    auto create = request(wire_operation::create_account, "alice");
    expect(daemon.control, create, reply, wire_status::ok, "bridge-create-owner");
    const auto account = reply.token;
    auto alice_key = reply.key;
    auto other = request(wire_operation::create_account, "carol");
    expect(daemon.control, other, reply, wire_status::ok, "bridge-create-other");
    ipc_client owner, foreign;
    bind_user(owner, daemon.pid);
    bind_user(foreign, daemon.pid);
    auto session = identity_login(owner, "alice", alice_key);
    const auto foreign_session = identity_login(foreign, "carol", reply.key);
    wipe_bytes(&reply, sizeof(reply));

    broker_run broker;
    broker.start(daemon, account, session, owner);
    prove_process_binding(broker.pid, owner, session);
    {
        read_lane original(broker.pid), wrong_lane(broker.pid);
        wrong_lane.prepare(foreign, session, wire_status::denied);
        const auto ticket = original.prepare(owner, session);
        wrong_lane.take(ticket, wire_status::denied, "broker-connection-binding");
        original.take(ticket, wire_status::ok, "broker-owner");
        read_lane replay(broker.pid);
        replay.take(ticket, wire_status::denied, "broker-consumed");
    }
    {
        read_lane denied(broker.pid);
        denied.take(denied.prepare(foreign, foreign_session), wire_status::denied, "broker-other-account");
    }
    {
        read_lane expired(broker.pid);
        const auto ticket = expired.prepare(owner, session);
        require(sdk::syscall(sys_sleep_until, now() + 2'100'000'000ull) == 0, "broker-expiry-wait");
        expired.take(ticket, wire_status::denied, "broker-expired-ticket");
    }
    {
        read_lane pending(broker.pid);
        const auto ticket = pending.prepare(owner, session);
        auto logout = request(wire_operation::logout);
        logout.token = session;
        expect(owner, logout, reply, wire_status::ok, "bridge-logout");
        pending.take(ticket, wire_status::denied, "broker-after-logout");
        session = identity_login(owner, "alice", alice_key);
    }
    {
        read_lane pending(broker.pid);
        ipc_client temporary;
        bind_user(temporary, daemon.pid);
        const auto temporary_session = identity_login(temporary, "alice", alice_key);
        const auto ticket = pending.prepare(temporary, temporary_session);
        temporary.close();
        pending.take(ticket, wire_status::denied, "broker-after-origin-disconnect");
    }
    wipe_bytes(&alice_key, sizeof(alice_key));
    wire_id old_ticket{};
    {
        read_lane pending(broker.pid);
        old_ticket = pending.prepare(owner, session);
    }
    broker.stop();
    broker_run restarted;
    restarted.start(daemon, account, session, owner);
    {
        read_lane stale(restarted.pid);
        stale.take(old_ticket, wire_status::denied, "broker-replaced");
        read_lane current(restarted.pid);
        current.take(current.prepare(owner, session), wire_status::ok, "broker-replacement-owner");
    }
    {
        read_lane pending(restarted.pid);
        const auto ticket = pending.prepare(owner, session);
        auto revoke = request(wire_operation::revoke_account);
        revoke.token = account;
        expect(daemon.control, revoke, reply, wire_status::ok, "bridge-revoke");
        pending.take(ticket, wire_status::denied, "broker-after-revocation");
    }
    owner.close();
    foreign.close();
    daemon.stop();
    restarted.expect_exit();
    close_ipc(restarted.control);
}
#endif

}

extern "C" int xos_user_main([[maybe_unused]] const xos::startup_info* startup) {
#if XOS_PUMPKIN_RESOURCE_BRIDGE
    if (startup != nullptr && startup->magic == xos::startup_magic && startup->argc == 3) {
        const auto* args = reinterpret_cast<const char* const*>(startup->argv);
        if (sdk::equal(args[1], "--read-other-process")) { return read_other_process(args[2]); }
    }
#endif
    daemon_run daemon;
    daemon.start();
    exercise(daemon);
    daemon.stop();
    daemon_run restarted;
    restarted.start();
    require(restarted.realm != daemon.realm, "new-test-realm");
    restarted.stop();
    sdk::print("PUMPKIN_P1_PASS real-ipc volatile-store role-and-session-isolation result-unknown cleanup\n");
#if XOS_PUMPKIN_RESOURCE_BRIDGE
    daemon_run authority;
    authority.start("--resource-bridge-test");
    exercise_bridge(authority);
    sdk::print("PUMPKIN_BRIDGE_PASS independent-broker owner wrong-account endpoint process one-shot expiry logout disconnect replacement revoke\n");
#endif
    return 0;
}
