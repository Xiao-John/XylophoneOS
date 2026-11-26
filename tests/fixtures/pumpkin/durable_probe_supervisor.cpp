// SPDX-License-Identifier: Apache-2.0
#include "durable_probe.hpp"
#include "durable_probe_supervisor.hpp"

namespace xos::user::pumpkin::durable_probe {
namespace {
namespace storage = user::files_private_storage;

void close_pipe(u32 handle) {
    if (handle != 0) {
        (void)sdk::syscall(sys_pipe_close, handle);
    }
}

bool write_pipe(u32 handle, const void* packet, usize size) {
    return sdk::syscall(sys_pipe_write, handle, reinterpret_cast<u64>(packet), size) == static_cast<i64>(size);
}

struct discovery {
    ipc_channel channel{};
    bool published = false;

    ~discovery() {
        close_ipc(channel);
        if (published) {
            (void)sdk::ipc_name_unpublish(rendezvous);
        }
    }
};

class daemon {
public:
    ~daemon() {
        if (pid != 0) {
            control.close();
            (void)sdk::syscall(10, pid);
            process_status ignored{};
            (void)sdk::wait(pid, ignored);
        }
    }

    bool start(u32 image, grant_function grant, bool initialize) {
        discovery entry;
        entry.published = sdk::ipc_name_publish(rendezvous) == 0;
        pipe_handles pipe{};
        if (!entry.published || sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&pipe)) != 0) {
            return false;
        }
        sdk::spawn_options options;
        options.stdio[0] = pipe.read_token;
        const char* args[]{daemon_image, initialize ? "--durable-init-test" : "--durable-test", rendezvous};
        const i64 child = sdk::spawn_image_options(image, 3, args, options);
        close_pipe(pipe.read_token);
        storage::grant_reply lease;
        if (child > 0) {
            pid = static_cast<u64>(child);
        }
        const bool delivered = pid != 0 && grant(pid, storage::access::writer, lease) &&
            write_pipe(pipe.write_token, &lease, sizeof(lease));
        close_pipe(pipe.write_token);
        if (!delivered || !accept_control(entry)) {
            return false;
        }
        // Keep the discovery pair until the service has observed consumption
        // and the authenticated registrar can answer its first request.
        wire_reply ready;
        auto lookup = operation_request(wire_operation::lookup_account, true);
        return expect(control, lookup, ready, initialize ? wire_status::not_found : wire_status::ok);
    }

    bool stop() {
        control.close();
        process_status child{};
        const auto waited = sdk::wait(pid, child);
        if (waited == 0) {
            pid = 0;
        }
        return waited == 0 && child.outcome == process_outcome::exited && child.code == 0;
    }

    u64 pid = 0;
    ipc_client control;

private:
    bool accept_control(discovery& entry) {
        const auto deadline = storage::exchange_deadline();
        for (;;) {
            const i64 accepted = sdk::ipc_name_try_accept(entry.channel);
            if (accepted == 0 && authenticated_peer(entry.channel) == pid) {
                break;
            }
            if (accepted == 0) {
                close_ipc(entry.channel);
            } else if (accepted != process_error_would_block) {
                return false;
            }
            if (!storage::wait_tick(deadline)) {
                return false;
            }
        }
        control_message offer;
        i64 received = 0;
        while ((received = sdk::ipc_recv(entry.channel.receive, &offer, sizeof(offer))) ==
               process_error_would_block) {
            if (!storage::wait_tick(deadline)) {
                return false;
            }
        }
        return received == sizeof(offer) && offer.version == wire_version && offer.reserved == 0 &&
            offer.realm == disk_test_realm && control.bind(offer.channel, pid);
    }
};

struct test_account {
    wire_id identity;
    credential key;
    ~test_account() { wipe_bytes(&key, sizeof(key)); }
};

bool check_identity(ipc_client& client, const session_id& session, const wire_id& identity, wire_status expected) {
    auto who = operation_request(wire_operation::identity);
    who.token = {session.incarnation, session.number};
    wire_reply reply;
    return expect(client, who, reply, expected) &&
        (expected != wire_status::ok ||
         (reply.token.scope == identity.scope && reply.token.number == identity.number));
}

bool lookup(daemon& server, const wire_id& account_id, bool disabled) {
    auto request = operation_request(wire_operation::lookup_account, true);
    wire_reply reply;
    return expect(server.control, request, reply, wire_status::ok) &&
        reply.token.scope == account_id.scope && reply.token.number == account_id.number &&
        reply.flags == (disabled ? 1u : 0u);
}

