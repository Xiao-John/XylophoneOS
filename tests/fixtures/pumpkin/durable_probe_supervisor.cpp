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
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
#include "../../../src/user/pumpkin/fat_resource_import.hpp"
#include "../../../src/user/pumpkin/named_operator.hpp"
#endif
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
        return control.call(lookup, ready) == exchange::received &&
            (ready.result == wire_status::not_found || (!initialize && ready.result == wire_status::ok));
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

#if XOS_PUMPKIN_NAMED_RESOURCE_STORE
constexpr char resource_name[] = "preview";
constexpr u32 first_content = 0x314d5550, second_content = 0x324d5550;
constexpr u64 first_generation = 4, second_generation = 5;

wire_request named_request(wire_operation operation, wire_id token, u64 generation, u32 data = 0) {
    named_resource_request fields{};
    fields.generation = generation;
    fields.data = data;
    fields.length = sizeof(resource_name) - 1;
    __builtin_memcpy(fields.name, resource_name, fields.length);
    auto request = operation_request(operation);
    request.name_length = sizeof(fields);
    request.token = token;
    __builtin_memcpy(request.name, &fields, sizeof(fields));
    return request;
}

struct named_user {
    ipc_client client;
    wire_id identity{};
    wire_id session{};

    bool start(daemon& server, account_name name, u64 expected_number, bool new_account) {
        auto request = operation_request(new_account ? wire_operation::create_account : wire_operation::lookup_account);
        request.name_length = static_cast<u32>(name.length);
        __builtin_memcpy(request.name, name.data, name.length);
        wire_reply reply{};
        if (!expect(server.control, request, reply, wire_status::ok) ||
            reply.token.scope != disk_test_realm || reply.token.number != expected_number || reply.flags) {
            wipe_bytes(&reply, sizeof(reply));
            return false;
        }
        identity = reply.token;
        if (!new_account) {
            auto rotate = operation_request(wire_operation::rotate_credential);
            rotate.token = identity;
            if (!expect(server.control, rotate, reply, wire_status::ok)) { return false; }
        }
        request.operation = wire_operation::authenticate;
        request.key = reply.key;
        const bool accepted = bind_ordinary(client, server.pid) && expect(client, request, reply, wire_status::ok);
        session = reply.token;
        wipe_bytes(&request, sizeof(request));
        wipe_bytes(&reply, sizeof(reply));
        return accepted && check_identity(client, {session.scope, session.number}, identity, wire_status::ok);
    }

    bool read(u64 generation, wire_status expected, u32 data = 0) {
        auto request = named_request(wire_operation::read_named_resource, session, generation);
        wire_reply reply{};
        return expect(client, request, reply, expected) &&
            (expected != wire_status::ok || (reply.token.scope == disk_test_realm &&
             reply.token.number == generation && reply.flags == data));
    }
};

bool named_cycle(daemon& server) {
    named_user alice, carol;
    if (!alice.start(server, {"alice", 5}, 1, true) || !carol.start(server, {"carol", 5}, 2, true)) { return false; }
    auto put = named_request(wire_operation::put_named_resource, alice.identity, 0, first_content);
    wire_reply reply{};
    if (!expect(carol.client, put, reply, wire_status::denied) ||
        !expect(server.control, put, reply, wire_status::ok) ||
        reply.token.scope != disk_test_realm || reply.token.number != first_generation ||
        !alice.read(first_generation, wire_status::ok, first_content) ||
        !carol.read(first_generation, wire_status::denied)) { return false; }

    auto replace = named_request(wire_operation::put_named_resource, carol.identity, first_generation, second_content);
    return expect(server.control, replace, reply, wire_status::ok) &&
        reply.token.scope == disk_test_realm && reply.token.number == second_generation &&
        expect(server.control, replace, reply, wire_status::conflict) &&
        alice.read(second_generation, wire_status::denied) &&
        carol.read(first_generation, wire_status::denied) &&
        carol.read(second_generation, wire_status::ok, second_content);
}

bool named_recover_then_erase(daemon& server) {
    named_user alice, carol;
    if (!alice.start(server, {"alice", 5}, 1, false) || !carol.start(server, {"carol", 5}, 2, false) ||
        !alice.read(second_generation, wire_status::denied) ||
        !carol.read(first_generation, wire_status::denied) ||
        !carol.read(second_generation, wire_status::ok, second_content)) { return false; }
    auto erase = named_request(wire_operation::erase_named_resource, {}, second_generation);
    wire_reply reply{};
    return expect(alice.client, erase, reply, wire_status::denied) &&
        expect(server.control, erase, reply, wire_status::ok) &&
        carol.read(second_generation, wire_status::denied);
}

