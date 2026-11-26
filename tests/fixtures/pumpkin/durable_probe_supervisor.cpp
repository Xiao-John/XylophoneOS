// SPDX-License-Identifier: Apache-2.0
#include "durable_probe.hpp"
#include "durable_probe_supervisor.hpp"
#if XOS_PUMPKIN_ANCHORED_PROBE
#include "../../../src/user/pumpkin/generation_guest.hpp"
#endif
#if XOS_PUMPKIN_NATIVE_LOGIN
#include "../../../src/user/pumpkin/native_login.hpp"
#endif
#if XOS_PUMPKIN_USER_LOGIN
#include "../../../src/user/pumpkin/user_login.hpp"
#endif

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

struct anchor_startup {
    u64 proxy = 0;
    u32 control = 0;
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

    bool start(u32 image, grant_function grant, bool initialize, [[maybe_unused]] anchor_startup anchor = {}) {
        discovery entry;
        entry.published = sdk::ipc_name_publish(rendezvous) == 0;
        pipe_handles pipe{};
        if (!entry.published || sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&pipe)) != 0) {
            return false;
        }
        sdk::spawn_options options;
        options.stdio[0] = pipe.read_token;
        const char* mode = initialize ? "--durable-init-test" : "--durable-test";
#if XOS_PUMPKIN_ANCHORED_PROBE
        if (anchor.proxy != 0) {
            mode = initialize ? "--anchored-init-test" : "--anchored-test";
            options.prepare_context = &anchor.proxy;
            options.prepare_child = [](u64 child, void* context) -> i64 {
                anchor_guest::pair endpoints{};
                return anchor_guest::create_pair(child, *static_cast<u64*>(context), endpoints)
                    ? 0 : process_error_denied;
            };
        }
#endif
        const char* args[]{daemon_image, mode, rendezvous};
        const i64 child = sdk::spawn_image_options(image, 3, args, options);
        close_pipe(pipe.read_token);
        storage::grant_reply lease;
        if (child > 0) {
            pid = static_cast<u64>(child);
        }
        bool delivered = pid != 0 && grant(pid, storage::access::writer, lease) &&
            write_pipe(pipe.write_token, &lease, sizeof(lease));
#if XOS_PUMPKIN_ANCHORED_PROBE
        if (delivered && anchor.proxy != 0) {
            const anchor_guest::bind_proxy binding{pid};
            delivered = sdk::channel_send_wait(anchor.control, &binding, sizeof(binding), anchor_guest::deadline()) == 0 &&
                write_pipe(pipe.write_token, &anchor.proxy, sizeof(anchor.proxy));
        }
#endif
        close_pipe(pipe.write_token);
        control_admitted = delivered && accept_control(entry);
        if (!control_admitted) {
            return false;
        }
        // Keep the discovery pair until the service has observed consumption
        // and the authenticated registrar can answer its first request.
        wire_reply ready;
        auto lookup = operation_request(wire_operation::lookup_account, true);
        return expect(control, lookup, ready, initialize ? wire_status::not_found : wire_status::ok);
    }

    bool stop(int code = 0) {
        control.close();
        process_status child{};
        const auto waited = sdk::wait(pid, child);
        if (waited == 0) {
            pid = 0;
        }
        return waited == 0 && child.outcome == process_outcome::exited && child.code == code;
    }

    u64 pid = 0;
    ipc_client control;
    bool control_admitted = false;

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

