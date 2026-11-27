// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "DNS.h"

#include <charconv>
#include <cstdint>
#include <cstdio>
#include <optional>
#include <string_view>
#include <wtf/CompletionHandler.h>
#include <wtf/Expected.h>
#include <wtf/Function.h>
#include <wtf/MainThread.h>
#include <wtf/RunLoop.h>
#include <wtf/Seconds.h>
#include <wtf/Vector.h>
#include <wtf/text/WTFString.h>

namespace {
using WebCore::DNSAddressesOrError;
using WebCore::DNSError;
using WebCore::resolveDNS;
using WebCore::stopResolveDNS;

struct observed_result {
    unsigned callback_count { 0 };
    bool callbacks_on_main { true };
    std::optional<DNSError> error;
    std::optional<uint32_t> address;

    void capture(DNSAddressesOrError&& result)
    {
        ++callback_count;
        callbacks_on_main &= WTF::RunLoop::isMain();
        if (!result) {
            error = result.error();
            return;
        }
        if (result->size() != 1 || !result->first().isIPv4())
            return;
        uint32_t packed = 0;
        for (auto byte : result->first().ipv4Address())
            packed = (packed << 8) | byte;
        address = packed;
    }

    bool has_address(uint32_t expected) const
    {
        return callback_count == 1 && callbacks_on_main && !error && address == expected;
    }

    bool has_error(DNSError expected) const
    {
        return callback_count == 1 && callbacks_on_main && !address && error == expected;
    }
};

template<typename Integer>
std::optional<Integer> parse_number(std::string_view text)
{
    Integer result;
    const auto end = text.data() + text.size();
    const auto parsed = std::from_chars(text.data(), end, result);
    if (parsed.ec != std::errc { } || parsed.ptr != end)
        return std::nullopt;
    return result;
}

bool wait_for_lookup(WTF::Function<void()>&& submit)
{
    auto& main = WTF::RunLoop::mainSingleton();
    bool timed_out = false;
    auto timer = main.dispatchAfter(WTF::Seconds { 12 }, [&] {
        timed_out = true;
        main.stop();
    });
    main.dispatch(WTF::move(submit));
    WTF::RunLoop::run();
    timer->stop();
    return !timed_out;
}

void lookup(const WTF::String& host, uint64_t identifier, observed_result& observed)
{
    resolveDNS(host, identifier, [&](DNSAddressesOrError&& result) {
        observed.capture(WTF::move(result));
        WTF::RunLoop::mainSingleton().stop();
    });
}

int run_live(uint32_t expected_address)
{
    observed_result positive, missing, cancelled, reused;
    if (!wait_for_lookup([&] { lookup("pair.n4.test"_s, 1, positive); }) || !positive.has_address(expected_address))
        return 3;
    if (!wait_for_lookup([&] { lookup("missing.n4.test"_s, 2, missing); }) || !missing.has_error(DNSError::CannotResolve))
        return 4;

    constexpr uint64_t reusable_identifier = 3;
    auto& main = WTF::RunLoop::mainSingleton();
    auto cancel_timer = main.dispatchAfter(WTF::Seconds { 1.5 }, [] {
        stopResolveDNS(reusable_identifier);
        stopResolveDNS(reusable_identifier);
    });
    const bool cancelled_in_time = wait_for_lookup([&] {
        lookup("cancelled.n4.test"_s, reusable_identifier, cancelled);
    });
    cancel_timer->stop();
    if (!cancelled_in_time || !cancelled.has_error(DNSError::Cancelled))
        return 5;

    if (!wait_for_lookup([&] { lookup("pair.n4.test"_s, reusable_identifier, reused); })
        || !reused.has_address(expected_address))
        return 6;

    bool quiet_period_elapsed = false;
    auto timer = main.dispatchAfter(WTF::Seconds { 6 }, [&] {
        quiet_period_elapsed = true;
        main.stop();
    });
    WTF::RunLoop::run();
    timer->stop();
    if (!quiet_period_elapsed || !positive.has_address(expected_address) || !missing.has_error(DNSError::CannotResolve)
        || !cancelled.has_error(DNSError::Cancelled) || !reused.has_address(expected_address))
        return 7;

    std::printf("XOS_WEBCORE_RESOLVER_LIVE_OK answer=%u nxdomain=1 cancelled=1 reused=1\n", *positive.address);
    return 0;
}
}

int main(int argc, char** argv)
{
    if (argc < 3)
        return 1;
    const std::string_view mode { argv[1] };
    const auto pid = parse_number<uint64_t>(argv[2]);
    if (!pid || !*pid)
        return 1;

    WTF::initializeMainThread();
    if (!WebCore::configureXOSDNSService(*pid))
        return 2;

    if (mode == "live" && argc == 4) {
        if (const auto expected = parse_number<uint32_t>(argv[3]))
            return run_live(*expected);
        return 1;
    }

    if (argc != 3 || (mode != "wrong-pid" && mode != "stopped"))
        return 1;
    observed_result refused;
    const auto host = mode == "wrong-pid" ? "refused.n4.test"_s : "failure.n4.test"_s;
    if (!wait_for_lookup([&] { lookup(host, 1, refused); }) || !refused.has_error(DNSError::CannotResolve))
        return 8;
    std::printf("XOS_WEBCORE_RESOLVER_DENIED_OK mode=%s\n", argv[1]);
    return 0;
}
