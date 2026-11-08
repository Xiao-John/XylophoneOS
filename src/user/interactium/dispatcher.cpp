// SPDX-License-Identifier: Apache-2.0
#include "dispatcher.hpp"

namespace xos::interactium {

namespace {
void copy_bytes(void* destination, const void* source, u32 length) {
    auto* out = static_cast<u8*>(destination);
    const auto* in = static_cast<const u8*>(source);
    for (u32 i = 0; i < length; ++i) out[i] = in[i];
}

template <typename T>
bool payload_is(const wire_header& header, u32 request_size) {
    return header.payload_length == sizeof(T) &&
           request_size == sizeof(wire_header) + sizeof(T);
}

bool empty_payload(const wire_header& header, u32 request_size) {
    return header.payload_length == 0 && request_size == sizeof(wire_header);
}

bool checked_rect(const dirty_rect& rect, u32 width, u32 height) {
    return rect.width != 0 && rect.height != 0 && rect.x < width && rect.y < height &&
           rect.width <= width - rect.x && rect.height <= height - rect.y;
}
}

bool protocol_dispatcher::session_matches(const wire_header& header) const {
    return connected() && header.session == session_.value;
}

i32 protocol_dispatcher::write_reply(const wire_header& request, message_type type,
                                     window_id object, i64 result, const void* payload,
                                     u32 payload_length, u8* response,
                                     u32 response_capacity, u32& response_size) const {
    const u64 total = sizeof(wire_header) + payload_length;
    if (payload_length > max_wire_payload || total > response_capacity) {
        response_size = 0;
        return static_cast<i32>(dispatch_result::resources);
    }
    const u64 response_session = session_.value != 0 ? session_.value : request.session;
    wire_header header{protocol_version, static_cast<u32>(total), type, 0,
                       request.sequence, response_session, object.value, payload_length, 0};
    copy_bytes(response, &header, sizeof(header));
    if (payload_length != 0) copy_bytes(response + sizeof(header), payload, payload_length);
    response_size = static_cast<u32>(total);
    (void)result;
    return static_cast<i32>(dispatch_result::ok);
}

i32 protocol_dispatcher::write_status(const wire_header& request, window_id object,
                                      i64 result, u8* response, u32 response_capacity,
                                      u32& response_size) const {
    const status_payload status{result};
    return write_reply(request, message_type::ack, object, result, &status,
                       sizeof(status), response, response_capacity, response_size);
}

i32 protocol_dispatcher::dispatch(const u8* request, u32 request_size, u8* response,
                                   u32 response_capacity, u32& response_size) {
    response_size = 0;
    if (!request || !response || request_size < sizeof(wire_header) ||
        response_capacity < sizeof(wire_header)) return static_cast<i32>(dispatch_result::malformed);

    wire_header header{};
    copy_bytes(&header, request, sizeof(header));
    if (header.version != protocol_version || header.size != request_size ||
        header.payload_length != request_size - sizeof(wire_header) ||
        header.payload_length > max_wire_payload || header.reserved != 0 ||
        header.sequence == 0 || header.sequence <= last_sequence_) {
        return static_cast<i32>(dispatch_result::malformed);
    }
    const u8* payload = request + sizeof(wire_header);

    if (header.type == message_type::hello) {
        if (connected() || header.session != 0 || header.object != 0 ||
            !payload_is<hello_payload>(header, request_size)) {
            return static_cast<i32>(dispatch_result::denied);
        }
        hello_payload hello{};
        copy_bytes(&hello, payload, sizeof(hello));
        if (hello.client_version != protocol_version || owner_ == 0) {
            return static_cast<i32>(dispatch_result::unsupported);
        }
        const auto session = service_->connect(owner_);
        if (session.value == 0) return static_cast<i32>(dispatch_result::resources);
        session_ = session;
        last_sequence_ = header.sequence;
        const hello_reply_payload reply{protocol_version, 0, 800, 600, session.value, 0};
        return write_reply(header, message_type::hello_reply, {}, 0, &reply,
                           sizeof(reply), response, response_capacity, response_size);
    }

    if (!session_matches(header)) return static_cast<i32>(dispatch_result::denied);
    if (header.type == message_type::disconnect) {
        if (!empty_payload(header, request_size) || header.object != 0) {
            return static_cast<i32>(dispatch_result::malformed);
        }
        last_sequence_ = header.sequence;
        const bool disconnected = service_->disconnect(session_);
        session_ = {};
        frame_ = {};
        return write_status(header, {}, disconnected ? 0 : -1, response,
                            response_capacity, response_size);
    }

    i64 result = static_cast<i64>(dispatch_result::malformed);
    window_id object{header.object};
    switch (header.type) {
    case message_type::create_window: {
        if (header.object != 0 || !payload_is<create_window_payload>(header, request_size)) break;
        create_window_payload create{};
        copy_bytes(&create, payload, sizeof(create));
        object = service_->create_window(session_, create);
        result = object.valid() ? 0 : static_cast<i64>(dispatch_result::resources);
        break;
    }
    case message_type::destroy_window:
        if (!object.valid() || !empty_payload(header, request_size)) break;
        result = service_->destroy_window(session_, object) ? 0 : static_cast<i64>(dispatch_result::denied);
        if (result == 0 && frame_.window == object) frame_ = {};
        break;
    case message_type::configure: {
        if (!object.valid() || !payload_is<configure_payload>(header, request_size)) break;
        configure_payload configure{};
        copy_bytes(&configure, payload, sizeof(configure));
        result = service_->configure_window(session_, object, configure) ? 0 : static_cast<i64>(dispatch_result::denied);
        break;
    }
    case message_type::focus:
        if (!object.valid() || !empty_payload(header, request_size)) break;
        result = service_->focus_window(session_, object) ? 0 : static_cast<i64>(dispatch_result::denied);
        break;
    case message_type::input: {
        if (!object.valid() || !empty_payload(header, request_size)) break;
        input_payload event{};
        if (service_->take_input(session_, object, event)) {
            last_sequence_ = header.sequence;
            return write_reply(header, message_type::input, object, 0, &event, sizeof(event),
                               response, response_capacity, response_size);
        }
        result = static_cast<i64>(dispatch_result::busy);
        break;
    }
    case message_type::begin_frame: {
        if (!object.valid() || !payload_is<frame_payload>(header, request_size) || frame_.active) break;
        frame_payload frame{};
        copy_bytes(&frame, payload, sizeof(frame));
        if (frame.frame_serial == 0 || frame.width == 0 || frame.height == 0 ||
            frame.width > 800 || frame.height > 600 || frame.stride < frame.width * 4u ||
            frame.bytes > max_frame_bytes || frame.bytes < u64(frame.stride) * frame.height ||
            frame.format != pixel_format::argb8888_premultiplied) break;
        if (!service_->begin_frame(session_, object)) { result = static_cast<i64>(dispatch_result::denied); break; }
        frame_ = {true, object, frame.frame_serial, frame.width, frame.height,
                  frame.stride, frame.bytes};
        result = 0;
        break;
    }
    case message_type::write_tile: {
        if (!object.valid() || header.payload_length < sizeof(tile_payload) ||
            request_size != sizeof(wire_header) + header.payload_length ||
            !frame_.active || frame_.window != object) break;
        tile_payload tile{};
        copy_bytes(&tile, payload, sizeof(tile));
        if (tile.frame_serial != frame_.serial || tile.width == 0 || tile.height == 0 ||
            !checked_rect({tile.x, tile.y, tile.width, tile.height}, frame_.width, frame_.height) ||
            u64(tile.width) * tile.height * 4 != tile.source_length ||
            tile.source_length != header.payload_length - sizeof(tile_payload) ||
            tile.source_offset != u64(tile.y) * frame_.stride + u64(tile.x) * 4 ||
            u64(tile.y + tile.height - 1) * frame_.stride + u64(tile.x + tile.width) * 4 > frame_.bytes ||
            u64(tile.width) * 4 > frame_.stride) break;
        result = service_->write_tile(session_, object, tile, payload + sizeof(tile), tile.source_length)
            ? 0 : static_cast<i64>(dispatch_result::denied);
        break;
    }
    case message_type::commit_frame: {
        if (!object.valid() || !frame_.active || frame_.window != object ||
            header.payload_length < sizeof(commit_payload)) break;
        commit_payload commit{};
        copy_bytes(&commit, payload, sizeof(commit));
        const u64 expected = sizeof(commit_payload) + u64(commit.dirty_rect_count) * sizeof(dirty_rect);
        if (commit.frame_serial != frame_.serial || commit.dirty_rect_count > max_dirty_rects ||
            expected != header.payload_length) break;
        bool valid = true;
        for (u32 i = 0; i < commit.dirty_rect_count; ++i) {
            dirty_rect rect{};
            copy_bytes(&rect, payload + sizeof(commit) + i * sizeof(rect), sizeof(rect));
            valid &= checked_rect(rect, frame_.width, frame_.height);
        }
        if (valid && service_->accept_frame(session_, object, commit.frame_serial)) {
            result = 0;
            frame_ = {};
        } else {
            result = static_cast<i64>(dispatch_result::denied);
        }
        break;
    }
    case message_type::cancel_frame:
        if (!object.valid() || !empty_payload(header, request_size) ||
            !frame_.active || frame_.window != object) break;
        frame_ = {};
        result = 0;
        break;
    case message_type::close_request:
        if (!object.valid() || !payload_is<close_payload>(header, request_size)) break;
        result = 0;
        break;
    default:
        result = static_cast<i64>(dispatch_result::unsupported);
        break;
    }
    last_sequence_ = header.sequence;
    return write_status(header, object, result, response, response_capacity, response_size);
}

void protocol_dispatcher::transport_closed() {
    if (session_.value != 0) (void)service_->disconnect(session_);
    session_ = {};
    frame_ = {};
}

} // namespace xos::interactium
