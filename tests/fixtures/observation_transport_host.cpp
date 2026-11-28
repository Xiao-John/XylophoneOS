// SPDX-License-Identifier: Apache-2.0
// Actual endpoint.cpp runs against deterministic host mailboxes and clock.
// This is protocol/lifetime validation, not kernel or guest qualification.
#include <xos/observation.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

namespace fixture {
using namespace xos;
using namespace xos::observation;
constexpr u64 service_pid = 20;
struct route {
    u32 send, receive;
    u64 server, client, image_generation;
    bool live = true, send_blocked = false;
    std::vector<u8> request_bytes, reply_bytes;
};
std::vector<route> routes;
u64 current_pid = service_pid, now_ns = 1000, next_epoch = 100;
u32 next_handle = 100;
server* active_server = nullptr;
bool pump_wait = true;
u32 captures = 0, wait_count = 0, replies_sent = 0;
bool malformed_capture = false, replace_peer_during_capture = false;
u64 capture_delay = 0;

route* lookup(u64 handle) {
    for (auto& item : routes)
        if (item.live && (item.send == handle || item.receive == handle)) return &item;
    return nullptr;
}
ipc_channel new_route(u64 client, u64 image_generation = 1) {
    const u32 first = next_handle;
    next_handle += 2;
    routes.push_back({first, first + 1, service_pid, client, image_generation,
                      true, false, {}, {}});
    return {first, first + 1}; // server send and receive
}
route& by_client(u64 pid) {
    for (auto& item : routes) if (item.live && item.client == pid) return item;
    assert(false); return routes.front();
}
void clear_fixture() {
    routes.clear(); current_pid = service_pid; now_ns = 1000;
    active_server = nullptr; pump_wait = true; captures = wait_count = replies_sent = 0;
    malformed_capture = replace_peer_during_capture = false; capture_delay = 0;
}
status capture(void*, kind subject, u64, response& output) {
    ++captures; now_ns += capture_delay;
    output = {}; output.origin = scope::self;
    output.object_id = service_pid; output.generation = 3;
    if (subject != kind::process) return status::unavailable;
    output.value.values[0] = 1;
    output.value.values[1] = 4; // running
    output.value.values[2] = 2;
    if (malformed_capture) output.value.values[9] = 1;
    if (replace_peer_during_capture) by_client(41).image_generation = 2;
    return status::ok;
}
void setup(server& value) {
    assert(value.initialize(capture, nullptr) == status::ok);
    active_server = &value;
}
void attach(server& value, u64 pid, bool authorize = true, u32 reads = max_reads) {
    current_pid = service_pid;
    assert(value.attach(new_route(pid)) == status::ok);
    if (authorize)
        assert(value.authorize(pid, mask(kind::process), reads, now_ns + 100000) == status::ok);
}
request request_for(const server& value, u64 sequence = 1) {
    return {version, sizeof(request), 1, kind::process, sequence, now_ns + 50000,
            value.epoch(), 0, 0, 0};
}
void queue(u64 pid, const request& input) {
    auto& item = by_client(pid);
    assert(item.request_bytes.empty());
    const auto* first = reinterpret_cast<const u8*>(&input);
    item.request_bytes.assign(first, first + sizeof(input));
}
response take(u64 pid) {
    auto& item = by_client(pid);
    assert(item.reply_bytes.size() == sizeof(response));
    response output{};
    std::memcpy(&output, item.reply_bytes.data(), sizeof(output));
    item.reply_bytes.clear(); return output;
}
bool empty_payload(const response& value) {
    const data zero{};
    return !value.object_id && !value.generation &&
        !std::memcmp(&value.value, &zero, sizeof(zero));
}
void poll(server& value) { current_pid = service_pid; (void)value.poll(); }

void authorization_and_budget() {
    clear_fixture(); server value; setup(value); attach(value, 41, false);
    queue(41, request_for(value)); poll(value);
    auto reply = take(41);
    assert(reply.outcome == status::unauthorized && empty_payload(reply) && !captures);
    assert(value.authorize(41, mask(kind::process), 1, now_ns + 100000) == status::ok);
    queue(41, request_for(value, 2)); poll(value); reply = take(41);
    assert(reply.outcome == status::ok && valid_response(reply) && captures == 1);
    assert(reply.server_pid == service_pid && reply.caller_pid == 41);
    queue(41, request_for(value, 3)); poll(value); reply = take(41);
    assert(reply.outcome == status::quota && empty_payload(reply) && captures == 1);
    attach(value, 42); queue(42, request_for(value)); poll(value);
    assert(take(42).outcome == status::ok && captures == 2);
    std::puts("PASS authorization, per-peer read budget and unrelated-client usability");
}

void deferred_revocation() {
    clear_fixture(); server value; setup(value); attach(value, 41);
    by_client(41).send_blocked = true;
    queue(41, request_for(value)); poll(value);
    assert(captures == 1 && by_client(41).reply_bytes.empty());
    assert(value.revoke(41) == status::ok);
    by_client(41).send_blocked = false; poll(value);
    const auto reply = take(41);
    assert(reply.outcome == status::revoked && empty_payload(reply));
    assert(captures == 1); // no recapture or implicit replay
    std::puts("PASS pending success loses data on revoke before mailbox publication");
}

void deferred_reauthorization() {
    clear_fixture(); server value; setup(value); attach(value, 41);
    by_client(41).send_blocked = true;
    queue(41, request_for(value)); poll(value);
    assert(value.authorize(41, mask(kind::process), max_reads, now_ns + 100000) == status::ok);
    by_client(41).send_blocked = false; poll(value);
    const auto reply = take(41);
    assert(reply.outcome == status::stale && empty_payload(reply) && captures == 1);
    std::puts("PASS grant revision cannot bless a capture made under an older grant");
}

void reconnect_identity_and_forget() {
    clear_fixture(); server value; setup(value);
    for (u64 pid = 41; pid < 45; ++pid) attach(value, pid);
    const auto fifth = new_route(45);
    assert(value.attach(fifth) == status::quota);
    assert(value.forget(41) == status::ok);
    assert(value.attach(fifth) == status::ok);
    assert(value.authorize(45, mask(kind::process), 1, now_ns + 100000) == status::ok);
    assert(value.forget(999) == status::unauthorized);
    // A successful exec revokes old endpoints; reconnect has a different image.
    by_client(42).live = false; poll(value);
    assert(value.attach(new_route(42, 2)) == status::ok);
    queue(42, request_for(value)); poll(value);
    assert(take(42).outcome == status::unauthorized);
    assert(value.authorize(42, mask(kind::process), 1, now_ns + 100000) == status::ok);
    queue(42, request_for(value, 2)); poll(value);
    assert(take(42).outcome == status::ok);
    std::puts("PASS explicit retirement reclaims capacity; exec identity needs fresh authority");
}

void framing_and_sequences() {
    clear_fixture(); server value; setup(value); attach(value, 41);
    auto bad = request_for(value); bad.operation = 2;
    queue(41, bad); poll(value);
    assert(take(41).outcome == status::invalid && !captures);
    bad = request_for(value); bad.reserved = 1;
    queue(41, bad); poll(value);
    assert(take(41).outcome == status::invalid && !captures);
    bad = request_for(value); bad.version = 2;
    queue(41, bad); poll(value);
    assert(take(41).outcome == status::invalid && !captures);
    bad = request_for(value); --bad.size;
    queue(41, bad); poll(value);
    assert(take(41).outcome == status::invalid && !captures);
    queue(41, request_for(value)); poll(value);
    assert(take(41).outcome == status::ok && captures == 1);
    queue(41, request_for(value)); poll(value); // repeat sequence 1
    assert(take(41).outcome == status::invalid && captures == 1);
    malformed_capture = true;
    queue(41, request_for(value, 2)); poll(value);
    const auto reply = take(41);
    assert(reply.outcome == status::unavailable && empty_payload(reply));
    std::puts("PASS malformed requests and repeated sequences never trigger capture; malformed provider fails closed");
}

void deadline_and_snapshot_preconditions() {
    clear_fixture(); server value; setup(value); attach(value, 41);
    auto input = request_for(value); input.expected_generation = 9;
    queue(41, input); poll(value);
    auto reply = take(41);
    assert(reply.outcome == status::stale && empty_payload(reply));
    by_client(41).send_blocked = true;
    input = request_for(value, 2); input.deadline_ns = now_ns + 10;
    queue(41, input); poll(value);
    now_ns = input.deadline_ns;
    poll(value);
    assert(!lookup(routes.front().send));
    // Capture itself may consume its budget; never publish late success.
    attach(value, 42); capture_delay = 50001;
    queue(42, request_for(value)); poll(value);
    assert(!lookup(routes.back().send));
    std::puts("PASS stale preconditions and exact/late deadlines discard pending observations");
}

void malformed_request_retention_bound() {
    clear_fixture(); server value; setup(value); attach(value, 41, false);
    by_client(41).send_blocked = true;
    auto input = request_for(value); input.deadline_ns = ~u64{0};
    queue(41, input); poll(value);
    assert(!captures);
    now_ns += max_request_ns + 1;
    poll(value);
    assert(!lookup(routes.front().send));
    std::puts("PASS malformed infinite deadline cannot retain a blocked reply beyond the service budget");
}

void preserved_endpoint_exec_identity() {
    clear_fixture(); server value; setup(value); attach(value, 41);
    // sys81 can preserve a route through exec: PID and endpoint stay the same,
    // but the old image's grant must no longer authorize a new capture.
    by_client(41).image_generation = 2;
    queue(41, request_for(value)); poll(value);
    assert(!captures && !lookup(routes.front().send));
    value.close();

    clear_fixture(); setup(value); attach(value, 41);
    by_client(41).send_blocked = true;
    queue(41, request_for(value)); poll(value);
    assert(captures == 1 && by_client(41).reply_bytes.empty());
    by_client(41).image_generation = 2;
    by_client(41).send_blocked = false;
    poll(value);
    assert(captures == 1 && !lookup(routes.front().send));
    std::puts("PASS exec-preserved endpoint cannot reuse old image authority or publish an older pending success");
}

void image_change_during_capture() {
    clear_fixture(); server value; setup(value); attach(value, 41);
    // Defensive transport simulation: the host keeps this route alive while
    // capture changes its peer identity. Actual sys84/86 exec revokes the route;
    // this does not qualify sys81 as an observation-service transport.
    replace_peer_during_capture = true;
    queue(41, request_for(value)); poll(value);
    assert(captures == 1 && replies_sent == 0 && !lookup(routes.front().send));
    std::puts("PASS defensive peer change during capture retires the route before any success publication");
}

void public_client() {
    clear_fixture(); server value; setup(value);
    current_pid = 41;
    client consumer;
    assert(consumer.connect("observation", service_pid, value.epoch()) == status::ok);
    current_pid = service_pid;
    const auto& route = by_client(41);
    assert(value.attach({route.send, route.receive}) == status::ok);
    assert(value.authorize(41, mask(kind::process), 3, now_ns + 100000) == status::ok);
    current_pid = 41; response output{};
    assert(consumer.read(kind::process, now_ns + 10000, output) == status::ok);
    assert(output.caller_pid == 41 && output.object_id == service_pid && captures == 1);
    assert(wait_count == 1);
    assert(consumer.read(kind::process, now_ns + 10000, output, service_pid, 99) == status::stale);
    assert(empty_payload(output) && captures == 2);
    pump_wait = false;
    const auto deadline = now_ns + 100;
    assert(consumer.read(kind::process, deadline, output) == status::deadline);
    assert(now_ns == deadline && output.version == 0 && captures == 2);
    current_pid = service_pid;
    std::puts("PASS ordinary client drives one bounded exchange; no retry after unresponsive service");
}

void client_epoch_and_peer_authentication() {
    clear_fixture(); server value; setup(value);
    current_pid = 41;
    client wrong_peer;
    assert(wrong_peer.connect("observation", service_pid + 1, value.epoch()) == status::stale);
    client old_epoch;
    assert(old_epoch.connect("observation", service_pid, value.epoch() + 1) == status::ok);
    current_pid = service_pid;
    const auto& route = by_client(41);
    assert(value.attach({route.send, route.receive}) == status::ok);
    assert(value.authorize(41, mask(kind::process), 1, now_ns + 100000) == status::ok);
    current_pid = 41; response output{};
    assert(old_epoch.read(kind::process, now_ns + 10000, output) == status::stale);
    assert(empty_payload(output) && !captures);
    current_pid = service_pid;
    std::puts("PASS client verifies both peer routes and reports changed service epoch without capture");
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace fixture;
    if (number == 6) return current_pid;
    if (number == sys_clock_monotonic) return now_ns;
    if (number == sys_random_bytes) {
        assert(second == sizeof(u64) && third == 0);
        const u64 epoch = next_epoch++;
        std::memcpy(reinterpret_cast<void*>(first), &epoch, sizeof(epoch)); return 0;
    }
    if (number == sys_observe) {
        const auto& input = *reinterpret_cast<const observe_native::request*>(first);
        auto& output = *reinterpret_cast<observe_native::snapshot*>(second);
        output = {};
        if (input.version != observe_native::version || input.size != sizeof(input) ||
            input.kind != observe_native::query::service || input.deadline_ns <= now_ns)
            return static_cast<i64>(observe_native::result::invalid);
        auto* item = lookup(input.target);
        if (!item || current_pid != item->server)
            return static_cast<i64>(observe_native::result::denied);
        if ((input.expected_pid && input.expected_pid != item->client) ||
            (input.expected_generation && input.expected_generation != item->image_generation))
            return static_cast<i64>(observe_native::result::stale);
        output.pid = item->client; output.image_generation = item->image_generation;
        output.version = observe_native::version; output.size = sizeof(output); return 0;
    }
    if (number == sys_ipc_name && first == static_cast<u64>(ipc_name_action::connect)) {
        const auto channel = new_route(current_pid);
        *reinterpret_cast<ipc_channel*>(third) = {channel.receive, channel.send}; return 0;
    }
    auto* item = lookup(number == sys_ipc_endpoint ? second : first);
    if (!item || (current_pid != item->server && current_pid != item->client)) return -1;
    if (number == sys_ipc_endpoint) {
        if (first == static_cast<u64>(ipc_endpoint_action::query_peer)) {
            *reinterpret_cast<u64*>(third) = current_pid == item->server ? item->client : item->server;
            return 0;
        }
        if (first == static_cast<u64>(ipc_endpoint_action::close)) {
            item->live = false; item->request_bytes.clear(); item->reply_bytes.clear(); return 0;
        }
    }
    if (number == 4) {
        const bool from_server = current_pid == item->server;
        if (first != (from_server ? item->send : item->receive)) return -1;
        auto& buffer = from_server ? item->reply_bytes : item->request_bytes;
        if (!buffer.empty() || (from_server && item->send_blocked)) return ipc_error_full;
        const auto* bytes = reinterpret_cast<const u8*>(second);
        buffer.assign(bytes, bytes + third);
        if (from_server) ++replies_sent;
        return 0;
    }
    if (number == 5) {
        const bool to_server = current_pid == item->server;
        if (first != (to_server ? item->receive : item->send)) return -1;
        auto& buffer = to_server ? item->request_bytes : item->reply_bytes;
        if (buffer.empty()) return process_error_would_block;
        if (third < buffer.size()) return ipc_error_full;
        const auto length = buffer.size();
        std::memcpy(reinterpret_cast<void*>(second), buffer.data(), length);
        buffer.clear(); return static_cast<i64>(length);
    }
    if (number == sys_ipc_wait) {
        ++wait_count;
        const u64 caller = current_pid;
        if (pump_wait && active_server && caller != service_pid) {
            current_pid = service_pid; (void)active_server->poll(); current_pid = caller;
        }
        item = lookup(first);
        if (!item) return ipc_error_broken;
        const bool receiving = second == static_cast<u64>(ipc_wait_mode::receive_until);
        if (receiving && !item->reply_bytes.empty()) return 0;
        if (!receiving && item->request_bytes.empty()) return 0;
        if (now_ns < third) now_ns = third;
        return thread_error_timeout;
    }
    assert(false); return -1;
}
}

int main() {
    fixture::authorization_and_budget();
    fixture::deferred_revocation();
    fixture::deferred_reauthorization();
    fixture::reconnect_identity_and_forget();
    fixture::framing_and_sequences();
    fixture::deadline_and_snapshot_preconditions();
    fixture::malformed_request_retention_bound();
    fixture::preserved_endpoint_exec_identity();
    fixture::image_change_during_capture();
    fixture::public_client();
    fixture::client_epoch_and_peer_authentication();
}
