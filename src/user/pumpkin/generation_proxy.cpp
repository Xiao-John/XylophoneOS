// SPDX-License-Identifier: Apache-2.0
#include "generation_guest.hpp"
#include "session_limits.hpp"
#if XOS_PUMPKIN_NATIVE_LOGIN
#include "native_login.hpp"
#endif
#if XOS_PUMPKIN_USER_LOGIN
#include "anchored_installation.hpp"
#include "user_login.hpp"
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
#include "named_operator.hpp"
#endif
#endif
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

template<class Frame>
bool serial_exchange(user::uart::driver& uart, const Frame& request, Frame& reply) {
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
        response.value != generation_mark{}) return false;
    const auto mode = static_cast<scenario>(response.result);
#if XOS_PUMPKIN_MOBIUS
    const bool desktop = desktop_scenario(mode);
    u64 desktop_admin_sequence = 0;
    bool desktop_revocation_requested = false;
#else
    constexpr bool desktop = false;
#endif
#if XOS_PUMPKIN_USER_LOGIN
#if XOS_PUMPKIN_USER_RESOURCE
    constexpr auto last_mode = scenario::user_resource;
#else
    constexpr auto last_mode = scenario::user_revoke;
#endif
    bool named_read = false, named_mutation = false;
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
    if (mode == scenario::user_resource) return false;
    const auto named_mode = named_operator::for_scenario(mode);
    named_read = named_mode == named_operator::operation::select;
    named_mutation = named_mode == named_operator::operation::put || named_mode == named_operator::operation::erase ||
        named_mode == named_operator::operation::import_fat;
    named_operator::packet selected{};
    u8 named_result = 0;
#endif
    if ((mode < scenario::user_enroll || mode > last_mode) && !named_read && !named_mutation && !desktop) return false;
    const bool submitting = mode == scenario::user_login || mode == scenario::user_resource || named_read || desktop;
    const bool credentials_needed = submitting || mode == scenario::user_enroll;
    wire_id credential_owner{};
    bool credential_exchanged = false, credential_slots_cleared = false;
    bool destination_reserved = false;
#else
#if XOS_PUMPKIN_PROVISIONING_STORE
    if ((mode < scenario::cycle || mode > scenario::stale) &&
        (mode < scenario::provisioning_update || mode > scenario::provisioning_new)) return false;
#elif XOS_PUMPKIN_NAMED_RESOURCE_STORE
    if ((mode < scenario::cycle || mode > scenario::stale) && mode != scenario::named_empty) return false;
#else
    if (mode < scenario::cycle || mode > scenario::stale) return false;
#endif
#endif
    if (sdk::channel_send_wait(supervisor.transmit, &response.result, sizeof(response.result), deadline()) != 0) {
        return false;
    }
#if XOS_PUMPKIN_USER_LOGIN
    user_login::account_packet account_prompt{}, selected_account{};
    account_prompt.op = mode;
    if (!serial_exchange(uart, account_prompt, selected_account) ||
        !user_login::selected_account(selected_account, mode) ||
        sdk::channel_send_wait(supervisor.transmit, &selected_account, sizeof(selected_account), deadline()) != 0) {
        return false;
    }
#endif
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
    if (named_read || named_mutation) {
        named_operator::packet prompt{};
        prompt.op = named_mode;
        if (!serial_exchange(uart, prompt, selected) || !named_operator::selection(selected, named_mode) ||
            sdk::channel_send_wait(supervisor.transmit, &selected, sizeof(selected), deadline()) != 0) { return false; }
    }
