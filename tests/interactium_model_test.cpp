// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstring>
#include "../src/user/interactium/service.hpp"
#include "../src/user/interactium/dispatcher.hpp"

using namespace xos::interactium;
using namespace xos;

static void request_bytes(u8* buffer, u32& size, u64 sequence, u64 session,
                          message_type type, u64 object, const void* payload, u32 payload_size) {
    const wire_header header{protocol_version, static_cast<u32>(sizeof(wire_header) + payload_size), type, 0,
                             sequence, session, object, payload_size, 0};
    std::memcpy(buffer, &header, sizeof(header));
    if (payload_size != 0) std::memcpy(buffer + sizeof(header), payload, payload_size);
    size = header.size;
}

static i64 reply_status(const u8* buffer) {
    status_payload status{};
    std::memcpy(&status, buffer + sizeof(wire_header), sizeof(status));
    return status.result;
}

int main() {
    service service_model;
    const auto session_one = service_model.connect(11);
    const auto session_two = service_model.connect(22);
    assert(session_one.value != 0 && session_two.value != 0);
    window_manager manager;
    const create_window_payload first{10, 20, 300, 200, window_role::normal, 0, 0};
    const create_window_payload second{40, 50, 300, 200, window_role::normal, 0, 0};
    const auto one = manager.create(11, first);
    const auto two = manager.create(22, second);
    assert(one.valid() && two.valid() && one != two);
    assert(!manager.destroy(one, 22));
    assert(manager.raise_and_focus(one, 11));
    const auto hit = manager.hit_test(50, 60);
    assert(hit.id == one && hit.local_x == 40 && hit.local_y == 40);
    assert(manager.accept_frame(one, 11, 1));
    assert(!manager.accept_frame(one, 11, 1));
    compositor composed(manager);
    assert(composed.rebuild() == 2);
    assert(manager.destroy(one, 11));
    // Focus falls back to the remaining visible window instead of going dark.
    assert(manager.focused() == two);
    assert(composed.rebuild() == 1);
    assert(service_model.create_window(session_one, first).valid());
    const auto foreign = service_model.create_window(session_two, second);
    assert(foreign.valid());
    assert(!service_model.destroy_window(session_one, foreign));
    assert(service_model.focus_window(session_two, foreign));
    assert(service_model.rebuild() == 2);
    assert(service_model.disconnect(session_one));
    assert(service_model.rebuild() == 1);

    service multi_window_service;
    const auto multi_session = multi_window_service.connect(33);
    const auto first_window = multi_window_service.create_window(multi_session, first);
    const create_window_payload second_same_owner{400, 20, 300, 200, window_role::normal, 0, 0};
    const auto second_window = multi_window_service.create_window(multi_session, second_same_owner);
    assert(first_window.valid() && second_window.valid());
    display_event first_click{};
    first_click.sequence = 41;
    first_click.kind = 3;
    first_click.buttons = 1;
    first_click.x = 20;
    first_click.y = 30;
    display_event second_click = first_click;
    second_click.sequence = 42;
    second_click.x = 410;
    assert(multi_window_service.queue_input(first_click));
    assert(multi_window_service.queue_input(second_click));
    input_payload routed{};
    assert(multi_window_service.take_input(multi_session, second_window, routed));
    assert(routed.input_sequence == 42 && routed.x == 410);
    assert(!multi_window_service.take_input(multi_session, second_window, routed));
    assert(multi_window_service.take_input(multi_session, first_window, routed));
    assert(routed.input_sequence == 41 && routed.x == 20);
    // The window that used to own the pointer is told it no longer does.
    assert(multi_window_service.take_input(multi_session, first_window, routed));
    assert(routed.kind == input_kind::pointer && routed.x == 410);
    assert(!multi_window_service.take_input(multi_session, first_window, routed));

    window_manager pixel_manager;
    const auto red_window = pixel_manager.create(31, {0, 0, 2, 2, window_role::normal, 0, 0});
    const auto green_window = pixel_manager.create(32, {1, 1, 2, 2, window_role::normal, 0, 0});
    const u32 red_pixels[] = {0xffff0000, 0xffff0000, 0xffff0000, 0xffff0000};
    const u32 green_pixels[] = {0xff00ff00, 0xff00ff00, 0xff00ff00, 0x80008000};
    const surface_view pixel_surfaces[] = {
        {red_window, red_pixels, 2, 2, 8},
        {green_window, green_pixels, 2, 2, 8},
    };
    u32 composed_pixels[9]{};
    compositor pixel_compositor(pixel_manager);
    assert(pixel_compositor.compose(pixel_manager, pixel_surfaces, 2,
                                    composed_pixels, 3, 3, 0xff0000ff));
    assert(composed_pixels[0] == 0x00ff0000);
    assert(composed_pixels[4] == 0x0000ff00);
    assert(composed_pixels[8] == 0x0000807f);

    static surface_buffer protocol_surfaces[surface_capacity];
    service protocol_service(protocol_surfaces);
    protocol_dispatcher client_one(protocol_service, 101);
    protocol_dispatcher client_two(protocol_service, 202);
    alignas(8) u8 request[256]{}, response[256]{};
    u32 request_size = 0, response_size = 0;
    const hello_payload hello{protocol_version, 0, 800, 600};
    request_bytes(request, request_size, 1, 0, message_type::hello, 0, &hello, sizeof(hello));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    wire_header hello_reply{};
    std::memcpy(&hello_reply, response, sizeof(hello_reply));
    assert(hello_reply.type == message_type::hello_reply && client_one.connected());

    const create_window_payload create{20, 30, 300, 200, window_role::normal, 0, 0};
    request_bytes(request, request_size, 2, client_one.session().value,
                  message_type::create_window, 0, &create, sizeof(create));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    wire_header create_reply{};
    std::memcpy(&create_reply, response, sizeof(create_reply));
    assert(reply_status(response) == 0 && create_reply.object != 0);

    request_bytes(request, request_size, 1, client_one.session().value,
                  message_type::hello, 0, &hello, sizeof(hello));
    assert(client_two.dispatch(request, request_size, response, sizeof(response), response_size) ==
           static_cast<i32>(dispatch_result::denied));
    request_bytes(request, request_size, 1, 0, message_type::hello, 0, &hello, sizeof(hello));
    assert(client_two.dispatch(request, request_size, response, sizeof(response), response_size) == 0);

    const u64 object = create_reply.object;
    const frame_payload frame{1, 300, 200, 1200, pixel_format::argb8888_premultiplied, 240000};
    request_bytes(request, request_size, 3, client_one.session().value,
                  message_type::begin_frame, object, &frame, sizeof(frame));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    const tile_payload tile{1, 0, 0, 1, 1, 0, 4, 0};
    u8 tile_request[sizeof(tile_payload) + 4]{};
    const u8 red_pixel[]{0, 0, 0xff, 0xff};
    std::memcpy(tile_request, &tile, sizeof(tile));
    std::memcpy(tile_request + sizeof(tile), red_pixel, sizeof(red_pixel));
    request_bytes(request, request_size, 4, client_one.session().value,
                  message_type::write_tile, object, tile_request, sizeof(tile_request));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    assert(reply_status(response) == 0);
    assert(protocol_surfaces[0].pixels[0] == 0xff101820);
    alignas(8) u8 commit_bytes[sizeof(commit_payload) + sizeof(dirty_rect)]{};
    const commit_payload commit{1, 1, 0};
    const dirty_rect dirty{0, 0, 300, 200};
    std::memcpy(commit_bytes, &commit, sizeof(commit));
    std::memcpy(commit_bytes + sizeof(commit), &dirty, sizeof(dirty));
    request_bytes(request, request_size, 5, client_one.session().value,
                  message_type::commit_frame, object, commit_bytes, sizeof(commit_bytes));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    assert(reply_status(response) == 0);
    assert(protocol_surfaces[0].pixels[0] == 0xffff0000);
    const frame_payload cancelled_frame{2, 300, 200, 1200, pixel_format::argb8888_premultiplied, 240000};
    request_bytes(request, request_size, 6, client_one.session().value,
                  message_type::begin_frame, object, &cancelled_frame, sizeof(cancelled_frame));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    tile_payload cancelled_tile{2, 0, 0, 1, 1, 0, 4, 0};
    std::memcpy(tile_request, &cancelled_tile, sizeof(cancelled_tile));
    std::memset(tile_request + sizeof(cancelled_tile), 0, 4);
    request_bytes(request, request_size, 7, client_one.session().value,
                  message_type::write_tile, object, tile_request, sizeof(tile_request));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    request_bytes(request, request_size, 8, client_one.session().value,
                  message_type::cancel_frame, object, nullptr, 0);
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    assert(reply_status(response) == 0 && protocol_surfaces[0].pixels[0] == 0xffff0000);

    // W1: the window table is shared, but the quota is counted per session.
    {
        window_manager quota_manager;
        for (u32 owner = 1; owner <= max_sessions; ++owner)
            for (u32 i = 0; i < max_windows_per_session; ++i)
                assert(quota_manager.create(owner, first).valid());
        // The table covers every session slot, so a fifth session finds no room.
        assert(!quota_manager.create(max_sessions + 1, first).valid());

        service quota_service;
        const auto quota_one = quota_service.connect(41);
        const auto quota_two = quota_service.connect(42);
        window_id quota_windows[max_windows_per_session]{};
        for (u32 i = 0; i < max_windows_per_session; ++i) {
            quota_windows[i] = quota_service.create_window(quota_one, first);
            assert(quota_windows[i].valid());
        }
        assert(!quota_service.create_window(quota_one, first).valid());   // own quota reached
        const auto quota_other = quota_service.create_window(quota_two, second);
        assert(quota_other.valid());   // another session is not starved
        for (u32 i = 1; i < max_windows_per_session; ++i)
            assert(quota_service.create_window(quota_two, second).valid());
        assert(!quota_service.create_window(quota_two, second).valid());
        assert(quota_service.destroy_window(quota_one, quota_windows[0]));
        assert(quota_service.create_window(quota_one, first).valid());   // destroying frees the count
    }

    // W2: an overflowing input queue reports its losses instead of silently
    // swallowing the event that would have cleared a held key.
    {
        service overflow_service;
        const auto overflow_owner = overflow_service.connect(51);
        const auto overflow_window = overflow_service.create_window(overflow_owner, first);
        display_event key{};
        key.kind = 1;
        key.code = 42;
        key.sequence = 1;
        assert(overflow_service.queue_input(key));
        for (u32 i = 0; i < display_event_capacity; ++i) {
            key.kind = 2;
            key.sequence = 2 + i;
            assert(overflow_service.queue_input(key));
        }
        input_payload event{};
        u32 delivered = 0, resyncs = 0, lost_total = 0;
        u64 last_sequence = 0;
        bool press_delivered = false;
        while (overflow_service.take_input(overflow_owner, overflow_window, event)) {
            // The client aborts when the input sequence stops increasing.
            assert(event.input_sequence > last_sequence);
            last_sequence = event.input_sequence;
            ++delivered;
            lost_total += event.lost;
            resyncs += event.kind == input_kind::resync;
            press_delivered |= event.kind == input_kind::key_press;
        }
        assert(!press_delivered);                 // the press was the dropped event
        assert(resyncs == 1 && lost_total == 1);  // ... and the client is told about it
        assert(delivered == display_event_capacity + 1);
    }

    // W2: loss accounting is per window, even when another window's backlog is
    // what evicted the events.
    {
        service squeeze_service;
        const auto squeeze_a = squeeze_service.connect(52);
        const auto squeeze_b = squeeze_service.connect(53);
        const auto squeeze_window_a = squeeze_service.create_window(
            squeeze_a, {0, 0, 100, 100, window_role::normal, 0, 0});
        const auto squeeze_window_b = squeeze_service.create_window(
            squeeze_b, {200, 0, 100, 100, window_role::normal, 0, 0});
        display_event move{};
        move.kind = 3;
        move.x = 10;
        move.y = 10;   // inside A
        for (u32 i = 0; i < 40; ++i) {
            move.sequence = 1 + i;
            assert(squeeze_service.queue_input(move));
        }
        move.x = 210;   // inside B: crossing also queues A's leave copy
        for (u32 i = 0; i < 30; ++i) {
            move.sequence = 41 + i;
            assert(squeeze_service.queue_input(move));
        }
        input_payload event{};
        u32 resyncs = 0, lost_total = 0, from_a = 0;
        while (squeeze_service.take_input(squeeze_a, squeeze_window_a, event)) {
            ++from_a;
            resyncs += event.kind == input_kind::resync;
            lost_total += event.lost;
        }
        // 40 moves plus one leave, 7 evicted by B's backlog, one resync.
        assert(resyncs == 1 && lost_total == 7);
        assert(from_a == 35);
        u32 from_b = 0;
        while (squeeze_service.take_input(squeeze_b, squeeze_window_b, event)) ++from_b;
        assert(from_b == 30);   // B kept everything it was sent
    }

    // W3: crossing to another window leaves a trace in the previous one.
    {
        service leave_service;
        const auto leave_a = leave_service.connect(61);
        const auto leave_b = leave_service.connect(62);
        const auto leave_window_a = leave_service.create_window(leave_a, first);   // {10,20,300,200}
        const auto leave_window_b = leave_service.create_window(leave_b, second);  // {40,50,300,200}
        display_event move{};
        move.kind = 3;
        move.sequence = 1;
        move.x = 20;
        move.y = 30;
        assert(leave_service.queue_input(move));
        input_payload event{};
        assert(leave_service.take_input(leave_a, leave_window_a, event));
        move.sequence = 2;
        move.x = 100;
        move.y = 100;   // inside both windows; the newer one wins the hit test
        assert(leave_service.queue_input(move));
        assert(leave_service.take_input(leave_a, leave_window_a, event));
        assert(event.kind == input_kind::pointer);
        // The copy lands outside A even though the pointer point overlaps it.
        assert(event.x < 10 || event.x >= 310 || event.y < 20 || event.y >= 220);
        assert(leave_service.take_input(leave_b, leave_window_b, event));
        assert(event.x == 100 && event.y == 100);
        assert(!leave_service.take_input(leave_a, leave_window_a, event));

        // A hidden window stops being the previous pointer target.
        assert(leave_service.configure_window(leave_b, leave_window_b,
                                              {0, 40, 50, 300, 200, 0, 0}));
        move.sequence = 3;
        move.x = 20;
        move.y = 30;
        assert(leave_service.queue_input(move));
        assert(leave_service.take_input(leave_a, leave_window_a, event));
        assert(event.x == 20 && event.y == 30);
        assert(!leave_service.take_input(leave_b, leave_window_b, event));

        // So does a destroyed one.
        service destroy_leave_service;
        const auto destroy_a = destroy_leave_service.connect(71);
        const auto destroy_b = destroy_leave_service.connect(72);
        const auto destroy_window_a = destroy_leave_service.create_window(destroy_a, first);
        const auto destroy_window_b = destroy_leave_service.create_window(destroy_b, second);
        move = display_event{};
        move.kind = 3;
        move.sequence = 1;
        move.x = 20;
        move.y = 30;
        assert(destroy_leave_service.queue_input(move));
        assert(destroy_leave_service.take_input(destroy_a, destroy_window_a, event));
        move.sequence = 2;
        move.x = 100;
        move.y = 100;
        assert(destroy_leave_service.queue_input(move));
        assert(destroy_leave_service.take_input(destroy_b, destroy_window_b, event));
        assert(destroy_leave_service.take_input(destroy_a, destroy_window_a, event));   // leave for A
        assert(event.x < 10 || event.x >= 310 || event.y < 20 || event.y >= 220);
        assert(destroy_leave_service.destroy_window(destroy_b, destroy_window_b));
        move.sequence = 3;
        assert(destroy_leave_service.queue_input(move));
        assert(destroy_leave_service.take_input(destroy_a, destroy_window_a, event));
        assert(event.x == 100 && event.y == 100);
        assert(!destroy_leave_service.take_input(destroy_a, destroy_window_a, event));
    }

    // W4: keyboard input survives close, hide, and disconnect of the focus.
    {
        service focus_service;
        const auto focus_a = focus_service.connect(81);
        const auto focus_b = focus_service.connect(82);
        const auto focus_window_a = focus_service.create_window(focus_a, first);
        const auto focus_window_b = focus_service.create_window(focus_b, second);   // focused
        display_event key{};
        key.kind = 1;
        key.code = 30;
        input_payload event{};

        assert(focus_service.get_window(window_id{0}) == nullptr);   // id 0 never matches an empty slot
        assert(focus_service.destroy_window(focus_b, focus_window_b));
        assert(focus_service.get_window(focus_window_a)->focused);
        key.sequence = 1;
        assert(focus_service.queue_input(key));
        assert(focus_service.take_input(focus_a, focus_window_a, event));
        assert(event.kind == input_kind::key_press && event.code == 30);

        const auto focus_window_hidden = focus_service.create_window(focus_b, second);
        assert(focus_service.get_window(focus_window_hidden)->focused);
        assert(focus_service.configure_window(focus_b, focus_window_hidden,
                                              {0, 40, 50, 300, 200, 0, 0}));
        assert(focus_service.get_window(focus_window_a)->focused);
        key.sequence = 2;
        assert(focus_service.queue_input(key));
        assert(focus_service.take_input(focus_a, focus_window_a, event));
        assert(event.kind == input_kind::key_press);

        const auto focus_window_gone = focus_service.create_window(focus_b, second);
        assert(focus_service.get_window(focus_window_gone)->focused);
        assert(focus_service.disconnect(focus_b));
        assert(focus_service.get_window(focus_window_a)->focused);
        key.sequence = 3;
        assert(focus_service.queue_input(key));
        assert(focus_service.take_input(focus_a, focus_window_a, event));
        assert(event.kind == input_kind::key_press);

        service empty_service;
        (void)empty_service.connect(91);
        key.sequence = 4;
        assert(!empty_service.queue_input(key));   // no window at all: reject instead of misroute
    }

    // W5: a key release goes to the window that took the press.
    {
        service release_service;
        const auto release_a = release_service.connect(93);
        const auto release_b = release_service.connect(94);
        const auto release_window_a = release_service.create_window(release_a, first);
        const auto release_window_b = release_service.create_window(release_b, second);
        display_event key{};
        key.kind = 1;
        key.code = 30;
        key.sequence = 1;
        input_payload event{};

        // Focus change through the protocol.
        assert(release_service.focus_window(release_a, release_window_a));
        assert(release_service.queue_input(key));
        assert(release_service.focus_window(release_b, release_window_b));
        key.kind = 2;
        key.sequence = 2;
        assert(release_service.queue_input(key));
        bool release_seen = false;
        while (release_service.take_input(release_a, release_window_a, event))
            release_seen |= event.kind == input_kind::key_release;
        assert(release_seen);
        assert(!release_service.take_input(release_b, release_window_b, event));

        // Focus change through a click on the other window.
        assert(release_service.focus_window(release_a, release_window_a));
        key.kind = 1;
        key.sequence = 3;
        assert(release_service.queue_input(key));
        display_event click{};
        click.kind = 3;
        click.sequence = 4;
        click.buttons = 1;
        click.x = 60;
        click.y = 60;
        assert(release_service.queue_input(click));
        key.kind = 2;
        key.sequence = 5;
        assert(release_service.queue_input(key));
        release_seen = false;
        while (release_service.take_input(release_a, release_window_a, event))
            release_seen |= event.kind == input_kind::key_release;
        assert(release_seen);
        while (release_service.take_input(release_b, release_window_b, event))
            assert(event.kind == input_kind::pointer);   // never a stray release

        // The press window is destroyed while the key is held.
        assert(release_service.focus_window(release_a, release_window_a));
        key.kind = 1;
        key.sequence = 6;
        assert(release_service.queue_input(key));
        assert(release_service.destroy_window(release_a, release_window_a));
        assert(release_service.get_window(release_window_b)->focused);
        key.kind = 2;
        key.sequence = 7;
        assert(!release_service.queue_input(key));   // orphan release is dropped, not reassigned
        assert(!release_service.take_input(release_b, release_window_b, event));
    }

    {
        service repeat_service;
        const auto owner = repeat_service.connect(95);
        const auto original = repeat_service.create_window(owner, first);
        const auto other = repeat_service.create_window(owner, second);
        assert(repeat_service.focus_window(owner, original));
        display_event key{};
        key.kind = 1;
        key.code = 30;
        key.sequence = 1;
        assert(repeat_service.queue_input(key));
        assert(repeat_service.focus_window(owner, other));
        key.sequence = 2;
        assert(repeat_service.queue_input(key));
        key.sequence = 3;
        key.kind = 2;
        assert(repeat_service.queue_input(key));
        input_payload event{};
        assert(repeat_service.take_input(owner, original, event));
        assert(event.kind == input_kind::key_press && event.input_sequence == 1);
        assert(repeat_service.take_input(owner, original, event));
        assert(event.kind == input_kind::key_press && event.input_sequence == 2);
        assert(repeat_service.take_input(owner, original, event));
        assert(event.kind == input_kind::key_release && event.input_sequence == 3);
        assert(!repeat_service.take_input(owner, other, event));

        key.sequence = 4;
        key.kind = 1;
        assert(repeat_service.queue_input(key));
        assert(repeat_service.take_input(owner, other, event));
        assert(event.kind == input_kind::key_press);
    }

    {
        service resync_service;
        const auto owner = resync_service.connect(96);
        const auto original = resync_service.create_window(owner, first);
        const auto other = resync_service.create_window(owner, second);
        assert(resync_service.focus_window(owner, original));
        display_event key{};
        key.kind = 1;
        key.code = 30;
        key.sequence = 1;
        assert(resync_service.queue_input(key));
        input_payload event{};
        assert(resync_service.take_input(owner, original, event));
        assert(resync_service.focus_window(owner, other));
        display_event resync{};
        resync.kind = 4;
        resync.sequence = 2;
        resync.lost = 65;
        assert(resync_service.queue_input(resync));
        assert(resync_service.take_input(owner, original, event));
        assert(event.kind == input_kind::resync && event.lost == 65);
        assert(resync_service.take_input(owner, other, event));
        assert(event.kind == input_kind::resync && event.lost == 65);

        key.sequence = 3;
        assert(resync_service.queue_input(key));
        assert(resync_service.take_input(owner, other, event));
        assert(event.kind == input_kind::key_press);
        assert(!resync_service.take_input(owner, original, event));
    }
    return 0;
}
