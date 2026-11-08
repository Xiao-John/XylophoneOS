// SPDX-License-Identifier: Apache-2.0
#include "service.hpp"

namespace xos::interactium {

const service::session* service::find(session_token token) const {
    for (const auto& item : sessions_) if (item.token.value == token.value && token.value != 0) return &item;
    return nullptr;
}

service::session* service::find(session_token token) {
    for (auto& item : sessions_) if (item.token.value == token.value && token.value != 0) return &item;
    return nullptr;
}

session_token service::connect(u64 owner) {
    if (owner == 0) return {};
    for (const auto& item : sessions_) if (item.owner == owner) return {};
    for (auto& item : sessions_) {
        if (item.token.value == 0) {
            item.owner = owner;
            item.token = {next_session_++};
            if (item.token.value == 0) item.token = {next_session_++};
            return item.token;
        }
    }
    return {};
}

bool service::disconnect(session_token token) {
    auto* item = find(token);
    if (!item) return false;
    manager_.destroy_owner(item->owner);
    if (surfaces_) {
        for (u32 i = 0; i < surface_capacity; ++i) {
            if (surfaces_[i].id.valid() && !manager_.get(surfaces_[i].id)) surfaces_[i] = {};
        }
    }
    *item = {};
    damaged_ = true;
    return true;
}

window_id service::create_window(session_token token, const create_window_payload& request) {
    const auto* item = find(token);
    if (!item) return {};
    const auto id = manager_.create(item->owner, request);
    if (!id.valid()) return {};
    if (surfaces_) {
        surface_buffer* slot = nullptr;
        for (u32 i = 0; i < surface_capacity; ++i) {
            if (!surfaces_[i].id.valid()) { slot = &surfaces_[i]; break; }
        }
        if (!slot) { (void)manager_.destroy(id, item->owner); return {}; }
        slot->id = id;
        for (u32 i = 0; i < surface_pixels; ++i) slot->pixels[i] = 0xff101820;
    }
    (void)manager_.raise_and_focus(id, item->owner);
    damaged_ = true;
    return id;
}

bool service::destroy_window(session_token token, window_id id) {
    const auto* item = find(token);
    if (!item || !manager_.destroy(id, item->owner)) return false;
    if (surfaces_) for (u32 i = 0; i < surface_capacity; ++i)
        if (surfaces_[i].id == id) surfaces_[i] = {};
    damaged_ = true;
    return true;
}

bool service::configure_window(session_token token, window_id id, const configure_payload& request) {
    const auto* item = find(token);
    if (!item || !manager_.configure(id, item->owner, request)) return false;
    (void)manager_.set_visible(id, item->owner, (request.flags & flag_visible) != 0);
    damaged_ = true;
    return true;
}

bool service::focus_window(session_token token, window_id id) {
    const auto* item = find(token);
    if (!item || !manager_.raise_and_focus(id, item->owner)) return false;
    damaged_ = true;
    return true;
}

bool service::accept_frame(session_token token, window_id id, u64 frame_serial) {
    const auto* item = find(token);
    if (!item || !manager_.accept_frame(id, item->owner, frame_serial)) return false;
    if (surfaces_) for (u32 i = 0; i < surface_capacity; ++i)
        if (surfaces_[i].id == id)
            for (u32 p = 0; p < surface_pixels; ++p) surfaces_[i].pixels[p] = surfaces_[i].pending_pixels[p];
    damaged_ = true;
    return true;
}

bool service::begin_frame(session_token token, window_id id) {
    const auto* item = find(token);
    const auto* window = manager_.get(id);
    if (!item || !window || window->owner != item->owner || !surfaces_) return false;
    for (u32 i = 0; i < surface_capacity; ++i) {
        if (surfaces_[i].id != id) continue;
        for (u32 p = 0; p < surface_pixels; ++p) surfaces_[i].pending_pixels[p] = surfaces_[i].pixels[p];
        return true;
    }
    return false;
}

bool service::write_tile(session_token token, window_id id, const tile_payload& tile,
                         const u8* pixels, u32 length) {
    const auto* owner_session = find(token);
    const auto* window = manager_.get(id);
    if (!owner_session || !window || window->owner != owner_session->owner || !surfaces_ || !pixels ||
        tile.width == 0 || tile.height == 0 || tile.x > window->width || tile.y > window->height ||
        tile.width > window->width - tile.x || tile.height > window->height - tile.y ||
        u64(tile.width) * tile.height * 4 != length) return false;
    surface_buffer* surface = nullptr;
    for (u32 i = 0; i < surface_capacity; ++i)
        if (surfaces_[i].id == id) { surface = &surfaces_[i]; break; }
    if (!surface) return false;
    for (u32 row = 0; row < tile.height; ++row) {
        for (u32 column = 0; column < tile.width; ++column) {
            const u32 source = (row * tile.width + column) * 4;
            const u32 pixel = u32(pixels[source]) | (u32(pixels[source + 1]) << 8) |
                              (u32(pixels[source + 2]) << 16) | (u32(pixels[source + 3]) << 24);
            surface->pending_pixels[(tile.y + row) * surface_stride + tile.x + column] = pixel;
        }
    }
    return true;
}

bool service::queue_input(const display_event& source) {
    window_id target{};
    if (source.kind == 3) {
        const auto hit = manager_.hit_test(source.x, source.y);
        target = hit.id.valid() ? hit.id : manager_.focused();
        const bool pressed = (source.buttons & 1u) != 0;
        if (pressed && (mouse_buttons_ & 1u) == 0 && hit.id.valid()) {
            const auto* window = manager_.get(hit.id);
            if (window && manager_.raise_and_focus(hit.id, window->owner)) damaged_ = true;
        }
        mouse_buttons_ = source.buttons;
    } else {
        target = manager_.focused();
        if (source.kind == 4) mouse_buttons_ = source.buttons;
    }
    const auto* window = manager_.get(target);
    if (!window) return false;
    input_payload payload{};
    payload.input_sequence = source.sequence;
    payload.kind = source.kind == 1 ? input_kind::key_press :
                   source.kind == 2 ? input_kind::key_release :
                   source.kind == 3 ? input_kind::pointer : input_kind::resync;
    payload.code = source.code;
    payload.modifiers = source.modifiers;
    payload.buttons = source.buttons;
    payload.x = source.x;
    payload.y = source.y;
    payload.dx = source.dx;
    payload.dy = source.dy;
    payload.lost = source.lost;
    if (input_count_ == display_event_capacity) {
        inputs_[input_head_] = {};
        input_head_ = (input_head_ + 1) % display_event_capacity;
        --input_count_;
    }
    const u32 tail = (input_head_ + input_count_) % display_event_capacity;
    inputs_[tail] = {target, payload, true};
    ++input_count_;
    return true;
}

bool service::take_input(session_token token, window_id target, input_payload& event) {
    const auto* owner_session = find(token);
    const auto* target_window = manager_.get(target);
    if (!owner_session || !target_window || target_window->owner != owner_session->owner) return false;
    for (u32 offset = 0; offset < input_count_; ++offset) {
        const u32 index = (input_head_ + offset) % display_event_capacity;
        if (!inputs_[index].ready || inputs_[index].target != target) continue;
        event = inputs_[index].payload;
        for (u32 move = offset; move + 1 < input_count_; ++move) {
            const u32 destination = (input_head_ + move) % display_event_capacity;
            const u32 next = (input_head_ + move + 1) % display_event_capacity;
            inputs_[destination] = inputs_[next];
        }
        const u32 tail = (input_head_ + input_count_ - 1) % display_event_capacity;
        inputs_[tail] = {};
        --input_count_;
        return true;
    }
    return false;
}

bool service::compose(u32* destination, u32 width, u32 height, u32 background) {
    if (!surfaces_) return false;
    surface_view views[surface_capacity]{};
    u32 count = 0;
    for (u32 i = 0; i < surface_capacity; ++i) {
        const auto* window = manager_.get(surfaces_[i].id);
        if (!window) continue;
        views[count++] = {window->id, surfaces_[i].pixels, window->width, window->height,
                          surface_stride * 4};
    }
    return compositor_.compose(manager_, views, count, destination, width, height, background);
}

} // namespace xos::interactium
