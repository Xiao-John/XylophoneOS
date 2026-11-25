// SPDX-License-Identifier: Apache-2.0
// Restricted native fixture for an empty startup-v3 FD snapshot. Unexpected
// inherited descriptors are rejected before any application operation.
#include <xos/net_service_client.hpp>
namespace {
using namespace xos;
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::used, gnu::section(".xos.exec")]] const exec_marker marker{exec_image_abi_magic, 3, 16};
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (!startup || startup->version != 3 || startup->argc != 2 || startup->reserved != startup_extension_offset) return 81;
    const auto* snapshot = reinterpret_cast<const startup_exec_extension*>(reinterpret_cast<const u8*>(startup) + startup_exec_offset);
    if (snapshot->magic != startup_exec_magic || snapshot->count || snapshot->reserved) return 82;
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    u64 expected = 0;
    for (const char* text = argv[1]; *text; ++text) {
        if (*text < '0' || *text > '9' || expected > (~u64{0} - 9) / 10) return 83;
        expected = expected * 10 + static_cast<u64>(*text - '0');
    }
    net2::session_client client;
    if (client.connect(expected)) return 84;
    net2::message request{}, reply{}; request.action = net2::operation::information;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0) return 85;
    request.deadline = static_cast<u64>(now) + 5'000'000'000ull;
    if (client.request(request, reply)) return 86;
    net2::information info{}; __builtin_memcpy(&info, reply.data, sizeof(info));
    if (info.connections != 0) return 87;
    sdk::print("NET_EXEC_PASS\n"); return 0;
}
