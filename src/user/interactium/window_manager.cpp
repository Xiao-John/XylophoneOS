// SPDX-License-Identifier: Apache-2.0
#include "window_manager.hpp"

namespace xos::interactium {

window_state* window_manager::find_mut(window_id id) {
    for (auto& window : windows_) {
        if (window.id == id) return &window;
    }
    return nullptr;
}

const window_state* window_manager::find(window_id id) const {
    for (const auto& window : windows_) {
        if (window.id == id) return &window;
    }
    return nullptr;
}

window_id window_manager::create(u64 owner, const create_window_payload& request) {
    if (owner == 0 || request.width == 0 || request.height == 0 ||
        request.width > 800 || request.height > 600 ||
        request.role > window_role::overlay || request.reserved != 0) return {};
    for (auto& window : windows_) {
        if (!window.id.valid()) {
            window = {};
            window.id = {next_id_++};
            if (window.id.value == 0) window.id = {next_id_++};
            window.owner = owner;
            window.x = request.x;
            window.y = request.y;
            window.width = request.width;
            window.height = request.height;
            window.z_order = next_z_++;
            window.flags = static_cast<u32>(request.role);
            window.visible = true;
            return window.id;
        }
    }
    return {};
}

bool window_manager::destroy(window_id id, u64 owner) {
    auto* window = find_mut(id);
    if (!window || window->owner != owner) return false;
    if (focused_ == id) focused_ = {};
    *window = {};
    return true;
}

bool window_manager::configure(window_id id, u64 owner, const configure_payload& request) {
    auto* window = find_mut(id);
    if (!window || window->owner != owner || request.width == 0 || request.height == 0 ||
        request.width > 800 || request.height > 600 || request.reserved != 0) return false;
    window->x = request.x;
    window->y = request.y;
    window->width = request.width;
    window->height = request.height;
    window->flags = request.flags;
    return true;
}

bool window_manager::set_visible(window_id id, u64 owner, bool visible) {
    auto* window = find_mut(id);
    if (!window || window->owner != owner) return false;
    window->visible = visible;
    if (!visible && focused_ == id) focused_ = {};
    return true;
}

bool window_manager::raise_and_focus(window_id id, u64 owner) {
    auto* window = find_mut(id);
    if (!window || window->owner != owner || !window->visible) return false;
    for (auto& candidate : windows_) candidate.focused = false;
    window->z_order = next_z_++;
    window->focused = true;
    focused_ = id;
    return true;
}

bool window_manager::accept_frame(window_id id, u64 owner, u64 frame_serial) {
    auto* window = find_mut(id);
    if (!window || window->owner != owner || frame_serial <= window->accepted_frame) return false;
    window->accepted_frame = frame_serial;
    return true;
}

u32 window_manager::destroy_owner(u64 owner) {
    if (owner == 0) return 0;
    u32 count = 0;
    for (auto& window : windows_) {
        if (window.id.valid() && window.owner == owner) {
            if (focused_ == window.id) focused_ = {};
            window = {};
            ++count;
        }
    }
    return count;
}

const window_state* window_manager::at(u32 index) const {
    return index < max_windows_per_session ? &windows_[index] : nullptr;
}

hit_result window_manager::hit_test(i32 x, i32 y) const {
    const window_state* best = nullptr;
    for (const auto& window : windows_) {
        if (!window.id.valid() || !window.visible || x < window.x || y < window.y ||
            static_cast<i64>(x) >= static_cast<i64>(window.x) + window.width ||
            static_cast<i64>(y) >= static_cast<i64>(window.y) + window.height) continue;
        if (!best || window.z_order > best->z_order) best = &window;
    }
    if (!best) return {};
    return {best->id, x - best->x, y - best->y};
}

u32 compositor::rebuild() {
    count_ = 0;
    for (u32 i = 0; i < max_windows_per_session; ++i) {
        const auto* window = manager_->at(i);
        if (!window || !window->id.valid() || !window->visible) continue;
        u32 position = count_;
        while (position != 0 && items_[position - 1].z_order > window->z_order) {
            items_[position] = items_[position - 1];
            --position;
        }
        items_[position] = {window->id, window->z_order};
        ++count_;
    }
    return count_;
}

bool compositor::compose(const window_manager& manager, const surface_view* surfaces,
                         u32 surface_count, u32* destination, u32 width, u32 height,
                         u32 background) {
    if (!destination || width == 0 || height == 0 || width > 800 || height > 600 ||
        width > 0xffffffffu / height) return false;
    for (u64 i = 0; i < u64(width) * height; ++i) destination[i] = background & 0x00ffffffu;
    rebuild();
    for (u32 layer = 0; layer < count_; ++layer) {
        const auto* window = manager.get(items_[layer].id);
        if (!window) continue;
        const surface_view* surface = nullptr;
        for (u32 i = 0; i < surface_count; ++i) {
            if (surfaces[i].id == window->id) { surface = &surfaces[i]; break; }
        }
        if (!surface || !surface->pixels || surface->width != window->width ||
            surface->height != window->height || surface->stride < surface->width * 4u) return false;

        const i64 left = window->x < 0 ? 0 : window->x;
        const i64 top = window->y < 0 ? 0 : window->y;
        const i64 right = static_cast<i64>(window->x) + window->width > width
                              ? width : static_cast<i64>(window->x) + window->width;
        const i64 bottom = static_cast<i64>(window->y) + window->height > height
                               ? height : static_cast<i64>(window->y) + window->height;
        for (i64 y = top; y < bottom; ++y) {
            const u64 source_row = u64(y - window->y) * (surface->stride / 4u);
            const u64 destination_row = u64(y) * width;
            for (i64 x = left; x < right; ++x) {
                const u32 source = surface->pixels[source_row + u64(x - window->x)];
                const u32 alpha = source >> 24;
                const u32 inverse = 255u - alpha;
                const u32 target = destination[destination_row + u64(x)];
                const u32 red = ((source >> 16) & 255u) + ((((target >> 16) & 255u) * inverse + 127u) / 255u);
                const u32 green = ((source >> 8) & 255u) + ((((target >> 8) & 255u) * inverse + 127u) / 255u);
                const u32 blue = (source & 255u) + (((target & 255u) * inverse + 127u) / 255u);
                destination[destination_row + u64(x)] =
                    (red > 255u ? 255u : red) << 16 |
                    (green > 255u ? 255u : green) << 8 |
                    (blue > 255u ? 255u : blue);
            }
        }
    }
    return true;
}

} // namespace xos::interactium