bool named_absent(daemon& server) {
    named_user alice;
    if (!alice.start(server, {"alice", 5}, 1, false) ||
        !alice.read(second_generation, wire_status::denied) || !alice.read(0, wire_status::denied)) { return false; }
    auto erase = named_request(wire_operation::erase_named_resource, {}, second_generation);
    wire_reply reply{};
    return expect(server.control, erase, reply, wire_status::conflict);
}

#if XOS_PUMPKIN_USER_RESOURCE
u8 mutate_named(daemon& server, named_operator::packet& input, account_name owner) {
    const bool importing = input.op == named_operator::operation::import_fat;
    const bool put = importing || input.op == named_operator::operation::put;
    wire_reply found{};
    if (put) {
        auto lookup = operation_request(wire_operation::lookup_account);
        lookup.name_length = static_cast<u32>(owner.length);
        __builtin_memcpy(lookup.name, owner.data, owner.length);
        if (!expect(server.control, lookup, found, wire_status::ok) || found.flags != 0) return 0;
    }
    auto update = operation_request(put ? wire_operation::put_named_resource : wire_operation::erase_named_resource);
    if (importing) {
        file::client files;
        named_resource_data source{};
        if (!files.init() || !read_fat_resource(files, reinterpret_cast<const char*>(input.payload), source)) {
            return named_operator::source_rejected;
        }
        update.operation = wire_operation::put_named_binary;
        input.fields.data = source.length;
        __builtin_memcpy(update.key.bytes, source.bytes, sizeof(source.bytes));
    }
    update.token = found.token;
    update.name_length = sizeof(input.fields);
    __builtin_memcpy(update.name, &input.fields, sizeof(input.fields));
    wire_reply result{};
    if (server.control.call(update, result) != exchange::received) return 0;
    if (result.result == wire_status::conflict) return named_operator::conflict;
    if (result.result != wire_status::ok || (put && (result.token.scope != disk_test_realm ||
                                                      result.token.number <= input.fields.generation))) return 0;
    if (put) input.fields.generation = result.token.number;
    input.fields.data = 0;
    return 1;
}
#endif
#endif
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
                 [[maybe_unused]] u32 broker_image, [[maybe_unused]] const native_login::desktop_session* desktop) {
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
    bool ready = sdk::channel_receive_wait(proxy_control.receive, &mode, sizeof(mode),
                                                 anchor_guest::deadline()) == sizeof(mode);
#if XOS_PUMPKIN_USER_LOGIN
    user_login::account_packet selection{};
    ready = ready && sdk::channel_receive_wait(proxy_control.receive, &selection, sizeof(selection),
        anchor_guest::deadline()) == sizeof(selection) && user_login::selected_account(selection, mode);
    const account_name chosen{selection.name, selection.length};
#endif
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
    const auto named_mode = named_operator::for_scenario(mode);
    named_operator::packet named_input{};
    if (ready && named_mode != named_operator::operation{} &&
        (sdk::channel_receive_wait(proxy_control.receive, &named_input, sizeof(named_input), anchor_guest::deadline()) !=
             sizeof(named_input) || !named_operator::selection(named_input, named_mode))) {
        (void)sdk::syscall(10, static_cast<u64>(proxy));
        process_status failed{};
        (void)sdk::wait(static_cast<u64>(proxy), failed);
        return 22;
    }
    u8 named_result = 0;
#endif
    bool passed = false;
#if XOS_PUMPKIN_NATIVE_LOGIN
    u8 login_result = 0;
#endif
#if XOS_PUMPKIN_NATIVE_LOGIN || XOS_PUMPKIN_NAMED_RESOURCE_STORE
    process_stats before{}, after{};
    const bool bounded_start = sdk::syscall(sys_process_stats, reinterpret_cast<u64>(&before)) == 0;
#else
    const bool bounded_start = true;
#endif
    if (ready && bounded_start) {
        daemon server;
        bool initialized = mode == anchor_guest::scenario::cycle;
#if XOS_PUMPKIN_USER_LOGIN
        initialized = initialized || selection.initialize;
#endif
        const bool started = server.start(image, grant, initialized,
                                          {static_cast<u64>(proxy), proxy_control.transmit});
        switch (mode) {
        case anchor_guest::scenario::cycle: {
#if XOS_PUMPKIN_NAMED_RESOURCE_STORE
            passed = started && named_cycle(server) && server.stop();
#elif XOS_PUMPKIN_NATIVE_LOGIN
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
#if XOS_PUMPKIN_NAMED_RESOURCE_STORE
            passed = started && named_recover_then_erase(server) && server.stop();
            break;
        case anchor_guest::scenario::named_empty:
            passed = started && named_absent(server) && server.stop();
#else
            passed = started && check_revoked(server, {disk_test_realm, 1}, {}) && server.stop();
#endif
            break;
        case anchor_guest::scenario::stale:
            passed = !started && server.control_admitted && server.stop(11);
            break;
#if XOS_PUMPKIN_USER_LOGIN
        case anchor_guest::scenario::user_enroll:
            if (started) {
                login_result = native_login::enroll_user(server.control, chosen, proxy_control);
                passed = (login_result == 1 || login_result == user_login::duplicate_enrollment) && server.stop();
            }
            break;
        case anchor_guest::scenario::user_login:
            if (started) {
                login_result = native_login::login_user(holder_image, server.pid, server.control,
                    chosen, proxy_control);
                passed = login_result != 0 && server.stop();
            }
            break;
#if XOS_PUMPKIN_MOBIUS
        case anchor_guest::scenario::user_desktop:
        case anchor_guest::scenario::user_desktop_admin:
            if (started && desktop != nullptr) {
                auto selected = *desktop;
                selected.managed = mode == anchor_guest::scenario::user_desktop_admin;
                login_result = native_login::login_user(holder_image, server.pid, server.control,
                    chosen, proxy_control, 0, nullptr, &selected);
                const bool stopped = server.stop();
                passed = (login_result == 1 || login_result == user_login::denied ||
                          (selected.managed && login_result == user_login::desktop_revoked)) && stopped;
            }
            break;
#endif
#if XOS_PUMPKIN_USER_RESOURCE
#if XOS_PUMPKIN_NAMED_RESOURCE_STORE
        case anchor_guest::scenario::user_named_read:
            if (started) {
                native_login::named_read access{named_input.fields};
                login_result = broker_image ? native_login::login_user(holder_image, server.pid, server.control,
                    chosen, proxy_control, broker_image, &access)
                    : static_cast<u8>(native_login::result::broker_launch);
                named_input.fields = access.selection;
                named_input.fields.data = access.data.length;
                __builtin_memcpy(named_input.payload, access.data.bytes, sizeof(access.data.bytes));
                named_result = login_result;
                passed = (named_result == 1 || named_result == user_login::denied ||
                          named_result == user_login::resource_denied) && server.stop();
            }
            break;
        case anchor_guest::scenario::user_named_put:
        case anchor_guest::scenario::user_named_erase:
        case anchor_guest::scenario::user_named_import:
            if (started) {
                named_result = mutate_named(server, named_input, chosen);
                passed = named_result != 0 && server.stop();
            }
            break;
#else
        case anchor_guest::scenario::user_resource:
            if (started) {
                login_result = broker_image ? native_login::login_user(holder_image, server.pid, server.control,
                    chosen, proxy_control, broker_image)
                    : static_cast<u8>(native_login::result::broker_launch);
                passed = (login_result == 1 || login_result == user_login::denied) && server.stop();
            }
            break;
#endif
#endif
        case anchor_guest::scenario::user_revoke:
            passed = started && native_login::revoke_user(server.control, chosen) && server.stop();
            break;
#endif
        default:
            break;
        }
    }
#if XOS_PUMPKIN_NATIVE_LOGIN || XOS_PUMPKIN_NAMED_RESOURCE_STORE
    const bool recovered = bounded_start && sdk::syscall(sys_process_stats, reinterpret_cast<u64>(&after)) == 0 &&
        before.free_pages == after.free_pages && before.tasks == after.tasks && before.completions == after.completions;
    passed = passed && recovered;
#if XOS_PUMPKIN_MOBIUS
    if (anchor_guest::desktop_scenario(mode) && !recovered) { login_result = 0; }
#endif
#endif
    u8 outcome = static_cast<u8>(passed);
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
    if (passed && named_result) {
        named_input.sequence = 2;
        named_input.result = named_result;
        if (named_result != 1) named_input.fields = {};
        if (named_mode != named_operator::operation::select || named_result != 1) {
            __builtin_memset(named_input.payload, 0, sizeof(named_input.payload));
        }
        passed = sdk::channel_send_wait(proxy_control.transmit, &named_input, sizeof(named_input),
                                       anchor_guest::deadline()) == 0;
        outcome = passed ? named_result : 0;
    }
#endif
#if XOS_PUMPKIN_NATIVE_LOGIN
#if XOS_PUMPKIN_USER_LOGIN
    if (passed && (mode == anchor_guest::scenario::user_login || mode == anchor_guest::scenario::user_resource ||
                   anchor_guest::desktop_scenario(mode)) &&
        login_result == user_login::denied) { outcome = login_result; }
    if (passed && mode == anchor_guest::scenario::user_desktop_admin && login_result == user_login::desktop_revoked) {
        outcome = login_result;
    }
    if (passed && mode == anchor_guest::scenario::user_enroll && login_result == user_login::duplicate_enrollment) {
        outcome = login_result;
    }
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
