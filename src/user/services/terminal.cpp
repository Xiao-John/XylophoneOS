// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/channel_io.hpp>
#include <xos/thread_core.hpp>
#include <xos/terminal_abi.hpp>
#include "../drivers/uart_16550.hpp"

namespace {
using namespace xos;
user::uart::driver device;
u32 lock_word, stopping, input_ready, request_pending;
i64 worker_error;
u64 device_irq_token;
u32 control_incoming, control_outgoing;
terminal::request pending_request;
struct application_session { u32 incoming, outgoing; u64 peer; };
// The initial supervisor-attached application occupies slot zero. Additional
// slots are reserved for authenticated descendants; they are not enabled yet.
constexpr u32 max_app_sessions = 3;
application_session apps[max_app_sessions];
u32 app_pending, app_dead;
u64 app_thread, controller_pid;
terminal::request pending_app_request;
terminal::mode app_mode = terminal::default_mode;
void lock();
void unlock();

void fail_worker(i64 error) {
    lock();
    __atomic_store_n(&worker_error, error == 0 ? process_error_state : error, __ATOMIC_RELEASE);
    __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE);
    unlock();
    (void)thread::wake(&input_ready, 1);
    // Wake both the request loop and a controller waiting for a response. A
    // response already sent may have been observed; this is not a rollback.
    (void)sdk::channel_close(control_incoming);
    (void)sdk::channel_close(control_outgoing);
}

void lock() {
    while (__atomic_exchange_n(&lock_word, 1u, __ATOMIC_ACQUIRE) != 0) {
        (void)thread::wait(&lock_word, 1);
    }
}
void unlock() {
    __atomic_store_n(&lock_word, 0u, __ATOMIC_RELEASE);
    (void)thread::wake(&lock_word, 1);
}
u64 receive_worker(void*) {
    while (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0) {
        const i64 event = sdk::irq_event(irq_event_action::wait, device_irq_token, thread_deadline_infinite);
        if (event <= 0) {
            if (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0) fail_worker(event);
            return 0;
        }
        lock();
        const i64 result = device.service_irq(static_cast<u64>(event));
        __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE);
        unlock();
        (void)thread::wake(&input_ready, 1);
        if (result != 0) { fail_worker(result); return 0; }
    }
    return 0;
}

i64 read_until(u8* output, u32 length, u64 deadline) {
    for (;;) {
        lock();
        const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
        const i64 result = error != 0 ? error :
            length != 0 && (__atomic_load_n(&request_pending, __ATOMIC_ACQUIRE) != 0 ||
                            __atomic_load_n(&app_pending, __ATOMIC_ACQUIRE) != 0 ||
                            __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0) ? terminal::interrupted :
            device.read(output, length);
        if (result != 0 || length == 0) { unlock(); return result; }
        // Reset while holding the same lock used by the IRQ worker. If the
        // worker runs before wait registers, the value comparison prevents sleep.
        __atomic_store_n(&input_ready, 0u, __ATOMIC_RELEASE);
        unlock();
        const i64 waited = thread::wait(&input_ready, 0, deadline);
        if (waited != 0 && waited != thread_value_changed) return waited;
    }
}

i64 wait_readable(u64 deadline) {
    for (;;) {
        lock();
        const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
        const i64 result = error != 0 ? error :
            (__atomic_load_n(&request_pending, __ATOMIC_ACQUIRE) != 0 ||
             __atomic_load_n(&app_pending, __ATOMIC_ACQUIRE) != 0 ||
             __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0) ? terminal::interrupted : device.readable();
        if (result != 0) { unlock(); return result; }
        __atomic_store_n(&input_ready, 0u, __ATOMIC_RELEASE);
        unlock();
        const i64 waited = thread::wait(&input_ready, 0, deadline);
        if (waited != 0 && waited != thread_value_changed) return waited;
    }
}

