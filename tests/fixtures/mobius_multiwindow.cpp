// SPDX-License-Identifier: Apache-2.0
#include <xos/interactium_client.hpp>
#ifdef XOS_THREADED_RUNTIME
#include <errno.h>
#include <pthread.h>
#endif

namespace {
using namespace xos;
using namespace xos::interactium;

u64 now() { return u64(sdk::syscall(sys_clock_monotonic)); }
u64 deadline() { return now() + 5000000000ull; }
u64 number(const char* text) {
    u64 value = 0;
    if (!text || !*text) return 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9' || value > (~u64(0) - 9) / 10) return 0;
        value = value * 10 + u64(*text - '0');
    }
    return value;
}
void decimal(u64 value) {
    char text[24]{}; u32 count = 0;
    do { text[count++] = char('0' + value % 10); value /= 10; } while (value);
    while (count) (void)sdk::write(1, &text[--count], 1);
}
const char* role;
void marker(const char* message) { sdk::print(message); sdk::print(" role="); sdk::print(role); }
int failure(const char* detail, i64 code) {
    marker("MOBIUS_FAIL"); sdk::print(" case="); sdk::print(detail);
    sdk::print(" error="); if (code < 0) sdk::print("-"); decimal(u64(code < 0 ? -code : code));
    sdk::print("\n"); return 1;
}

#ifdef XOS_THREADED_RUNTIME
__thread u32 thread_local_value = 9;
void* thread_worker(void* argument) {
    if (thread_local_value != 9) sdk::exit(97);
    thread_local_value = 42; errno = 117;
    (void)sdk::syscall(sys_sleep_until, now() + 1000000u);
    if (thread_local_value != 42 || errno != 117) sdk::exit(98);
    return argument;
}
bool threading_profile_check() {
    pthread_t worker{}; void* result = nullptr;
    void* expected = reinterpret_cast<void*>(u64(47));
    errno = 19;
    if (pthread_create(&worker, nullptr, thread_worker, expected) ||
        pthread_equal(worker, pthread_self()) || pthread_join(worker, &result) ||
        result != expected || thread_local_value != 9 || errno != 19) return false;
    marker("MOBIUS_THREAD_RUNTIME_PASS"); sdk::print("\n"); return true;
}
#endif

i64 paint(client& connection, u64 object, u64 serial, u32 width, u32 height,
          dirty_rect area, u32 color, bool commit = true) {
    const u64 end = deadline();
    const frame_payload frame{serial, width, height, width * 4,
                              pixel_format::argb8888_premultiplied, u64(width) * height * 4};
    i64 result = connection.begin(object, frame, end);
    if (result) return result;
    u32 pixels[1000]{};
    for (auto& pixel : pixels) pixel = color;
    for (u32 y = area.y; y < area.y + area.height;) {
        const u32 rows = 1000 / area.width < area.y + area.height - y ?
                             1000 / area.width : area.y + area.height - y;
        const tile_payload tile{serial, area.x, y, area.width, rows,
                                 (y * width + area.x) * 4, area.width * rows * 4, 0};
        result = connection.tile(object, tile, pixels, tile.source_length, end);
        if (result) return result;
        y += rows;
    }
    return commit ? connection.commit(object, serial, end) : 0;
}

