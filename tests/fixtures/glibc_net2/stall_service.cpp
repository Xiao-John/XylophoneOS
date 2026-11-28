// SPDX-License-Identifier: Apache-2.0
// Test-only authenticated Net2 peer. No network driver or production authority.
#include <xos/net_service_client.hpp>
#include <xos/ipc_v1.hpp>

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::net2;
    const i64 began = sdk::syscall(sys_clock_monotonic);
    if (began < 0 || sdk::ipc_name_publish(service_name)) return 1;
    const u64 limit = static_cast<u64>(began) + 15'000'000'000ull;
    sdk::print("NET2_STALL_READY\n");
    ipc_channel channel{};
    auto pause = [&]() {
        const i64 now = sdk::syscall(sys_clock_monotonic);
        return now >= 0 && static_cast<u64>(now) < limit &&
            !sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000ull);
    };
    for (;;) {
        const i64 accepted = sdk::ipc_name_try_accept(channel);
        if (!accepted) break;
        if (accepted != process_error_would_block || !pause()) return 2;
    }
    u64 send_peer = 0, receive_peer = 0;
    if (sdk::ipc_endpoint_peer(channel.send, send_peer) || sdk::ipc_endpoint_peer(channel.receive, receive_peer) ||
        !send_peer || send_peer != receive_peer) return 3;
    u64 sequence = 0, grant = 0, length = 0, map = 0, delegated = 0;
    readiness_page* page = nullptr;
    u32 capability_count = 0, readiness_count = 0;
    for (;;) {
        message request{};
        const i64 received = sdk::ipc_recv(channel.receive, &request, sizeof(request));
        if (received == -3) { if (!pause()) return 4; continue; }
        if (received != header_bytes || request.version != version || request.sequence != ++sequence ||
            request.length || request.reserved || request.result) return 5;
        message reply{};
        reply.version = version; reply.action = request.action; reply.sequence = request.sequence;
        reply.object = request.object;
        if (request.action == operation::open) {
            if (request.object || request.transport != protocol::tcp || request.address != permitted_address) return 6;
            reply.object = 77; reply.flags = connected;
            if (page) {
                page->sequence = 1; page->revision = readiness_page_revision;
                page->count = 1; page->session_generation = 91;
                page->sampled_ns = static_cast<u64>(sdk::syscall(sys_clock_monotonic));
                page->records[0] = {77, {1, 0, 0, 0, 0, 0}, 0};
                __atomic_store_n(&page->sequence, 2, __ATOMIC_RELEASE);
            }
        } else if (request.action == operation::capabilities) {
            if (request.object || ++capability_count != 1) return 7;
            const capability_snapshot snapshot{request.flags == capabilities_extended ? socket_extension_revision_2 : socket_extension_revision,
                capability_readiness | capability_shutdown_write | (request.flags ? capability_readiness_page : 0), 0};
            reply.length = sizeof(snapshot); __builtin_memcpy(reply.data, &snapshot, sizeof(snapshot));
        } else if (request.action == operation::readiness_bind) {
            if (grant || request.object || ipc_v1::grant_create(0, 4096, 11, grant, length) ||
                ipc_v1::grant_map(grant, 0x100000b00000ull, ipc_v1_grant_access::read_write, map, length) ||
                ipc_v1::grant_delegate(grant, send_peer, 1, delegated) || delegated != grant) return 15;
            page = reinterpret_cast<readiness_page*>(0x100000b00000ull);
            const readiness_binding binding{readiness_page_revision, 4096, grant, 91, 0};
            reply.length = sizeof(binding); __builtin_memcpy(reply.data, &binding, sizeof(binding));
        } else if (request.action == operation::readiness) {
            if (request.object != 77 || ++readiness_count != 1) return 8;
            const i64 now = sdk::syscall(sys_clock_monotonic);
            if (now < 0) return 9;
            sdk::print("NET2_STALL_HOLDING_REPLY\n");
            // The process stays alive and owns the authenticated endpoints.
            // A 40 ms poll must complete before this one-second response.
            if (sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000'000ull)) return 10;
            const readiness_snapshot snapshot{1, ready_write, 0, 64, 0, 0};
            reply.length = sizeof(snapshot); __builtin_memcpy(reply.data, &snapshot, sizeof(snapshot));
        } else if (request.action != operation::close || request.object != 77) return 11;
        for (;;) {
            const i64 sent = sdk::ipc_send(channel.send, &reply, header_bytes + reply.length);
            if (!sent) break;
            if (sent != ipc_error_full || !pause()) return 12;
        }
        for (;;) {
            const i64 consumed = sdk::ipc_wait(channel.send, ipc_wait_mode::try_send);
            if (!consumed) break;
            // The client can consume close and exit before this observation.
            // The harness independently requires its successful close/exit.
            if (request.action == operation::close &&
                (consumed == ipc_error_broken || consumed == process_error_denied)) break;
            if (consumed != process_error_would_block || !pause()) return 13;
        }
        if (request.action == operation::close) {
            if (capability_count != 1 || readiness_count != 1) return 14;
            sdk::print("NET2_STALL_SERVICE_PASS capabilities=1 readiness=1\n");
            return 0;
        }
    }
}
