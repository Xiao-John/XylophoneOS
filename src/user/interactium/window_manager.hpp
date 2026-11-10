// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/interactium_abi.hpp>

namespace xos::interactium {

// Client sessions the service accepts. The shared window table covers every
// session slot times the per-session window quota from the protocol ABI.
inline constexpr u32 max_sessions = 4;
inline constexpr u32 window_table_capacity = max_sessions * max_windows_per_session;

struct window_id {
    u64 value = 0;
    constexpr bool valid() const { return value != 0; }
    constexpr bool operator==(window_id other) const { return value == other.value; }
    constexpr bool operator!=(window_id other) const { return value != other.value; }
};

struct window_state {
    window_id id{};
    u64 owner = 0;
    i32 x = 0;
    i32 y = 0;
    u32 width = 0;
    u32 height = 0;
    u32 flags = 0;
    u32 z_order = 0;
    u64 accepted_frame = 0;
    bool visible = false;
    bool focused = false;
};

struct hit_result {
    window_id id{};
    i32 local_x = 0;
    i32 local_y = 0;
};

// Fixed-capacity registry for the first service profile. It keeps policy and
// identity separate from pixel storage, so the transport can evolve later.
// Slots are shared by all sessions, but create() enforces the per-session
// window quota, so one client cannot starve the others.
class window_manager {
    window_state windows_[window_table_capacity]{};
    u64 next_id_ = 1;
    u32 next_z_ = 1;
    window_id focused_{};

    window_state* find_mut(window_id id);
    const window_state* find(window_id id) const;
    void refocus_top();

public:
    window_id create(u64 owner, const create_window_payload& request);
    bool destroy(window_id id, u64 owner);
    bool configure(window_id id, u64 owner, const configure_payload& request);
    bool set_visible(window_id id, u64 owner, bool visible);
    bool raise_and_focus(window_id id, u64 owner);
    bool accept_frame(window_id id, u64 owner, u64 frame_serial);
    u32 destroy_owner(u64 owner);
    hit_result hit_test(i32 x, i32 y) const;
    const window_state* at(u32 index) const;
    const window_state* get(window_id id) const { return find(id); }
    window_id focused() const { return focused_; }
};

struct composition_item { window_id id{}; u32 z_order = 0; };

struct surface_view {
    window_id id{};
    const u32* pixels = nullptr;
    u32 width = 0;
    u32 height = 0;
    u32 stride = 0;
};

// The compositor stage currently produces an ordered list. Pixel blending and
// Display Service submission are intentionally separate from window policy.
class compositor {
    window_manager* manager_ = nullptr;
    composition_item items_[window_table_capacity]{};
    u32 count_ = 0;

public:
    explicit compositor(window_manager& manager) : manager_(&manager) {}
    u32 rebuild();
    bool compose(const class window_manager& manager, const struct surface_view* surfaces,
                 u32 surface_count, u32* destination, u32 width, u32 height,
                 u32 background);
    u32 count() const { return count_; }
    const composition_item* items() const { return items_; }
};

} // namespace xos::interactium