int negative(client& connection, u64 foreign) {
    if (connection.status(message_type::focus, foreign, nullptr, 0, deadline()) != -2)
        return failure("foreign_focus", 0);
    if (connection.status(message_type::destroy_window, foreign, nullptr, 0, deadline()) != -2)
        return failure("foreign_destroy", 0);
    const configure_payload configure{0, 0, 0, 64, 64, flag_visible, 0};
    if (connection.configure(foreign, configure, deadline()) != -2)
        return failure("foreign_configure", 0);
    const close_payload close{};
    if (connection.status(message_type::close_request, foreign, &close, sizeof(close), deadline()) != -2)
        return failure("foreign_close", 0);
    input_payload input{};
    if (connection.input(foreign, input, deadline()) != -2) return failure("foreign_input", 0);
    u64 object = 0;
    if (connection.create({700, 500, 64, 64, window_role::normal, 0, 0}, object, deadline()))
        return failure("create", 0);
    const frame_payload wrong_size{1, 32, 32, 128, pixel_format::argb8888_premultiplied, 4096};
    if (connection.begin(object, wrong_size, deadline()) != -1) return failure("wrong_size", 0);
    const frame_payload frame{1, 64, 64, 256, pixel_format::argb8888_premultiplied, 16384};
    if (connection.begin(object, frame, deadline())) return failure("begin", 0);
    const tile_payload tile{1, 0, 0, 1, 1, 0, 4, 0};
    const u32 bad_alpha = 0x1000ff00;
    if (connection.tile(object, tile, &bad_alpha, 4, deadline()) != -2)
        return failure("invalid_alpha", 0);
    tile_payload reserved = tile; reserved.reserved = 1;
    const u32 good_alpha = 0xff00ff00;
    if (connection.tile(object, reserved, &good_alpha, 4, deadline()) != -1)
        return failure("reserved_tile", 0);
    if (connection.configure(object, {0, 700, 500, 48, 48, flag_visible, 0}, deadline()))
        return failure("resize", 0);
    if (connection.commit(object, 1, deadline()) != -1) return failure("retired_frame", 0);
    if (connection.status(message_type::close_request, object, &close, sizeof(close), deadline()))
        return failure("close", 0);
    if (connection.status(message_type::focus, object, nullptr, 0, deadline()) != -2)
        return failure("stale_window", 0);
    marker("MOBIUS_NEGATIVE_PASS"); sdk::print(" checks=11\n"); return 0;
}
}

