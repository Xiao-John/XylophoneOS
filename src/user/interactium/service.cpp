// SPDX-License-Identifier: Apache-2.0
#include "service.hpp"

namespace xos::interactium {

namespace {
input_payload make_payload(const display_event& source) {
    input_payload payload{};
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
    return payload;
}
}

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
    for (u32 i = 0; i < window_table_capacity; ++i) {
        const auto* window = manager_.at(i);
        if (window && window->id.valid() && window->owner == item->owner)
            release_window(window->id, i);
    }
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
    // Slots are reused, so a new window starts with clean input bookkeeping.
    reset_window_state(id);
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
    if (!item) return false;
    const u32 slot = window_slot(id);   // resolve before the window disappears
    if (!manager_.destroy(id, item->owner)) return false;
    release_window(id, slot);
    if (surfaces_) for (u32 i = 0; i < surface_capacity; ++i)
        if (surfaces_[i].id == id) surfaces_[i] = {};
    damaged_ = true;
    return true;
}

bool service::configure_window(session_token token, window_id id, const configure_payload& request) {
    const auto* item = find(token);
    if (!item || !manager_.configure(id, item->owner, request)) return false;
    (void)manager_.set_visible(id, item->owner, (request.flags & flag_visible) != 0);
    // A hidden window cannot receive the event that proves the pointer left it.
    if ((request.flags & flag_visible) == 0 && pointer_target_ == id) pointer_target_ = {};
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
    last_modifiers_ = source.modifiers;
    window_id target{};
    if (source.kind == 4) {
        mouse_buttons_ = source.buttons;
        last_pointer_x_ = source.x;
        last_pointer_y_ = source.y;
        const auto hit = manager_.hit_test(source.x, source.y);
        pointer_target_ = hit.id.valid() ? hit.id : manager_.focused();
        for (auto& key : pressed_) key = {};
        // The display queue may have lost a release owned by any window.
        bool queued = false;
        for (u32 i = 0; i < window_table_capacity; ++i) {
            const auto* window = manager_.at(i);
            if (!window->id.valid()) continue;
            display_event sync = source;
            sync.buttons = window->id == pointer_target_ ? mouse_buttons_ : 0;
            queued |= enqueue_event(window->id, sync);
        }
        return queued;
    }
    if (source.kind == 3) {
        const auto hit = manager_.hit_test(source.x, source.y);
        target = hit.id.valid() ? hit.id : manager_.focused();
        const bool pressed = (source.buttons & 1u) != 0;
        if (pressed && (mouse_buttons_ & 1u) == 0 && hit.id.valid()) {
            const auto* window = manager_.get(hit.id);
            if (window && manager_.raise_and_focus(hit.id, window->owner)) damaged_ = true;
        }
        mouse_buttons_ = source.buttons;
        last_pointer_x_ = source.x;
        last_pointer_y_ = source.y;
        // One event is routed to one window, so the previous hit window never
        // sees the coordinates that prove the pointer left it.
        if (pointer_target_.valid() && pointer_target_ != target)
            send_pointer_leave(source, pointer_target_);
        pointer_target_ = target;
    } else {
        target = manager_.focused();
        if (source.kind == 1) {
            target = note_key_press(target, source.code);
        } else if (source.kind == 2) {
            const window_id pressed_at = take_press_target(source.code);
            // A release belongs to the window that took the press. When that
            // window is gone the release is dropped rather than leaked into the
            // window that inherited focus.
            if (pressed_at.valid()) {
                if (!manager_.get(pressed_at)) return false;
                target = pressed_at;
            }
        }
    }
    return enqueue_event(target, source);
}

bool service::enqueue_event(window_id target, const display_event& source) {
    if (!manager_.get(target)) return false;
    const u32 slot = window_slot(target);
    // Report earlier drops for this window before delivering new input: the
    // resync tells the client how much input it missed and lets it drop held
    // key state, matching the display queue's own kind=4 recovery event. Only
    // synthesize when it fits for free - under sustained pressure a resync per
    // event would crowd out the very input it explains, so the count stays
    // pending until the client drains some room.
    if (slot < window_table_capacity && pending_lost_[slot] != 0 &&
        input_count_ < display_event_capacity) {
        const u32 lost = pending_lost_[slot];
        pending_lost_[slot] = 0;
        (void)put_input(target, make_resync(lost, target));
    }
    input_payload payload = make_payload(source);
    payload.input_sequence = assign_sequence(target, source.sequence);
    return put_input(target, payload);
}

// Resync payloads reuse the pointer branch of the client, so they carry the
// last known pointer state instead of zeros to avoid fake enter/leave events.
input_payload service::make_resync(u32 lost, window_id target) {
    input_payload sync{};
    sync.kind = input_kind::resync;
    sync.lost = lost;
    sync.x = last_pointer_x_;
    sync.y = last_pointer_y_;
    sync.modifiers = last_modifiers_;
    sync.buttons = pointer_target_ == target ? mouse_buttons_ : 0;
    sync.input_sequence = assign_sequence(target, 1);
    return sync;
}

// Clients learn about drops as soon as they drain their queue, even when no
// further input arrives for the affected window.
void service::flush_pending_resyncs() {
    for (u32 slot = 0; slot < window_table_capacity && input_count_ < display_event_capacity; ++slot) {
        if (pending_lost_[slot] == 0) continue;
        const auto* window = manager_.at(slot);
        if (!window || !window->id.valid()) { pending_lost_[slot] = 0; continue; }
        const u32 lost = pending_lost_[slot];
        pending_lost_[slot] = 0;
        (void)put_input(window->id, make_resync(lost, window->id));
    }
}

