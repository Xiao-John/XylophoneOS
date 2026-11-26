// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/native_ipc.hpp"

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

    void start() {
        require(sdk::ipc_name_publish(rendezvous_name) == 0, "publish-rendezvous");
        const char* args[] = {daemon_path, "--volatile-test", rendezvous_name};
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

}

extern "C" int xos_user_main(const xos::startup_info*) {
    daemon_run daemon;
    daemon.start();
    exercise(daemon);
    daemon.stop();
    daemon_run restarted;
    restarted.start();
    require(restarted.realm != daemon.realm, "new-test-realm");
    restarted.stop();
    sdk::print("PUMPKIN_P1_PASS real-ipc volatile-store role-and-session-isolation result-unknown cleanup\n");
    return 0;
}
