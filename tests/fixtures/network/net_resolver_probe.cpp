// SPDX-License-Identifier: Apache-2.0
#include <xos/net_service_client.hpp>
#include <xos/text.hpp>

namespace {
using namespace xos;
using namespace xos::net2;
constexpr u64 second = 1'000'000'000ull;

void check(bool valid, const char* operation, i64 result = 0) {
    if (valid) return;
    sdk::print("N4_FAIL "); sdk::print(operation); sdk::print(" result=");
    sdk::signed_decimal(result); sdk::print("\n"); sdk::exit(90);
}

u64 clock_ns() {
    const i64 time = sdk::syscall(sys_clock_monotonic);
    check(time >= 0, "clock", time);
    return static_cast<u64>(time);
}

u64 argument_number(const char* input) {
    check(*input, "empty argument");
    u64 result = 0;
    while (*input) {
        check(*input >= '0' && *input <= '9', "invalid argument");
        const u64 digit = static_cast<u64>(*input++ - '0');
        check(result <= (~u64{0} - digit) / 10, "argument overflow");
        result = result * 10 + digit;
    }
    return result;
}

u64 begin(session_client& client, const char* name, u64 limit) {
    u32 length = 0;
    while (name[length]) ++length;
    u64 ticket = 0;
    const i64 status = client.resolve_start(name, length, clock_ns() + limit, ticket);
    check(!status && ticket, "start", status);
    return ticket;
}

i64 complete(session_client& client, u64 ticket, resolve_reply& answer) {
    const auto stop = clock_ns() + 12 * second;
    while (clock_ns() < stop) {
        const i64 status = client.resolve_result(ticket, clock_ns() + second, answer);
        if (status != would_block) return status;
        check(!sdk::syscall(sys_sleep_until, clock_ns() + 10'000'000ull), "sleep");
    }
    return timeout;
}

void print_ticket(const char* marker, u64 ticket) {
    sdk::print(marker); sdk::decimal(ticket); sdk::print("\n");
}

void print_answer(const resolve_reply& answer) {
    sdk::print("N4_ANSWER epoch="); sdk::decimal(answer.epoch);
    sdk::print(" address="); sdk::decimal(answer.address); sdk::print("\n");
}

i64 open_destination(session_client& client, u32 address, protocol transport, u16 port, u64& handle) {
    message request{}, reply{};
    request.action = operation::open; request.address = address; request.transport = transport;
    request.port = port; request.deadline = clock_ns() + second;
    const auto result = client.request(request, reply); handle = reply.object; return result;
}

void policy_probe(session_client& client, const config_snapshot& initial, const char* nonce) {
    u32 nonce_length = 0; while (nonce_length < 33 && nonce[nonce_length]) ++nonce_length;
    check(nonce_length == 32, "policy nonce");
    char allowed_name[64] = "allow-", denied_name[64] = "deny-";
    for (u32 i = 0; i < 32; ++i) { allowed_name[6 + i] = nonce[i]; denied_name[5 + i] = nonce[i]; }
    __builtin_memcpy(allowed_name + 38, ".n4.test", 9);
    __builtin_memcpy(denied_name + 37, ".n4.test", 9);
    u64 old_ticket = 0; u32 old_address = 0;
    for (u32 round = 0; round < 2; ++round) {
        resolve_reply allowed{}, forbidden{};
        const u64 ticket = begin(client, allowed_name, 8 * second);
        check(!complete(client, ticket, allowed) && allowed.expiry > clock_ns(), "policy resolve admitted");
        check((allowed.address & 0xffffff00u) == 0xc0000200u && allowed.address != old_address,
              "fresh permitted CIDR answer");
        if (!round) {
            const u64 denied_ticket = begin(client, denied_name, 8 * second);
            check(!complete(client, denied_ticket, forbidden), "policy resolve denied address still succeeds");
            u64 rejected = 0;
            check(open_destination(client, forbidden.address, protocol::udp, 41001, rejected) == denied && !rejected,
                  "DNS answer cannot grant address authority");
            check(open_destination(client, forbidden.address, protocol::tcp, 41001, rejected) == denied && !rejected,
                  "DNS answer cannot grant TCP authority");
            sdk::print("EGRESS_DENIED_ADDRESS="); sdk::decimal(forbidden.address); sdk::print("\n");
        }
        u64 handle = 0;
        check(open_destination(client, allowed.address, protocol::udp, 41002, handle) == denied && !handle,
              "same address wrong port denied");
        check(open_destination(client, allowed.address, protocol::tcp, 41001, handle) == denied && !handle,
              "same tuple wrong transport denied");
        check(!open_destination(client, allowed.address, protocol::udp, 41001, handle) && handle,
              "trusted CIDR tuple admitted");
        message request{}, reply{};
        request.action = operation::send; request.object = handle; request.deadline = clock_ns() + second;
        request.length = 32; __builtin_memcpy(request.data, nonce, 32);
        check(client.request(request, reply) == 32, "policy UDP nonce sent");
        const auto stop = clock_ns() + 5 * second;
        for (;;) {
            request = {}; request.action = operation::receive; request.object = handle;
            request.deadline = clock_ns() + second; request.flags = 32;
            const auto result = client.request(request, reply);
            if (!result) { check(reply.length == 32, "fresh challenge length"); break; }
            check(result == would_block && clock_ns() < stop, "challenge wait", result);
            check(!sdk::syscall(sys_sleep_until, clock_ns() + 10'000'000ull), "policy sleep");
        }
        sdk::print("EGRESS_CHALLENGE round="); sdk::decimal(round);
        sdk::print(" address="); sdk::decimal(allowed.address); sdk::print(" data=");
        constexpr char hex[] = "0123456789abcdef";
        char encoded[65]{};
        for (u32 i = 0; i < reply.length; ++i) {
            encoded[2 * i] = hex[reply.data[i] >> 4]; encoded[2 * i + 1] = hex[reply.data[i] & 15];
        }
        sdk::print(encoded); sdk::print("\n");
        request = {}; request.action = operation::close; request.object = handle; request.deadline = clock_ns() + second;
        check(!client.request(request, reply), "policy close");
        if (!round) {
            old_ticket = ticket; old_address = allowed.address;
            sdk::print("EGRESS_AWAIT_EPOCH\n");
            config_snapshot current{};
            const auto deadline = clock_ns() + 12 * second;
            for (;;) {
                check(!client.configuration(clock_ns() + second, current), "policy configuration");
                if (current.epoch >= initial.epoch + 2 && current.mode == network_mode::static_direct) break;
                check(clock_ns() < deadline, "controller epoch transition timeout");
                check(!sdk::syscall(sys_sleep_until, clock_ns() + 20'000'000ull), "epoch wait");
            }
            resolve_reply ignored{};
            check(client.resolve_result(old_ticket, clock_ns() + second, ignored) == closed,
                  "old ticket remains invalid after epoch change");
        }
    }
    sdk::print("EGRESS_POLICY_PASS\n");
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    using namespace xos::net2;
    check(startup->argc == 3 || startup->argc == 4, "usage");
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    session_client client;
    const i64 connected_status = client.connect(argument_number(args[2]));
    check(!connected_status, "connect", connected_status);
    config_snapshot config{};
    const auto descriptor = client.configuration(clock_ns() + second, config);
    if (sdk::equal(args[1], "legacy")) {
        check(descriptor == unsupported, "legacy unsupported", descriptor);
        message request{}, reply{};
        request.action = operation::information; request.deadline = clock_ns() + second;
        check(!client.request(request, reply) && reply.length == sizeof(information), "legacy v2 survived");
        sdk::print("N4_LEGACY_COMPATIBLE\n");
        return 0;
    }
    check(!descriptor && config.capabilities == resolve_in_a, "configuration", descriptor);
    if (sdk::equal(args[1], "disabled")) {
        u64 ticket = 0;
        check(config.mode == network_mode::disabled && config.tickets == 0 &&
              client.resolve_start("pair.n4.test", 12, clock_ns() + second, ticket) == closed && !ticket, "disabled");
        sdk::print("N4_DISABLED\n");
        return 0;
    }
    check(config.mode == network_mode::static_direct, "expected enabled");
    if (sdk::equal(args[1], "policy")) {
        check(startup->argc == 4, "policy nonce argument");
        policy_probe(client, config, args[3]); return 0;
    }
    resolve_reply answer{};
    if (sdk::equal(args[1], "owner")) {
        const u64 ticket = begin(client, "pair.n4.test", 10 * second);
        u64 extra = 0;
        check(client.resolve_start("pair.n4.test", 12, clock_ns() + second, extra) == resources && !extra, "one ticket quota");
        print_ticket("N4_OWNER ticket=", ticket);
        const auto result = complete(client, ticket, answer);
        check(!result, "owner result", result);
        print_answer(answer);
        return 0;
    }
    if (sdk::equal(args[1], "join")) {
        check(startup->argc == 4, "foreign ticket argument");
        const u64 foreign = argument_number(args[3]);
        check(client.resolve_result(foreign, clock_ns() + second, answer) == denied &&
              client.resolve_cancel(foreign, clock_ns() + second) == denied, "foreign ticket denial");
        config_snapshot ignored{};
        check(client.configure(network_mode::disabled, config.epoch, clock_ns() + second, ignored) == denied,
              "configuration authority");
        const u64 ticket = begin(client, "PAIR.N4.TEST.", 10 * second);
        check(client.resolve_result(ticket, clock_ns() + second, answer) == would_block, "shared pending");
        print_ticket("N4_JOIN ticket=", ticket);
        const auto result = complete(client, ticket, answer);
        check(!result && answer.epoch == config.epoch && answer.expiry > clock_ns(), "joined result", result);
        print_answer(answer);
        check(client.resolve_result(ticket, clock_ns() + second, answer) == closed, "consumed ticket");
        return 0;
    }
    if (sdk::equal(args[1], "errors")) {
        struct error_case { const char* name; i64 status; };
        const error_case errors[]{{"missing.n4.test", name_not_found}, {"empty.n4.test", name_no_data},
                                  {"referral.n4.test", dns_failure}, {"soa.n4.test", name_no_data},
                                  {"failure.n4.test", dns_failure}, {"refused.n4.test", dns_refused},
                                  {"truncated.n4.test", dns_truncated}, {"silent.n4.test", timeout}};
        for (const auto& test : errors) {
            const u64 ticket = begin(client, test.name, test.status == timeout ? second / 3 : 8 * second);
            const auto result = complete(client, ticket, answer);
            check(result == test.status, test.name, result);
            check(client.resolve_result(ticket, clock_ns() + second, answer) == closed, "error consumed");
        }
        const u64 pending = begin(client, "cancelled.n4.test", 8 * second);
        check(!client.resolve_cancel(pending, clock_ns() + second) &&
              client.resolve_result(pending, clock_ns() + second, answer) == closed, "cancel consumed");
        sdk::print("N4_STRUCTURED_RESULTS_PASS\n");
        return 0;
    }
    check(sdk::equal(args[1], "fresh"), "mode");
    const u64 ticket = begin(client, "pair.n4.test", 8 * second);
    const auto result = complete(client, ticket, answer);
    check(!result && answer.epoch == config.epoch && answer.expiry > clock_ns(), "fresh result", result);
    print_answer(answer);
    return 0;
}
