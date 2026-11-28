// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstdio>
#include <cstring>
#include "../src/user/interactium/dispatcher.hpp"
#include "../src/user/interactium/service_loop.hpp"
using namespace xos;
using namespace xos::interactium;

static surface_buffer surfaces[surface_capacity];
static u32 full[800 * 600], damaged[800 * 600];
static unsigned checks;
static void check(bool ok) { assert(ok); ++checks; }

struct peer {
    protocol_dispatcher dispatcher;
    u64 sequence = 0;
    wire_header response{};
    explicit peer(service& model, u64 owner) : dispatcher(model, owner) {
        const hello_payload hello{1, 0, 800, 600};
        check(call(message_type::hello, 0, &hello, sizeof(hello)) == 0);
    }
    i64 call(message_type type, u64 object, const void* body = nullptr, u32 bytes = 0,
             u32 flags = 0) {
        u8 request[4096]{}, reply[4096]{}; u32 size = 0;
        const wire_header header{1, u32(sizeof(wire_header)) + bytes, type, flags, ++sequence,
                                  dispatcher.session().value, object, bytes, 0};
        std::memcpy(request, &header, sizeof(header));
        if (bytes) std::memcpy(request + sizeof(header), body, bytes);
        const auto result = dispatcher.dispatch(request, header.size, reply, sizeof(reply), size);
        if (result) return result;
        check(size >= sizeof(wire_header));
        std::memcpy(&response, reply, sizeof(response));
        if (response.type != message_type::ack) return 0;
        status_payload status{}; std::memcpy(&status, reply + sizeof(response), sizeof(status));
        return status.result;
    }
    u64 create(i32 x, i32 y, u32 width, u32 height) {
        const create_window_payload create{x, y, width, height, window_role::normal, 0, 0};
        check(call(message_type::create_window, 0, &create, sizeof(create)) == 0);
        return response.object;
    }
    i64 tile(u64 object, u64 serial, u32 width, dirty_rect area, u32 color) {
        u8 body[4096]{};
        const tile_payload tile{serial, area.x, area.y, area.width, area.height,
                                 (area.y * width + area.x) * 4, area.width * area.height * 4, 0};
        assert(tile.source_length <= 4000);
        std::memcpy(body, &tile, sizeof(tile));
        for (u32 i = 0; i < area.width * area.height; ++i)
            std::memcpy(body + sizeof(tile) + i * 4, &color, 4);
        return call(message_type::write_tile, object, body, u32(sizeof(tile)) + tile.source_length);
    }
    i64 begin(u64 object, u64 serial, u32 width, u32 height) {
        const frame_payload frame{serial, width, height, width * 4,
                                  pixel_format::argb8888_premultiplied, u64(width) * height * 4};
        return call(message_type::begin_frame, object, &frame, sizeof(frame));
    }
    i64 commit(u64 object, u64 serial) {
        const commit_payload commit{serial, 0, 0};
        return call(message_type::commit_frame, object, &commit, sizeof(commit));
    }
};

static void compare(service& model) {
    dirty_rect region{};
    if (model.take_damage(region))
        check(model.compose_region(damaged, 800, 600, 0xff273342, region));
    check(model.compose(full, 800, 600, 0xff273342));
    check(std::memcmp(full, damaged, sizeof(full)) == 0);
}