u32 service::window_slot(window_id id) const {
    if (!id.valid()) return window_table_capacity;
    for (u32 i = 0; i < window_table_capacity; ++i) {
        const auto* window = manager_.at(i);
        if (window && window->id == id) return i;
    }
    return window_table_capacity;
}

// Input sequences stay strictly increasing per window even when the router
// injects a synthetic event between two display events.
u64 service::assign_sequence(window_id target, u64 preferred) {
    const u32 slot = window_slot(target);
    if (slot >= window_table_capacity) return preferred;
    const u64 assigned = next_sequence_[slot] > preferred ? next_sequence_[slot] : preferred;
    next_sequence_[slot] = assigned + 1;
    return assigned;
}

void service::record_loss(window_id target, u32 count) {
    const u32 slot = window_slot(target);
    if (slot >= window_table_capacity) return;   // window gone: nobody to notify
    const u32 current = pending_lost_[slot];
    pending_lost_[slot] = current > 0xffffffffu - count ? 0xffffffffu : current + count;
}

void service::evict_oldest() {
    if (input_count_ == 0) return;
    const queued_input evicted = inputs_[input_head_];
    inputs_[input_head_] = {};
    input_head_ = (input_head_ + 1) % display_event_capacity;
    --input_count_;
    if (!evicted.ready) return;
    // A dropped resync only means the report has to be regenerated; counting
    // it as a lost event would inflate the number the client eventually sees.
    const u32 carried = evicted.payload.lost;
    const u32 count = evicted.payload.kind == input_kind::resync ? carried : carried + 1;
    if (count != 0) record_loss(evicted.target, count);
}

bool service::put_input(window_id target, const input_payload& payload) {
    if (input_count_ == display_event_capacity) evict_oldest();
    const u32 tail = (input_head_ + input_count_) % display_event_capacity;
    inputs_[tail] = {target, payload, true};
    ++input_count_;
    return true;
}

void service::purge_input(window_id target) {
    if (!target.valid() || input_count_ == 0) return;
    u32 count = 0;
    for (u32 offset = 0; offset < input_count_; ++offset) {
        const u32 index = (input_head_ + offset) % display_event_capacity;
        if (inputs_[index].ready && inputs_[index].target == target) continue;
        const u32 tail = (input_head_ + count) % display_event_capacity;
        if (tail != index) inputs_[tail] = inputs_[index];
        ++count;
    }
    for (u32 i = count; i < input_count_; ++i)
        inputs_[(input_head_ + i) % display_event_capacity] = {};
    input_count_ = count;
}

void service::reset_window_state(window_id id) {
    const u32 slot = window_slot(id);
    if (slot >= window_table_capacity) return;
    pending_lost_[slot] = 0;
    next_sequence_[slot] = 0;
}

// Called right after a window disappears: its queued input can never be
// delivered, and its slot may be reused by the next window. Pressed-key
// entries are kept so a later release is dropped instead of falling through
// to the window that inherited focus.
void service::release_window(window_id id, u32 slot) {
    if (pointer_target_ == id) pointer_target_ = {};
    purge_input(id);
    if (slot < window_table_capacity) {
        pending_lost_[slot] = 0;
        next_sequence_[slot] = 0;
    }
}

window_id service::note_key_press(window_id target, u32 code) {
    if (!target.valid()) return {};
    // PS/2 auto-repeat belongs to the original press until its release.
    for (auto& item : pressed_)
        if (item.used && item.code == code) return item.target;
    for (auto& item : pressed_)
        if (!item.used) { item = {code, target, true}; return target; }
    // More keys held than tracked slots: recycle the oldest entry.
    pressed_[pressed_next_] = {code, target, true};
    pressed_next_ = (pressed_next_ + 1) % pressed_key_capacity;
    return target;
}

window_id service::take_press_target(u32 code) {
    for (auto& item : pressed_) {
        if (!item.used || item.code != code) continue;
        const window_id target = item.target;
        item = {};
        return target;
    }
    return {};
}

void service::send_pointer_leave(const display_event& source, window_id old_target) {
    const auto* old_window = manager_.get(old_target);
    if (!old_window || !old_window->visible) return;   // destroyed or hidden: no recipient
    display_event leave = source;
    const i64 right = static_cast<i64>(old_window->x) + old_window->width;
    const i64 bottom = static_cast<i64>(old_window->y) + old_window->height;
    if (leave.x >= old_window->x && leave.y >= old_window->y &&
        static_cast<i64>(leave.x) < right && static_cast<i64>(leave.y) < bottom) {
        // Overlapping windows still contain the pointer, so shift the copy just
        // outside the previous window: that coordinate is what tells the client
        // the pointer left.
        if (old_window->x > -2147483647) leave.x = old_window->x - 1;
        else if (old_window->y > -2147483647) leave.y = old_window->y - 1;
    }
    (void)enqueue_event(old_target, leave);
}

bool service::take_input(session_token token, window_id target, input_payload& event) {
    const auto* owner_session = find(token);
    const auto* target_window = manager_.get(target);
    if (!owner_session || !target_window || target_window->owner != owner_session->owner) return false;
    flush_pending_resyncs();
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
