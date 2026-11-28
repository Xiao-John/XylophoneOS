// SPDX-License-Identifier: Apache-2.0
// Ordinary native SDK clients, an independent read-only provider, and an
// explicitly private fixture control channel. No model or action executor.
#include <xos/observation.hpp>
#include <xos/observation_sources.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include "observation_native_guest.hpp"

namespace {
using namespace xos;
namespace obs = xos::observation;
namespace native_test = xos::test_observation_native;
constexpr const char* image = "/bin/observe.elf";
constexpr const char* observation_name = "p1a-observation";
constexpr const char* control_name = "p1a-observation-control";
constexpr const char* peer_name = "p1a-observation-peer";
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
enum class operation : u32 { ready, authorize, revoke, activate, stop, stall, resume, peer_read, peer_done };
struct control { operation action; u32 reserved; u64 value[7]; };
static_assert(sizeof(control) == 64);

[[noreturn]] void fail(const char* label, i64 code = 0) {
    sdk::print("OBS_FAIL "); sdk::print(label); sdk::print(" result=");
    sdk::signed_decimal(code); sdk::print("\n"); sdk::exit(91);
}
void require(bool good, const char* label, i64 code = 0) { if (!good) fail(label, code); }
u64 now() { return native_test::now(); }
u64 deadline() { return now() + 2'000'000'000ULL; }
void decimal_text(u64 number, char (&text)[21]) {
    char reversed[20]; u32 count = 0;
    do { reversed[count++] = static_cast<char>('0' + number % 10); number /= 10; } while (number);
    for (u32 i = 0; i < count; ++i) text[i] = reversed[count - i - 1];
    text[count] = 0;
}
u64 parse(const char* text) {
    require(text && *text, "empty-number"); u64 result = 0;
    for (; *text; ++text) {
        require(*text >= '0' && *text <= '9' && result <= (~u64{0} - 9) / 10, "bad-number");
        result = result * 10 + static_cast<u64>(*text - '0');
    }
    return result;
}
void authenticate(const ipc_channel& channel, u64 expected) {
    u64 sender = 0, receiver = 0;
    require(!sdk::ipc_endpoint_peer(channel.send, sender) &&
            !sdk::ipc_endpoint_peer(channel.receive, receiver) && sender == expected && receiver == expected,
            "control-peer");
}
void close(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
void send(const ipc_channel& channel, const control& message) {
    const u64 end = deadline();
    for (;;) {
        const i64 result = sdk::ipc_send(channel.send, &message, sizeof(message));
        if (!result) return;
        require(result == ipc_error_full && now() < end, "control-send", result);
        require(!sdk::ipc_wait_until(channel.send, ipc_wait_mode::send, end), "control-send-wait");
    }
}
control receive(const ipc_channel& channel) {
    const u64 end = deadline(); control message{};
    for (;;) {
        const i64 result = sdk::ipc_recv(channel.receive, &message, sizeof(message));
        if (result != process_error_would_block) {
            require(result == sizeof(message) && !message.reserved && now() < end, "control-receive", result);
            return message;
        }
        require(!sdk::ipc_wait_until(channel.receive, ipc_wait_mode::receive, end), "control-receive-wait");
    }
}
ipc_channel connect_control(const char* name, u64 pid) {
    const u64 end = deadline(); ipc_channel channel{};
    for (;;) {
        const i64 result = sdk::ipc_name_connect(name, channel);
        if (!result) break;
        require(result == ipc_error_name_not_found && now() < end, "control-connect", result);
        sdk::yield();
    }
    authenticate(channel, pid); return channel;
}
ipc_channel accept_control(u64 expected) {
    const u64 end = deadline(); ipc_channel channel{};
    for (;;) {
        const i64 result = sdk::ipc_name_try_accept(channel);
        if (!result) break;
        require(result == process_error_would_block && now() < end, "control-accept", result);
        sdk::yield();
    }
    authenticate(channel, expected); return channel;
}
void wait(u64 pid) {
    process_status value{};
    const i64 result = sdk::wait(pid, value);
    require(!result && value.pid == pid && value.outcome == process_outcome::exited && value.code == 0,
            "child-wait", result ? result : value.code);
}
void record(const obs::response& value) {
    require(obs::valid_response(value), "record-shape");
    sdk::print("OBS_JSON ");
    require(obs::print_json(value) == obs::status::ok, "record-json");
}
obs::response read(obs::client& client, obs::kind kind, obs::status expected,
                   u64 object = 0, u64 generation = 0) {
    obs::response value{};
    const auto result = client.read(kind, deadline(), value, object, generation);
    require(result == expected, "typed-read-outcome", static_cast<i64>(result));
    record(value); return value;
}

// These two roots are explicit fixture configuration. The real catalog
// implementation is exercised; no ELF runtime or CA load is implied.
int provider(u64 network_pid) {
    dynamic::generation_root roots[2]{};
    roots[0].id = 101; roots[1].id = 102;
    for (u32 i = 0; i < 32; ++i) { roots[0].sha256[i] = static_cast<u8>(i + 1); roots[1].sha256[i] = static_cast<u8>(i + 65); }
    dynamic::activation_catalog catalog;
    require(catalog.initialize(roots, 2, 0) == dynamic::error::none, "catalog-initialize");
    net2::session_client network;
    if (network_pid) require(!network.connect(network_pid), "network-connect");
    obs::sources source{}; source.runtime = &catalog;
    source.network = network_pid ? &network : nullptr;
    obs::server server;
    require(server.initialize(obs::sources::capture, &source) == obs::status::ok, "server-initialize");
    const u64 parent = native_test::own().parent_pid;
    require(parent && !sdk::ipc_name_publish(control_name), "control-publish");
    ipc_channel controller = accept_control(parent);
    source.service_endpoint = controller.send;
    require(!sdk::ipc_name_publish(observation_name), "observation-publish");
    send(controller, {operation::ready, 0, {sdk::pid(), server.epoch()}});
    bool stalled = false;
    const u64 expires = now() + 25'000'000'000ULL;
    while (now() < expires) {
        // Retire closed prior connections before authorizing a reconnect of
        // the same PID; no timing assumption about the peer's last close.
        if (!stalled) (void)server.poll();
        // A connect request precedes its controller authorization command.
        // Drain admission first; bare PID knowledge never grants access.
        for (u32 i = 0; i < obs::max_clients; ++i) {
            ipc_channel incoming{};
            const i64 accepted = sdk::ipc_name_try_accept(incoming);
            if (accepted == process_error_would_block) break;
            require(!accepted, "server-accept", accepted);
            if (server.attach(incoming) != obs::status::ok) close(incoming);
        }
        control message{};
        const i64 received = sdk::ipc_recv(controller.receive, &message, sizeof(message));
        if (received != process_error_would_block) {
            require(received == sizeof(message) && !message.reserved, "server-control", received);
            authenticate(controller, parent);
            obs::status result = obs::status::ok;
            switch (message.action) {
            case operation::authorize:
                result = server.authorize(message.value[0], static_cast<u32>(message.value[1]),
                    static_cast<u32>(message.value[2]), now() + 15'000'000'000ULL); break;
            case operation::revoke: result = server.revoke(message.value[0]); break;
            case operation::activate:
                require(catalog.activate(static_cast<u32>(message.value[0]), catalog.sequence()) ==
                        dynamic::error::none, "catalog-activate"); break;
            case operation::stall: stalled = true; break;
            case operation::resume: stalled = false; break;
            case operation::stop:
                send(controller, {message.action, 0, {static_cast<u64>(result)}});
                require(receive(controller).action == operation::stop, "stop-ack-consumed");
                server.close(); close(controller); return 0;
            default: fail("unknown-control-operation");
            }
            send(controller, {message.action, 0, {static_cast<u64>(result)}});
        }
        if (!stalled) (void)server.poll();
        sdk::yield();
    }
    fail("server-lifetime");
}
struct service { u64 pid, epoch; ipc_channel control_channel; };
service start_service(u64 network_pid = 0) {
    char network_text[21]{}; decimal_text(network_pid, network_text);
    const char* args[]{image, "provider", network_text};
    const i64 pid = sdk::spawn_file(image, 3, args);
    require(pid > 0, "spawn-provider", pid);
    service result{static_cast<u64>(pid), 0, connect_control(control_name, static_cast<u64>(pid))};
    const auto ready = receive(result.control_channel);
    require(ready.action == operation::ready && ready.value[0] == result.pid && ready.value[1], "ready-identity");
    result.epoch = ready.value[1]; return result;
}
obs::status command(service& service, operation action, u64 first = 0, u64 second = 0, u64 third = 0) {
    send(service.control_channel, {action, 0, {first, second, third}});
    const auto reply = receive(service.control_channel);
    require(reply.action == action && reply.value[0] <= static_cast<u64>(obs::status::unsupported), "control-ack");
    return static_cast<obs::status>(reply.value[0]);
}
void grant(service& service, u64 pid, u32 kinds = obs::all_kinds, u32 reads = 32) {
    require(command(service, operation::authorize, pid, kinds, reads) == obs::status::ok, "authorize");
}
void connect(obs::client& client, const service& server, u64 epoch = 0) {
    require(client.connect(observation_name, server.pid, epoch ? epoch : server.epoch) == obs::status::ok, "client-connect");
}
void stop(service& service) {
    require(command(service, operation::stop) == obs::status::ok, "stop");
    send(service.control_channel, {operation::stop, 0, {}});
    wait(service.pid); close(service.control_channel);
}
int peer(u64 service_pid, u64 epoch) {
    obs::client client;
    require(client.connect(observation_name, service_pid, epoch) == obs::status::ok, "peer-connect");
    require(!sdk::ipc_name_publish(peer_name), "peer-publish");
    ipc_channel controller = accept_control(native_test::own().parent_pid);
    send(controller, {operation::ready, 0, {sdk::pid()}});
    require(receive(controller).action == operation::peer_read, "peer-read-command");
    (void)read(client, obs::kind::resource, obs::status::ok);
    send(controller, {operation::peer_done, 0, {sdk::pid()}});
    require(receive(controller).action == operation::peer_done, "peer-result-consumed");
    close(controller); return 0;
}
void authorized(u64 network_pid) {
    auto server = start_service(network_pid); obs::client client; connect(client, server); grant(server, sdk::pid());
    for (u32 index = 1; index <= 6; ++index) {
        const auto subject = static_cast<obs::kind>(index);
        const auto value = read(client, subject, subject == obs::kind::trust ||
            (subject == obs::kind::network && !network_pid) ?
            obs::status::unavailable : obs::status::ok);
        if (subject == obs::kind::network && network_pid)
            require(value.object_id == network_pid && value.generation && value.value.values[1] == 1 &&
                    value.value.values[2] == 1, "live-static-network");
    }
    client.close(); stop(server);
}
void denials() {
    auto server = start_service();
    require(command(server, operation::authorize, sdk::pid(), obs::all_kinds, 4) == obs::status::unauthorized,
            "bare-pid-not-authority");
    obs::client client; connect(client, server);
    (void)read(client, obs::kind::process, obs::status::unauthorized);
    grant(server, sdk::pid(), obs::mask(obs::kind::process), 8);
    (void)read(client, obs::kind::trust, obs::status::unauthorized);
    (void)read(client, obs::kind::process, obs::status::ok);
    obs::client stale; connect(stale, server, server.epoch == 1 ? 2 : 1);
    (void)read(stale, obs::kind::process, obs::status::stale);
    obs::client wrong;
    require(wrong.connect(observation_name, server.pid + 1, server.epoch) == obs::status::stale,
            "wrong-server-pid");
    client.close(); stop(server);
}
void quota() {
    auto server = start_service(); obs::client client; connect(client, server); grant(server, sdk::pid(), obs::all_kinds, 1);
    (void)read(client, obs::kind::process, obs::status::ok);
    (void)read(client, obs::kind::resource, obs::status::quota);
    char pid_text[21]{}, epoch_text[21]{};
    decimal_text(server.pid, pid_text); decimal_text(server.epoch, epoch_text);
    const char* args[]{image, "peer", pid_text, epoch_text};
    const i64 other = sdk::spawn_file(image, 4, args);
    require(other > 0, "spawn-independent-peer", other);
    ipc_channel peer_control = connect_control(peer_name, static_cast<u64>(other));
    const auto ready = receive(peer_control);
    require(ready.action == operation::ready && ready.value[0] == static_cast<u64>(other), "peer-ready");
    grant(server, static_cast<u64>(other), obs::all_kinds, 2);
    send(peer_control, {operation::peer_read, 0, {}});
    require(receive(peer_control).action == operation::peer_done, "peer-success");
    send(peer_control, {operation::peer_done, 0, {}});
    wait(static_cast<u64>(other)); close(peer_control);
    (void)read(client, obs::kind::process, obs::status::quota);
    client.close(); stop(server);
}
void lifecycle() {
    auto server = start_service(); obs::client client; connect(client, server); grant(server, sdk::pid());
    const auto before = read(client, obs::kind::runtime, obs::status::ok);
    require(before.object_id == 101 && before.generation == 1, "initial-runtime-root");
    require(command(server, operation::activate, 1) == obs::status::ok, "activate-next-root");
    (void)read(client, obs::kind::runtime, obs::status::stale, before.object_id, before.generation);
    const auto after = read(client, obs::kind::runtime, obs::status::ok);
    require(after.object_id == 102 && after.generation == 2, "current-runtime-root");
    require(command(server, operation::revoke, sdk::pid()) == obs::status::ok, "revoke");
    (void)read(client, obs::kind::process, obs::status::revoked);
    grant(server, sdk::pid());
    (void)read(client, obs::kind::process, obs::status::ok);
    const u64 old_pid = server.pid, old_epoch = server.epoch;
    const u32 old_endpoint = server.control_channel.send;
    stop(server);
    auto native_input = native_test::request(observe_native::query::service, old_endpoint);
    observe_native::snapshot native_output{};
    require(sdk::observe(native_input, native_output) == observe_native::result::denied &&
            native_test::zero(native_output), "retired-native-endpoint");
    obs::response absent{};
    require(client.read(obs::kind::process, deadline(), absent) == obs::status::revoked, "retired-client-channel");
    server = start_service();
    require(server.pid != old_pid && server.epoch != old_epoch, "restart-new-incarnation");
    obs::client wrong;
    require(wrong.connect(observation_name, old_pid, old_epoch) == obs::status::stale, "restart-old-pid");
    obs::client old; connect(old, server, old_epoch);
    (void)read(old, obs::kind::process, obs::status::stale);
    obs::client recovered; connect(recovered, server); grant(server, sdk::pid());
    (void)read(recovered, obs::kind::process, obs::status::ok);
    recovered.close(); stop(server);
}
void deadlines() {
    auto server = start_service(); obs::client client; connect(client, server); grant(server, sdk::pid());
    obs::response value{};
    require(client.read(obs::kind::process, now(), value) == obs::status::deadline, "already-expired-client");
    (void)read(client, obs::kind::process, obs::status::ok);
    require(command(server, operation::stall) == obs::status::ok, "stall-live-service");
    auto input = native_test::request(observe_native::query::service, server.control_channel.send);
    observe_native::snapshot live{};
    require(sdk::observe(input, live) == observe_native::result::ok && live.pid == server.pid, "stalled-peer-live");
    const u64 began = now(), end = began + 150'000'000ULL;
    require(client.read(obs::kind::process, end, value) == obs::status::deadline, "unresponsive-deadline");
    const u64 finished = now();
    require(finished >= end && finished - end <= 300'000'000ULL, "deadline-bound");
    require(command(server, operation::resume) == obs::status::ok, "resume-same-service");
    sdk::print("OBS_DEADLINE elapsed_ns="); sdk::decimal(finished - began); sdk::print("\n");
    obs::client recovered; connect(recovered, server); grant(server, sdk::pid());
    (void)read(recovered, obs::kind::process, obs::status::ok);
    recovered.close(); stop(server);
}
[[noreturn]] void replace_self() {
    const auto before = native_test::own();
    sdk::spawn_options options{}; options.replace_image = true;
    const char* missing[]{"/missing-observation-exec"};
    require(sdk::spawn_file_options(missing[0], 1, missing, options) < 0, "failed-exec-refused");
    const auto retained = native_test::own();
    require(retained.pid == before.pid && retained.image_generation == before.image_generation,
            "failed-exec-retains-generation");
    sdk::print("OBS_FAILED_EXEC_RETAINED\n");
    char pid_text[21]{}, generation_text[21]{};
    decimal_text(before.pid, pid_text); decimal_text(before.image_generation, generation_text);
    const char* args[]{image, "after-exec", pid_text, generation_text};
    fail("successful-exec-returned", sdk::spawn_file_options(image, 4, args, options));
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    require(startup->argc >= 2, "arguments");
    if (sdk::equal(args[1], "provider") && startup->argc == 3) return provider(parse(args[2]));
    if (sdk::equal(args[1], "peer") && startup->argc == 4) return peer(parse(args[2]), parse(args[3]));
    if (sdk::equal(args[1], "after-exec") && startup->argc == 4) {
        const auto value = native_test::own();
        require(startup->version == 3 && value.pid == parse(args[2]) &&
                value.image_generation == parse(args[3]) + 1, "successful-exec-generation");
        sdk::print("OBS_SUCCESSFUL_EXEC_GENERATION\nOBS_PASS exec\n"); return 0;
    }
    if (sdk::equal(args[1], "native")) native_test::run_native_checks();
    else if (sdk::equal(args[1], "authorized")) authorized(0);
    else if (sdk::equal(args[1], "network") && startup->argc == 3) authorized(parse(args[2]));
    else if (sdk::equal(args[1], "denials")) denials();
    else if (sdk::equal(args[1], "quota")) quota();
    else if (sdk::equal(args[1], "lifecycle")) lifecycle();
    else if (sdk::equal(args[1], "deadline")) deadlines();
    else if (sdk::equal(args[1], "exec")) replace_self();
    else fail("unknown-case");
    sdk::print("OBS_PASS "); sdk::print(args[1]); sdk::print("\n"); return 0;
}
