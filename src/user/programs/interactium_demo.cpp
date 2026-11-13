// SPDX-License-Identifier: Apache-2.0
#include <xos/display_client.hpp>
#include <xos/interactium_abi.hpp>
#include "../interactium/service.hpp"

namespace {
using namespace xos;
using namespace xos::sdk;
using namespace xos::interactium;

constexpr u32 screen_width = 800;
constexpr u32 screen_height = 600;
constexpr u32 window_width = 360;
constexpr u32 window_height = 250;
constexpr u32 font_scale = 2;
u32 output[screen_width * screen_height];
u32 first_pixels[window_width * window_height];
u32 second_pixels[window_width * window_height];

void fill(u32* pixels, u32 stride, u32 x, u32 y, u32 width, u32 height, u32 color) {
    for (u32 row = y; row < y + height; ++row)
        for (u32 col = x; col < x + width; ++col) pixels[row * stride + col] = color;
}

u8 glyph_column(char character, u32 column) {
    static constexpr u8 letters[26][5] = {
        {0x7e,0x11,0x11,0x11,0x7e},{0x7f,0x49,0x49,0x49,0x36},
        {0x3e,0x41,0x41,0x41,0x22},{0x7f,0x41,0x41,0x22,0x1c},
        {0x7f,0x49,0x49,0x49,0x41},{0x7f,0x09,0x09,0x09,0x01},
        {0x3e,0x41,0x49,0x49,0x7a},{0x7f,0x08,0x08,0x08,0x7f},
        {0x00,0x41,0x7f,0x41,0x00},{0x20,0x40,0x41,0x3f,0x01},
        {0x7f,0x08,0x14,0x22,0x41},{0x7f,0x40,0x40,0x40,0x40},
        {0x7f,0x02,0x0c,0x02,0x7f},{0x7f,0x04,0x08,0x10,0x7f},
        {0x3e,0x41,0x41,0x41,0x3e},{0x7f,0x09,0x09,0x09,0x06},
        {0x3e,0x41,0x51,0x21,0x5e},{0x7f,0x09,0x19,0x29,0x46},
        {0x46,0x49,0x49,0x49,0x31},{0x01,0x01,0x7f,0x01,0x01},
        {0x3f,0x40,0x40,0x40,0x3f},{0x1f,0x20,0x40,0x20,0x1f},
        {0x7f,0x20,0x18,0x20,0x7f},{0x63,0x14,0x08,0x14,0x63},
        {0x07,0x08,0x70,0x08,0x07},{0x61,0x51,0x49,0x45,0x43}
    };
    if (character >= 'a' && character <= 'z') character = static_cast<char>(character - 'a' + 'A');
    if (character == ' ') return 0;
    if (character == '-') return column == 2 ? 0x08 : 0;
    if (character == '.') return column == 2 ? 0x40 : 0;
    if (character < 'A' || character > 'Z') return 0;
    return letters[character - 'A'][column];
}

void text(u32* pixels, u32 x, u32 y, const char* value, u32 color) {
    for (u32 index = 0; value[index] != 0; ++index) {
        for (u32 column = 0; column < 5; ++column) {
            const u8 bits = glyph_column(value[index], column);
            for (u32 row = 0; row < 7; ++row) {
                if ((bits & (1u << row)) != 0)
                    fill(pixels, window_width, x + index * 12 + column * font_scale,
                         y + row * font_scale, font_scale, font_scale, color);
            }
        }
    }
}

void paint_window(u32* pixels, u32 title, const char* title_text,
                  const char* body_text, u32 accent) {
    fill(pixels, window_width, 0, 0, window_width, window_height, 0xff18212d);
    fill(pixels, window_width, 0, 0, window_width, 34, title);
    fill(pixels, window_width, 14, 13, 8, 8, 0xfff5f7fa);
    fill(pixels, window_width, 28, 13, 8, 8, 0xfff5f7fa);
    fill(pixels, window_width, 42, 13, 8, 8, 0xfff5f7fa);
    text(pixels, 66, 10, title_text, 0xff101820);
    fill(pixels, window_width, 18, 62, 5, 46, accent);
    text(pixels, 38, 68, body_text, 0xfff5f7fa);
    fill(pixels, window_width, 38, 106, 280, 1, 0xff405064);
    text(pixels, 38, 130, "INTERACTIUM DEMO", 0xffbdc9d6);
    fill(pixels, window_width, 38, 177, 112, 32, accent);
    text(pixels, 53, 185, "OPEN", 0xff101820);
}

void draw_cursor(u32* pixels, u32 width, u32 height, i32 x, i32 y) {
    constexpr u32 cursor_height = 18;
    constexpr u32 cursor_width = 13;
    for (u32 row = 0; row < cursor_height; ++row) {
        const u32 row_width = 1 + row * (cursor_width - 1) / (cursor_height - 1);
        for (u32 column = 0; column < row_width; ++column) {
            const i32 screen_x = x + static_cast<i32>(column);
            const i32 screen_y = y + static_cast<i32>(row);
            if (screen_x < 0 || screen_y < 0 || screen_x >= static_cast<i32>(width) ||
                screen_y >= static_cast<i32>(height)) continue;
            const bool outline = column == 0 || column + 1 == row_width || row + 1 == cursor_height;
            pixels[static_cast<u32>(screen_y) * width + static_cast<u32>(screen_x)] =
                outline ? 0xff101820 : 0xfff5f7fa;
        }
    }
}

bool render(service& windows, const surface_view* surfaces, u32 surface_count,
            display_client& display, const display_mode& mode, i32 cursor_x, i32 cursor_y) {
    if (!windows.compose(surfaces, surface_count, output, mode.width, mode.height, 0xff273342)) return false;
    draw_cursor(output, mode.width, mode.height, cursor_x, cursor_y);
    const display_present frame{1, sizeof(display_present), reinterpret_cast<u64>(output),
                                mode.bytes, mode.stride, display_xrgb8888,
                                {0, 0, mode.width, mode.height}};
    return display.present(frame) == 0;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos::sdk;
    using namespace xos::interactium;
    service window_service;
    display_client display;
    if (display.open() != 0) return 2;
    display_mode mode{};
    if (display.mode(mode) != 0 || mode.width != screen_width || mode.height != screen_height ||
        mode.stride != screen_width * 4 || display.focus(true) != 0) {
        (void)display.close();
        return 3;
    }

    const auto first_session = window_service.connect(0x1001);
    const auto second_session = window_service.connect(0x1002);
    const create_window_payload first_create{72, 96, window_width, window_height,
                                              window_role::normal, 0, 0};
    const create_window_payload second_create{352, 230, window_width, window_height,
                                               window_role::normal, 0, 0};
    const auto first_window = window_service.create_window(first_session, first_create);
    const auto second_window = window_service.create_window(second_session, second_create);
    if (!first_window.valid() || !second_window.valid() ||
        !window_service.focus_window(second_session, second_window)) {
        (void)display.close();
        return 4;
    }
    paint_window(first_pixels, 0xff3e8290, "WINDOW A", "FIRST CLIENT", 0xff66c6b9);
    paint_window(second_pixels, 0xffd28b3c, "WINDOW B", "SECOND CLIENT", 0xffffce73);
    const surface_view surfaces[] = {
        {first_window, first_pixels, window_width, window_height, window_width * 4},
        {second_window, second_pixels, window_width, window_height, window_width * 4},
    };
    i32 cursor_x = static_cast<i32>(mode.width / 2);
    i32 cursor_y = static_cast<i32>(mode.height / 2);
    if (!render(window_service, surfaces, 2, display, mode, cursor_x, cursor_y)) {
        (void)display.close();
        return 5;
    }
    print("[interactium-demo] two windows visible; click to focus, drag title bars, Q/Esc exits\n");
    window_id dragging{};
    i32 drag_offset_x = 0;
    i32 drag_offset_y = 0;
    bool left_was_down = false;
    bool succeeded = true;
    for (;;) {
        display_event event{};
        const i64 result = display.input(event);
        if (result == display_again) {
            if (display.wait_input() != 0) { succeeded = false; break; }
            continue;
        }
        if (result != 0) { succeeded = false; break; }
        if (event.kind == 1 && (event.code == 16 || event.code == 1)) break;
        if (event.kind == 4) {
            cursor_x = event.x;
            cursor_y = event.y;
            left_was_down = (event.buttons & 1u) != 0;
            dragging = {};
            if (!render(window_service, surfaces, 2, display, mode, cursor_x, cursor_y)) {
                succeeded = false; break;
            }
            continue;
        }
        if (event.kind != 3) continue;
        cursor_x = event.x;
        cursor_y = event.y;
        const bool left_down = (event.buttons & 1u) != 0;
        const auto hit = window_service.hit_test(event.x, event.y);
        if (left_down && !left_was_down && hit.id.valid()) {
            if (hit.id == first_window) (void)window_service.focus_window(first_session, first_window);
            if (hit.id == second_window) (void)window_service.focus_window(second_session, second_window);
            if (hit.local_y < 34) {
                dragging = hit.id;
                drag_offset_x = hit.local_x;
                drag_offset_y = hit.local_y;
            }
        }
        if (left_down && dragging.valid()) {
            const auto* state = window_service.get_window(dragging);
            if (state) {
                const configure_payload move{0, event.x - drag_offset_x, event.y - drag_offset_y,
                                             state->width, state->height,
                                             state->visible ? flag_visible : 0u, 0};
                const auto token = dragging == first_window ? first_session : second_session;
                (void)window_service.configure_window(token, dragging, move);
            }
        }
        if (!left_down) dragging = {};
        left_was_down = left_down;
        if (!render(window_service, surfaces, 2, display, mode, cursor_x, cursor_y)) {
            succeeded = false; break;
        }
    }
    print("[interactium-demo] closed\n");
    (void)display.focus(false);
    (void)display.close();
    return succeeded ? 0 : 6;
}