#endif
    bind_proxy owner{};
    if (sdk::channel_receive_wait(supervisor.receive, &owner, sizeof(owner), deadline()) != sizeof(owner)) {
        return false;
    }
    pair service{};
    if (owner.daemon == 0 || !find_pair(controller, owner.daemon, service)) return false;

    u64 sequence = 0;
    const u64 end = deadline(23'000'000'000 + (desktop ? connection_lifetime_ns : 0));
    if (end == 0) return false;
    for (;;) {
        supervisor_result finish{};
#if XOS_PUMPKIN_USER_LOGIN
        user_login::packet credentials{};
        const i64 report = sdk::ipc_recv(supervisor.receive, &credentials, sizeof(credentials));
        if (report == sizeof(credentials)) {
            if (credentials.tag == user_login::account_magic) {
                user_login::account_packet reservation{}, ack{};
                __builtin_memcpy(static_cast<void*>(&reservation), &credentials, sizeof(reservation));
                if (mode != scenario::user_enroll || destination_reserved || credential_exchanged ||
                    !user_login::enrollment_ready(reservation) || !serial_exchange(uart, reservation, ack) ||
                    !user_login::enrollment_ready(ack) ||
                    sdk::channel_send_wait(supervisor.transmit, &ack, sizeof(ack), deadline()) != 0) { return false; }
                destination_reserved = true;
                continue;
            }
#if XOS_PUMPKIN_MOBIUS
            if (credentials.tag == user_login::desktop_admin_magic) {
                user_login::desktop_admin_poll request{}, reply{};
                __builtin_memcpy(&request, static_cast<const void*>(&credentials), sizeof(request));
                if (mode != scenario::user_desktop_admin || !credential_slots_cleared || desktop_revocation_requested ||
                    !user_login::header(request, mode, ++desktop_admin_sequence) || request.revoke ||
                    !serial_exchange(uart, request, reply) ||
                    sdk::channel_send_wait(supervisor.transmit, &reply, sizeof(reply), deadline()) != 0) return false;
                desktop_revocation_requested = reply.revoke == 1;
                continue;
            }
#endif
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
            if (credentials.tag == named_operator::magic) {
                named_operator::packet returned{}, ack{};
                __builtin_memcpy(static_cast<void*>(&returned), &credentials, sizeof(returned));
                if ((!named_read && !named_mutation) || named_result || (named_read && !credential_slots_cleared) ||
                    !named_operator::outcome(returned, selected) || !serial_exchange(uart, returned, ack) || ack.result ||
                    !named_operator::empty(ack)) { return false; }
                named_result = returned.result;
                continue;
            }
#endif
            const auto operation = mode == scenario::user_enroll ? user_login::operation::issue : user_login::operation::submit;
            if (!credentials_needed || credentials.identity.number == 0 ||
                credentials.identity.scope != anchored_installation_realm ||
                (mode == scenario::user_enroll && !destination_reserved)) return false;
            if (credential_exchanged) {
                if (credential_slots_cleared || !user_login::header(credentials, operation, 2) ||
                    !user_login::same_identity(credentials.identity, credential_owner) ||
                    has_bytes(credentials.key.bytes, secret_bytes) ||
                    sdk::channel_send_wait(supervisor.transmit, &credentials, sizeof(credentials), deadline()) != 0) return false;
                credential_slots_cleared = true;
                continue;
            }
            if (!user_login::header(credentials, operation, 1) ||
                has_bytes(credentials.key.bytes, secret_bytes) != (mode == scenario::user_enroll)) return false;
            user_login::packet reply{};
            if (!serial_exchange(uart, credentials, reply) || !user_login::same_identity(reply.identity, credentials.identity) ||
                has_bytes(reply.key.bytes, secret_bytes) != submitting ||
                sdk::channel_send_wait(supervisor.transmit, &reply, sizeof(reply), deadline()) != 0) return false;
            credential_owner = credentials.identity;
            credential_exchanged = true;
            continue;
        } else if (report == sizeof(finish)) {
            finish.pass = static_cast<u8>(credentials.tag);
        } else if (report != sdk::ipc_error_empty) {
            return false;
        }
#else
        const i64 report = sdk::ipc_recv(supervisor.receive, &finish, sizeof(finish));
#endif
        bool valid = finish.pass <= 1;
        bool completed = finish.pass == 1;
#if XOS_PUMPKIN_USER_LOGIN
#if XOS_PUMPKIN_MOBIUS
        if (finish.pass == user_login::desktop_revoked && desktop_revocation_requested) {
            valid = true;
            completed = true;
        }
#endif
        if (finish.pass == user_login::denied && submitting && credential_exchanged) {
            valid = true;
            completed = true;
        }
#if XOS_PUMPKIN_USER_RESOURCE && XOS_PUMPKIN_NAMED_RESOURCE_STORE
        if ((named_read || named_mutation) && finish.pass && named_result == finish.pass) {
            valid = true;
            completed = true;
        }
        if ((named_read || named_mutation) && completed && finish.pass != named_result) return false;
#endif
        if (completed && credentials_needed && !credential_slots_cleared) return false;
        if (finish.pass == user_login::duplicate_enrollment && mode == scenario::user_enroll &&
            !credential_exchanged && !destination_reserved) {
            valid = true;
            completed = true;
        }
#endif
#if XOS_PUMPKIN_NATIVE_LOGIN
        using result = xos::user::pumpkin::native_login::result;
        const auto last_error = desktop ? result::desktop_failed :
            (mode == scenario::user_resource || mode == scenario::user_named_read
                ? result::broker_cleanup : result::holder_exit);
        valid = valid || (finish.pass >= static_cast<u8>(result::holder_start) &&
                          finish.pass <= static_cast<u8>(last_error));
#endif
        if (report == sizeof(finish) && valid) {
            packet done{}, ack{};
            done.op = operation::finish;
            done.result = finish.pass;
            done.sequence = sequence + 1;
            return serial_exchange(uart, done, ack) && ack.result == 0 &&
                ack.expected == generation_mark{} && ack.value == generation_mark{} && completed;
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
