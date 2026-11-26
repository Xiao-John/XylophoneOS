// SPDX-License-Identifier: Apache-2.0
#include "service_loop.hpp"
#include "lwip_stack.hpp"
#include <xos/text.hpp>
#include <xos/thread_abi.hpp>
extern "C" {
#include "lwip/dns.h"
}

namespace xos::user::network {
namespace {
struct lookup {
    ip_addr_t address{};
    u32 callbacks = 0;
    bool success = false;
};

lwip_stack stack;

void found(const char*, const ip_addr_t* address, void* context) {
    auto& result = *static_cast<lookup*>(context);
    ++result.callbacks;
    result.success = address != nullptr;
    if (address) result.address = *address;
}

bool await_answer(virtio_net::driver& nic, lookup& result) {
    const i64 start = stack.monotonic_time();
    if (start < 0) return false;
    const u64 deadline = static_cast<u64>(start) + 5'000'000'000ull;
    while (!result.callbacks) {
        const i64 current = stack.monotonic_time();
        if (current < 0 || static_cast<u64>(current) >= deadline || stack.poll()) return false;
        if (result.callbacks) break;
        const auto wake = nic.wait(static_cast<u64>(current) + thread_tick_ns);
        if (wake && wake != device_timeout) return false;
    }
    return result.callbacks == 1 && result.success;
}

void print_answer(const char* label, const ip_addr_t& address) {
    const auto* ip = ip_2_ip4(&address);
    sdk::print(label);
    sdk::decimal(ip4_addr1(ip)); sdk::print(".");
    sdk::decimal(ip4_addr2(ip)); sdk::print(".");
    sdk::decimal(ip4_addr3(ip)); sdk::print(".");
    sdk::decimal(ip4_addr4(ip)); sdk::print("\n");
}

i64 check_dns(virtio_net::driver& nic) {
    ip_addr_t immediate{}, resolver{};
    IP_ADDR4(&resolver, 10, 0, 2, 2);
    dns_setserver(0, &resolver);
    lookup original{}, cancelled{}, refreshed{}, abandoned{};
    constexpr const char* name = "cache.n4.test";
    if (dns_gethostbyname(name, &immediate, found, &original) != ERR_INPROGRESS ||
        dns_gethostbyname(name, &immediate, found, &cancelled) != ERR_INPROGRESS ||
        dns_xos_cancel(found, &cancelled) != 1 || !await_answer(nic, original) || cancelled.callbacks) return 1;
    print_answer("[net-dns] initial=", original.address);
    if (dns_gethostbyname("CACHE.N4.TEST.", &immediate, found, &refreshed) != ERR_OK ||
        !ip_addr_eq(&original.address, &immediate) || refreshed.callbacks) return 2;

    // Cross the shorter TTL without calling the lwIP maintenance timer.
    const i64 now = stack.monotonic_time();
    if (now < 0 || sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'250'000'000ull)) return 3;
    if (dns_gethostbyname(name, &immediate, found, &refreshed) != ERR_INPROGRESS ||
        !await_answer(nic, refreshed) || ip_addr_eq(&original.address, &refreshed.address)) return 4;
    print_answer("[net-dns] refreshed=", refreshed.address);

    if (dns_gethostbyname("cancel.n4.test", &immediate, found, &abandoned) != ERR_INPROGRESS ||
        dns_xos_cancel(found, &abandoned) != 1 || dns_xos_cancel(found, &abandoned) != 0 || abandoned.callbacks) return 5;
    if (dns_gethostbyname("stop.n4.test", &immediate, found, &abandoned) != ERR_INPROGRESS || abandoned.callbacks) return 6;
    dns_xos_reset();
    if (dns_xos_cancel(found, &abandoned) || abandoned.callbacks ||
        dns_gethostbyname(name, &immediate, found, &abandoned) != ERR_VAL) return 7;
    sdk::print("[net-dns] shared_cancel=1 cache_hit=1 expired=1 reset=1\n");
    return 0;
}
}

i64 probe_dns(virtio_net::driver& nic) {
    const i64 started = stack.initialize(network_frame_io(nic), nic.mac());
    const i64 result = started ? started : check_dns(nic);
    stack.shutdown();
    return result;
}
}