bool revoke_live_session(daemon& server, const test_account& account_data, bool with_dash = true) {
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
        (!with_dash || dash_login(server.pid, account_data.key)) &&
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
        if (!active.start(image, grant, false) || !revoke_live_session(active, account_data) || !active.stop()) {
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

#if XOS_PUMPKIN_ANCHORED_PROBE
int run_anchored(u32 image, u32 proxy_image, grant_function grant, [[maybe_unused]] u32 holder_image,
                 [[maybe_unused]] u32 broker_image) {
    anchor_guest::pair proxy_control{};
    sdk::spawn_options options{};
    for (auto& fd : options.stdio) fd = -2;
    options.prepare_context = &proxy_control;
    options.prepare_child = [](u64 child, void* context) -> i64 {
        auto& endpoints = *static_cast<anchor_guest::pair*>(context);
        if (!anchor_guest::create_pair(sdk::pid(), child, endpoints)) return process_error_denied;
        return sdk::pio_grant(pio_grant_action::grant, child, pio_resource_com1);
    };
    const char* args[]{"p2_anchor_proxy"};
    const i64 proxy = sdk::spawn_image_options(proxy_image, 1, args, options);
    if (proxy <= 0) return 21;

    anchor_guest::scenario mode{};
    const bool ready = sdk::channel_receive_wait(proxy_control.receive, &mode, sizeof(mode),
                                                 anchor_guest::deadline()) == sizeof(mode);
    bool passed = false;
#if XOS_PUMPKIN_NATIVE_LOGIN
    u8 login_result = 0;
    process_stats before{}, after{};
    const bool bounded_start = sdk::syscall(sys_process_stats, reinterpret_cast<u64>(&before)) == 0;
#else
    const bool bounded_start = true;
#endif
    if (ready && bounded_start) {
        daemon server;
        const bool initialized = mode == anchor_guest::scenario::cycle || mode == anchor_guest::scenario::user_enroll;
        const bool started = server.start(image, grant, initialized,
                                          {static_cast<u64>(proxy), proxy_control.transmit});
        switch (mode) {
        case anchor_guest::scenario::cycle: {
#if XOS_PUMPKIN_NATIVE_LOGIN
            if (started) {
                const auto result = native_login::run(holder_image, server.pid, server.control, {account, sizeof(account) - 1});
                login_result = static_cast<u8>(result);
                passed = result == native_login::result::passed && server.stop();
            }
#else
            test_account account_data;
            passed = started && enroll(server, account_data) &&
                revoke_live_session(server, account_data, false) && server.stop();
#endif
            break;
        }
        case anchor_guest::scenario::healthy:
            passed = started && check_revoked(server, {disk_test_realm, 1}, {}) && server.stop();
            break;
        case anchor_guest::scenario::stale:
            passed = !started && server.control_admitted && server.stop(11);
            break;
#if XOS_PUMPKIN_USER_LOGIN
        case anchor_guest::scenario::user_enroll:
            passed = started && native_login::enroll_user(server.control, {account, sizeof(account) - 1}, proxy_control) &&
                server.stop();
            break;
        case anchor_guest::scenario::user_login:
            if (started) {
                login_result = native_login::login_user(holder_image, server.pid, server.control,
                    {account, sizeof(account) - 1}, proxy_control);
                passed = login_result != 0 && server.stop();
            }
            break;
#if XOS_PUMPKIN_USER_RESOURCE
        case anchor_guest::scenario::user_resource:
            if (started) {
                login_result = broker_image ? native_login::login_user(holder_image, server.pid, server.control,
                    {account, sizeof(account) - 1}, proxy_control, broker_image)
                    : static_cast<u8>(native_login::result::broker_launch);
                passed = (login_result == 1 || login_result == user_login::denied) && server.stop();
            }
            break;
#endif
        case anchor_guest::scenario::user_revoke:
            passed = started && native_login::revoke_user(server.control, {account, sizeof(account) - 1}) && server.stop();
            break;
#endif
        default:
            break;
        }
    }
#if XOS_PUMPKIN_NATIVE_LOGIN
    passed = passed && sdk::syscall(sys_process_stats, reinterpret_cast<u64>(&after)) == 0 &&
        before.free_pages == after.free_pages && before.tasks == after.tasks && before.completions == after.completions;
#endif
    u8 outcome = static_cast<u8>(passed);
#if XOS_PUMPKIN_NATIVE_LOGIN
#if XOS_PUMPKIN_USER_LOGIN
    if (passed && (mode == anchor_guest::scenario::user_login || mode == anchor_guest::scenario::user_resource) &&
        login_result == user_login::denied) { outcome = login_result; }
    if (!passed && login_result >= static_cast<u8>(native_login::result::holder_start)) { outcome = login_result; }
#else
    if (!passed && login_result > 1) { outcome = login_result; }
#endif
#endif
    const anchor_guest::supervisor_result result{outcome};
    if (!ready || sdk::channel_send_wait(proxy_control.transmit, &result, sizeof(result), anchor_guest::deadline()) != 0) {
        (void)sdk::syscall(10, static_cast<u64>(proxy));
    }
    process_status child{};
    const bool stopped = sdk::wait(static_cast<u64>(proxy), child) == 0 &&
        child.outcome == process_outcome::exited && child.code == 0;
    return passed && stopped ? 0 : 22;
}
#endif
}
