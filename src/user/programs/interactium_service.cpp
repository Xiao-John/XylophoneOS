// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/display_client.hpp>
#include <xos/thread_abi.hpp>
#include "../interactium/ipc_transport.hpp"
#include "../interactium/service_loop.hpp"

namespace {
using namespace xos;
using namespace xos::interactium;

surface_buffer surfaces[surface_capacity];
u32 display_pixels[800 * 600];

// The pointer is composited last by Interactium, never baked into client frames.
void draw_cursor(u32* pixels, u32 width, u32 height, i32 x, i32 y) {
    for (u32 row = 0; row < 18; ++row) {
        const u32 row_width = 1 + row * 12 / 17;
        for (u32 column = 0; column < row_width; ++column) {
            const i32 px = x + static_cast<i32>(column);
            const i32 py = y + static_cast<i32>(row);
            if (px < 0 || py < 0 || px >= static_cast<i32>(width) || py >= static_cast<i32>(height)) continue;
            const bool outline = column == 0 || column + 1 == row_width || row == 17;
            pixels[static_cast<u32>(py) * width + static_cast<u32>(px)] = outline ? 0xff101820 : 0xfff5f7fa;
        }
    }
}

struct client_slot {
    ipc_session_transport transport{};
    service_loop loop;
    bool active = false;
    explicit client_slot(service& manager) : loop(manager) {}
};
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::sdk;
    service manager(surfaces);
    display_client display;
    if (display.open() != 0) return 8;
    display_mode mode{};
    if (display.mode(mode) != 0 || mode.width != 800 || mode.height != 600 ||
        mode.stride != 800 * 4 || display.focus(true) != 0) {
        (void)display.close();
        return 9;
    }
    client_slot clients[] = {client_slot(manager), client_slot(manager),
                             client_slot(manager), client_slot(manager)};
    if (ipc_name_publish("interactium") != 0) {
        (void)display.focus(false);
        (void)display.close();
        return 10;
    }
    print("[interactium-service] ready display=800x600\n");
    manager.invalidate(0, 0, mode.width, mode.height);
    i32 cursor_x = static_cast<i32>(mode.width / 2);
    i32 cursor_y = static_cast<i32>(mode.height / 2);

    for (;;) {
        bool progressed = false;
        for (auto& client : clients) {
            if (client.active) continue;
            ipc_channel channel{};
            const i64 accepted = ipc_name_try_accept(channel);
            if (accepted == 0) {
                client.transport.bind(channel);
                client.loop.bind(client.transport);
                client.active = true;
                progressed = true;
            } else if (accepted != process_error_would_block) {
                return 11;
            }
            break;
        }
        for (auto& client : clients) {
            if (!client.active) continue;
            const auto result = client.loop.step();
            progressed |= result != loop_result::again;
            if (result == loop_result::session_closed || result == loop_result::transport_error ||
                result == loop_result::protocol_error) {
                client.active = false;
            }
        }
        display_event event{};
        const i64 input_result = display.input(event);
        if (input_result == 0) {
            progressed = true;
            (void)manager.queue_input(event);
            if (event.kind == 3 || event.kind == 4) {
                if (cursor_x != event.x || cursor_y != event.y) {
                    manager.invalidate(cursor_x, cursor_y, 13, 18);
                    manager.invalidate(event.x, event.y, 13, 18);
                }
                cursor_x = event.x;
                cursor_y = event.y;
            }
        }
        else if (input_result != display_again) return 11;
        dirty_rect damage{};
        if (manager.take_damage(damage)) {
            progressed = true;
            if (!manager.compose_region(display_pixels, mode.width, mode.height, 0xff273342, damage)) return 12;
            draw_cursor(display_pixels, mode.width, mode.height, cursor_x, cursor_y);
            const display_present frame{1, sizeof(display_present), reinterpret_cast<u64>(display_pixels),
                                        mode.bytes, mode.stride, display_xrgb8888,
                                        {damage.x, damage.y, damage.width, damage.height}};
            if (display.present(frame) != 0) return 13;
        }
        if (progressed) yield();
        else {
            // Display v1 and named IPC have no common wait set. Sleep on the
            // existing monotonic clock between bounded readiness scans; do not
            // keep an idle desktop runnable or change either public ABI.
            const auto now = static_cast<u64>(syscall(sys_clock_monotonic));
            (void)syscall(sys_sleep_until, now + 10000000u);
        }
    }
}
