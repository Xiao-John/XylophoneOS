// SPDX-License-Identifier: Apache-2.0
#include <xos/terminal_client.hpp>
#include <xos/thread_abi.hpp>

namespace {
struct marker { xos::u64 magic; xos::u32 version, size; };
[[gnu::section(".xos.tty"), gnu::used]] const marker terminal_marker{
    xos::terminal_image_abi_magic, 1, sizeof(marker)};
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    terminal::client client{};
    if (terminal::connect_startup(client, startup) != 0) return 1;
    const char message[] = "W1_APP_OK\n";
    for (u32 i = 0; i < sizeof(message) - 1; ++i)
        if (terminal::write_until(client, message + i, 1, thread_deadline_infinite) != 1) return 2;
    terminal::close(client);
    return 0;
}