i64 write_until(const u8* input, u32 length, u64 deadline) {
    for (;;) {
        lock();
        const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
        const i64 result = error != 0 ? error :
            length != 0 && (__atomic_load_n(&request_pending, __ATOMIC_ACQUIRE) != 0 ||
                            __atomic_load_n(&app_pending, __ATOMIC_ACQUIRE) != 0 ||
                            __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0) ? terminal::interrupted :
            device.write(input, length);
        if (result != 0 || length == 0) { unlock(); return result; }
        __atomic_store_n(&input_ready, 0u, __ATOMIC_RELEASE);
        const i64 armed = device.arm_write();
        unlock();
        if (armed != 0) return armed;
        const i64 waited = thread::wait(&input_ready, 0, deadline);
        if (waited != 0 && waited != thread_value_changed) return waited;
    }
}

i64 read_configured(u8* output, u32 length) {
    if (app_mode.vmin == 0 && app_mode.vtime == 0) {
        lock();
        const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
        const i64 result = error != 0 ? error : device.read(output, length);
        unlock(); return result;
    }
    u64 deadline = thread_deadline_infinite;
    if (app_mode.vmin == 0) {
        const u64 now = thread::clock();
        const u64 delay = static_cast<u64>(app_mode.vtime) * 100000000ull;
        deadline = now >= thread_deadline_infinite - delay ? thread_deadline_infinite - 1 : now + delay;
    }
    const i64 result = read_until(output, length, deadline);
    return result == thread_error_timeout && app_mode.vmin == 0 ? 0 : result;
}

i64 drain_output() {
    for (;;) {
        lock();
        const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
        const bool interrupted = __atomic_load_n(&request_pending, __ATOMIC_ACQUIRE) != 0 ||
            __atomic_load_n(&app_pending, __ATOMIC_ACQUIRE) != 0 ||
            __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0;
        const i64 empty = error != 0 ? error : interrupted ? terminal::interrupted : device.transmitter_empty();
        unlock();
        if (empty < 0) return empty;
        if (empty == 1) return 0;
        // 16550 has no TEMT interrupt. Sleep for a timer tick before checking
        // again; cancellation and peer failure are observed on the next tick.
        const i64 now = sdk::syscall(sys_clock_monotonic);
        if (now < 0) return now;
        const u64 current = static_cast<u64>(now);
        if (current >= thread_deadline_infinite - thread_tick_ns) return thread_error_timeout;
        const i64 waited = thread::sleep_until(current + thread_tick_ns);
        if (waited != 0) return waited;
    }
}

u64 control_worker(void*) {
    while (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0) {
        while (__atomic_load_n(&request_pending, __ATOMIC_ACQUIRE) != 0 &&
               __atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0)
            (void)thread::wait(&request_pending, 1);
        if (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) != 0) break;
        terminal::request request{};
        const i64 received = sdk::channel_receive_wait(control_incoming, &request, sizeof(request),
                                                        thread_deadline_infinite);
        if (received != static_cast<i64>(sizeof(request))) {
            if (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0)
                fail_worker(received < 0 ? received : process_error_state);
            break;
        }
        lock();
        pending_request = request;
        __atomic_store_n(&request_pending, 1u, __ATOMIC_RELEASE);
        __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE);
        unlock();
        (void)thread::wake(&input_ready, 1);
    }
    return 0;
}

