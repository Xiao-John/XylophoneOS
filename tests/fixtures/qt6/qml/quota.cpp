// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QQmlEngine>

#include <xos/vm.hpp>

#include <cstdio>

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    // The profile allows 4 TiB per sparse reservation and 8 TiB per process.
    // Fill the virtual allowance without committing or touching physical pages.
    constexpr xos::u64 max_reservation = 4ull << 40;
    const auto first = xos::sdk::vm_reserve(0, max_reservation);
    const auto second = xos::sdk::vm_reserve(0, max_reservation);
    if (first <= 0 || second <= 0) {
        std::fputs("QML_QUOTA_SETUP_FAILED\n", stderr);
        return 1;
    }
    std::puts("QML_QUOTA_ARMED");
    std::fflush(stdout);

    QQmlEngine engine;
    std::fputs("QML_QUOTA_ENGINE_UNEXPECTEDLY_STARTED\n", stderr);
    return 2;
}
