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