u64 app_worker(void*) {
    while (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0 &&
           __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) == 0) {
        while (__atomic_load_n(&app_pending, __ATOMIC_ACQUIRE) != 0 &&
               __atomic_load_n(&stopping, __ATOMIC_ACQUIRE) == 0 &&
               __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) == 0)
            (void)thread::wait(&app_pending, 1);
        if (__atomic_load_n(&stopping, __ATOMIC_ACQUIRE) != 0 ||
            __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0) break;
        terminal::request request{};
        const channel_wait_many_request wait{channel_version, sizeof(channel_wait_many_request),
                                             1, 0, {apps[0].incoming, 0, 0, 0}};
        const i64 ready = sdk::channel_wait_many(wait, thread_deadline_infinite);
        // A wake is only a hint, including on endpoint closure. Recheck the
        // full set before consuming; a closed endpoint fails that recheck.
        if (ready == 0) continue;
        if (ready < 0) break;
        const i64 received = sdk::ipc_recv(apps[0].incoming, &request, sizeof(request));
        if (received == sdk::ipc_error_empty) continue;
        if (received != static_cast<i64>(sizeof(request))) break;
        lock();
        pending_app_request = request;
        __atomic_store_n(&app_pending, 1u, __ATOMIC_RELEASE);
        __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE);
        unlock();
        (void)thread::wake(&input_ready, 1);
    }
    lock();
    __atomic_store_n(&app_dead, 1u, __ATOMIC_RELEASE);
    __atomic_store_n(&input_ready, 1u, __ATOMIC_RELEASE);
    unlock();
    (void)thread::wake(&input_ready, 1);
    return 0;
}

bool close_app() {
    if (app_thread == 0) return true;
    __atomic_store_n(&app_dead, 1u, __ATOMIC_RELEASE);
    (void)sdk::channel_close(apps[0].incoming);
    (void)sdk::channel_close(apps[0].outgoing);
    __atomic_store_n(&app_pending, 0u, __ATOMIC_RELEASE);
    (void)thread::wake(&app_pending, 1);
    u64 result = 0;
    const i64 joined = thread::join(app_thread, result);
    if (joined != 0) { fail_worker(joined); return false; }
    app_thread = 0; apps[0] = {};
    app_mode = terminal::default_mode;
    __atomic_store_n(&app_pending, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&app_dead, 0u, __ATOMIC_RELEASE);
    return true;
}

bool authenticated_app_channels(const terminal::session_channels& requested) {
    if (requested.incoming == 0 || requested.outgoing == 0 ||
        requested.incoming == requested.outgoing || requested.peer_pid == 0 ||
        requested.peer_pid == controller_pid) return false;
    bool incoming = false, outgoing = false;
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const i64 result = sdk::channel_get(i, info);
        if (result == thread_error_not_found) break;
        if (result != 0 || info.version != channel_version || info.size != sizeof(info)) return false;
        if (info.controller_pid != controller_pid || info.peer_pid != requested.peer_pid) continue;
        if (info.handle == requested.incoming && info.rights == channel_receive) incoming = true;
        if (info.handle == requested.outgoing && info.rights == channel_send) outgoing = true;
    }
    return incoming && outgoing;
}

bool next_request(terminal::request& request, bool& from_app) {
    for (;;) {
        lock();
        if (__atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0) { unlock(); return false; }
        if (__atomic_load_n(&request_pending, __ATOMIC_ACQUIRE) != 0) {
            request = pending_request;
            from_app = false;
            __atomic_store_n(&request_pending, 0u, __ATOMIC_RELEASE);
            unlock();
            (void)thread::wake(&request_pending, 1);
            return true;
        }
        if (__atomic_load_n(&app_pending, __ATOMIC_ACQUIRE) != 0) {
            request = pending_app_request;
            from_app = true;
            __atomic_store_n(&app_pending, 0u, __ATOMIC_RELEASE);
            unlock();
            (void)thread::wake(&app_pending, 1);
            return true;
        }
        if (__atomic_load_n(&worker_error, __ATOMIC_ACQUIRE) != 0) { unlock(); return false; }
        __atomic_store_n(&input_ready, 0u, __ATOMIC_RELEASE);
        unlock();
        const i64 waited = thread::wait(&input_ready, 0);
        if (waited != 0 && waited != thread_value_changed) return false;
    }
}

