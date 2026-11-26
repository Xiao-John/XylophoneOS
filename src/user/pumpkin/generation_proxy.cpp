// SPDX-License-Identifier: Apache-2.0
#include "generation_guest.hpp"
#include "../drivers/uart_16550.hpp"

namespace {
using namespace xos;
using namespace xos::user::pumpkin;
using namespace xos::user::pumpkin::anchor_guest;

bool clean_line(const user::uart::driver& uart) {
    const auto loss = uart.counters();
    return loss.software_drops == 0 && loss.hardware_overruns == 0 &&
        loss.framing_errors == 0 && loss.parity_errors == 0 && loss.breaks == 0;
}

bool wait_irq(user::uart::driver& uart, u64 end) {
    const i64 ready = uart.wait(end);
    return ready > 0 && uart.service_irq(static_cast<u64>(ready)) == 0 && clean_line(uart);
}

bool serial_exchange(user::uart::driver& uart, const packet& request, packet& reply) {
    const u64 end = deadline();
    if (end == 0) return false;
    const auto* output = reinterpret_cast<const u8*>(&request);
    auto* input = reinterpret_cast<u8*>(&reply);
    for (u32 sent = 0; sent < sizeof(request);) {
        const i64 count = uart.write(output + sent, sizeof(request) - sent);
        if (count < 0) return false;
        sent += static_cast<u32>(count);
        if (sent < sizeof(request) && (uart.arm_write() != 0 || !wait_irq(uart, end))) return false;
    }
    for (u32 received = 0; received < sizeof(reply);) {
        const i64 count = uart.read(input + received, sizeof(reply) - received);
        if (count < 0) return false;
        received += static_cast<u32>(count);
        if (received < sizeof(reply) && !wait_irq(uart, end)) return false;
    }
    return clean_line(uart) && header(reply, request.op, request.sequence);
}

bool relay(user::uart::driver& uart, u64 controller, const pair& supervisor) {
    packet ready{}, response{};
    ready.op = operation::ready;
    if (!serial_exchange(uart, ready, response) || response.expected != generation_mark{} ||
        response.value != generation_mark{} || response.result < static_cast<u8>(scenario::cycle) ||
        response.result > static_cast<u8>(scenario::stale)) return false;
    if (sdk::channel_send_wait(supervisor.transmit, &response.result, sizeof(response.result), deadline()) != 0) {
        return false;
    }
    bind_proxy owner{};
    if (sdk::channel_receive_wait(supervisor.receive, &owner, sizeof(owner), deadline()) != sizeof(owner)) {
        return false;
    }
    pair service{};
    if (owner.daemon == 0 || !find_pair(controller, owner.daemon, service)) return false;

    u64 sequence = 0;
    const u64 end = deadline(23'000'000'000);
    if (end == 0) return false;
    for (;;) {
        supervisor_result finish{};
        const i64 report = sdk::ipc_recv(supervisor.receive, &finish, sizeof(finish));
        if (report == sizeof(finish) && finish.pass <= 1) {
            packet done{}, ack{};
            done.op = operation::finish;
            done.result = finish.pass;
            done.sequence = sequence + 1;
            return serial_exchange(uart, done, ack) && ack.result == 0 &&
                ack.expected == generation_mark{} && ack.value == generation_mark{} && finish.pass != 0;
        }
        if (report != sdk::ipc_error_empty) return false;

        packet request{}, reply{};
        const i64 received = sdk::ipc_recv(service.receive, &request, sizeof(request));
        if (received == sizeof(request)) {
            if ((request.op != operation::read && request.op != operation::publish) ||
                !header(request, request.op, ++sequence) || request.result != 0 ||
                !serial_exchange(uart, request, reply) ||
                sdk::channel_send_wait(service.transmit, &reply, sizeof(reply), deadline()) != 0) {
                return false;
            }
        } else if (received > 0) {
            return false;
        }
        const i64 now = sdk::syscall(sys_clock_monotonic);
        if (now < 0 || static_cast<u64>(now) >= end ||
            sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000) != 0) {
            return false;
        }
    }
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    const i64 controller = sdk::pio_grant(pio_grant_action::controller, 0, pio_resource_com1);
    pair supervisor{};
    user::uart::driver uart;
    if (controller <= 0 || !find_pair(controller, controller, supervisor) || uart.start() != 0) return 1;
    const bool completed = relay(uart, static_cast<u64>(controller), supervisor);
    const auto closed = uart.close();
    return completed && closed == 0 ? 0 : 2;
}