bool enroll(daemon& server, test_account& account_data) {
    auto request = operation_request(wire_operation::create_account, true);
    wire_reply reply;
    const bool accepted = expect(server.control, request, reply, wire_status::ok);
    account_data.identity = reply.token;
    account_data.key = reply.key;
    wipe_bytes(&reply, sizeof(reply));
    if (!accepted || !has_bytes(account_data.key.bytes, secret_bytes)) {
        return false;
    }
    ipc_client user;
    return bind_ordinary(user, server.pid) &&
        login(user, {}, reply, wire_status::denied) &&
        login(user, account_data.key, reply, wire_status::ok) &&
        check_identity(user, {reply.token.scope, reply.token.number}, account_data.identity, wire_status::ok);
}

bool dash_login(u64 pid, const credential& key) {
    pipe_handles pipe{};
    if (sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&pipe)) != 0) {
        return false;
    }
    const char* args[]{"/bin/dash", "/bin/pumpkin_auth.sh"};
    sdk::spawn_options options;
    options.stdio[0] = pipe.read_token;
    options.prepare_child = [](u64 child, void*) {
        return sdk::syscall(sys_process_authority, child,
                            static_cast<u64>(process_authority_mode::copy_from_caller));
    };
    const i64 child = sdk::spawn_file_options(args[0], 2, args, options);
    close_pipe(pipe.read_token);
    dash_offer packet{pid, key};
    const bool delivered = child > 0 && write_pipe(pipe.write_token, &packet, sizeof(packet));
    wipe_bytes(&packet, sizeof(packet));
    close_pipe(pipe.write_token);
    process_status result{};
    const bool exited = child > 0 && sdk::wait(static_cast<u64>(child), result) == 0;
    return delivered && exited && result.outcome == process_outcome::exited && result.code == 0;
}

bool revoke_after_restart(daemon& server, const test_account& account_data) {
    if (!lookup(server, account_data.identity, false)) {
        return false;
    }
    ipc_client user;
    wire_reply reply;
    if (!bind_ordinary(user, server.pid) || !login(user, account_data.key, reply, wire_status::ok)) {
        return false;
    }
    const session_id session{reply.token.scope, reply.token.number};
    auto revoke = operation_request(wire_operation::revoke_account);
    revoke.token = account_data.identity;
    return check_identity(user, session, account_data.identity, wire_status::ok) &&
        dash_login(server.pid, account_data.key) &&
        expect(server.control, revoke, reply, wire_status::ok) &&
        check_identity(user, session, account_data.identity, wire_status::denied) &&
        login(user, account_data.key, reply, wire_status::denied);
}

bool check_revoked(daemon& server, const wire_id& account_id, const credential& key) {
    ipc_client user;
    wire_reply reply;
    return lookup(server, account_id, true) && bind_ordinary(user, server.pid) &&
        login(user, key, reply, wire_status::denied);
}
}

void run(u32 image, grant_function grant, const char* mode) {
    if (sdk::equal(mode, "cycle")) {
        test_account account_data;
        daemon initial, active, revoked;
        if (!initial.start(image, grant, true) || !enroll(initial, account_data) || !initial.stop()) {
            sdk::print("PUMPKIN_DURABLE_FAIL provision-or-enroll\n");
            return;
        }
        if (!active.start(image, grant, false) || !revoke_after_restart(active, account_data) || !active.stop()) {
            sdk::print("PUMPKIN_DURABLE_FAIL authenticate-or-revoke\n");
            return;
        }
        if (!revoked.start(image, grant, false) ||
            !check_revoked(revoked, account_data.identity, account_data.key) || !revoked.stop()) {
            sdk::print("PUMPKIN_DURABLE_FAIL restart-after-revoke\n");
            return;
        }
        sdk::print("PUMPKIN_DURABLE cycle-pass\n");
    } else if (sdk::equal(mode, "check")) {
        daemon restarted;
        if (!restarted.start(image, grant, false) ||
            !check_revoked(restarted, {disk_test_realm, 1}, {}) || !restarted.stop()) {
            sdk::print("PUMPKIN_DURABLE_FAIL boot-recovery\n");
            return;
        }
        sdk::print("PUMPKIN_DURABLE reboot-pass\n");
    } else {
        sdk::print("pumpkin-durable-test: use cycle or check\n");
    }
}
}