bool find_control_channels(u64 controller, u32& incoming, u32& outgoing) {
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const i64 result = sdk::channel_get(i, info);
        if (result == thread_error_not_found) break;
        if (result != 0 || info.version != channel_version || info.size != sizeof(info)) return false;
        if (info.controller_pid != controller || info.peer_pid != controller) continue;
        if (info.rights == channel_receive && incoming == 0) incoming = info.handle;
        else if (info.rights == channel_send && outgoing == 0) outgoing = info.handle;
        else return false;
    }
    return incoming != 0 && outgoing != 0;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    const i64 controller = sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1);
    if (controller <= 0 || thread::enable() != 0) return 1;
    controller_pid = static_cast<u64>(controller);
    u32 incoming = 0, outgoing = 0;
    if (!find_control_channels(static_cast<u64>(controller), incoming, outgoing)) return 2;
    control_incoming = incoming; control_outgoing = outgoing;
    if (device.start() != 0) return 3;
    device_irq_token = device.token();
    u64 worker = 0;
    if (thread::create(worker, receive_worker, nullptr) != 0) { (void)device.close(); return 4; }
    u64 control_thread = 0;
    if (thread::create(control_thread, control_worker, nullptr) != 0) {
        __atomic_store_n(&stopping, 1u, __ATOMIC_RELEASE);
        lock(); (void)device.close(); unlock();
        u64 result = 0; (void)thread::join(worker, result); return 4;
    }
    bool done = false;
    while (!done) {
        if (__atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0 && !close_app()) break;
        terminal::request request{};
        bool from_app = false;
        if (!next_request(request, from_app)) {
            if (__atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0 && close_app()) continue;
            break;
        }
        terminal::response response{};
        response.version = terminal::version; response.size = sizeof(response); response.sequence = request.sequence;
        if (request.version != terminal::version || request.size != sizeof(request) ||
            request.length > terminal::data_bytes || request.sequence == 0) {
            response.result = process_error_invalid;
        } else {
            const auto op = static_cast<terminal::operation>(request.operation);
            const bool io_op = op == terminal::operation::read || op == terminal::operation::read_until ||
                op == terminal::operation::read_mode || op == terminal::operation::wait_readable ||
                op == terminal::operation::write || op == terminal::operation::write_until;
            const bool mode_op = op == terminal::operation::mode_get || op == terminal::operation::mode_set ||
                op == terminal::operation::drain || op == terminal::operation::flush_input;
            const bool denied = (from_app && !(io_op || mode_op || op == terminal::operation::cancel)) ||
                (!from_app && mode_op) ||
                (!from_app && app_thread != 0 && io_op) ||
                (from_app && __atomic_load_n(&app_dead, __ATOMIC_ACQUIRE) != 0);
            if (denied) response.result = process_error_denied;
            else if (op == terminal::operation::mode_get) {
                if (request.length != 0) response.result = process_error_invalid;
                else {
                    const auto* bytes = reinterpret_cast<const u8*>(&app_mode);
                    for (u32 i = 0; i < sizeof(app_mode); ++i) response.data[i] = bytes[i];
                    response.length = sizeof(app_mode); response.result = 0;
                }
            } else if (op == terminal::operation::mode_set) {
                terminal::mode proposed{};
                auto* bytes = reinterpret_cast<u8*>(&proposed);
                if (request.length != sizeof(proposed) || request.deadline_ns > 2) response.result = process_error_invalid;
                else {
                    for (u32 i = 0; i < sizeof(proposed); ++i) bytes[i] = request.data[i];
                    if (!terminal::valid_mode(proposed)) response.result = thread_error_unsupported;
                    else {
                        response.result = request.deadline_ns != 0 ? drain_output() : 0;
                        if (response.result == 0 && request.deadline_ns == 2) {
                            lock(); response.result = device.flush_input(); unlock();
                        }
                        if (response.result == 0) app_mode = proposed;
                    }
                }
            } else if (op == terminal::operation::drain) {
                response.result = request.length == 0 ? drain_output() : process_error_invalid;
            } else if (op == terminal::operation::flush_input) {
                if (request.length != 0) response.result = process_error_invalid;
                else { lock(); response.result = device.flush_input(); unlock(); }
            } else if (op == terminal::operation::wait_readable) {
                response.result = request.length == 0 ? wait_readable(request.deadline_ns) : process_error_invalid;
            } else if (op == terminal::operation::read_mode) {
                response.result = read_configured(response.data, request.length);
                if (response.result > 0) response.length = static_cast<u32>(response.result);
            }
            else if (op == terminal::operation::read_until) {
                response.result = read_until(response.data, request.length, request.deadline_ns);
                if (response.result > 0) response.length = static_cast<u32>(response.result);
            }
            else if (op == terminal::operation::write_until)
                response.result = write_until(request.data, request.length, request.deadline_ns);
            else if (op == terminal::operation::attach) {
                terminal::session_channels channels{};
                auto* bytes = reinterpret_cast<u8*>(&channels);
                if (request.length != sizeof(channels)) response.result = process_error_invalid;
                else {
                    for (u32 i = 0; i < sizeof(channels); ++i) bytes[i] = request.data[i];
                    if (app_thread != 0) response.result = process_error_busy;
                    else if (!authenticated_app_channels(channels)) response.result = process_error_denied;
                    else {
                        apps[0] = {channels.incoming, channels.outgoing, channels.peer_pid};
                        __atomic_store_n(&app_dead, 0u, __ATOMIC_RELEASE);
                        response.result = thread::create(app_thread, app_worker, nullptr);
                        if (response.result != 0) { apps[0] = {}; app_thread = 0; }
                    }
                }
            } else if (op == terminal::operation::detach) {
                response.result = close_app() ? 0 : process_error_state;
            }
            lock();
            const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
            if (error != 0 && !((op == terminal::operation::read_until || op == terminal::operation::read_mode ||
                                 op == terminal::operation::write_until) && response.result > 0)) {
                response.result = error; response.length = 0;
            }
            else if (denied || mode_op || op == terminal::operation::read_mode || op == terminal::operation::wait_readable ||
                     op == terminal::operation::attach || op == terminal::operation::detach) { }
            else if (op == terminal::operation::read_until) { /* already serviced */ }
            else if (op == terminal::operation::write_until) { /* already serviced */ }
            else if (op == terminal::operation::read) {
                response.result = device.read(response.data, request.length);
                if (response.result == 0 && request.length != 0) response.result = process_error_would_block;
                if (response.result > 0) response.length = static_cast<u32>(response.result);
            } else if (op == terminal::operation::write) {
                response.result = device.write(request.data, request.length);
                if (response.result == 0 && request.length != 0) response.result = process_error_would_block;
            } else if (op == terminal::operation::statistics) response.result = 0;
            else if (op == terminal::operation::cancel) response.result = 0;
            else if (op == terminal::operation::stop) { response.result = 0; done = true; }
            else response.result = process_error_invalid;
            const auto stats = device.counters();
            response.software_drops = stats.software_drops; response.hardware_overruns = stats.hardware_overruns;
            response.parity_errors = stats.parity_errors; response.framing_errors = stats.framing_errors;
            response.breaks = stats.breaks;
            unlock();
        }
        const u32 reply_channel = from_app ? apps[0].outgoing : outgoing;
        // An untrusted app must not hold the service forever by refusing to
        // receive a response. App clients use one outstanding request.
        const u64 reply_deadline = from_app ? 0 : thread_deadline_infinite;
        if (sdk::channel_send_wait(reply_channel, &response, sizeof(response), reply_deadline) != 0) {
            if (from_app && close_app()) continue;
            break;
        }
    }
    __atomic_store_n(&stopping, 1u, __ATOMIC_RELEASE);
    (void)sdk::channel_close(incoming);
    const bool app_closed = close_app();
    lock();
    __atomic_store_n(&request_pending, 0u, __ATOMIC_RELEASE);
    (void)device.close();
    unlock();
    (void)thread::wake(&request_pending, 1);
    u64 result = 0, control_result = 0;
    const i64 irq_join = thread::join(worker, result);
    const i64 control_join = thread::join(control_thread, control_result);
    return irq_join == 0 && control_join == 0 && app_closed && done ? 0 : 5;
}
