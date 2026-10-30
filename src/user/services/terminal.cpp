// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <xos/terminal_abi.hpp>
#include "../drivers/uart_16550.hpp"

namespace {
using namespace xos;
user::uart::driver device;
u32 lock_word, stopping;
i64 worker_error;
u64 device_irq_token;
u32 control_incoming, control_outgoing;

void fail_worker(i64 error) {
    __atomic_store_n(&worker_error, error == 0 ? process_error_state : error, __ATOMIC_RELEASE);
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
        unlock();
        if (result != 0) { fail_worker(result); return 0; }
    }
    return 0;
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
    u32 incoming = 0, outgoing = 0;
    if (!find_control_channels(static_cast<u64>(controller), incoming, outgoing)) return 2;
    control_incoming = incoming; control_outgoing = outgoing;
    if (device.start() != 0) return 3;
    device_irq_token = device.token();
    u64 worker = 0;
    if (thread::create(worker, receive_worker, nullptr) != 0) { (void)device.close(); return 4; }
    bool done = false;
    while (!done) {
        if (sdk::channel_wait(incoming, thread_deadline_infinite) != 0) break;
        terminal::request request{};
        if (sdk::ipc_recv(incoming, &request, sizeof(request)) != static_cast<i64>(sizeof(request))) break;
        terminal::response response{};
        response.version = terminal::version; response.size = sizeof(response); response.sequence = request.sequence;
        if (request.version != terminal::version || request.size != sizeof(request) ||
            request.length > terminal::data_bytes || request.sequence == 0) {
            response.result = process_error_invalid;
        } else {
            lock();
            const i64 error = __atomic_load_n(&worker_error, __ATOMIC_ACQUIRE);
            const auto op = static_cast<terminal::operation>(request.operation);
            if (error != 0) response.result = error;
            else if (op == terminal::operation::read) {
                response.result = device.read(response.data, request.length);
                if (response.result == 0 && request.length != 0) response.result = process_error_would_block;
                if (response.result > 0) response.length = static_cast<u32>(response.result);
            } else if (op == terminal::operation::write) {
                response.result = device.write(request.data, request.length);
                if (response.result == 0 && request.length != 0) response.result = process_error_would_block;
            } else if (op == terminal::operation::statistics) response.result = 0;
            else if (op == terminal::operation::stop) { response.result = 0; done = true; }
            else response.result = process_error_invalid;
            const auto stats = device.counters();
            response.software_drops = stats.software_drops; response.hardware_overruns = stats.hardware_overruns;
            response.parity_errors = stats.parity_errors; response.framing_errors = stats.framing_errors;
            response.breaks = stats.breaks;
            unlock();
        }
        if (sdk::channel_wait(outgoing, thread_deadline_infinite) != 0 ||
            sdk::ipc_send(outgoing, &response, sizeof(response)) != 0) break;
    }
    __atomic_store_n(&stopping, 1u, __ATOMIC_RELEASE);
    lock(); (void)device.close(); unlock();
    u64 result = 0;
    return thread::join(worker, result) == 0 && done ? 0 : 5;
}
