// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "window_manager.hpp"
#include <xos/display_abi.hpp>

namespace xos::interactium {

// Pixel storage is a separate first-version rendering budget from the window
// quota: only this many windows hold drawable surfaces at once.
inline constexpr u32 surface_capacity = max_windows_per_session;
inline constexpr u32 surface_stride = 800;
inline constexpr u32 surface_pixels = surface_stride * 600;
inline constexpr u32 pressed_key_capacity = 16;

struct surface_buffer {
    window_id id{};
    u32 pixels[surface_pixels]{};
    u32 pending_pixels[surface_pixels]{};
};

struct session_token { u64 value = 0; };

// Policy shell for the future endpoint loop. It authenticates every operation
// against an owner-bound session before forwarding it to the window model.
class service {
    struct session { session_token token{}; u64 owner = 0; };
    session sessions_[max_sessions]{};
    u64 next_session_ = 1;
    window_manager manager_{};
    compositor compositor_;
    surface_buffer* surfaces_ = nullptr;
    struct queued_input { window_id target{}; input_payload payload{}; bool ready = false; };
    queued_input inputs_[display_event_capacity]{};
    u32 input_head_ = 0;
    u32 input_count_ = 0;
    u32 mouse_buttons_ = 0;
    bool damaged_ = false;
    // Input state the router keeps so recovered or redirected events stay
    // consistent with what each client window last observed.
    window_id pointer_target_{};
    i32 last_pointer_x_ = -1000000;
    i32 last_pointer_y_ = -1000000;
    u32 last_modifiers_ = 0;
    u32 pending_lost_[window_table_capacity]{};
    u64 next_sequence_[window_table_capacity]{};
    struct pressed_key { u32 code = 0; window_id target{}; bool used = false; };
    pressed_key pressed_[pressed_key_capacity]{};
    u32 pressed_next_ = 0;

    const session* find(session_token token) const;
    session* find(session_token token);
    u32 window_slot(window_id id) const;
    u64 assign_sequence(window_id target, u64 preferred);
    void record_loss(window_id target, u32 count);
    void evict_oldest();
    bool put_input(window_id target, const input_payload& payload);
    bool enqueue_event(window_id target, const display_event& source);
    input_payload make_resync(u32 lost, window_id target);
    void flush_pending_resyncs();
    void purge_input(window_id target);
    void reset_window_state(window_id id);
    void release_window(window_id id, u32 slot);
    window_id note_key_press(window_id target, u32 code);
    window_id take_press_target(u32 code);
    void send_pointer_leave(const display_event& source, window_id old_target);

public:
    explicit service(surface_buffer* surfaces = nullptr) : compositor_(manager_), surfaces_(surfaces) {}

    session_token connect(u64 owner);
    bool disconnect(session_token token);
    window_id create_window(session_token token, const create_window_payload& request);
    bool destroy_window(session_token token, window_id id);
    bool configure_window(session_token token, window_id id, const configure_payload& request);
    bool focus_window(session_token token, window_id id);
    bool accept_frame(session_token token, window_id id, u64 frame_serial);
    bool begin_frame(session_token token, window_id id);
    bool write_tile(session_token token, window_id id, const tile_payload& tile,
                    const u8* pixels, u32 length);
    bool queue_input(const display_event& event);
    bool take_input(session_token token, window_id target, input_payload& event);
    bool take_damage() { const bool result = damaged_; damaged_ = false; return result; }
    hit_result hit_test(i32 x, i32 y) const { return manager_.hit_test(x, y); }
    const window_state* window_at(u32 index) const { return manager_.at(index); }
    const window_state* get_window(window_id id) const { return manager_.get(id); }
    bool compose(const surface_view* surfaces, u32 surface_count, u32* destination,
                 u32 width, u32 height, u32 background) {
        return compositor_.compose(manager_, surfaces, surface_count, destination,
                                   width, height, background);
    }
    bool compose(u32* destination, u32 width, u32 height, u32 background);
    u32 rebuild() { return compositor_.rebuild(); }
    const composition_item* composition() const { return compositor_.items(); }
};

} // namespace xos::interactium