int application_main(int argc, const char* const* argv) {
    using namespace xos; using namespace xos::interactium;
    if (argc < 3) return 2;
    role = argv[1];
#ifdef XOS_THREADED_RUNTIME
    if (!threading_profile_check()) return failure("threading_runtime", 0);
#endif
    if (sdk::equal(role, "stall")) {
        if (sdk::ipc_name_publish("interactium")) return failure("stall_publish", 0);
        marker("MOBIUS_STALL_READY"); sdk::print("\n");
        (void)sdk::syscall(sys_sleep_until, now() + 30000000000ull); return 0;
    }
    if (sdk::equal(role, "malformed")) {
        ipc_channel channel{};
        if (sdk::ipc_name_connect("interactium", channel)) return failure("malformed_connect", 0);
        const wire_header invalid{protocol_version, sizeof(wire_header), message_type::hello,
                                  1, 1, 0, 0, 0, 0};
        const u64 began = now();
        if (sdk::ipc_send(channel.send, &invalid, sizeof(invalid))) return failure("malformed_send", 0);
        const i64 result = sdk::ipc_wait_until(channel.receive, ipc_wait_mode::receive, began + 1000000000u);
        (void)sdk::ipc_channel_close(channel.send);
        if (result >= 0 || result == thread_error_timeout || now() - began >= 1000000000u)
            return failure("malformed_revoke", result);
        marker("MOBIUS_MALFORMED_PASS"); sdk::print("\n"); return 0;
    }
    client connection;
    const u64 began = now();
    const i64 opened = connection.open(number(argv[2]), deadline());
    if (sdk::equal(role, "timeout")) {
        if (opened != thread_error_timeout || now() - began > 5500000000ull)
            return failure("original_deadline", opened);
        marker("MOBIUS_TIMEOUT_PASS"); sdk::print("\n"); return 0;
    }
    if (sdk::equal(role, "wrong-peer")) {
        if (opened == 0) return failure("wrong_peer_accepted", opened);
        marker("MOBIUS_WRONG_PEER_PASS"); sdk::print("\n"); return 0;
    }
    if (opened) return failure("open", opened);
    if (sdk::equal(role, "negative")) return argc == 4 ? negative(connection, number(argv[3])) : 2;
    const bool left = sdk::equal(role, "left");
    if (!left && !sdk::equal(role, "right")) return 2;
    i32 x = left ? 60 : 240, y = left ? 80 : 180;
    u32 width = 300, height = 220;
    const u32 color = left ? 0xff2860c0 : 0xffd06830;
    u64 object = 0, serial = 1;
    i64 result = connection.create({x, y, width, height, window_role::normal, 0, 0}, object, deadline());
    if (result) return failure("create", result);
    result = paint(connection, object, serial, width, height, {0, 0, width, height}, color);
    if (result) return failure("initial_frame", result);
    marker("MOBIUS_READY"); sdk::print(" pid="); decimal(sdk::pid());
    sdk::print(" window="); decimal(object); sdk::print("\n");
    bool staged = false;
    u64 last_sequence = 0;
    for (;;) {
        input_payload event{};
        result = connection.input(object, event, deadline());
        if (result == -3) {
            (void)sdk::syscall(sys_sleep_until, now() + 10000000u); continue;
        }
        if (result) { marker("MOBIUS_SERVICE_LOST"); sdk::print("\n"); return 0; }
        if (event.input_sequence <= last_sequence) return failure("input_sequence", 0);
        last_sequence = event.input_sequence;
        if (event.kind == input_kind::pointer) {
            if (event.buttons) {
                marker("MOBIUS_POINTER"); sdk::print(" buttons="); decimal(event.buttons); sdk::print("\n");
            }
            continue;
        }
        if (event.kind != input_kind::key_press && event.kind != input_kind::key_release) continue;
        marker(event.kind == input_kind::key_press ? "MOBIUS_KEY" : "MOBIUS_RELEASE");
        sdk::print(" code="); decimal(event.code); sdk::print("\n");
        if (event.kind != input_kind::key_press) continue;
        if (event.code == 45) {
            marker("MOBIUS_CRASH"); sdk::print("\n"); __asm__ volatile("ud2");
        }
        if (event.code == 16) {
            const close_payload close{};
            result = connection.status(message_type::close_request, object, &close, sizeof(close), deadline());
            if (result) return failure("close", result);
            marker("MOBIUS_CLOSED"); sdk::print("\n"); return 0;
        }
        if (event.code == 46 && staged) {
            result = connection.status(message_type::cancel_frame, object, nullptr, 0, deadline());
            if (result) return failure("cancel", result);
            staged = false; marker("MOBIUS_CANCELLED"); sdk::print("\n"); continue;
        }
        if (event.code == 25 && staged) {
            result = connection.commit(object, serial, deadline());
            if (result) return failure("commit", result);
            staged = false; marker("MOBIUS_COMMITTED"); sdk::print("\n"); continue;
        }
        if (staged) continue;
        if (event.code == 30 || event.code == 31) {
            result = paint(connection, object, ++serial, width, height, {80, 60, 40, 20},
                           event.code == 30 ? 0xff20c070 : 0xffc020c0, event.code == 30);
            if (result) return failure("partial_frame", result);
            staged = event.code == 31;
            marker(staged ? "MOBIUS_STAGED" : "MOBIUS_DAMAGE"); sdk::print("\n");
        } else if (event.code == 19 || event.code == 50) {
            if (event.code == 19) { width = left ? 360u : 240u; height = left ? 260u : 180u; }
            else { x = left ? 100 : 260; y = left ? 120 : 200; }
            result = connection.configure(object, {serial, x, y, width, height, flag_visible, 0}, deadline());
            if (!result) result = paint(connection, object, ++serial, width, height,
                                        {0, 0, width, height}, color);
            if (result) return failure("configure_frame", result);
            marker(event.code == 19 ? "MOBIUS_RESIZED" : "MOBIUS_MOVED"); sdk::print("\n");
        }
    }
}

#ifdef XOS_THREADED_RUNTIME
extern "C" int main(int argc, char** argv) {
    return application_main(argc, argv);
}
#else
extern "C" int xos_user_main(const xos::startup_info* startup) {
    return application_main(static_cast<int>(startup->argc),
                            reinterpret_cast<const char* const*>(startup->argv));
}
#endif
