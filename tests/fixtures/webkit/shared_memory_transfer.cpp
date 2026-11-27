// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "IntSize.h"
#include "ShareableBitmap.h"
#include "xos/SharedMemoryTransferXOS.h"

#include <cstdio>
#include <cstring>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
#include <skia/core/SkCanvas.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkImageInfo.h>
#include <skia/core/SkPixmap.h>
#include <skia/core/SkSurface.h>
#include <xos/ipc_v1.hpp>
#include <xos/thread_core.hpp>

namespace {

using WebCore::SharedMemory;
using WebCore::ShareableBitmap;
using WebCore::xos_loan_result;
using WebCore::xos_memory_loan;
using WebCore::xos_memory_offer;
using WebCore::xos_shared_memory_route;
using Protection = SharedMemory::Protection;

enum class Scenario : uint64_t { readOnly = 1, readWrite, holderExit, ownerExit };
constexpr char endpointName[] = "clarke-bitmap-loan";
constexpr uint32_t exitPermission = 0x314f4758; // XGO1

uint64_t deadline()
{
    return xos::thread::clock() + 10'000'000'000;
}

void require(bool passed, const char* step)
{
    if (!passed) {
        std::printf("XOS_WEBCORE_BITMAP_TRANSFER_FAIL pid=%llu step=%s\n",
            static_cast<unsigned long long>(xos::sdk::pid()), step);
        std::fflush(stdout);
        _exit(1);
    }
}

bool pauseUntil(uint64_t limit)
{
    const auto now = xos::thread::clock();
    return now < limit && !xos::thread::sleep_until(now + 1'000'000);
}

bool waitForChild(pid_t child)
{
    int status = 0;
    return waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

xos_shared_memory_route channel(bool parent, uint64_t peer, Scenario scenario)
{
    xos::ipc_channel endpoints { };
    const auto limit = deadline();
    for (;;) {
        const auto result = parent ? xos::sdk::ipc_name_try_accept(endpoints)
                                   : xos::sdk::ipc_name_connect(endpointName, endpoints);
        if (!result)
            return { endpoints, peer, static_cast<uint64_t>(scenario) };
        require(result == (parent ? xos::process_error_would_block : xos::ipc_error_name_not_found)
                && pauseUntil(limit), "rendezvous");
    }
}

void waitForExitPermission(const xos_shared_memory_route& route)
{
    uint32_t packet = 0;
    const auto limit = deadline();
    for (;;) {
        const auto result = xos::sdk::ipc_recv(route.endpoints.receive, &packet, sizeof(packet));
        if (result == static_cast<xos::i64>(sizeof(packet))) {
            require(packet == exitPermission, "exit-permission");
            return;
        }
        require(result == xos::process_error_would_block && pauseUntil(limit), "wait-exit-permission");
    }
}

bool draw(ShareableBitmap& bitmap, SkColor color)
{
    if (bitmap.mutableSpan().empty())
        return false;
    auto canvas = SkSurfaces::WrapPixels(SkImageInfo::MakeN32Premul(16, 8),
        bitmap.mutableSpan().data(), bitmap.bytesPerRow());
    if (!canvas)
        return false;
    canvas->getCanvas()->clear(color);
    return true;
}

bool colorIs(ShareableBitmap& bitmap, SkColor color)
{
    const auto image = bitmap.createPlatformImage(WebCore::BackingStoreCopy::DontCopyBackingStore);
    SkPixmap pixels;
    return image && image->peekPixels(&pixels) && pixels.getColor(2, 2) == color && pixels.getColor(12, 6) == color;
}

Protection protectionFor(Scenario scenario)
{
    return scenario == Scenario::readWrite ? Protection::ReadWrite : Protection::ReadOnly;
}

void owner(const xos_shared_memory_route& route, Scenario scenario, pid_t child = 0)
{
    const WebCore::ShareableBitmapConfiguration configuration(WebCore::IntSize(16, 8));
    auto memory = SharedMemory::allocate_for_xos_transfer(configuration.sizeInBytes());
    require(!!memory, "transfer-allocation");
    auto bitmap = ShareableBitmap::create(configuration, Ref { *memory });
    require(bitmap && draw(*bitmap, SK_ColorRED), "owner-draw-red");
    auto handle = memory->createHandle(protectionFor(scenario));
    require(!!handle, "owner-handle");
    auto wrong = route;
    wrong.expected_peer = xos::sdk::pid();
    require(!xos_memory_offer::send(WTF::move(*handle), wrong, deadline()), "reject-wrong-receiver");
    auto offer = xos_memory_offer::send(WTF::move(*handle), route, deadline());
    require(offer && offer->published(), "publish-handle");
    require(offer->confirm_map(deadline()), "owner-map-confirmation");

    if (scenario == Scenario::ownerExit)
        _exit(0);
    if (scenario == Scenario::holderExit) {
        require(!xos::sdk::ipc_send(route.endpoints.send, &exitPermission, sizeof(exitPermission)), "permit-holder-exit");
        require(waitForChild(child), "wait-holder-exit");
        bitmap = nullptr;
        memory = nullptr;
        require(offer->revoke() == xos_loan_result::ok, "revoke-after-holder-exit");
        return;
    }

    require(offer->close_after_release(deadline()) == xos_loan_result::local_views_active,
        "owner-local-bitmap-pins-storage");
    require(colorIs(*bitmap, scenario == Scenario::readWrite ? SK_ColorBLUE : SK_ColorRED), "owner-observes-alias");
    bitmap = nullptr;
    memory = nullptr;
    require(offer->close_after_release(deadline()) == xos_loan_result::ok, "owner-closes-grant");
    require(offer->close_after_release(deadline()) == xos_loan_result::ok, "idempotent-owner-close");
    require(waitForChild(child), "wait-cooperative-holder");
}

void holder(const xos_shared_memory_route& route, Scenario scenario, pid_t child = 0)
{
    const WebCore::ShareableBitmapConfiguration configuration(WebCore::IntSize(16, 8));
    auto wrong = route;
    wrong.expected_peer = xos::sdk::pid();
    require(!xos_memory_loan::receive(wrong, protectionFor(scenario), deadline()), "reject-wrong-producer");
    auto loan = xos_memory_loan::receive(route, protectionFor(scenario), deadline());
    require(!!loan, "receive-native-memory");
    auto memory = loan->view();
    require(memory && memory->span().size() == configuration.sizeInBytes(), "receive-size");
    auto bitmap = ShareableBitmap::create(configuration, Ref { *memory });
    require(bitmap && colorIs(*bitmap, SK_ColorRED), "holder-observes-publisher");
    if (scenario == Scenario::readWrite)
        require(draw(*bitmap, SK_ColorBLUE), "holder-writes-same-pages");
    else
        require(bitmap->mutableSpan().empty() && !memory->createHandle(Protection::ReadWrite), "holder-rights-ceiling");

    if (scenario == Scenario::holderExit) {
        waitForExitPermission(route);
        _exit(0);
    }
    if (scenario == Scenario::ownerExit) {
        require(waitForChild(child) && colorIs(*bitmap, SK_ColorRED), "alias-survives-owner-exit");
        bitmap = nullptr;
        memory = nullptr;
        require(loan->release(deadline()) == xos_loan_result::exchange_unconfirmed, "departed-owner-cannot-confirm-release");
        return;
    }

    require(loan->release(deadline()) == xos_loan_result::local_views_active, "holder-local-bitmap-pins-storage");
    bitmap = nullptr;
    memory = nullptr;
    require(loan->release(deadline()) == xos_loan_result::ok, "holder-sent-release");
    require(loan->confirm_close(deadline()), "holder-received-final-close");
}

void run(char* imagePath, Scenario scenario)
{
    const auto parent = xos::sdk::pid();
    require(!xos::sdk::ipc_name_publish(endpointName), "publish-rendezvous");
    char childRole[] = "loan-child";
    char mode[] = { static_cast<char>('0' + static_cast<unsigned int>(scenario)), '\0' };
    char* arguments[] = { imagePath, childRole, mode, nullptr };
    pid_t child = 0;
    const int launch = posix_spawn(&child, imagePath, nullptr, nullptr, arguments, environ);
    if (launch)
        std::printf("XOS_WEBCORE_BITMAP_TRANSFER_SPAWN_ERROR %d\n", launch);
    require(!launch && child > 0, "spawn-child");

    const auto route = channel(true, static_cast<uint64_t>(child), scenario);
    require(!xos::sdk::ipc_name_unpublish(endpointName), "unpublish-rendezvous");
    if (scenario == Scenario::ownerExit)
        holder(route, scenario, child);
    else
        owner(route, scenario, child);
    require(xos::sdk::ipc_channel_close(route.endpoints.send) == xos::process_error_denied, "exited-peer-channel-reclaimed");
    std::printf("XOS_WEBCORE_BITMAP_TRANSFER_CASE mode=%llu parent=%llu child=%ld\n",
        static_cast<unsigned long long>(scenario), static_cast<unsigned long long>(parent), static_cast<long>(child));
}

void runChild(Scenario scenario)
{
    // The kernel resolves zero to the real parent of this launched process.
    xos::ipc_channel parentLane { };
    xos::u64 parent = 0;
    require(!xos::sdk::ipc_channel_create(0, parentLane)
            && !xos::sdk::ipc_endpoint_peer(parentLane.send, parent)
            && !xos::sdk::ipc_channel_close(parentLane.send), "authenticate-parent");
    const auto route = channel(false, parent, scenario);
    if (scenario == Scenario::ownerExit)
        owner(route, scenario);
    else
        holder(route, scenario);
    _exit(0);
}

}

int main(int argc, char** argv)
{
    if (argc == 3 && !std::strcmp(argv[1], "loan-child")) {
        require(argv[2][0] >= '1' && argv[2][0] <= '4' && !argv[2][1], "child-mode");
        runChild(static_cast<Scenario>(argv[2][0] - '0'));
    }
    require(argc == 1, "driver-mode");
    run(argv[0], Scenario::readOnly);
    run(argv[0], Scenario::readWrite);
    run(argv[0], Scenario::holderExit);
    // The exiting owner leaves the borrowed capability in this process's table.
    // The final test ends this process to exercise kernel holder-exit cleanup.
    run(argv[0], Scenario::ownerExit);
    std::puts("XOS_WEBCORE_BITMAP_TRANSFER_PASS RO RW peer binding, release and both exit orders");
    return 0;
}