int main() {
    service model(surfaces);
    model.invalidate(0, 0, 800, 600);
    compare(model);
    peer a(model, 100), b(model, 200);
    const u64 one = a.create(40, 60, 40, 20), two = b.create(60, 70, 40, 20);
    compare(model);
    check(a.begin(one, 1, 40, 20) == 0);
    check(a.tile(one, 1, 40, {0, 0, 40, 20}, 0xff2860c0) == 0);
    // A partially copied frame is never exposed.
    compare(model);
    check(a.commit(one, 1) == 0);
    compare(model);
    check(b.begin(two, 1, 40, 20) == 0);
    check(b.tile(two, 1, 40, {0, 0, 40, 20}, 0x80402010) == 0);
    check(b.commit(two, 1) == 0);
    compare(model);
    check(full[75 * 800 + 65] == 0x00545070);
    check(a.begin(one, 2, 40, 20) == 0);
    check(a.tile(one, 2, 40, {5, 5, 4, 3}, 0xff20c070) == 0);
    check(a.commit(one, 2) == 0);
    dirty_rect area{};
    check(model.take_damage(area) && area.x == 45 && area.y == 65 && area.width == 4 && area.height == 3);
    check(model.compose_region(damaged, 800, 600, 0xff273342, area));
    compare(model);
    check(a.begin(one, 2, 40, 20) == -1);
    check(a.begin(one, 3, 39, 20) == -1);
    check(a.begin(one, 3, 40, 20) == 0);
    check(a.tile(one, 3, 40, {0, 0, 2, 1}, 0x1020ff00) == -2);
    check(a.call(message_type::cancel_frame, one) == 0);
    compare(model);
    check(b.call(message_type::focus, one) == -2);
    check(b.call(message_type::destroy_window, one) == -2);
    check(b.call(message_type::input, one) == -2);
    const close_payload close{};
    check(b.call(message_type::close_request, one, &close, sizeof(close)) == -2);
    check(a.call(message_type::focus, one, nullptr, 0, 1) == -1);
    const configure_payload resize{0, 20, 30, 60, 30, flag_visible, 0};
    check(a.begin(one, 4, 40, 20) == 0);
    check(a.tile(one, 4, 40, {0, 0, 2, 1}, 0xffe02020) == 0);
    check(a.call(message_type::configure, one, &resize, sizeof(resize)) == 0);
    check(a.commit(one, 4) == -1);
    compare(model);
    check(full[30 * 800 + 20] == 0x002860c0);
    check(full[30 * 800 + 70] == 0x00101820);
    // Drag capture belongs to the original press even across another app.
    display_event event{};
    event.kind = 3; event.sequence = 1; event.x = 30; event.y = 40; event.buttons = 1;
    check(model.queue_input(event));
    event.sequence = 2; event.x = 90; event.y = 80;
    check(model.queue_input(event));
    input_payload input{};
    check(!model.take_input(b.dispatcher.session(), {two}, input));
    check(model.take_input(a.dispatcher.session(), {one}, input) && input.buttons == 1);
    check(model.take_input(a.dispatcher.session(), {one}, input) && input.x == 90);
    event.sequence = 3; event.buttons = 0;
    check(model.queue_input(event));
    check(model.take_input(a.dispatcher.session(), {one}, input) && input.buttons == 0);
    check(!model.take_input(b.dispatcher.session(), {two}, input));
    event.sequence = 4;
    check(model.queue_input(event));
    check(model.take_input(b.dispatcher.session(), {two}, input));
    event.sequence = 5; event.x = 30; event.y = 40; event.buttons = 1;
    check(model.queue_input(event));
    while (model.take_input(b.dispatcher.session(), {two}, input)) check(input.buttons == 0);
    check(a.call(message_type::close_request, one, &close, sizeof(close)) == 0);
    check(model.get_window({one}) == nullptr && model.get_window({two})->focused);
    event.sequence = 6; event.x = 90; event.y = 80;
    check(!model.queue_input(event));
    check(!model.take_input(b.dispatcher.session(), {two}, input));
    event.sequence = 7; event.buttons = 0;
    check(!model.queue_input(event));
    event.sequence = 8;
    check(model.queue_input(event));
    check(model.take_input(b.dispatcher.session(), {two}, input) && input.buttons == 0);
    compare(model);
    b.dispatcher.transport_closed();
    compare(model);
    check(model.get_window({two}) == nullptr);
    std::printf("MOBIUS_MULTIWINDOW_HOST_PASS checks=%u\n", checks);
}
