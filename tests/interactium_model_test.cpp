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
    assert(manager.focused().value == 0);
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
    alignas(8) u8 commit_bytes[sizeof(commit_payload) + sizeof(dirty_rect)]{};
    const commit_payload commit{1, 1, 0};
    const dirty_rect dirty{0, 0, 300, 200};
    std::memcpy(commit_bytes, &commit, sizeof(commit));
    std::memcpy(commit_bytes + sizeof(commit), &dirty, sizeof(dirty));
    request_bytes(request, request_size, 5, client_one.session().value,
                  message_type::commit_frame, object, commit_bytes, sizeof(commit_bytes));
    assert(client_one.dispatch(request, request_size, response, sizeof(response), response_size) == 0);
    assert(reply_status(response) == 0);
    return 0;
}
