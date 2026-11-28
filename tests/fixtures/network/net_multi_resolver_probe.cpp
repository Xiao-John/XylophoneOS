// SPDX-License-Identifier: Apache-2.0
#include <xos/net_service_client.hpp>
#include <xos/text.hpp>

namespace {
using namespace xos;
using namespace xos::net2;
constexpr u64 second = 1'000'000'000ull;
void check(bool okay, const char* label, i64 error = 0) {
    if (okay) return;
    sdk::print("P1I_FAIL "); sdk::print(label); sdk::print(" error=");
    sdk::signed_decimal(error); sdk::print("\n"); sdk::exit(91);
}
u64 now() {
    const auto value = sdk::syscall(sys_clock_monotonic);
    check(value >= 0, "clock", value); return static_cast<u64>(value);
}
void sleep_until(u64 stop) { check(!sdk::syscall(sys_sleep_until, stop), "sleep"); }
u64 number(const char* text) {
    u64 value = 0; check(text && *text, "number");
    while (*text) { check(*text >= '0' && *text <= '9' && value < (~u64{0} - 9) / 10, "number range");
        value = value * 10 + static_cast<u64>(*text++ - '0'); }
    return value;
}
u64 begin(session_client& client, const char* name, u64 deadline) {
    u32 size = 0; while (name[size]) ++size;
    u64 ticket = 0; const auto result = client.resolve_start(name, size, deadline, ticket);
    check(!result && ticket, "resolve start", result); return ticket;
}
i64 complete(session_client& client, u64 ticket, resolve_reply& answer, u64 deadline) {
    for (;;) {
        const auto value = client.resolve_result(ticket, now() + second, answer);
        if (value != would_block) return value;
        check(now() < deadline, "outer wait deadline"); sleep_until(now() + 10'000'000ull);
    }
}
void answer_line(const char* label, const resolve_reply& answer, u64 elapsed) {
    sdk::print(label); sdk::print(" address="); sdk::decimal(answer.address);
    sdk::print(" epoch="); sdk::decimal(answer.epoch); sdk::print(" elapsed_ns=");
    sdk::decimal(elapsed); sdk::print("\n");
}
void cache_and_epoch(session_client& client, u64 epoch) {
    resolve_reply first{}, cached{}, second_answer{}, fresh{};
    const u64 started = now();
    const auto ticket = begin(client, "cache.p1i.test", started + 18 * second);
    u64 extra = 0;
    check(client.resolve_start("quota.p1i.test", 14, now() + second, extra) == resources && !extra,
          "one ticket per owner");
    check(!complete(client, ticket, first, started + 19 * second), "secondary answer");
    check(first.epoch == epoch && first.expiry > now(), "secondary TTL/epoch");
    answer_line("P1I_FALLBACK", first, now() - started);
    const auto cached_ticket = begin(client, "CACHE.P1I.TEST.", now() + second);
    check(!client.resolve_result(cached_ticket, now() + second, cached) && cached.address == first.address &&
          cached.expiry == first.expiry, "cache hit preserves original expiry");
    check(client.resolve_result(ticket, now() + second, cached) == closed, "consumed ticket");
    sleep_until(first.expiry + 20'000'000ull);
    const u64 refreshed = now();
    const auto next = begin(client, "cache.p1i.test", refreshed + 18 * second);
    check(!complete(client, next, second_answer, refreshed + 19 * second) &&
          second_answer.address != first.address, "TTL expiry requires new wire answer");
    answer_line("P1I_TTL_REFRESH", second_answer, now() - refreshed);
    sdk::print("P1I_AWAIT_EPOCH\n");
    const auto epoch_limit = now() + 12 * second;
    config_snapshot config{};
    do {
        check(!client.configuration(now() + second, config), "epoch configuration");
        check(now() < epoch_limit, "epoch barrier deadline"); sleep_until(now() + 10'000'000ull);
    } while (config.epoch < epoch + 2 || config.mode != network_mode::static_direct);
    check(client.resolve_result(next, now() + second, cached) == closed, "old epoch ticket invalid");
    const u64 reconfigured = now();
    const auto final_ticket = begin(client, "cache.p1i.test", reconfigured + 18 * second);
    check(!complete(client, final_ticket, fresh, reconfigured + 19 * second) &&
          fresh.address != second_answer.address && fresh.epoch == epoch + 2,
          "epoch retires unexpired cached answer");
    answer_line("P1I_EPOCH_REFRESH", fresh, now() - reconfigured);
    sdk::print("P1I_CACHE_PASS\n");
}
void deadline_and_cancel(session_client& client) {
    resolve_reply answer{};
    const auto started = now(), deadline = started + 9 * second;
    const auto ticket = begin(client, "deadline.p1i.test", deadline);
    check(complete(client, ticket, answer, deadline + second) == timeout, "one shared deadline");
    const auto elapsed = now() - started;
    check(elapsed >= 9 * second && elapsed < 10 * second, "failover cannot renew deadline");
    sdk::print("P1I_DEADLINE elapsed_ns="); sdk::decimal(elapsed); sdk::print("\n");
    const auto cancelled = begin(client, "cancel.p1i.test", now() + 18 * second);
    sleep_until(now() + 100'000'000ull);
    check(!client.resolve_cancel(cancelled, now() + second), "cancel pending DNS");
    check(client.resolve_result(cancelled, now() + second, answer) == closed, "cancel retires ticket");
    sdk::print("P1I_CANCELLED\n");
    sleep_until(now() + second);
    const auto retry = begin(client, "cancel.p1i.test", now() + 18 * second);
    check(retry != cancelled && client.resolve_result(retry, now() + second, answer) == would_block,
          "late cancelled answer cannot seed cache or another ticket");
    check(!client.resolve_cancel(retry, now() + second), "cancel new owner ticket");
    sdk::print("P1I_DEADLINE_CANCEL_PASS\n");
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos; using namespace xos::net2;
    check(startup->argc == 3 || startup->argc == 4, "usage");
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    session_client client;
    const auto result = client.connect(number(args[2]));
    if (sdk::equal(args[1], "full")) {
        // Name lookup admits a transport before the service authenticates and
        // attaches it. A fifth application is rejected by closing that channel;
        // a successful name_connect alone does not imply a Net2 session.
        config_snapshot rejected{};
        const auto admitted = result ? result : client.configuration(now() + second, rejected);
        check(admitted == closed, "global session quota", admitted);
        sdk::print("P1I_GLOBAL_QUOTA_PASS\n"); return 0;
    }
    check(!result, "connect", result);
    config_snapshot config{};
    check(!client.configuration(now() + second, config) && config.mode == network_mode::static_direct &&
          config.resolver == 0x0a000202, "profile primary compatibility");
    if (sdk::equal(args[1], "cache")) cache_and_epoch(client, config.epoch);
    else if (sdk::equal(args[1], "deadline")) deadline_and_cancel(client);
    else if (sdk::equal(args[1], "hold")) {
        check(startup->argc == 4, "hold name");
        const auto ticket = begin(client, args[3], now() + 25 * second);
        sdk::print("P1I_HOLD ticket="); sdk::decimal(ticket); sdk::print("\n");
        sleep_until(now() + 20 * second);
        check(!client.resolve_cancel(ticket, now() + second), "held ticket cleanup");
    } else if (sdk::equal(args[1], "foreign")) {
        check(startup->argc == 4, "foreign ticket"); resolve_reply answer{};
        const auto ticket = number(args[3]);
        check(client.resolve_result(ticket, now() + second, answer) == denied &&
              client.resolve_cancel(ticket, now() + second) == denied, "foreign ticket denied");
        sdk::print("P1I_FOREIGN_PASS\n");
    } else check(false, "mode");
    client.close(); return 0;
}
