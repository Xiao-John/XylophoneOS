// SPDX-License-Identifier: Apache-2.0
#include "config.h"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <sys/mman.h>
#include <sys/random.h>
#include <unistd.h>
#include <wtf/Threading.h>
#include <wtf/WTFConfig.h>

#if CLARKE_TEST_PREEXISTING_CONFIG
static void reserve_config_address_first()
{
    void* const expected = WebConfig::configuration_slots();
    if (mmap(expected, WTF::ConfigSizeToProtect, PROT_NONE,
            MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) != expected)
        _exit(2);
    constexpr char marker[] = "CLARKE_CONFIG_COLLISION_SETUP\n";
    static_cast<void>(write(STDERR_FILENO, marker, sizeof(marker) - 1));
}

[[gnu::used, gnu::section(".preinit_array")]]
static void (*const before_config_constructor)() = reserve_config_address_first;
#endif

static bool native_write_denied(void* address)
{
    errno = 0;
    return getrandom(address, 1, 0) == -1 && errno == EFAULT;
}

int main()
{
    auto* slots = reinterpret_cast<uint8_t*>(WebConfig::configuration_slots());
    if (reinterpret_cast<uintptr_t>(slots) != WebConfig::g_xos_jsc_config_address
        || reinterpret_cast<uintptr_t>(slots) % WTF::ConfigAlignment)
        return 3;
    auto* tail = slots + WTF::ConfigSizeToProtect - 1;
    volatile uint8_t* sentinel = tail;
    if (*sentinel)
        return 4;
    *sentinel = 0x5b;

    WTF::initialize();
    if (g_wtfConfig.isPermanentlyFrozen || !g_wtfConfig.lowestAccessibleAddress)
        return 5;
    WTF::Config::finalize();
    if (!g_wtfConfig.isPermanentlyFrozen || *sentinel != 0x5b)
        return 6;
    if (!native_write_denied(tail) || *sentinel != 0x5b
        || !native_write_denied(const_cast<uintptr_t*>(&WebConfig::g_xos_jsc_config_address)))
        return 7;

    std::puts("CLARKE_WTF_CONFIG_FROZEN");
    return 0;
}
